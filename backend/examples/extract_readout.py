"""Pull the two tensors a **logit lens** needs out of a sharded checkpoint.

Why this file exists
--------------------
Every previous readout in this project loaded the whole model just to reach
``model.norm`` and ``lm_head``. For a sharded 1.7B checkpoint that is 3.4 GB and
a ~20 s import, to use two tensors that total 622 MB and are pure constants:
neither depends on the input, the KV cache, or anything about the prompt.

The logit lens is a *read-out*, not a forward pass::

    logit_v(h_L) = W_head[v] · (g ⊙ h_L / rms(h_L))

so ``h_L`` can come out of a stored ``.npz`` and the readout can run in numpy
with no torch in the loop at all. That is what makes it possible to ask "which
residual coordinates flipped this token" as arithmetic over data already on
disk, instead of another GPU pass.

Layer-index caveat this file is silent about, stated here so nobody re-derives
it wrongly: for ``num_hidden_layers = n`` the ``hidden_states`` tuple has
``n + 1`` entries and ``hidden_states[i]`` is the residual *entering* block
``i``. ``hidden_states[n]`` is therefore the last readable one, and it is the
one the true logits are computed from. The paired collector defaults to
``{4, 12, 20, 26}`` and **does not store it** — see INTERPRETABILITY.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from safetensors import safe_open

NORM_KEY = "model.norm.weight"
HEAD_KEY = "lm_head.weight"


def _shard_index(model_dir: Path) -> dict:
    idx_path = model_dir / "model.safetensors.index.json"
    if idx_path.is_file():
        return json.loads(idx_path.read_text())["weight_map"]
    # single-file checkpoint
    return {}


def extract(model_dir: Path, out_path: Path, keys=(NORM_KEY, HEAD_KEY)) -> None:
    shards = _shard_index(model_dir)
    if not shards:
        only = model_dir / "model.safetensors"
        if not only.is_file():
            raise SystemExit(f"no safetensors under {model_dir}")
        shards = {k: only.name for k in keys}

    missing = [k for k in keys if k not in shards]
    if missing:
        raise SystemExit(
            f"checkpoint is missing {missing}; the lens needs a final norm and "
            f"an unembedding. Qwen3-1.7B ships both explicitly even though "
            f"tie_word_embeddings is true.")

    out: dict = {}
    # Group by shard so each file is opened once and only the wanted tensors
    # are paged in. safe_open is lazy: this never materialises the other ~1 GB
    # of tensors that live in the same shard.
    by_shard: dict = {}
    for k in keys:
        by_shard.setdefault(shards[k], []).append(k)

    for shard, wanted in by_shard.items():
        # framework="np" cannot materialise bfloat16, which is what Qwen3 ships,
        # so read through torch and convert on the way out. float16 is not a
        # precision *loss* here: bfloat16 keeps 7 mantissa bits, float16 keeps
        # 10, and the only way float16 could lose a value bfloat16 kept is
        # overflow above 65504, which is checked for rather than assumed.
        with safe_open(str(model_dir / shard), framework="pt") as f:
            for k in wanted:
                t = f.get_tensor(k)
                a16 = t.to(torch.float16).numpy()
                if not np.isfinite(a16.astype(np.float32)).all():
                    raise SystemExit(
                        f"{k} overflowed float16 — the checkpoint holds values "
                        f"outside [-65504, 65504]; store as float32 instead")
                out[k] = np.ascontiguousarray(a16)
                print(f"  {k:24s} {str(out[k].shape):18s} {out[k].dtype}"
                      f"  (from {t.dtype})")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path, **out)
    size = out_path.stat().st_size
    print(f"\nwrote {out_path}  ({size / 1e6:.1f} MB)")
    # A readout that is silently the wrong tensor is the one failure mode that
    # would make every downstream number plausible and wrong, so the shape is
    # echoed rather than assumed.
    head = out[HEAD_KEY]
    if head.ndim != 2:
        raise SystemExit(f"{HEAD_KEY} is {head.ndim}-D, expected 2-D")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    extract(Path(a.model_path), Path(a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
