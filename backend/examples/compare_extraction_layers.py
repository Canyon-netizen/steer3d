"""How much does the extraction layer actually matter?

The project extracts steering vectors at L14 and injects them at L20.
That is a confound: any result could be due to the vector being *about*
confidence, or merely to where it was read out.

This script separates the two, and answers the question without needing a
GPU. It extracts the same semantic direction at several layers and
measures how similar the resulting vectors are to each other.

If the vectors extracted at L8 and L20 are nearly parallel, the choice
of extraction layer is largely irrelevant and the confound is benign.
If they are far apart, the vector is layer-specific and the confound has
to be dealt with properly — by extracting and injecting at the same
layer, or by reporting results per extraction layer.

Read the per-layer Cohen's d alongside the cosines: a direction can be
more cleanly separated at depth (higher d) while also pointing somewhere
different.

Usage:
    python3 backend/examples/compare_extraction_layers.py \
        --layers 8 14 20 24 --out-dir /tmp/vec --data-root datasets/...
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

DIRECTIONS = [
    "confidence_up",
    "caution",
    "creativity",
    "reasoning_deep",
]


def extract(layer: int, out_dir: Path, data_root: str) -> Path:
    """Run compute_steering_vectors.py for one layer."""
    cmd = [
        sys.executable, str(HERE / "compute_steering_vectors.py"),
        "--layer", str(layer),
        "--out-dir", str(out_dir),
        "--data-root", data_root,
        # The cosine matrix below is unreadable without a floor to read
        # it against.
        "--with-null",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"extraction failed at L{layer}:\n{res.stderr[-800:]}")
    return out_dir


def cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return float("nan")
    return float(a @ b / (na * nb))


def main(args) -> int:
    layers: List[int] = args.layers
    root = Path(args.out_root)
    root.mkdir(parents=True, exist_ok=True)

    print("=" * 68)
    print("Does the extraction layer change the vector?")
    print("=" * 68)
    print()

    dirs: Dict[int, Path] = {}
    for L in layers:
        d = root / f"L{L}"
        if args.reuse and (d / "confidence_up.npy").exists():
            print(f"L{L}: reusing {d}")
        else:
            print(f"L{L}: extracting …", flush=True)
            extract(L, d, args.data_root)
        dirs[L] = d

    # Per-layer effect sizes, so "more separated" and "pointing
    # differently" are not conflated.
    cohens_d: Dict[str, Dict[int, float]] = {}
    for L in layers:
        meta = json.loads((dirs[L] / "steering_vectors.json").read_text())
        for name, info in meta.items():
            d = (info.get("validation") or {}).get("confidence_cohens_d")
            if d is not None:
                cohens_d.setdefault(name, {})[L] = float(d)

    results: Dict[str, dict] = {}
    for name in DIRECTIONS:
        paths = {L: dirs[L] / f"{name}.npy" for L in layers}
        if not all(p.exists() for p in paths.values()):
            print(f"{name}: missing at some layer, skipping")
            continue
        V = {L: np.load(paths[L]).astype(np.float64) for L in layers}

        # Matched random control, same sample sizes, same layers. Two
        # vectors from the same model are correlated whether or not they
        # mean anything, so without this the numbers below cannot be read
        # as evidence of a shared direction.
        nulls = {L: dirs[L] / f"{name}_NULL.npy" for L in layers}
        N = ({L: np.load(nulls[L]).astype(np.float64) for L in layers}
             if all(p.exists() for p in nulls.values()) else None)

        print("-" * 68)
        print(f"{name}")
        print("-" * 68)
        header = "        " + "".join(f"{'L'+str(L):>9}" for L in layers)
        print(f"{'cosine':>8}{header[8:]}")
        for a in layers:
            row = "".join(f"{cos(V[a], V[b]):>9.3f}" for b in layers)
            print(f"  L{a:<3}{row}")
        if N is not None:
            for a in layers:
                row = "".join(f"{cos(N[a], N[b]):>9.3f}" for b in layers)
                print(f"  L{a:<3}{row}   <- null floor")
        ds = cohens_d.get(name, {})
        drow = "".join(f"{ds.get(L, float('nan')):>9.2f}" for L in layers)
        print(f"  {'d':<4}{drow}")

        off = [cos(V[a], V[b]) for i, a in enumerate(layers) for b in layers[i + 1:]]
        mean_off = float(np.nanmean(off)) if off else float("nan")
        null_off = None
        if N is not None:
            noff = [cos(N[a], N[b]) for i, a in enumerate(layers)
                    for b in layers[i + 1:]]
            null_off = float(np.nanmean(noff))
            print(f"  mean off-diagonal cosine: {mean_off:+.3f}   "
                  f"(null floor {null_off:+.3f}, "
                  f"excess {mean_off - null_off:+.3f})")
        else:
            print(f"  mean off-diagonal cosine: {mean_off:+.3f}")
        print()

        results[name] = {
            "cosine_matrix": {
                str(a): {str(b): cos(V[a], V[b]) for b in layers} for a in layers
            },
            "mean_offdiagonal_cosine": mean_off,
            "null_mean_offdiagonal_cosine": null_off,
            "excess_over_null": (None if null_off is None
                                 else mean_off - null_off),
            "cohens_d": {str(L): ds.get(L) for L in layers},
            "norms": {str(L): float(np.linalg.norm(V[L])) for L in layers},
        }

    print("=" * 68)
    print("Reading")
    print("=" * 68)
    print("  A cosine has to be read against the null floor beside it. Two")
    print("  vectors extracted from the same model share most of their")
    print("  direction through the residual stream's own geometry, so a")
    print("  high cosine is the expected result and not by itself evidence")
    print("  that the extraction found the same concept.")
    for name, r in results.items():
        m = r["mean_offdiagonal_cosine"]
        null = r.get("null_mean_offdiagonal_cosine")
        excess = r.get("excess_over_null")
        if excess is None:
            print(f"  {name:>18}: mean cos {m:+.3f} — no null available, "
                  f"this number is not interpretable on its own")
            continue
        if excess > 0.15:
            verdict = ("well above the floor: the extraction really does "
                       "recover a shared direction")
        elif excess > 0.05:
            verdict = "above the floor, but only modestly"
        else:
            verdict = ("at the floor: these extractions share no more than "
                       "random groupings do, so the cosine between them is "
                       "not evidence of a rotating single direction")
        print(f"  {name:>18}: mean cos {m:+.3f} vs null {null:+.3f} "
              f"(excess {excess:+.3f}) — {verdict}")
    print()
    print("  A vector can be better separated at depth (higher d) and still "
          "point elsewhere, so read the two rows together.")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"layers": layers, "directions": results}, indent=2
        ))
        print(f"\nwrote {out}")
    return 0


def cli():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--layers", type=int, nargs="+", default=[8, 14, 20, 24])
    ap.add_argument("--out-root", type=str, default="/tmp/steer3d_vec_layers")
    ap.add_argument("--data-root", type=str,
                    default="datasets/aime_qwen3_1p7b_16k_fp16/aime")
    ap.add_argument("--reuse", action="store_true",
                    help="Skip extraction where the vectors already exist")
    ap.add_argument("--out", type=str, default=None)
    return main(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(cli())
