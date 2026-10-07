#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 PROBE 选负例：既要**不太近**（平凡）也不要**太远**（位置偏差）。

⚠ 前一版把两个混淆混在一起，两个读数都不可单独解释：
  · 最近邻负例（|Δt|=1）    → AUROC 0.972，但正负隐状态相对距离只有
                              0.41–1.49，且随机位置对也有 0.544
                              ⇒ 难度被「相邻」抬高
  · 最远负例（跨整个轨迹）  → AUROC **1.000**，L0 就是
                              ⇒ 任务退化成「这是轨迹的哪一半」

所以需要一条**距离扫描**：负例固定在距动摇点 Δ 个 token 处
（Δ = 1, 3, 5, 10, 20, 50, 100, 200, 500），看 AUROC 怎么随 Δ 变。

判读（**取数前定死**）：
  · 若曲线在某个 Δ 之后**趋于平稳**，那个平台值就是「剔除了距离效应后」
    的真实可分度；
  · 若在 Δ=1 最高、随 Δ 单调下降到 0.5，说明近邻处的 0.97 里
    **混着距离效应**，不能当「动摇的信号」用；
  · 任何读数都必须带上它对应的 Δ，不许只报最好看的那个。
"""
from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, ".cache", "xcheck"))
import probe_hinge_layers as P  # noqa: E402

N_LAYERS = 28
LAM = 1e4
DELTAS = (1, 3, 5, 10, 20, 50, 100, 200, 500)


def pairs_at_delta(pos, tmap, delta, rng):
    """负例固定在 t+delta（或 t-delta，越界则换边），必须不是动摇点。"""
    pr, nr = {}, {}
    for t, toks in pos.items():
        T = tmap[t]
        ts = set(toks)
        ps, ns = [], []
        for x in toks:
            ps.append(x)
            cands = [x + delta, x - delta]
            pick = None
            for c in cands:
                if 0 <= c < T and c not in ts:
                    pick = c
                    break
            if pick is None:
                # 该 Δ 不可用：跳过这个正例
                ps.pop()
                continue
            ns.append(pick)
        if ps:
            pr[t] = ps
            nr[t] = ns
    return pr, nr


def main() -> int:
    rng = np.random.default_rng(20261007)
    pos = P.load_positives()
    tmap = {t: P.real_T(t) for t in pos}

    curves = {}
    print(f"{'Δ':>5s} {'n':>5s} {'峰值层':>6s} {'峰值':>6s} {'浅层max':>8s}  逐层")
    for d in DELTAS:
        pr, nr = pairs_at_delta(pos, tmap, d, rng)
        if not pr:
            continue
        X, y, traj = P.build_xy(pr, nr)
        a = np.array([P.auroc(*P.fit_scores(X[:, L, :], y, traj, LAM)[:2])
                      for L in range(N_LAYERS)])
        curves[d] = a
        print(f"{d:>5d} {X.shape[0]:>5d} {a.argmax():>6d} {a.max():>6.3f} "
              f"{a[:13].max():>8.3f}  " +
              " ".join(f"{v:.2f}" for v in a[:14]))

    print("\n=== 逐 Δ 的峰值（只报 3 个数，必须连 Δ 一起引用）===")
    for d, a in curves.items():
        print(f"  Δ={d:<4d} 峰值 {a.max():.3f} @L{a.argmax():<3d} "
              f"浅层max {a[:13].max():.3f}")

    ds = sorted(curves)
    peaks = [curves[d].max() for d in ds]
    print("\n=== 判读（取数前定死的三条）===")
    # 1) 单调性
    mono = all(peaks[i] >= peaks[i + 1] - 0.01 for i in range(len(peaks) - 1))
    print(f"  1) 峰值随 Δ 单调不升：{'是' if mono else '否'}")
    # 2) 平台
    last3 = peaks[-3:]
    plateau = (max(last3) - min(last3)) < 0.05
    print(f"  2) 最后三个 Δ 构成平台（极差<0.05）：{'是' if plateau else '否'}"
          f"  极差 {max(last3)-min(last3):.3f}")
    # 3) 落到随机水平
    print(f"  3) 随机位置对基线（前一版量到）≈ 0.544")
    lo = min(peaks)
    print(f"     所有 Δ 的最低峰值 {lo:.3f}"
          f"（{'仍高于基线' if lo > 0.60 else '已落到基线附近'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())