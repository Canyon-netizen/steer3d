#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""零对照读数的**显著性**检验。

⚠ 上一支量到：动摇点 85% 的首层在 L20+，随机位置 62%。
  差 23 个百分点看着不小，但：
  (1) 121 个样本，且**同一轨迹内不独立**（一条轨迹里的多个位置高度相关）
      —— 直接套二项检验会**高估显著性**；
  (2) 读法必须是「同一条轨迹上，动摇点 vs 随机点」的**配对**比较。

所以用**轨迹级配对**：每条轨迹算一个「动摇点 L20+ 占比」与
「随机点 L20+ 占比」，做配对检验（符号秩 / Wilcoxon）。
⚠ 若某条轨迹里随机点少于 4 个，比例噪声太大，单独标出来不参与。
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MUT = os.path.join(ROOT, ".cache", "mutbak")


def rows_of(path):
    d = json.load(open(path, encoding="utf-8"))
    out = {}
    for tr in d["trajectories"]:
        out[tr["id"]] = [s for s in tr["steps"] if s["first_layer_correct"] is not None]
    return out


def frac_late(steps, lo=20):
    if not steps:
        return None
    return sum(1 for s in steps if s["first_layer_correct"] >= lo) / len(steps)


def wilcoxon(diffs):
    """两-sided 符号秩近似（正态近似 + 连续性校正）。"""
    d = [x for x in diffs if abs(x) > 1e-12]
    n = len(d)
    if n == 0:
        return None, None, n
    pos = sum(1 for x in d if x > 0)
    ranks = {}
    for x in sorted(d, key=abs):
        ranks.setdefault(round(abs(x), 12), 0)
    # 平均秩
    order = sorted(d, key=abs)
    i = 0
    rsum = 0.0
    while i < len(order):
        j = i
        while j + 1 < len(order) and abs(order[j + 1]) == abs(order[i]):
            j += 1
        r = (i + j) / 2 + 1
        rsum += r * len(order[i:j + 1])
        i = j + 1
    mu = n * (n + 1) / 4
    var = n * (n + 1) * (2 * n + 1) / 24
    z = (rsum - mu) / (var ** 0.5) if var > 0 else 0.0
    # 两尾正态近似
    from math import erfc, sqrt
    p = erfc(abs(z) / sqrt(2))
    return z, p, n


def main() -> int:
    h = rows_of(os.path.join(MUT, "logit_lens_hinge.json"))
    r = rows_of(os.path.join(MUT, "logit_lens_random.json"))
    trajs = sorted(set(h) & set(r))

    print(f"{'轨迹':8s} {'动摇点':>12s} {'随机位':>12s} {'差':>8s}")
    diffs = []
    dropped = []
    for t in trajs:
        fh, fr = frac_late(h[t]), frac_late(r[t])
        if fh is None or fr is None:
            continue
        tag = ""
        if len(h[t]) < 4 or len(r[t]) < 4:
            tag = "  (样本少，不参与检验)"
            dropped.append(t)
        print(f"{t[5:9]:8s} {len(h[t]):5d} {fh*100:5.0f}% "
              f"{len(r[t]):5d} {fr*100:5.0f}% {100*(fh-fr):+7.1f}{tag}")
        if not tag:
            diffs.append(fh - fr)

    z, p, n = wilcoxon(diffs)
    print(f"\n参与检验的轨迹 {n} 条（剔除 {len(dropped)} 条样本过少的）")
    print(f"Wilcoxon 符号秩：z = {z:.3f}   p(两尾) ≈ {p:.4f}")
    mean = sum(diffs) / len(diffs)
    print(f"配对差均值 {mean*100:+.1f} 个百分点")
    if p < 0.01:
        print("\n✓ p < 0.01：动摇点确实比随机位置更晚才「定型」。")
    elif p < 0.05:
        print("\n△ p < 0.05：有偏移，量级不大。")
    else:
        print("\n✗ 不显著：读到的偏移可能只是噪声，**不许**当结论用。")

    print("\n=== 这个检验能说与不能说什么 ===")
    print("  能说：在这套 lens（末层 argmax 对齐 + float16 重建）下，动摇点上的")
    print("        token 直到更深的层才与最终 token 一致。")
    print("  不能说：模型「先在浅层知道错误、后在深层表达」——那需要探针，")
    print("        这里测的是 argmax 对齐，不是「知道」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())