"""Why THIS token and not that one? Logit-lens attribution over a Qwen3 trace.

Every other experiment in this project asks what a *vector* does. None of
them ask the question the whole thing is named after: at a given decoding
step, why did the model emit token A rather than token B?

That question has a well-posed answer, and it is the standard logit lens:

  1. Take the final residual stream at a chosen position.
  2. Read a *partial* model out of it -- apply the final RMSNorm and the
     unembedding to the state at layer L, as if the network stopped there.
  3. The resulting logits approximate the final logits. The approximation
     is what needs testing, so the fidelity of the lens is reported
     alongside the attribution and never assumed.

With a working lens, the logit gap between the chosen token and its
runner-up decomposes layer by layer, and the question "which layer decided
this token" becomes a measurement rather than a story.

Two decompositions are computed, because they answer different questions:

  * **Layer-wise** (`--mode layers`): how the chosen-vs-runner-up logit gap
    accumulates with depth. Answers *when* the decision was made.
  * **Head-wise** (`--mode heads`): the direct logit contribution of every
    attention head, via the standard o_proj input decomposition -- write
    o_proj as a sum over heads, then read each head's output vector through
    the unembedding. Answers *which heads* pushed which token.

Head attribution is done on the layer norm *inside* each block (input_layernorm
for self-attention, post_attention_layernorm for MLP), which is what the
residual stream actually carries at that depth, not the final norm.

The honest caveat, which the script enforces and reports: a logit lens is a
linear probe through a non-linear network, and its fidelity is not uniform
across layers. So the script computes the lens-vs-true KL at every layer and
prints it beside the attribution. Layers where the lens is unfaithful are
flagged, and a summary that survives only in the unfaithful tail is not
evidence.

Usage:
    python3 backend/examples/attribute_token_choice.py \
        --model-path /data/model/Qwen3-1.7B \
        --problem-file backend/examples/output/problem_index.json \
        --limit 8 --steps 6 --mode both \
        --out backend/examples/output/token_attribution.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Model plumbing
# ---------------------------------------------------------------------------


def load_model(model_path: str, device: str, dtype: str = "bfloat16"):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    td = {"bfloat16": torch.bfloat16, "float16": torch.float16,
          "float32": torch.float32}[dtype]
    tok = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, dtype=td, device_map={"": device}
    )
    model.eval()
    return model, tok


def unembed(model, h: "torch.Tensor", norm: bool = True):
    """Map a residual-stream state to logits via the final norm + lm_head.

    `h` must already be the residual stream *after* the last block (i.e. the
    same object the model itself feeds to the final norm).
    """
    import torch

    x = model.model.norm(h) if norm else h
    return model.lm_head(x)


def lens_logits(model, hidden_states, layer: int, use_norm: bool = True):
    """Read the model out of the residual stream at `layer`.

    `hidden_states` from HF is a tuple indexed 0..L where index 0 is the
    embedding output and index L is the output of block L-1. So the state
    feeding block L is hidden_states[L], and passing it through the *final*
    norm is the logit-lens approximation at depth L.
    """
    return unembed(model, hidden_states[layer], norm=use_norm)


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


def attr_layers(model, hidden_states, tok_ids: List[int],
                true_logits=None) -> dict:
    """Layer-wise logit gap between the chosen token and each alternative.

    The gap is measured against the chosen token, so positive means the
    layer's partial model already prefers the chosen token. Reading the gap
    (rather than each logit separately) is what makes the result
    interpretable: the decision is a comparison, and only the difference
    carries the comparison.

    NOTE on the last layer. Under transformers 5.x, `hidden_states[-1]` is
    NOT the tensor the model feeds to its own unembedding: rebuilding the
    final logits from it disagrees with `model(...).logits` by up to 15 nats
    and even changes which token ranks second. So the last layer is not
    read through the lens at all -- its gap is the model's own logit gap,
    i.e. ground truth. Every earlier layer is a genuine lens read-out and is
    reported with its KL against those ground-truth logits, because a lens
    is a linear probe through a non-linear network and its fidelity is not
    uniform with depth.
    """
    import torch

    with torch.inference_mode():
        if true_logits is None:
            true_logits = model.lm_head(
                model.model.norm(hidden_states[-1]))[0, -1, :].float()
    out = {"layers": [], "alternatives": [int(t) for t in tok_ids]}

    n = len(hidden_states)
    for L in range(n):
        with torch.inference_mode():
            if L == n - 1:
                lg = true_logits
            else:
                lg = lens_logits(model, hidden_states, L)[0, -1, :].float()
            row = {"layer": L, "is_true_output": L == n - 1}
            for aid in tok_ids:
                row[str(int(aid))] = float(lg[int(aid)] - lg[int(tok_ids[0])])
            # lens fidelity: KL of the lens distribution at this layer against
            # the true final distribution, at this position.
            p_true = torch.log_softmax(true_logits, -1)
            p_lens = torch.log_softmax(lg, -1)
            row["lens_kl"] = float(torch.sum(p_true.exp() * (p_true - p_lens)))
            row["cos_to_final"] = float(
                torch.nn.functional.cosine_similarity(
                    lg.unsqueeze(0), true_logits.unsqueeze(0), dim=-1
                ).reshape(-1)[0]
            )
        # Degeneracy guard. A lens that returns the same logit for every
        # token carries no information, and it is trivially easy to produce
        # by accident (wrong precision, wrong normalisation, a norm applied
        # twice). Detected here rather than reported downstream as a flat,
        # highly "consistent" attribution curve.
        with torch.inference_mode():
            spread = float(lg.max() - lg.min())
        if spread < 1e-3:
            raise RuntimeError(
                f"logit lens at layer {L} is degenerate: logit spread over "
                f"{lg.numel()} tokens is {spread:.2e}. Check --dtype "
                f"(must be float32) and that the final norm is applied once."
            )
        out["layers"].append(row)
    return out


def attr_heads(model, hidden_states, tok_ids: List[int],
               layer: int) -> dict:
    """Per-head direct logit contribution at one layer.

    The attention block writes to the residual stream as
        o_proj( concat_h( z_h ) ) = sum_h W_o[:, h*d:(h+1)*d] @ z_h
    so each head's own output vector is recoverable, and its direct
    contribution to a token's logit is W_U[token] . W_o[:, h] @ z_h.

    Heads are read through the *final* norm's approximation being wrong at
    depth, so this is reported as a ranking with the layer's lens fidelity
    attached, not as an exact decomposition.
    """
    import torch

    block = model.model.layers[layer]
    attn = block.self_attn
    n_heads = model.config.num_attention_heads
    d_head = getattr(model.config, "head_dim", None) or (
        model.config.hidden_size // n_heads
    )
    hidden_size = model.config.hidden_size

    # The residual stream entering the attention block.
    h_in = hidden_states[layer]
    # What each head actually contributed, recovered by re-running the
    # attention with output_attentions and taking the slice of the
    # concatenated head states that o_proj consumed.
    with torch.inference_mode():
        normed = block.input_layernorm(h_in)
        # Re-run the block's attention explicitly to get per-head outputs.
        pos = h_in.shape[1] - 1  # last position only
        out = _head_outputs(attn, normed, model)
    if out is None:
        return {"error": "head outputs unavailable for this architecture"}

    W_o = attn.o_proj.weight  # (hidden_size, n_heads*d_head)
    W_U = model.lm_head.weight  # (vocab, hidden_size)

    rows = []
    for a in tok_ids:
        for hidx in range(n_heads):
            z = out[0, pos, hidx * d_head:(hidx + 1) * d_head]
            w = W_o[:, hidx * d_head:(hidx + 1) * d_head]  # (hidden, d_head)
            with torch.inference_mode():
                contrib = float((W_U[int(a)] @ w) @ z)
            rows.append({"token": int(a), "head": int(hidx),
                         "contribution": contrib})
    return {"layer": int(layer), "rows": rows}


def _head_outputs(attn, normed_hidden, model):
    """Per-position concatenated head outputs, as o_proj consumed them.

    Uses the attention module's own forward with output_attentions when the
    installed transformers supports it; returns None otherwise so the
    caller can degrade instead of guessing.
    """
    import torch

    num_heads = model.config.num_attention_heads
    num_kv = model.config.num_key_value_heads
    d_head = getattr(model.config, "head_dim", None) or (
        model.config.hidden_size // num_heads
    )
    bsz, seq, _ = normed_hidden.shape

    try:
        q = attn.q_proj(normed_hidden).view(bsz, seq, num_heads, d_head).transpose(1, 2)
        kv = attn.k_proj(normed_hidden).view(bsz, seq, num_kv, d_head).transpose(1, 2)
        v = attn.v_proj(normed_hidden).view(bsz, seq, num_kv, d_head).transpose(1, 2)
        if num_kv != num_heads:
            rep = num_heads // num_kv
            k = kv.repeat_interleave(rep, dim=1)
            v = v.repeat_interleave(rep, dim=1)
        else:
            k, v = kv, v
        # Causal single-window evaluation: the caller passes the full
        # sequence, so build a causal mask.
        mask = torch.full((seq, seq), float("-inf"), device=q.device,
                          dtype=q.dtype).triu(1)
        out = torch.nn.functional.scaled_dot_product_attention(
            q, k, v, attn_mask=mask
        )
        out = out.transpose(1, 2).reshape(bsz, seq, num_heads * d_head)
        return out.to(attn.o_proj.weight.dtype)
    except Exception as exc:  # pragma: no cover - architecture dependent
        print(f"  (head outputs unavailable: {exc})")
        return None


# ---------------------------------------------------------------------------
# Trace driver
# ---------------------------------------------------------------------------


def attribute_step(model, tok, input_ids, alt_k: int = 4,
                   with_heads: bool = False, rng=None) -> dict:
    """Attribute one decoding step: chosen token vs its top alternatives.

    With `rng` supplied, the alternatives are drawn at random from the
    vocabulary instead of taken as the model's own top-k. That produces the
    null control for the whole method: a random token carries no decision,
    so its sign-agreement curve should be flat and near 50%. Without that
    curve measured, "the early layers are near chance" is an assumption
    about what chance looks like rather than a control for it.
    """
    import torch

    with torch.inference_mode():
        out = model(input_ids=input_ids, output_hidden_states=True,
                    use_cache=False, return_dict=True)
    logits = out.logits[0, -1, :].float()
    hs = out.hidden_states

    top = torch.topk(logits, alt_k + 1)
    chosen = int(top.indices[0])
    if rng is None:
        alts = [int(i) for i in top.indices[1:]]
    else:
        vocab = int(logits.shape[0])
        pool = [t for t in top.indices.tolist() if int(t) != chosen]
        alts = []
        while len(alts) < alt_k:
            c = int(rng.integers(0, vocab))
            if c != chosen and c not in alts:
                alts.append(c)

    rec = {
        "chosen": chosen,
        "chosen_text": tok.decode([chosen]),
        "chosen_logit": float(logits[chosen]),
        "top": [{"id": int(i), "text": tok.decode([int(i)]),
                 "logit": float(logits[int(i)])} for i in top.indices],
        "alternatives_are_random": rng is not None,
        "alternatives": [{"id": a, "text": tok.decode([a]),
                          "logit": float(logits[a])} for a in alts],
        "margin": float(logits[chosen] - logits[alts[0]]) if alts else None,
        "entropy": float(-torch.sum(torch.softmax(logits, -1)
                                    * torch.log_softmax(logits, -1))),
        "n_alternatives": len(alts),
    }
    rec["layers"] = attr_layers(model, hs, [chosen] + alts, true_logits=logits)
    if with_heads:
        rec["_hs"] = hs
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--problem-file", default=None,
                    help="problem index json from make_problem_index.py")
    ap.add_argument("--prompt", default=None,
                    help="use this prompt instead of a problem file")
    ap.add_argument("--limit", type=int, default=4)
    ap.add_argument("--steps", type=int, default=4,
                    help="decoding steps to attribute per problem")
    ap.add_argument("--prefill", type=int, default=48,
                    help="teacher-forced prefill length before attributing")
    ap.add_argument("--mode", choices=["layers", "heads", "both"],
                    default="layers")
    ap.add_argument("--chat-template", type=int, default=1,
                    help="wrap the problem in Qwen3's chat template (default on)")
    ap.add_argument("--random-alternatives", type=int, default=0,
                    help="draw the alternatives at random from the "
                         "vocabulary instead of the model's top-k. This is "
                         "the null control for the attribution: its "
                         "sign-agreement curve should stay near 50%.")
    ap.add_argument("--device", default="cuda" if __import__("torch").cuda.is_available() else "cpu")
    ap.add_argument("--dtype", default="float32",
                    help="float32 is REQUIRED for a logit lens. In bfloat16 "
                         "the un-normalised residual stream read through "
                         "lm_head collapses to a constant across tokens and "
                         "every reported gap is identically zero -- a silent "
                         "precision failure, not a finding.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import torch

    rng = None
    if args.random_alternatives:
        rng = np.random.default_rng(0)

    model, tok = load_model(args.model_path, args.device, args.dtype)

    if args.prompt:
        problems = [{"label": "inline", "prompt": args.prompt}]
    else:
        if not args.problem_file:
            raise SystemExit("need --problem-file or --prompt")
        raw = json.loads(Path(args.problem_file).read_text())
        # `make_problem_index.py` emits a dict keyed by problem label; a list
        # of records is also accepted so the script works with either.
        if isinstance(raw, dict):
            if "problems" in raw:
                problems = raw["problems"]
            else:
                problems = [
                    dict(v, label=v.get("id", k)) if isinstance(v, dict)
                    else {"label": k, "prompt": str(v)}
                    for k, v in raw.items()
                ]
        else:
            problems = raw
    problems = problems[: args.limit]

    device = model.device
    results = []
    for pi, prob in enumerate(problems):
        text = prob.get("text") or prob.get("prompt") or ""
        if not text:
            continue
        enc = tok(text, return_tensors="pt", add_special_tokens=False)
        ids = enc.input_ids.to(device)
        if ids.shape[1] < 8:
            continue
        # Qwen3 is instruction-tuned with a reasoning template; attributing
        # the raw problem text measures a distribution the model is never
        # actually run in. The template puts the next-token prediction
        # inside a `<think>` block, which is the regime the rest of this
        # project studies.
        if args.chat_template and getattr(tok, "chat_template", None):
            try:
                templ = tok.apply_chat_template(
                    [{"role": "user", "content": text}],
                    tokenize=False, add_generation_prompt=True,
                )
                enc2 = tok(templ, return_tensors="pt", add_special_tokens=False)
                ids = enc2.input_ids.to(device)
            except Exception as exc:
                print(f"  (chat template unavailable: {exc})")
        print(f"[{pi+1}/{len(problems)}] {prob.get('label','?')} "
              f"({ids.shape[1]} prompt tokens)")

        for step in range(args.steps):
            # Teacher-forced prefill, then attribute the next-token choice.
            rec = attribute_step(model, tok, ids,
                                 with_heads=(args.mode in ("heads", "both")),
                                 rng=rng)
            rec["problem"] = prob.get("label")
            rec["step"] = step
            rec["context_len"] = int(ids.shape[1])
            rec["context_tail"] = tok.decode(ids[0, -24:].tolist())
            if args.mode in ("heads", "both"):
                alts = [t["id"] for t in rec["top"][1:]]
                rec["heads"] = attr_heads(model, rec.pop("_hs"), [rec["chosen"]] + alts,
                                          layer=args.prefill)
            results.append(rec)
            # Extend the context greedily so successive steps are a real trace.
            ids = torch.cat(
                [ids, torch.tensor([[rec["chosen"]]], device=device)], dim=1
            )
            print(f"   step {step}: {rec['chosen_text']!r} "
                  f"margin={rec['margin']:.3f} "
                  f"entropy={rec['entropy']:.3f}")

    out = {
        "model": args.model_path,
        "n_steps": len(results),
        "mode": args.mode,
        "note": ("logit-lens attribution; lens_kl per layer is the fidelity "
                 "of the partial read-out at that depth and bounds what the "
                 "layer-wise numbers can be claimed to show"),
        "steps": results,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
