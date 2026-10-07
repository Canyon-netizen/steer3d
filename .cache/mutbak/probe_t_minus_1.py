#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PROBE 修订 2：用 `h(t-1)` 绕开「已经写下 Wait」这个致命局限。

## 为什么必须做这一支

PROBE_PREREG §7.1 写死了本设计**最重要的局限**：

> 位置 t 的隐状态是在模型**已经写下** `Wait` 之后取的。
> ⇒ 分不清「先知道」与「后知道」。

实测 token（`probe_t_minus_1.py` 的诊断）证实了这件事有多严重：
动摇点 t 处的 token 就是 `Wait` / `no` / `let` 这些**标记词本身**。
探针在 h(t) 上分出 0.97，很大程度是在读
「这个位置的当前 token 是不是标记词」——**这是平凡的**。

## 怎么绕开

改取 **`h(t-1)`**：位置 t-1 处的 token 是
`30`（句号）/ `382`（空格）/ `11`（逗号）这类，
**标记词一个都还没写出来**。

⇒ 若在 h(t-1) 上仍有可分信号，那才是真的「**在写下之前**就已经有信息」。

⚠⚠ 但要诚实：h(t-1) 仍然**在同一条轨迹、同一个上下文**里，
且 t-1 常常就是句号位置。⇒ 必须配零对照：
  · **t-2 / t-3**（更早，且离标记词更远）
  · **随机位置的 t-1**（同样取「某位置的前一个 token」，
    但那个位置不是动摇点）—— 排除「句号位置本来就可分」
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, ".cache", "xcheck"))
import probe_hinge_layers as P  # noqa: E402

N_LAYERS = 28
LAM = 1e4
OFFSETS = (0, 1, 2, 3)          # 0 = h(t) 本身（已写下）；1..3 = 更早
DELTAS = (1, 5, 20)             # 负例到正例的距离


def load_pos():
    d = json.load(open(P.HINGE, encoding="utf-8"))
    pos = {}
    for r in d["rows"]:
        ts = [h["tok"] for h in r["hinges"] if h.get("tok", -1) >= 0]
        if ts:
            pos[r["trajectory_id"]] = sorted(ts)
    return pos


def build(pos, tmap, off, delta, rng, shuffle_pos=False):
    """正例取 h(t - off)，负例取 h(n - off)，|t - n| = delta。"""
    pr, nr = {}, {}
    for t, toks in pos.items():
        T = tmap[t]
        if shuffle_pos:
            cand_pos = [int(x) for x in rng.integers(off + 1, T, len(toks))]
        else:
            cand_pos = [x + off for x in toks if x + off < T]
        ts = set(toks)
        ps, ns = [], []
        for x in cand_pos:
            best = None
            for c in (x + delta, x - delta):
                if 0 <= c < T and c not in ts and c - off >= 0:
                    best = c
                    break
            if best is None:
                continue
            ps.append(x)
            ns.append(best)
        if ps:
            pr[t] = ps
            nr[t] = ns
    return P.build_xy(pr, nr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=0, help="bootstrap 次数（0=不跑）")
    a = ap.parse_args()
    rng = np.random.default_rng(20261007)
    pos = load_pos()
    tmap = {t: P.real_T(t) for t in pos}

    res = {}
    print("=== 逐层 AUROC：正例取 h(t-off)，负例距离 Δ ===")
    print("    off=0 是「已写下 Wait 之后」；off>=1 是「写下之前」\n")
    hdr = f"  {'off':>4s} {'Δ':>4s} {'n':>5s} {'峰值':>6s} {'@层':>4s} {'浅层max':>8s}  前 10 层"
    print(hdr)
    for off in OFFSETS:
        for d in DELTAS:
            X, y, traj = build(pos, tmap, off, d, rng)
            if X.shape[0] < 20:
                print(f"  {off:>4d} {d:>4d}  样本不足 ({X.shape[0]})")
                continue
            a_ = np.array([P.auroc(*P.fit_scores(X[:, L, :], y, traj, LAM)[:2])
                           for L in range(N_LAYERS)])
            res[f"off{off}_d{d}"] = a_.tolist()
            print(f"  {off:>4d} {d:>4d} {X.shape[0]:>5d} {a_.max():>6.3f} "
                  f"{a_.argmax():>4d} {a_[:13].max():>8.3f}  " +
                  " ".join(f"{v:.2f}" for v in a_[:10]))

    print("\n=== 零对照：正例换成**随机位置**的 h(x-off) ===")
    print("  若 off>=1 的分数与随机位置无异 ⇒ 那不是「提前知道」，是位置平凡性")
    for off in (0, 1, 2):
        X, y, traj = build(pos, tmap, off, 5, rng, shuffle_pos=True)
        if X.shape[0] < 20:
            continue
        a_ = np.array([P.auroc(*P.fit_scores(X[:, L, :], y, traj, LAM)[:2])
                       for L in range(N_LAYERS)])
        res[f"ctrl_off{off}_d5"] = a_.tolist()
        print(f"  off={off} n={X.shape[0]:4d} 峰值 {a_.max():.3f} @L{a_.argmax()}")

    print("\n=== 判读（预登记 §6/§7 的边界，不许越界）===")
    for off in (0, 1, 2, 3):
        k = f"off{off}_d5"
        if k in res:
            print(f"  off={off}: 峰值 {max(res[k]):.3f}")
    print("\n  ⚠ 即使 off>=1 分数仍高，**也不能**说「模型提前知道」——")
    print("    h(t-1) 仍在同一上下文里，且 t-1 常是句号位置。")
    print("    只有当 off>=1 **显著高于**同 off 的随机位置对照，")
    print("    才能说「在写下标记词之前就有可分信号」。")
    out = os.path.join(ROOT, ".cache", "mutbak", "probe_offsets.json")
    json.dump(res, open(out, "w", encoding="utf-8"), indent=1)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())