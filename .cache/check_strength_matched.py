#!/usr/bin/env python3
"""Check the four pre-registered predictions in strength_matched_prediction.md.

Written before the strength-matched run produced anything, so that "0.6B's
Finding 14 differs from 1.7B's" has a falsifiable version instead of a
post-hoc one. Each prediction prints PASS / FAIL / (out of range) and the
measured value; nothing here is a pass/fail gate on the *conclusions*, only on
the experiment having produced what it was designed to produce.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
PRED = [
    # (label, lo, hi, unit)
    ("1 rel_shift 落在 1.7B 区间", 0.24, 0.40, ""),
    ("2 C4 随机翻转率", 0.15, 0.20, ""),
    ("3 随机方向翻转所需 α 中位", 0.60, 1.40, ""),
    ("4 '前缀更险' 题数", 3, 4, "/6"),
]


def load_common(prefix: Path):
    return json.loads(prefix.read_text())["problems"]


def near_miss_count(probs):
    """Finding 14's own criterion: the steered arm's closest call anywhere in
    the common prefix, versus the control margin at the divergence step."""
    n = 0
    for p in probs:
        rows = p["rows"]
        k = p["k"]
        pre = [r for r in rows if not r["is_divergence_step"]][:k]
        dv = [r for r in rows if r["is_divergence_step"]][0]
        n += min(r["margin_steered"] for r in pre) < dv["margin_control"]
    return n


def rel_shifts(paired: Path):
    out = []
    for npz in sorted(paired.glob("pair_*.npz")):
        rec = json.loads(npz.with_suffix(".json").read_text())
        k = int(rec["paired"]["n_common_prefix"])
        z = np.load(npz)
        c = z["control_last32"][k].astype(np.float32)
        s = z["steered_last32"][k].astype(np.float32)
        out.append(float(np.linalg.norm(s - c) / np.linalg.norm(c)))
    return out


def main():
    div = Path(sys.argv[1] if len(sys.argv) > 1 else REPO / ".cache/analysis/divergence_logits_0p6b_matched.json")
    pre = Path(sys.argv[2] if len(sys.argv) > 2 else REPO / ".cache/analysis/common_prefix_0p6b_matched.json")
    pairs = Path(sys.argv[3] if len(sys.argv) > 3 else REPO / ".cache/analysis/paired_0p6b_matched")
    for p in (div, pre):
        if not p.exists():
            print(f"缺 {p}；先跑 analyse_divergence_logits.py / analyse_common_prefix.py")
            return 1

    D = json.loads(div.read_text())
    probs = load_common(pre)
    rs = rel_shifts(pairs)
    c4h = sum(r["controls"]["C4_random"]["hits"] for r in D["problems"])
    c4n = sum(r["controls"]["C4_random"]["n"] for r in D["problems"])
    c4 = c4h / c4n
    alphas = [r["controls"]["C4_random"]["median_flip_alpha"] for r in D["problems"]
              if r["controls"]["C4_random"]["median_flip_alpha"] is not None]
    nm = near_miss_count(probs)

    measured = [(min(rs), max(rs)), (c4, c4), (min(alphas), max(alphas)), (nm, nm)]
    print(f"{'预测':<34} {'实测':>16}  判定")
    print("-" * 66)
    for (label, lo, hi, unit), (a, b) in zip(PRED, measured):
        ok = lo <= a and b <= hi
        rng = f"{a:.3f} – {b:.3f}" if a != b else f"{a:.2f}{unit}"
        print(f"{label:<34} {rng:>16}  {'PASS' if ok else 'not in predicted range'}")
    print()
    print(f"C4 原始计数 {c4h}/{c4n}；α 中位 {sorted(alphas)}；rel_shift {['%.3f' % x for x in rs]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
