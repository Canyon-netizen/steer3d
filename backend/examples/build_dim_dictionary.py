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
    ap.add_argument("--model-path", default="",
                    help="Checkpoint dir. Required unless --readout is given, "
                         "in which case only the tokenizer comes from it.")
    args_model_required = False
    ap.add_argument("--device", default="cpu",
                    help="The unembedding is read once; CPU is faster than "
                         "moving 600 MB of weights to a busy GPU.")
    ap.add_argument("--depth", type=int, default=96,
                    help="How far down W_U[:, d] to look before giving up on "
                         "finding a readable piece for a dimension.")
    ap.add_argument("--names", type=int, default=6,
                    help="Readable tokens kept per dimension.")
    ap.add_argument("--readout", default="",
                    help="Read lm_head from an extract_readout.py .npz "
                         "instead of loading the model. Same checkpoint, same "
                         "matrix; only the tokenizer still comes from "
                         "--model-path.")
    ap.add_argument("--tokenizer", default="",
                    help="Path to a HuggingFace tokenizer.json, used with "
                         "--readout. Required in that mode.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if not args.readout and not args.model_path:
        raise SystemExit("--model-path is required unless --readout is given")
    if args.readout and not args.tokenizer:
        raise SystemExit("--readout needs --tokenizer (a HuggingFace tokenizer.json)")

    t0 = time.time()
    tied = None
    if args.readout:
        # The unembedding is the only thing this script needs from the model,
        # and `extract_readout.py` already writes it to an .npz taken from the
        # same checkpoint. Loading 1.5 GB of weights to re-read one matrix --
        # and, on a machine whose home directory is a shared NFS mount, waiting
        # tens of minutes for the imports -- is pure cost. Same matrix, same
        # checkpoint; `--model-path` is then only used to find the tokenizer.
        z = np.load(args.readout)
        W = z["lm_head.weight"].astype(np.float32)
        vocab, d_model = W.shape
        # A real tokenizer, not a hand-inverted vocab dict: Qwen's BPE is
        # byte-level, so `Ġgreater` has to come back as " greater" and a
        # multi-byte character has to come back as that character. Building it
        # from tokenizer.json alone is enough for PreTrainedTokenizerFast and
        # keeps this path entirely local.
        from transformers import PreTrainedTokenizerFast
        tok = PreTrainedTokenizerFast(tokenizer_file=args.tokenizer)
        print(f"unembedding {W.shape}  from readout {args.readout} "
              f"in {time.time()-t0:.1f}s")
        print(f"  tokenizer: {args.tokenizer}  vocab={len(tok)}")
        # The readout npz does not carry the config, so this is not read from
        # disk here. Both Qwen3 sizes tie the unembedding to the input
        # embedding, and `analyse_divergence_logits` already relies on that
        # (it verified lm_head.weight is bit-identical to embed_tokens.weight),
        # but it is recorded as what it is rather than as a measured fact.
        tied = None
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(args.model_path)
        model = AutoModelForCausalLM.from_pretrained(
            args.model_path, dtype="float32", device_map={"": args.device})
        W = model.lm_head.weight.detach().float().cpu().numpy()   # (V, D)
        vocab, d_model = W.shape
        print(f"unembedding {W.shape}  loaded in {time.time()-t0:.1f}s")
        tied = getattr(model.config, "tie_word_embeddings", None)
    if not args.readout:
        print(f"  tied to embed_tokens: {tied}")

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
        # `tied` is set on both paths. Reading `model.config` here instead
        # raised UnboundLocalError after all 1024 dimensions were already
        # computed -- the same "only assigned in one branch" shape as the
        # UnboundLocalError in measure_model_layer_norms.py, and just as fatal
        # because the work is lost at the last line.
        "tied_word_embeddings": bool(tied),
        "source": "readout" if args.readout else "checkpoint",
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
    # Sample dimensions that exist. The list used to be the literal
    # (337, 512, 1024), which is fine for a 2048-wide model and an IndexError
    # for a 1024-wide one -- thrown on the last line, after the file was
    # already written, so the run still exited non-zero on a good result.
    for d in [x for x in (337, 512, 1024) if x < len(dims)]:
        e = dims[d]
        print(f"  dim {d}: " + ", ".join(
            f"{q['t']!r}({q['w']})" for q in e["top"][:4]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
