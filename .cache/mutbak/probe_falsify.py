#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""伪信号证伪：那 0.94 的 AUROC 到底在测「动摇」还是测**别的**？

现象：`probe_hinge_layers.py` 报出 L0..L27 全部 AUROC ≈ 0.93–0.97，
峰值 L6 = 0.972，浅层最大 0.972 ⇒ 表面上是「浅层就知道」。

⚠ 但正例与负例只差 **1 个 token**（§2.1 取「最近的非动摇点」），
  实测两者隐状态的相对距离只有 0.41–1.49 —— 几乎不相关。
  一个「几乎不相关的 2048 维对」被线性探针分到 0.94，
  这**太容易了**，可疑。

假说（三个，逐个证伪）：
  H-a **位置平凡性**：任何位置 vs 它的邻居都这么可分
       ⇒ 换成**随机位置对**也该有 0.9x
  H-b **轨迹可分性**：探针学的是「这条轨迹」而不是「动摇点」
       ⇒ 跨轨迹 LOO 已排除，但可再验：把正例换成**随机 token**，
         标签仍按「原动摇点所在轨迹」分配
  H-c **真的强信号**：以上都不成立

⚠ 判据：**若 H-a 成立**（随机位置对也 ~0.9x），那 PROBE 的
  「最近邻负例」设计就是**恒绿判据**——它测的是位置平凡性。
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


def pairs_random(rng, pos, tmap):
    """H-a：正例 = 随机 token；负例 = 它的最近邻（**不含**任何位置偏好）。"""
    pr, nr = {}, {}
    for t, toks in pos.items():
        T = tmap[t]
        rs = rng.integers(0, T, len(toks))
        pr[t] = [int(x) for x in rs]
        nr[t] = []
        for x in rs:
            cand = np.setdiff1d(np.arange(T), np.array([x]))
            nr[t].append(int(cand[np.argmin(np.abs(cand - x))]))
    return pr, nr


def pairs_relabeled(rng, pos, tmap):
    """H-b：正例 = 随机 token，但**轨迹标签**照旧（检验是否只学到轨迹）。"""
    return pairs_random(rng, pos, tmap)


def main() -> int:
    rng = np.random.default_rng(20261007)
    pos = P.load_positives()
    tmap = {t: P.real_T(t) for t in pos}

    def curve(pr, nr, tag):
        X, y, traj = P.build_xy(pr, nr)
        a = np.array([P.auroc(*P.fit_scores(X[:, L, :], y, traj, LAM)[:2])
                      for L in range(N_LAYERS)])
        print(f"\n--- {tag} ---")
        print(f"  样本 {X.shape[0]}（正 {int(y.sum())}） 峰值 L{a.argmax()} = {a.max():.3f}"
              f"  浅层(<=12)最大 {a[:13].max():.3f}")
        print("  " + " ".join(f"{v:.2f}" for v in a))
        return a

    # 真：摇动点 vs 最近邻
    negr = P.pick_negatives(pos, rng, tmap=tmap)
    a_real = curve(pos, negr, "真摇动点 vs 最近邻（当前设计）")

    # H-a：随机 token vs 它的最近邻
    pr, nr = pairs_random(rng, pos, tmap)
    a_rand = curve(pr, nr, "H-a 随机 token vs 最近邻（应当**也**很高）")

    # H-b：负例取**远**的（跨半个轨迹）
    negr_far = {}
    for t, toks in pos.items():
        T = tmap[t]
        cand = np.setdiff1d(np.arange(T), np.array(toks, dtype=int))
        picks = []
        for x in toks:
            far = cand[np.argsort(-np.abs(cand - x), kind="stable")]
            picks.append(int(far[0]))
        negr_far[t] = picks
    a_far = curve(pos, negr_far, "H-b 摇动点 vs **最远**的非摇动点")

    print("\n=== 结论 ===")
    print(f"  真设计 峰值 {a_real.max():.3f}")
    print(f"  随机对照峰值 {a_rand.max():.3f}")
    if a_rand.max() >= a_real.max() - 0.02:
        print("\n✗ H-a 成立 ⇒ 「随机 token vs 最近邻」也能分到同样高。")
        print("  ⇒ 那 0.94 测的是**相邻位置可分**这个平凡事实，**不是**「动摇」。")
        print("  ⇒ PROBE 的「最近邻负例」是**恒绿判据**，必须换设计。")
        return 1
    print("\n△ 随机对照明显更低 ⇒ 最近邻负例不是唯一解释，继续查 H-b。")
    if a_far.max() > a_real.max() + 0.02:
        print(f"  远负例更容易分（{a_far.max():.3f} > {a_real.max():.3f}）"
              "⇒ 难度确实来自近邻，但近邻近到**不可分**是本设计的上限。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())