"""Multi-layer, multi-mode trajectory collection for Qwen3-1.7B on AIME.

This is the production collector. For each problem we run the model
TWICE — once with thinking enabled and once with thinking disabled —
and save the full per-token hidden states for ALL 28 layers, plus the
logits, into the standardised Trajectory format.

Key design choices:

  * Generation is **non-streaming** (we need all layers' hidden states
    at once; streaming would require re-running the forward pass).
  * We use ``output_hidden_states=True`` so HF gives us
    ``hidden_states`` as a tuple of length (n_layers + 1). Layer i is
    the residual stream *after* layer i-1 (so index 0 = embeddings,
    index n_layers = final).
  * Hidden states are saved as float16 (T, L, D) which is what the
    visualisation needs but halves the storage vs float32.
  * Logits are saved as float16 too.
  * We track whether each emitted token is inside a <think>...</think>
    block, and what its perplexity / entropy look like at every layer.
  * Greedy decoding (temperature=0) for reproducibility.

Outputs go to ``output/trajectories/<dataset>/<split>/<id>__<mode>.{json,npz}``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core.standard import (
    RunConfig, TokenRecord, TrajectoryMeta, save_trajectory
)
from core.aime_loader import load_aime, load_aime_from_jsonl, parse_aime_answer, check_correct


# ---------------------------------------------------------------------------
# AIME-specific system prompt
# ---------------------------------------------------------------------------

AIME_SYSTEM = (
    "You are an expert mathematician competing in the AIME "
    "(American Invitational Mathematics Examination). Solve the "
    "given problem step by step. Show all reasoning clearly. "
    "Your final answer must be a non-negative integer between 0 "
    "and 999. Present it inside \\boxed{} on its own line at the "
    "very end of your response."
)


# ---------------------------------------------------------------------------
# Qwen3 chat template: toggle thinking on/off
# ---------------------------------------------------------------------------


def build_prompt(tokenizer, problem_text: str, mode: str) -> Tuple[str, Dict]:
    """Apply chat template; return (full_prompt_text, kwargs).

    mode is "think" or "no_think".
    """
    messages = [
        {"role": "system", "content": AIME_SYSTEM},
        {"role": "user", "content": problem_text},
    ]
    kwargs = {"tokenize": False, "add_generation_prompt": True,
              "enable_thinking": (mode == "think")}
    text = tokenizer.apply_chat_template(messages, **kwargs)
    return text, kwargs


# ---------------------------------------------------------------------------
# Think-block tracking
# ---------------------------------------------------------------------------

_THINK_OPEN_RE = re.compile(r"<think>")
_THINK_CLOSE_RE = re.compile(r"</think>")


def scan_think_state(text: str) -> Tuple[bool, bool]:
    """Return (currently_inside_think, has_closed_think) given the
    cumulative generated text."""
    open_count = len(_THINK_OPEN_RE.findall(text))
    close_count = len(_THINK_CLOSE_RE.findall(text))
    inside = open_count > close_count
    closed = close_count > 0
    return inside, closed


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class HiddenStateCollector:
    """Saves per-token hidden states for every layer.

    We run generation in non-streaming mode with ``output_hidden_states=True``.
    HF returns a tuple ``(n_layers+1,)`` of ``(B, T, D)`` tensors. Layer
    index i is the residual stream AFTER layer i (with 0 being the
    embedding output). We discard the embedding layer (index 0) and keep
    the post-layer residual for each of the 28 layers.
    """

    def __init__(self):
        self.layers: List[np.ndarray] = []   # one (D,) per generated token
        self.logits: List[np.ndarray] = []   # one (V,) per generated token
        self.token_ids: List[int] = []
        self.token_strs: List[str] = []
        self.attn_mask: List[int] = []

    def add_token(self, layer_vec: np.ndarray, logit_vec: np.ndarray,
                  token_id: int, token_str: str):
        self.layers.append(layer_vec)
        self.logits.append(logit_vec)
        self.token_ids.append(token_id)
        self.token_strs.append(token_str)
        self.attn_mask.append(1)


# ---------------------------------------------------------------------------
# One-shot generation with all-layer hidden states
# ---------------------------------------------------------------------------


def generate_full(
    model, tokenizer, prompt: str,
    max_new_tokens: int, max_context: int,
    device: torch.device, dtype: torch.dtype,
) -> Tuple[List[int], np.ndarray, np.ndarray, List[str]]:
    """Greedy-generate and return (token_ids, hidden_states, logits, token_strs).

    hidden_states: (T, L, D) float32 — post-layer residual for each layer
    logits:        (T, V) float32
    """
    enc = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
    input_ids = enc.input_ids.to(device)
    if input_ids.shape[1] >= max_context - max_new_tokens:
        # Trim the front of the prompt so generation fits.
        keep = max_context - max_new_tokens - 1
        input_ids = input_ids[:, -keep:]
    attention_mask = torch.ones_like(input_ids, dtype=torch.long)

    collected_hs: List[np.ndarray] = []
    collected_logits: List[np.ndarray] = []
    gen_ids: List[int] = []

    cur_ids = input_ids
    cur_mask = attention_mask
    past_kv = None

    eos_id = tokenizer.eos_token_id
    pad_id = tokenizer.pad_token_id or eos_id

    with torch.no_grad():
        for step in range(max_new_tokens):
            if past_kv is None:
                out = model(
                    input_ids=cur_ids,
                    attention_mask=cur_mask,
                    use_cache=True,
                    output_hidden_states=True,
                    return_dict=True,
                )
            else:
                # Feed only the new token, KV cache handles the rest
                out = model(
                    input_ids=cur_ids[:, -1:],
                    attention_mask=cur_mask,
                    past_key_values=past_kv,
                    use_cache=True,
                    output_hidden_states=True,
                    return_dict=True,
                )

            past_kv = out.past_key_values
            logits = out.logits[:, -1, :].float()  # (1, V)
            hs = out.hidden_states                # tuple of (1, T, D), length = L+1

            # Greedy decode
            next_id = int(torch.argmax(logits[0], dim=-1))
            gen_ids.append(next_id)

            # Save hidden state of the LAST token at every layer (skip embedding)
            # hs[0] = embedding output, hs[i] = residual after layer i-1
            # For Qwen3 with 28 layers, that's hs[1]..hs[28] — 28 tensors.
            layer_vecs = []
            for li in range(1, len(hs)):
                v = hs[li][0, -1, :]    # (D,)
                # bfloat16 is not directly supported by np.array() in some
                # numpy builds, so cast to float32 first.
                v32 = v.detach().to(torch.float32).cpu().numpy()
                layer_vecs.append(v32)
            collected_hs.append(np.stack(layer_vecs, axis=0))   # (L, D)
            collected_logits.append(logits[0].detach().cpu().numpy().astype(np.float32))

            # Stop on EOS
            if next_id == eos_id:
                break

            # Append for next iteration
            cur_ids = torch.cat([cur_ids,
                                 torch.tensor([[next_id]], device=device, dtype=cur_ids.dtype)], dim=1)
            cur_mask = torch.cat([cur_mask,
                                  torch.ones((1, 1), device=device, dtype=cur_mask.dtype)], dim=1)

            # Cap attention window — Qwen3 with sliding-window off would
            # grow attention_mask up to max_context.
            if cur_ids.shape[1] >= max_context:
                break

    if not collected_hs:
        return [], np.zeros((0, 0, 0), dtype=np.float32), np.zeros((0, 0), dtype=np.float32), []

    T = len(collected_hs)
    L = collected_hs[0].shape[0]
    D = collected_hs[0].shape[1]
    V = collected_logits[0].shape[0]
    hidden = np.stack(collected_hs, axis=0)             # (T, L, D)
    logit_arr = np.stack(collected_logits, axis=0)      # (T, V)
    token_strs = [tokenizer.decode([t]) for t in gen_ids]
    return gen_ids, hidden, logit_arr, token_strs


# ---------------------------------------------------------------------------
# Build per-token metadata
# ---------------------------------------------------------------------------


def compute_metrics(logits_row: np.ndarray) -> Tuple[float, float, float]:
    """Return (top1_prob, entropy, perplexity) from a (V,) logits row.

    Uses log-softmax throughout for numerical stability (avoids overflow
    when logits contain large positive values).
    """
    m = float(logits_row.max())
    log_z = m + float(np.log(np.exp(logits_row - m).sum()))
    log_probs = logits_row - log_z
    top1 = float(np.exp(log_probs.max()))
    # entropy = -E[log p] = -sum p * log p
    # In log space: -sum exp(log_p) * log_p. For numerical stability use
    # the standard log-sum-exp trick: split by log_p threshold.
    log_p = log_probs
    # Mask out -inf (shouldn't exist after softmax) and very small probs
    finite = np.isfinite(log_p)
    lp = log_p[finite]
    if lp.size == 0:
        return top1, 0.0, 1.0 / max(top1, 1e-6)
    # Use scipy-style stable computation: -sum(p * log_p). When log_p is
    # very negative (small p), p * log_p ~ 0, so we can mask by threshold.
    threshold = -20.0  # log(p) < -20 ⇒ contribution < p * |log p| < 1e-9
    mask = lp > threshold
    entropy = float(-np.sum(np.exp(lp[mask]) * lp[mask]))
    ppl = 1.0 / max(top1, 1e-6)
    return top1, entropy, ppl


# ---------------------------------------------------------------------------
# Main per-problem pipeline
# ---------------------------------------------------------------------------


def run_one(model, tokenizer, problem: Dict, mode: str, args,
            device: torch.device, dtype: torch.dtype) -> Tuple[TrajectoryMeta, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Run Qwen3 on one AIME problem in the requested mode."""
    text, ct_kwargs = build_prompt(tokenizer, problem["problem"], mode)

    enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
    n_prompt_tokens = int(enc.input_ids.shape[1])

    t0 = time.time()
    gen_ids, hidden, logits, token_strs = generate_full(
        model, tokenizer, text,
        max_new_tokens=args.max_new_tokens,
        max_context=args.max_context,
        device=device, dtype=dtype,
    )
    dt = time.time() - t0

    generated_text = tokenizer.decode(gen_ids, skip_special_tokens=False)
    generated_answer = parse_aime_answer(generated_text) or ""
    is_correct = check_correct(generated_text, problem["answer"])

    n_layers = hidden.shape[1] if hidden.size else 0
    d_model = hidden.shape[2] if hidden.size else 0

    # Per-token records + think-block state
    cum_text = ""
    records: List[TokenRecord] = []
    in_think = False
    closed_think = False
    for i, (tid, tstr) in enumerate(zip(gen_ids, token_strs)):
        top1, entropy, ppl = compute_metrics(logits[i])
        cum_text += tstr
        in_think, closed_think = scan_think_state(cum_text)
        records.append(TokenRecord(
            step_id=i,
            token_id=tid,
            token=tstr,
            ts=t0 + dt * (i / max(len(gen_ids), 1)),
            perplexity=ppl,
            entropy=entropy,
            top1_prob=top1,
            is_self_check=False,  # heuristic in core.model_runner
            is_in_think_block=in_think and not closed_think,
            is_after_think=closed_think and not in_think,
        ))

    attention_mask = np.ones(len(gen_ids), dtype=np.int8)

    cfg = RunConfig(
        model=args.model_name,
        model_path=args.model_path,
        mode=mode,
        max_new_tokens=args.max_new_tokens,
        max_context=args.max_context,
        temperature=0.0,
        top_p=1.0,
        top_k=0,
        seed=args.seed,
        chat_template_kwargs={"enable_thinking": (mode == "think")},
    )

    meta = TrajectoryMeta(
        schema_version="1.0",
        trajectory_id=f"aime__{problem['split']}__{problem['id']}__{mode}",
        dataset="aime",
        split=problem["split"],
        problem_id=problem["id"],
        prompt=problem["problem"],
        system_prompt=AIME_SYSTEM,
        chat_template_input=text,
        ground_truth=problem["answer"],
        generated_text=generated_text,
        generated_answer=generated_answer,
        is_correct=is_correct,
        n_tokens=n_prompt_tokens + len(gen_ids),
        n_generated_tokens=len(gen_ids),
        n_layers=n_layers,
        d_model=d_model,
        config=cfg,
        tokens=records,
        extra={"wallclock_s": dt, "prompt_tokens": n_prompt_tokens},
    )

    token_ids_arr = np.asarray(gen_ids, dtype=np.int32)
    return meta, hidden, logits, token_ids_arr, attention_mask


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(args):
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"[collect] loading {args.model_path}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    device = torch.device(args.device)
    dtype = {"bfloat16": torch.bfloat16,
             "float16": torch.float16,
             "float32": torch.float32}[args.dtype]
    print(f"[collect] loading model onto {args.device}")
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path, dtype=dtype,
    )
    model = model.to(args.device)
    model.eval()
    print(f"[collect] model loaded: d_model={model.config.hidden_size}, "
          f"n_layers={model.config.num_hidden_layers}, device={args.device}")

    # Pick problems
    if args.jsonl:
        problems = load_aime_from_jsonl(args.jsonl)
        print(f"[collect] loaded {len(problems)} problems from {args.jsonl}")
    elif args.split:
        problems = load_aime(args.split)
        print(f"[collect] loaded {len(problems)} problems for split {args.split}")
    else:
        problems = load_aime()
        print(f"[collect] loaded {len(problems)} builtin problems (all splits)")

    if args.limit:
        problems = problems[:args.limit]

    out_root = Path(args.out_dir) / args.dataset
    out_root.mkdir(parents=True, exist_ok=True)

    for i, problem in enumerate(problems):
        for mode in ("think", "no_think"):
            tid = f"aime__{problem['split']}__{problem['id']}__{mode}"
            json_path = out_root / f"{tid}.json"
            npz_path = out_root / f"{tid}.npz"
            if json_path.exists() and npz_path.exists() and not args.overwrite:
                print(f"[{i+1}/{len(problems)}] {mode:8s} {problem['id']:10s} — SKIP (exists)")
                continue
            print(f"[{i+1}/{len(problems)}] {mode:8s} {problem['id']:10s} …", end=" ", flush=True)
            try:
                meta, hidden, logits, token_ids, attn = run_one(
                    model, tokenizer, problem, mode, args, device, dtype
                )
                save_trajectory(out_root, meta, hidden, logits, token_ids, attn,
                                save_full_logits=args.save_full_logits,
                                dtype=args.store_dtype)
                ans = meta.generated_answer or "(none)"
                corr = "✓" if meta.is_correct else "✗"
                print(f"{corr} {meta.n_generated_tokens:4d} tok  ans={ans[:30]:30s}  -> {npz_path.name}")
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                print(f"OOM on {problem['id']} / {mode}, skipping")
            except Exception as e:
                print(f"ERROR: {e}")
                continue

    print(f"\n[collect] done. Output under {out_root}")


def cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-name", default="Qwen/Qwen3-1.7B")
    ap.add_argument("--model-path",
                    default="/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master")
    ap.add_argument("--device", default="cuda:2",
                    help="PyTorch device index. NOTE: PyTorch's cuda:N is NOT "
                         "the same as nvidia-smi index N on multi-GPU boxes; "
                         "run `python -c 'import torch; [print(i, torch.cuda.get_device_name(i)) for i in range(torch.cuda.device_count())]'` "
                         "to see the mapping on this host.")
    ap.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16", "float32"])
    ap.add_argument("--max-new-tokens", type=int, default=4096,
                    help="Maximum tokens to generate per problem")
    ap.add_argument("--max-context", type=int, default=16384,
                    help="Context length cap (16k or 32k)")
    ap.add_argument("--dataset", default="aime")
    ap.add_argument("--split", default=None,
                    help="AIME split year: 1983, 2024, 2025, etc. (None = all)")
    ap.add_argument("--jsonl", default=None,
                    help="Override built-in problems with a JSONL file")
    ap.add_argument("--out-dir", default=str(HERE / "output" / "trajectories"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--save-full-logits", action="store_true",
                    help="Store full V-sized logits (default: top-K only)")
    ap.add_argument("--store-dtype", default="float32", choices=["float16", "float32"],
                    help="Precision for hidden_states / logits on disk "
                         "(default float32 for analysis-friendly precision)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    main(args)


if __name__ == "__main__":
    cli()
