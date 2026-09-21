"""Demo / smoke test for the standardised trajectory format.

Once you've run ``collect_qwen3_aime.py`` and have trajectories under
``output/trajectories/``, this script:

  1. Opens the dataset
  2. Picks a problem that exists in BOTH think and no_think mode
  3. Computes a global PCA over hidden states across ALL layers and modes
  4. Prints per-mode stats:
       - tokens generated
       - final-layer entropy trajectory summary
       - peak perplexity
       - is_correct
  5. Saves a small comparison JSON showing how the two modes diverge

Use::

    python inspect_dataset.py
    python inspect_dataset.py --root output/trajectories/aime
    python inspect_dataset.py --root output/trajectories/aime --problem 2024_I_1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core.standard import TrajectoryDataset, TrajectoryFilter


def _stats(arr: np.ndarray) -> dict:
    if arr.size == 0:
        return {"empty": True}
    return {
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
        "std": float(arr.std()),
    }


def per_layer_summary(traj) -> dict:
    """For each layer, summary stats of the residual stream norm."""
    out = {}
    for L in range(traj.meta.n_layers):
        norms = np.linalg.norm(traj.hidden_states[:, L, :], axis=1)
        out[L] = {"norm_mean": float(norms.mean()),
                  "norm_std": float(norms.std()),
                  "norm_max": float(norms.max())}
    return out


def compare_pair(think: "Trajectory", nothink: "Trajectory") -> dict:
    """Compute a small comparison summary between two modes."""
    def metrics(t):
        return {
            "n_tokens": t.meta.n_generated_tokens,
            "is_correct": t.is_correct,
            "generated_answer": t.meta.generated_answer,
            "ground_truth": t.meta.ground_truth,
            "n_think_tokens": int(np.array([tok.is_in_think_block for tok in t.meta.tokens]).sum()),
            "n_answer_tokens": int(np.array([tok.is_after_think for tok in t.meta.tokens]).sum()),
            "ppl_stats": _stats(np.array([tok.perplexity for tok in t.meta.tokens])),
            "ent_stats": _stats(np.array([tok.entropy for tok in t.meta.tokens])),
            "final_layer_norm": _stats(
                np.linalg.norm(t.hidden_states[:, -1, :], axis=1)
            ),
            "early_layer_norm": _stats(
                np.linalg.norm(t.hidden_states[:, 0, :], axis=1)
            ),
        }

    return {
        "problem_id": think.meta.problem_id,
        "split": think.meta.split,
        "think": metrics(think),
        "no_think": metrics(nothink),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(HERE / "output" / "trajectories" / "aime"))
    ap.add_argument("--problem", default=None,
                    help="Problem id like '2024_I_1' (omit to scan all)")
    ap.add_argument("--out", default=None,
                    help="Write the comparison JSON here")
    args = ap.parse_args()

    ds = TrajectoryDataset(args.root)
    print(f"[inspect] {len(ds)} trajectories under {args.root}")
    print(f"[inspect] summary: {ds.summary()}")

    # Group by (split, problem_id) — pair() returns (think, no_think) per problem
    by_problem: dict = {}
    for tid in ds.ids():
        # Strip the trailing __think / __no_think
        for mode in ("think", "no_think"):
            suffix = "__" + mode
            if tid.endswith(suffix):
                base = tid[:-len(suffix)]
                by_problem.setdefault(base, {})[mode] = tid

    pairs = {k: v for k, v in by_problem.items()
             if "think" in v and "no_think" in v}
    print(f"[inspect] {len(pairs)} problems have both think + no_think")

    if args.problem:
        # Find the matching problem
        target = None
        for k in pairs:
            if args.problem in k:
                target = k; break
        if target is None:
            print(f"No paired trajectory found for {args.problem!r}")
            return
        pairs = {target: pairs[target]}

    out = {
        "schema": "1.0",
        "n_pairs": len(pairs),
        "comparisons": [],
    }
    for base, tids in sorted(pairs.items()):
        think = ds.get(tids["think"])
        nothink = ds.get(tids["no_think"])
        cmp = compare_pair(think, nothink)
        out["comparisons"].append(cmp)
        # Print summary
        print(f"\n[{base}]")
        print(f"  think    : {cmp['think']['n_tokens']:5d} tok "
              f"answer={cmp['think']['generated_answer']!r:8s} "
              f"correct={cmp['think']['is_correct']}")
        print(f"  no_think : {cmp['no_think']['n_tokens']:5d} tok "
              f"answer={cmp['no_think']['generated_answer']!r:8s} "
              f"correct={cmp['no_think']['is_correct']}")
        print(f"  think ppl: mean={cmp['think']['ppl_stats'].get('mean', 0):.2f} "
              f"max={cmp['think']['ppl_stats'].get('max', 0):.2f}")
        print(f"  no_thk pl: mean={cmp['no_think']['ppl_stats'].get('mean', 0):.2f} "
              f"max={cmp['no_think']['ppl_stats'].get('max', 0):.2f}")

    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
        print(f"\n[inspect] wrote {args.out}")


if __name__ == "__main__":
    main()
