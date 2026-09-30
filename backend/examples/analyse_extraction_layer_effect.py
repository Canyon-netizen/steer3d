"""Does the extraction layer change the behavioural effect?

Finding 5 of docs/INTERPRETABILITY.md showed the vectors extracted at
different layers are not the same vector. This asks the behavioural
question that follows: if the vector is injected at L20 either way, does
where it was read out matter to what it does?

Every run is the same 24 problems, the same injection layer, the same
strength — only the extraction layer varies, so the comparison is paired
and the differences are attributable to the extraction.

Run this after collecting the per-layer runs:

    scp 'zju-57:/tmp/iv_ext_L*.json' /tmp/iv_ext/
    python3 backend/examples/analyse_extraction_layer_effect.py \
        --dir /tmp/iv_ext
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy import stats


def load(path: Path, control: float, treatment: float) -> Dict[str, dict]:
    """Group a run file by prompt, keeping the two strengths separate."""
    by: Dict[str, dict] = {}
    for r in json.loads(path.read_text()):
        by.setdefault(r["prompt_label"], {})[float(r["strength"])] = r["summary"]
    return {k: v for k, v in by.items() if control in v and treatment in v}


def main(args) -> int:
    runs: Dict[int, Dict[str, dict]] = {}
    for f in sorted(Path(args.dir).glob("iv_ext_L*.json")):
        try:
            L = int(f.stem.split("_L")[-1])
        except ValueError:
            continue
        runs[L] = load(f, args.control, args.strength)
    if not runs:
        print(f"no iv_ext_L*.json in {args.dir}")
        return 1

    layers = sorted(runs)
    labels = sorted(set.intersection(*(set(r) for r in runs.values())))
    n = len(labels)
    print("=" * 72)
    print("Extraction layer vs behavioural effect")
    print("=" * 72)
    print(f"{n} problems, injected at L{args.inject_at}, "
          f"strength {args.strength} (control {args.control})")
    print()

    metric = args.metric
    data: Dict[int, np.ndarray] = {}
    print(f"  {'extracted':>9} {'n':>3} {'control':>9} {args.strength:>7} "
          f"{'delta':>9} {'sd':>8} {'t':>7} {'p':>10} {'agree':>8}")
    for L in layers:
        c = np.array([runs[L][k][args.control][metric] for k in labels])
        t = np.array([runs[L][k][args.strength][metric] for k in labels])
        ag = np.array([runs[L][k][args.strength]["token_agreement"] for k in labels])
        d = t - c
        tt, pp = stats.ttest_rel(t, c)
        data[L] = t
        print(f"  L{L:<8} {n:>3} {c.mean():9.4f} {t.mean():7.4f} "
              f"{d.mean():+9.4f} {d.std(ddof=1):8.4f} {tt:7.2f} {pp:10.2e} "
              f"{ag.mean():8.4f}")

    # Every control should be inert. If one is not, the ordering below
    # would be about a broken run rather than about extraction depth.
    worst = max(abs(np.mean([runs[L][k][args.control][metric] for k in labels]))
                for L in layers)
    print()
    print(f"  largest control mean: {worst:.2e}"
          + ("  (inert, as it should be)" if worst < 1e-9
             else "  ** NON-ZERO — do not read the ordering below **"))

    print()
    print("  " + "-" * 68)
    m = np.stack([data[L] for L in layers])
    stat, p = stats.friedmanchisquare(*m)
    print(f"  Friedman across {len(layers)} extraction layers: "
          f"chi2={stat:.2f}  p={p:.2e}")
    print()
    print("  pairwise paired tests:")
    for a, b in itertools.combinations(layers, 2):
        d = data[b] - data[a]
        tt, pp = stats.ttest_rel(data[b], data[a])
        print(f"    L{b:<3} - L{a:<3} {d.mean():+.4f}   t={tt:6.2f}  p={pp:.2e}")

    lo, hi = layers[0], layers[-1]
    ratio = data[hi].mean() / data[lo].mean() if data[lo].mean() else float("nan")
    print()
    print(f"  {metric} at L{hi} is {ratio:.2f}x the value at L{lo}, with the "
          f"injection layer held fixed at L{args.inject_at}.")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "n_problems": n, "inject_at": args.inject_at,
            "strength": args.strength, "control": args.control,
            "metric": metric,
            "per_layer": {str(L): {
                "mean": float(data[L].mean()),
                "sd": float(data[L].std(ddof=1)),
            } for L in layers},
            "friedman_p": float(p),
            "problems": labels,
        }, indent=2))
        print(f"\nwrote {out}")
    return 0


def cli():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dir", default="/tmp/iv_ext")
    ap.add_argument("--metric", default="mean_logit_kl")
    ap.add_argument("--control", type=float, default=0.0)
    ap.add_argument("--strength", type=float, default=0.2)
    ap.add_argument("--inject-at", type=int, default=20)
    ap.add_argument("--out", default=None)
    return main(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(cli())
