"""Name every hidden-state dimension, so the viewer can be read by a human.

Why this is the difference between animation and explanation
-----------------------------------------------------------
A residual-stream vector has 2048 components with no names. Showing
"point 337 moved" is movement; showing it is not explanation. The bridge is
the unembedding: a dimension ``d`` contributes ``W_U[t, d] * h[d]`` to the
logit of token ``t``. So the tokens a dimension is *about* are simply the
ones with the largest ``W_U[:, d]`` — and the size of ``h[d]`` says whether
that dimension is currently leaning positive or negative.

That yields a sentence the page can show next to a bar:

    dim 337   h = +2.41   favours:  " therefore",  " thus",  " hence"

The activation comes from the data; the wording comes from here.

Subword pieces matter
---------------------
The top of ``W_U[:, d]`` is frequently not a word at all but a fragment
like "Ġthe" or "Ġ\Ň". Shipping the top 8 *tokens* blindly produces lists of
junk that read as noise. This script takes a deeper slice and keeps the
pieces that decode to a leading space (a word start) or to a standalone
word, so the dictionary a human reads is made of words.

Qwen3-1.7B ties ``lm_head`` to ``embed_tokens``, so one matrix serves for
both the lens and the names; the script uses ``lm_head`` and says so, so
that if the tying ever stops the discrepancy is visible rather than silent.

Usage
-----
    python3 backend/examples/build_dim_dictionary.py \
        --model-path /models/Qwen3-1.7B --out frontend/public/latent/dim_names.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import List

import numpy as np


def is_readable(text: str) -> bool:
    """Reject fragments that would make the dictionary look like noise."""
    t = text.strip()
    if not t:
        return False
    # A leading space means this piece starts a word, which is the signal
    # that it is a standalone token rather than a suffix chunk.
    starts_word = text.startswith(" ") or text.startswith("\n")
    standalone = t.isalpha() and len(t) >= 2
    return starts_word or standalone


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--device", default="cpu",
                    help="The unembedding is read once; CPU is faster than "
                         "moving 600 MB of weights to a busy GPU.")
    ap.add_argument("--depth", type=int, default=96,
                    help="How far down W_U[:, d] to look before giving up on "
                         "finding a readable piece for a dimension.")
    ap.add_argument("--names", type=int, default=6,
                    help="Readable tokens kept per dimension.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    t0 = time.time()
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.model_path)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path, dtype="float32", device_map={"": args.device})
    W = model.lm_head.weight.detach().float().cpu().numpy()   # (V, D)
    vocab, d_model = W.shape
    print(f"unembedding {W.shape}  loaded in {time.time()-t0:.1f}s")
    print(f"  tied to embed_tokens: "
          f"{getattr(model.config, 'tie_word_embeddings', None)}")

    # argmax per dimension, in one pass over the (V, D) matrix.
    best_idx = np.argmax(W, axis=0)                 # (D,)
    best_val = W[best_idx, np.arange(d_model)]      # (D,)

    # Per-dimension top list. Doing this one dimension at a time is 2048
    # small argsorts over a 151936-row column; the loop is cheap relative
    # to the token decode, which is the real cost.
    order = np.argsort(-W, axis=0)                  # (V, D) int32, ~1.2 GB

    dims: List[dict] = []
    n_sparse = 0
    for d in range(d_model):
        picked: List[dict] = []
        seen: set = set()
        for rank in range(min(args.depth, vocab)):
            tid = int(order[rank, d])
            if tid in seen:
                continue
            seen.add(tid)
            s = tok.decode([tid])
            if not is_readable(s):
                continue
            picked.append({"id": tid, "t": s,
                           "w": round(float(W[tid, d]), 3)})
            if len(picked) >= args.names:
                break
        if not picked:
            # A dimension with no readable piece in the top `depth` is
            # recorded as such rather than being filled with fragments.
            # Silently substituting junk would make every later claim about
            # this dimension untrustworthy.
            n_sparse += 1
        dims.append({
            "d": d,
            "top": picked,
            "peak": round(float(best_val[d]), 3),
            "peak_tok": tok.decode([int(best_idx[d])]),
        })
        if (d + 1) % 256 == 0:
            print(f"  {d+1}/{d_model} dimensions", flush=True)

    payload = {
        "schema": "dim_names_v1",
        "model_path": str(args.model_path),
        "d_model": d_model,
        "vocab": vocab,
        "tied_word_embeddings": bool(
            getattr(model.config, "tie_word_embeddings", False)),
        "n_without_readable_name": n_sparse,
        "definition": (
            "names are the tokens with the largest W_U[:, d]; a dimension's "
            "sign at runtime says whether it promotes or suppresses them"),
        "dims": dims,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False,
                              separators=(",", ":")))
    print(f"\nwrote {out}  ({out.stat().st_size/1e6:.2f} MB)")
    print(f"  {n_sparse}/{d_model} dimensions had no readable token in the "
          f"top {args.depth}")
    for d in (337, 512, 1024):
        e = dims[d]
        print(f"  L? dim {d}: " + ", ".join(
            f"{p['t']!r}({p['w']})" for p in e["top"][:4]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
