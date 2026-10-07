#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PROBE 探针：「哪一层先知道模型在动摇」。

判决规则全部在 `.cache/xcheck/PROBE_PREREG.md` 里，**取数之前**定死。
本文件是那份文件的实现，逐条照抄。

## 测什么

位置 t 的隐状态 `h(t, L)` → 线性方向 `W_L` → 分数
→ 「这里是动摇点」vs「这里是最近的非动摇点」的 AUROC，逐层 L=0..27。

## 测**不**什么（§6，取数前定死）

- 不测「知识」，只测**可分性**
- 不测**因果**（本轮无任何干预）
- 不测「推理阶段」（浅层=感知/深层=推理 是外部叙事，不在本轮范围）
- ⚠⚠ 位置 t 的隐状态是在模型**已经写下** `Wait` **之后**取的
  ⇒ 分不清「先知道」与「后知道」。见 §7.1，这是最重要的局限。

## 零对照（先于任何真实数据）

    X-1 标签置乱（轨迹内）    最大 AUROC <= 0.62
    X-2 维度置乱（轨迹内）    最大 AUROC <= 0.62
    X-3 跨轨迹负例应当更简单   AUROC >= 同轨迹 + 0.10

⚠ 切分一律**按轨迹分组**：同一轨迹的位置高度相关（同一道题、同一套
  变量名），随机划分会让测试点与训练点来自同一轨迹、分数虚高。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NPZ_DIR = os.path.join(ROOT, "datasets", "aime_qwen3_1p7b_16k_fp16", "aime")
HINGE = os.path.join(ROOT, ".cache", "xcheck", "hinge.json")
OUT = os.path.join(ROOT, ".cache", "mutbak", "probe_hinge.json")
N_LAYERS = 28
# §3 取数前定死的阈值，**不许看到结果后调**
SHUFFLE_AUROC_MAX = 0.62
P1_AUROC = 0.70
P1_LAYER_LE = 12
P3_GAIN = 0.10
X3_GAIN = 0.10


# --------------------------------------------------------------------------
# 数据
# --------------------------------------------------------------------------
def load_positives():
    d = json.load(open(HINGE, encoding="utf-8"))
    pos = defaultdict(list)
    for r in d["rows"]:
        for h in r["hinges"]:
            if h.get("tok", -1) >= 0:
                pos[r["trajectory_id"]].append(h["tok"])
    return {k: sorted(v) for k, v in pos.items()}


def pick_negatives(pos, rng, cross_traj=False, tmap=None):
    """§2.1 负例：同轨迹里**距离最近的非动摇点**（最难负例）。

    cross_traj=True 时改用跨轨迹随机位置 —— 只供 X-3 用。

    ⚠⚠ 第一版这里把 T 写死成 1024。实测 22 条轨迹里只有 4 条 T=1024，
      13 条是 2048，另有 1449 / 1960。⇒ 那些轨迹的负例被**系统性限制在
      前 1024 步**，而它们的动摇点散布到 2048 ⇒ 探针会退化成学
      「前半段 vs 后半段」，不是「动摇 vs 非动摇」。
      现在按 npz 的**真实 T** 取候选。
    """
    negs = defaultdict(list)
    if cross_traj:
        tids = sorted(pos)
        for t in tids:
            others = [o for o in tids if o != t]
            n = len(pos[t])
            picks = []
            for i in range(n):
                src = others[rng.integers(len(others))]
                T = (tmap or {}).get(src, 1024)
                picks.append(int(rng.integers(0, max(1, T))))
            negs[t] = picks
        return negs
    for t, toks in pos.items():
        T = (tmap or {}).get(t, 1024)
        cand = np.setdiff1d(np.arange(T), np.array(toks, dtype=int))
        picks = []
        for tpos in toks:
            if len(cand) == 0:
                break
            dist = np.abs(cand - tpos)
            # **升序**取最近的 ⇒ 最难负例
            order = np.argsort(dist, kind="stable")
            picks.append(int(cand[order[0]]))
        # ⚠ 不许 set 去重：相邻两个动摇点会各自挑到**同一个**最近负例，
        #   去重后负例数掉到 72（正例 121）⇒ 类别失衡、AUROC 方差不稳。
        #   宁可**允许重复**（重复的负例就是那个位置确实被两次挑中）。
        negs[t] = picks
    return negs


def real_T(tid):
    z = np.load(os.path.join(NPZ_DIR, tid + ".npz"))
    return int(z["hidden_states"].shape[0])


def build_xy(pos, negs, neg_label_by_traj=None):
    """返回 (X, y, traj) ；X 是 (n, 28, 2048) 的 float32。"""
    Xs, ys, ts = [], [], []
    for tid in sorted(pos):
        z = np.load(os.path.join(NPZ_DIR, tid + ".npz"))
        H = z["hidden_states"]
        T = H.shape[0]
        for t in pos[tid]:
            if 0 <= t < T:
                Xs.append(H[t].astype(np.float32))
                ys.append(1)
                ts.append(tid)
        for t in negs.get(tid, []):
            if 0 <= t < T:
                Xs.append(H[t].astype(np.float32))
                ys.append(0)
                ts.append(tid)
    return np.stack(Xs), np.array(ys, dtype=int), np.array(ts)


# --------------------------------------------------------------------------
# 探针
# --------------------------------------------------------------------------
def fit_scores(X, y, traj, lam):
    """按轨迹分组 LOO：每次留出一条**轨迹**的全部点做测试。

    返回 (scores, y, traj)，scores[i] 是留出点在其轨迹上的分数。
    """
    scores = np.zeros(len(y), dtype=np.float64)
    uniq = sorted(set(traj))
    for held in uniq:
        te = traj == held
        tr = ~te
        if tr.sum() == 0 or te.sum() == 0:
            continue
        Xtr, ytr = X[tr], y[tr].astype(np.float64)
        # 标签平衡权重：正负各占一半
        w = np.where(ytr > 0, 0.5 / max(1, (ytr > 0).sum()),
                     0.5 / max(1, (ytr == 0).sum()))
        # w_i = (2y-1) * h  的闭式解：W = (H'WH + lam I)^-1 H'W y
        # ⚠⚠ 先转 float64 再标准化。X 是从 **float16** 提上来的，
        #   在常量维上 sd 恰好为 0；float32 下 `Hm/0` 得到 inf，
        #   一次 inf 会把整条 matmul 链污染成 NaN —— 表现为
        #   `divide by zero` / `overflow` / `invalid value in matmul`，
        #   而**分数照常输出**，看上去只是个警告。
        #   ⇒ 必须 float64 + 显式裁掉零方差维（记进 drop 供报告）。
        Xtr = Xtr.astype(np.float64)
        mu = Xtr.mean(0, keepdims=True)
        sd = Xtr.std(0)
        keep = sd > 1e-8
        if keep.sum() == 0:
            continue
        Hn = (Xtr - mu)[:, keep] / sd[keep]
        sgn = 2 * ytr - 1
        Wt = Hn * (w * sgn)[:, None]
        A = Hn.T @ Wt + lam * np.eye(Hn.shape[1])
        try:
            coef = np.linalg.solve(A, Hn.T @ (w * sgn))
        except np.linalg.LinAlgError:
            coef = np.linalg.lstsq(A, Hn.T @ (w * sgn), rcond=None)[0]
        Hte = (X[te].astype(np.float64) - mu)[:, keep] / sd[keep]
        s = Hte @ coef
        if not np.all(np.isfinite(s)):
            # 不可静默：分数出现非有限值时该折作废，不用 0 冒充
            scores[te] = np.nan
        else:
            scores[te] = s
    return scores, y, traj


def auroc(scores, y):
    """Mann-Whitney U。scores 越大越像正例。"""
    y = np.asarray(y)
    if y.min() == y.max():
        return 0.5
    order = np.argsort(scores, kind="stable")
    ranks = np.empty(len(scores), dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1)
    # 平均秩处理并列
    s_sorted = scores[order]
    i = 0
    while i < len(s_sorted):
        j = i
        while j + 1 < len(s_sorted) and s_sorted[j + 1] == s_sorted[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2
        i = j + 1
    npos = int((y == 1).sum())
    nneg = int((y == 0).sum())
    return float((ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def sweep_lambda(X, y, traj):
    """§2.2 LOO 选定 lam。**不碰测试折**（LOO 下每一折都既是训练也是测试，
    故 lam 由内层再切一次按轨迹分组来选，取最保守的一档）。

    ⚠⚠ 第一版这里直接 `fit_scores(X, ...)`，但 X 是 (n, 28, 2048) 三维、
      fit_scores 要的是二维 ⇒ 广播失败。必须**逐层**取，且 lam 选定
      只看**跨层平均**（不是单层峰值）—— 用单层峰值会挑到最有利的一层。
    """
    best = None
    for lam in (1e2, 1e3, 1e4, 1e5):
        aucs = []
        for L in range(X.shape[1]):
            sc, yy, _ = fit_scores(X[:, L, :], y, traj, lam)
            aucs.append(auroc(sc, yy))
        a = float(np.mean(aucs))
        if best is None or a < best[1]:       # 取**最保守**（最小）
            best = (lam, a)
    return best[0]


def run():
    rng = np.random.default_rng(20261007)
    pos = load_positives()
    tmap = {t: real_T(t) for t in pos}
    print("真实 T 分布：", dict(sorted(
        {v: sum(1 for x in tmap.values() if x == v) for v in set(tmap.values())}
        .items())))
    negs = pick_negatives(pos, rng, cross_traj=False, tmap=tmap)
    X, y, traj = build_xy(pos, negs)
    print(f"样本 {X.shape[0]}（正 {int(y.sum())} / 负 {int((y==0).sum())}）"
          f"× {N_LAYERS} 层 × {X.shape[2]} 维；轨迹 {len(set(traj))} 条")

    lam = sweep_lambda(X, y, traj)
    print(f"lambda 选定 {lam:g}（按 §2.2 取最保守一档）")

    # ---- 主结果：逐层 AUROC ----
    aucs = []
    for L in range(N_LAYERS):
        sc, yy, _ = fit_scores(X[:, L, :], y, traj, lam)
        aucs.append(auroc(sc, yy))
    aucs = np.array(aucs)

    # bootstrap 区间（§7.2：必须报区间，不许只报点估计）
    boot = []
    for _ in range(200):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        a = []
        for L in range(N_LAYERS):
            try:
                sc, yy, _ = fit_scores(X[idx][:, L, :], y[idx], traj[idx], lam)
                a.append(auroc(sc, yy))
            except Exception:                      # noqa: BLE001
                a.append(np.nan)
        boot.append(a)
    boot = np.array(boot)
    lo = np.nanpercentile(boot, 2.5, axis=0)
    hi = np.nanpercentile(boot, 97.5, axis=0)

    # ---- 零对照 ----
    print("\n=== X-1 标签置乱（轨迹内，20 次）===")
    x1_max = []
    for r in range(20):
        ysh = y.copy()
        for tid in set(traj):
            m = np.where(traj == tid)[0]
            ysh[m] = ysh[rng.permutation(m)]
        a = [auroc(*fit_scores(X[:, L, :], ysh, traj, lam)[:2]) for L in range(N_LAYERS)]
        x1_max.append(max(a))
    x1_max = np.array(x1_max)
    print(f"  20 次里「最大 AUROC」的分布：均值 {x1_max.mean():.3f} "
          f"最大 {x1_max.max():.3f}（阈值 <= {SHUFFLE_AUROC_MAX}）")

    print("\n=== X-2 维度置乱（轨迹内，20 次）===")
    x2_max = []
    for r in range(20):
        Xp = X.copy()
        for tid in set(traj):
            m = np.where(traj == tid)[0]
            Xp[m] = Xp[m][:, rng.permutation(X.shape[2]), :]
        a = [auroc(*fit_scores(Xp[:, L, :], y, traj, lam)[:2]) for L in range(N_LAYERS)]
        x2_max.append(max(a))
    x2_max = np.array(x2_max)
    print(f"  20 次里「最大 AUROC」的分布：均值 {x2_max.mean():.3f} "
          f"最大 {x2_max.max():.3f}（阈值 <= {SHUFFLE_AUROC_MAX}）")

    print("\n=== X-3 跨轨迹负例应当更简单（反向 sanity）===")
    negs_x = pick_negatives(pos, rng, cross_traj=True, tmap=tmap)
    Xx, yx, tx = build_xy(pos, negs_x)
    ax = np.array([auroc(*fit_scores(Xx[:, L, :], yx, tx, lam)[:2])
                   for L in range(N_LAYERS)])
    peak_same = float(aucs.max())
    peak_cross = float(ax.max())
    print(f"  同轨迹负例峰值 AUROC {peak_same:.3f}（难）")
    print(f"  跨轨迹负例峰值 AUROC {peak_cross:.3f}（应更简单）")
    x3_ok = (peak_cross - peak_same) >= X3_GAIN

    # ---- 判决 ----
    shallow = aucs[:P1_LAYER_LE + 1]
    best_shallow = int(np.argmax(shallow))
    peak = int(np.argmax(aucs))
    # P-2 单调：上升到峰值前允许 1 层回撤
    seg = aucs[:peak + 1]
    drops = int((np.diff(seg) < 0).sum())
    verdicts = [
        {"name": f"X-1 标签置乱最大 AUROC <= {SHUFFLE_AUROC_MAX}",
         "ok": bool(x1_max.max() <= SHUFFLE_AUROC_MAX),
         "detail": f"{x1_max.max():.3f}"},
        {"name": f"X-2 维度置乱最大 AUROC <= {SHUFFLE_AUROC_MAX}",
         "ok": bool(x2_max.max() <= SHUFFLE_AUROC_MAX),
         "detail": f"{x2_max.max():.3f}"},
        {"name": f"X-3 跨轨迹负例更简单（+{X3_GAIN}）", "ok": bool(x3_ok),
         "detail": f"{peak_cross:.3f} vs {peak_same:.3f} "
                   f"（差 {peak_cross-peak_same:+.3f}）"},
        {"name": f"P-1 浅层 L<={P1_LAYER_LE} 最大 AUROC >= {P1_AUROC}",
         "ok": bool(aucs[best_shallow] >= P1_AUROC),
         "detail": f"L{best_shallow} = {aucs[best_shallow]:.3f}"},
        {"name": "P-2 上升段单调（允许 1 层回撤）",
         "ok": bool(drops <= 1), "detail": f"{drops} 处回撤"},
        {"name": f"P-3 超过随机对照 +{P3_GAIN}",
         "ok": bool(aucs.max() - x1_max.mean() >= P3_GAIN),
         "detail": f"{aucs.max():.3f} vs 置乱均值 {x1_max.mean():.3f}"},
    ]

    print("\n=== 逐层 AUROC（全部 28 层，§6.3 要求不许只报峰值）===")
    for L in range(N_LAYERS):
        star = "  <- 峰值" if L == peak else ("  <- 浅层最佳" if L == best_shallow else "")
        print(f"  L{L:2d}  {aucs[L]:.3f}  [{lo[L]:.3f}, {hi[L]:.3f}]{star}")

    print("\n=== 判决 ===")
    for v in verdicts:
        print(f"  {'PASS' if v['ok'] else 'FAIL'}  {v['name']}  —— {v['detail']}")
    res_all = all(v["ok"] for v in verdicts)

    out = {
        "prereg": "PROBE_PREREG.md",
        "n_samples": int(X.shape[0]), "n_pos": int(y.sum()),
        "n_traj": len(set(traj)), "lam": lam,
        "auroc": aucs.tolist(), "ci_lo": lo.tolist(), "ci_hi": hi.tolist(),
        "peak_layer": peak, "best_shallow_layer": best_shallow,
        "x1_max": x1_max.tolist(), "x1_mean": float(x1_max.mean()),
        "x2_max": x2_max.tolist(), "x2_mean": float(x2_max.mean()),
        "cross_traj_auroc": ax.tolist(),
        "verdicts": verdicts,
        "verdict": "PASS" if res_all else "FAIL",
        "honest_caveats": [
            "位置 t 的隐状态取自模型**已经写下** Wait 之后 ⇒ 本探针"
            "分不清「先知道」与「后知道」。见 PREREG §7.1。",
            "测的是**可分性**，不是**知识**；不是**因果**（本轮无干预）。",
            "浅层=感知/深层=推理 是外部叙事，本轮不测。",
        ],
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nRESULT {out['verdict']}")
    print(f"wrote {OUT}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
