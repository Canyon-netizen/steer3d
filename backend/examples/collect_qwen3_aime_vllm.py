"""vLLM-accelerated multi-layer trajectory collector for Qwen3-1.7B on AIME.

Speed strategy
--------------
vLLM does the generation (30-50x faster than HF sequential). We then run
**one** HuggingFace forward pass over the full prompt+generated-token
sequence with ``output_hidden_states=True`` to extract the per-token
hidden state at every one of the 28 layers.

Why one HF forward (instead of replaying vLLM's KV cache)?
  * We need the hidden state AT each layer for each token, not just the
    final logits. vLLM's public API does not expose this.
  * The forward is single-pass (one transformer block per layer), so it's
    bounded by `prompt_len + generated_len * d_model`.
  * For our 32k max-context traces this is ~1-2 s per problem.

Output
------
Standardised trajectory format (same as ``collect_qwen3_aime.py``):
``aime__<split>__<id>__<mode>.json`` + ``.npz`` with float32 hidden
states and logits.
"""

from __future__ import annotations

import argparse
import gc
import os
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, List, Tuple

# IMPORTANT: This script may ONLY run on nvidia-smi index 7 (the free
# RTX PRO 6000 102GB card). We pin the visible device at import time,
# BEFORE torch initializes, so both this process (HF model loader) and
# vLLM's EngineCore subprocess see exactly one device: the chosen GPU.
# On this host:
#   PCI_BUS_ID order maps cuda:N -> nvidia-smi index N directly, so
#   CUDA_VISIBLE_DEVICES=7 means "only the card at PCI bus 0xD6".
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "7"

import numpy as np
import torch  # env vars above already pinned the visible device(s)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core.standard import (
    RunConfig, TokenRecord, TrajectoryMeta, save_trajectory,
)
from core.aime_loader import (
    load_aime, load_aime_from_jsonl, parse_aime_answer, check_correct,
)


AIME_SYSTEM = (
    "You are an expert mathematician competing in the AIME "
    "(American Invitational Mathematics Examination). Solve the "
    "given problem step by step. Show all reasoning clearly. "
    "Your final answer must be a non-negative integer between 0 "
    "and 999. Present it inside \\boxed{} on its own line at the "
    "very end of your response."
)


def pick_free_gpu(min_free_gb: float = 80.0) -> int:
    """Return the PyTorch cuda:N index of the largest free GPU.

    Requires CUDA_DEVICE_ORDER=PCI_BUS_ID (set in main()) so the
    returned index is stable across processes and matches nvidia-smi.
    """
    import torch as _t
    best_i, best_free = -1, -1.0
    for i in range(_t.cuda.device_count()):
        free, total = _t.cuda.mem_get_info(i)
        if free > best_free:
            best_free = free
            best_i = i
    return best_i


_THINK_OPEN_RE = re.compile(r"<think>")
_THINK_CLOSE_RE = re.compile(r"</think>")


def scan_think_state(text: str) -> Tuple[bool, bool]:
    open_count = len(_THINK_OPEN_RE.findall(text))
    close_count = len(_THINK_CLOSE_RE.findall(text))
    inside = open_count > close_count
    closed = close_count > 0
    return inside, closed


def compute_metrics(logits_row: np.ndarray) -> Tuple[float, float, float]:
    m = float(logits_row.max())
    log_z = m + float(np.log(np.exp(logits_row - m).sum()))
    log_probs = logits_row - log_z
    top1 = float(np.exp(log_probs.max()))
    log_p = log_probs
    threshold = -20.0
    mask = log_p > threshold
    entropy = float(-np.sum(np.exp(log_p[mask]) * log_p[mask]))
    ppl = 1.0 / max(top1, 1e-6)
    return top1, entropy, ppl


def vllm_generate(llm, tokenizer, problem_text: str, mode: str,
                  max_new_tokens: int, temperature: float = 0.0,
                  ) -> Tuple[List[int], str]:
    """Generate greedy with vLLM; return (token_ids, prompt_text)."""
    from vllm import SamplingParams

    messages = [
        {"role": "system", "content": AIME_SYSTEM},
        {"role": "user", "content": problem_text},
    ]
    kwargs = {"tokenize": False, "add_generation_prompt": True,
              "enable_thinking": (mode == "think")}
    prompt_text = tokenizer.apply_chat_template(messages, **kwargs)

    sp = SamplingParams(
        temperature=temperature,
        top_p=1.0,
        max_tokens=max_new_tokens,
        stop_token_ids=[tokenizer.eos_token_id],
    )
    outputs = llm.generate([prompt_text], sp, use_tqdm=False)
    return list(outputs[0].outputs[0].token_ids), prompt_text


def hf_extract(model, tokenizer, prompt_text: str, gen_ids: List[int],
               device: "torch.device",
               ) -> Tuple[np.ndarray, np.ndarray]:
    """One forward pass; return (hidden_states, logits) for generated tokens.

    hidden_states: (T, L, D) float32 — at every generated token, the
        residual AFTER each of the L layers (skip embedding).
    logits:        (T, V) float32 — next-token logits for each step.
    """
    enc = tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False)
    prompt_ids = enc.input_ids[0].tolist()
    full_ids = prompt_ids + list(gen_ids)

    input_ids = torch.tensor([full_ids], dtype=torch.long, device=device)
    attention_mask = torch.ones_like(input_ids)

    with torch.no_grad():
        out = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
            return_dict=True,
            use_cache=False,
        )

    hs_tuple = out.hidden_states   # tuple length L+1, each (1, T_full, D)
    logits_full = out.logits[0]    # (T_full, V)

    n_prompt = len(prompt_ids)
    L = len(hs_tuple) - 1   # drop embedding
    D = hs_tuple[1].shape[-1]

    hidden_full = np.zeros((input_ids.shape[1], L, D), dtype=np.float32)
    for li in range(1, len(hs_tuple)):
        hidden_full[:, li - 1, :] = (
            hs_tuple[li][0].to(torch.float32).cpu().numpy()
        )

    # For each generated token gen_ids[k], the hidden state that PRODUCED
    # it is at position (n_prompt + k - 1). The logits at that position
    # predicted gen_ids[k].
    gen_positions = [n_prompt - 1 + k for k in range(len(gen_ids))]

    hidden_gen = hidden_full[gen_positions]                  # (T, L, D)
    logits_gen = (
        logits_full[gen_positions].to(torch.float32).cpu().numpy()  # (T, V)
    )

    del out, hs_tuple, logits_full, input_ids, attention_mask
    return hidden_gen, logits_gen


def run_one(llm, hf_model, tokenizer, problem: dict, mode: str, args,
            device: "torch.device",
            ) -> Tuple[TrajectoryMeta, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Run one AIME problem end-to-end (vLLM gen + HF forward)."""
    t0 = time.time()

    gen_ids, prompt_text = vllm_generate(
        llm, tokenizer, problem["problem"], mode,
        max_new_tokens=args.max_new_tokens,
        temperature=0.0,
    )
    t_gen = time.time() - t0

    generated_text = tokenizer.decode(gen_ids, skip_special_tokens=False)
    generated_answer = parse_aime_answer(generated_text) or ""
    is_correct = check_correct(generated_text, problem["answer"])

    n_prompt = len(tokenizer(prompt_text, add_special_tokens=False).input_ids)
    t1 = time.time()
    hidden, logits = hf_extract(hf_model, tokenizer, prompt_text, gen_ids, device)
    t_hf = time.time() - t1
    dt = time.time() - t0

    print(f"      vllm={t_gen:.1f}s hf={t_hf:.1f}s total={dt:.1f}s "
          f"prompt_tok={n_prompt} gen_tok={len(gen_ids)} "
          f"hidden.shape={hidden.shape}", flush=True)

    n_layers = hidden.shape[1] if hidden.size else 0
    d_model = hidden.shape[2] if hidden.size else 0

    cum_text = ""
    records: List[TokenRecord] = []
    in_think = False
    closed_think = False
    token_strs = [tokenizer.decode([t]) for t in gen_ids]
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
            is_self_check=False,
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
        chat_template_input=prompt_text,
        ground_truth=problem["answer"],
        generated_text=generated_text,
        generated_answer=generated_answer,
        is_correct=is_correct,
        n_tokens=n_prompt + len(gen_ids),
        n_generated_tokens=len(gen_ids),
        n_layers=n_layers,
        d_model=d_model,
        config=cfg,
        tokens=records,
        extra={"wallclock_s": dt, "prompt_tokens": n_prompt,
               "vllm_gen_s": t_gen, "hf_forward_s": t_hf,
               "engine": "vllm+hybrid-hf-forward"},
    )

    token_ids_arr = np.asarray(gen_ids, dtype=np.int32)
    return meta, hidden, logits, token_ids_arr, attention_mask


def main(args):
    from vllm import LLM
    from transformers import AutoModelForCausalLM, AutoTokenizer

    # Sanity check: confirm we really are pinned to one GPU.
    n = torch.cuda.device_count()
    assert n == 1, (
        f"Expected exactly 1 visible GPU (pinned by "
        f"CUDA_VISIBLE_DEVICES=7), got {n}. Check that no other env "
        f"var is overriding it."
    )
    print(f"[collect] CUDA_VISIBLE_DEVICES={os.environ['CUDA_VISIBLE_DEVICES']}; "
          f"1 visible GPU = {torch.cuda.get_device_name(0)} "
          f"({torch.cuda.mem_get_info(0)[0]/1e9:.1f}/"
          f"{torch.cuda.mem_get_info(0)[1]/1e9:.1f} GB free)")

    print(f"[collect] loading tokenizer for {args.model_path}")
    hf_tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    if hf_tokenizer.pad_token is None:
        hf_tokenizer.pad_token = hf_tokenizer.eos_token

    print(f"[collect] loading vLLM engine on cuda:0 "
          f"(gpu_memory_utilization={args.gpu_mem_util})")
    if args.vllm_device and args.vllm_device != "cuda:0":
        # We already pinned CUDA_VISIBLE_DEVICES=7 at module load, but
        # allow the user to override the visible nvidia-smi index.
        vllm_dev = args.vllm_device
        if vllm_dev.startswith("cuda:"):
            ns_idx = int(vllm_dev.split(":")[1])
            print(f"[collect] re-pinning CUDA_VISIBLE_DEVICES={ns_idx} "
                  "(was 7)")
            os.environ["CUDA_VISIBLE_DEVICES"] = str(ns_idx)

    vllm_kwargs = dict(
        model=args.model_path,
        dtype="bfloat16",
        max_model_len=args.max_context,
        gpu_memory_utilization=args.gpu_mem_util,
        enforce_eager=args.enforce_eager,
    )
    if args.tensor_parallel_size > 1:
        vllm_kwargs["tensor_parallel_size"] = args.tensor_parallel_size
    llm = LLM(**vllm_kwargs)
    vllm_tokenizer = llm.get_tokenizer()
    print(f"[collect] vLLM ready, model loaded.")

    device = torch.device(args.hf_device)
    dtype = {"bfloat16": torch.bfloat16,
             "float16": torch.float16,
             "float32": torch.float32}[args.dtype]
    # HF model runs on the (only) GPU visible to this process — which
    # is the same physical card as vLLM's EngineCore. We just need ~2 GB.
    print(f"[collect] loading HF model on {device} (dtype={args.dtype}) "
          "for per-layer extraction")
    hf_model = AutoModelForCausalLM.from_pretrained(
        args.model_path, dtype=dtype,
    )
    hf_model = hf_model.to(device)
    hf_model.eval()
    print(f"[collect] HF model loaded: d_model={hf_model.config.hidden_size}, "
          f"n_layers={hf_model.config.num_hidden_layers}")

    if args.jsonl:
        problems = load_aime_from_jsonl(args.jsonl)
        print(f"[collect] loaded {len(problems)} problems from {args.jsonl}")
    elif args.split:
        problems = load_aime(args.split)
        print(f"[collect] loaded {len(problems)} problems for split {args.split}")
    else:
        problems = load_aime()
        print(f"[collect] loaded {len(problems)} builtin problems")

    if args.limit:
        problems = problems[:args.limit]

    out_root = Path(args.out_dir) / args.dataset
    out_root.mkdir(parents=True, exist_ok=True)

    t_start = time.time()
    n_done = 0
    for i, problem in enumerate(problems):
        for mode in ("think", "no_think"):
            tid = f"aime__{problem['split']}__{problem['id']}__{mode}"
            json_path = out_root / f"{tid}.json"
            npz_path = out_root / f"{tid}.npz"
            if json_path.exists() and npz_path.exists() and not args.overwrite:
                print(f"[{i+1}/{len(problems)}] {mode:8s} {problem['id']:10s} "
                      "— SKIP (exists)")
                continue
            print(f"[{i+1}/{len(problems)}] {mode:8s} {problem['id']:10s} ...",
                  flush=True)
            try:
                meta, hidden, logits, token_ids, attn = run_one(
                    llm, hf_model, vllm_tokenizer, problem, mode,
                    args, device,
                )
                save_trajectory(out_root, meta, hidden, logits, token_ids, attn,
                                save_full_logits=args.save_full_logits,
                                dtype=args.store_dtype)
                ans = meta.generated_answer or "(none)"
                corr = "OK" if meta.is_correct else "X "
                print(f"      {corr} {meta.n_generated_tokens:4d} tok  "
                      f"ans={ans[:30]:30s}  -> {npz_path.name}", flush=True)
                n_done += 1
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                gc.collect()
                print(f"      OOM on {problem['id']} / {mode}, skipping",
                      flush=True)
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"      ERROR: {e}", flush=True)
                continue

    dt = time.time() - t_start
    print(f"\n[collect] done in {dt/60:.1f} min. "
          f"{n_done} new trajectories. Output under {out_root}")


def cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-name", default="Qwen/Qwen3-1.7B")
    ap.add_argument("--model-path",
                    default="/home/zhourui/.cache/huggingface/models/"
                            "Qwen--Qwen3-1.7B/snapshots/master")
    ap.add_argument("--vllm-device", default="cuda:0",
                    help="Ignored unless != 'cuda:0'. We pin "
                         "CUDA_VISIBLE_DEVICES=7 at import time so the "
                         "process only ever sees one GPU (nvidia-smi 7).")
    ap.add_argument("--hf-device", default="cuda:0",
                    help="Always 'cuda:0' — only one card is visible to "
                         "this process because CUDA_VISIBLE_DEVICES=7.")
    ap.add_argument("--dtype", default="bfloat16",
                    choices=["bfloat16", "float16", "float32"],
                    help="HF model dtype for the forward pass")
    ap.add_argument("--max-new-tokens", type=int, default=8192)
    ap.add_argument("--max-context", type=int, default=32768)
    ap.add_argument("--gpu-mem-util", type=float, default=0.85)
    ap.add_argument("--enforce-eager", action="store_true",
                    help="Disable CUDA graphs in vLLM (lower VRAM at cost of speed)")
    ap.add_argument("--tensor-parallel-size", type=int, default=1)
    ap.add_argument("--dataset", default="aime")
    ap.add_argument("--split", default=None)
    ap.add_argument("--jsonl", default=None)
    ap.add_argument("--out-dir", default=str(HERE / "output" / "trajectories"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--save-full-logits", action="store_true")
    ap.add_argument("--store-dtype", default="float32",
                    choices=["float16", "float32"])
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    main(args)


if __name__ == "__main__":
    cli()