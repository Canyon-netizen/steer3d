#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 48 取数：L1「与方向无关」在自己的观测量上有没有被 c 检验过。

判据写在 `.cache/xcheck/R6_RERUN_PREREG.md` §48.1，**取数前**已单独提交并推送
（`a15beb3`）。本脚本只负责执行，不负责改判。

三件事：

· P1 逐层报 `Δc = max−min` 的 `cos_mean`，阈值 0.01（几何定：方向至少把 h
  转到差 0.6°）。有层 `Δc < 0.01` ⇒ 整体「不可判定」。
· W1 精确枚举 `(4!)^4 = 331,776` 个分块置换，算「破坏量残差对 c 无依赖」
  的零分布，报 `p_exact` 与 β 的 95% 区间。
· W2 复算 `safe_regime.direction_independent` 这个布尔的判定阈值是否**被记录**。

⚠️⚠️ 为什么置换是**分块**的：`cos_mean` 在同一层内跨 `strength` 不变
（方向与 h 都不随 s 变），所以正确的对称群是「每层内整体置换 4 个方向标签，
4 个强度随方向一起走」，空间 `24^4`。若改成逐行独立置换，等于假装方向与强度
独立 —— 而它们在同一层里共享同一个 c 标签，那会**高估**零分布的方差。

⚠️⚠️ 自由度：x 只有 **16 个不同取值**（4 层 × 4 方向），每个在 4 个强度上
重复 4 次。64 对不是 64 个独立样本。报告里必须按 16 个块说。
"""
from __future__ import annotations

import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend/public/latent/data"
LAW = DATA / "linearity_law.json"
OUT = Path(__file__).resolve().parent.parent / "mutbak/direction_gap.json"

# ---- 判据常量（取数前写死，见预登记 §48.1）---------------------------
P1_DC_MIN = 0.01        # 几何：方向至少要把 h 转到差 0.6°
W1_P_ALPHA = 0.01       # H1 被否的阈值

sys.path.insert(0, str(ROOT / ".cache/pylibs"))
import numpy as np  # noqa: E402


def selfcheck():
    """等式必须先推导再写。

    恒等：逐行去均值 OLS 的斜率 = Σ(x−x̄)(y−ȳ) / Σ(x−x̄)²。
    反向锚点：同一批数据上，先去均值再乘与直接用矩阵恒等式两条路径
    必须逐位相同；且分母（x 的行内平方和）**不依赖置换**，否则分块置换
    的零分布就不是同一个统计量的零分布。
    """
    rng = np.random.default_rng(7)
    y = rng.normal(size=(4, 4, 4))
    x = np.broadcast_to(rng.normal(size=(4, 1, 4)), (4, 4, 4)).copy()
    xd, yd = x - x.mean(2, keepdims=True), y - y.mean(2, keepdims=True)
    b = (xd * yd).sum() / (xd * xd).sum()
    # 路径二：FWL 形式，用 numpy 的 lstsq 显式拟合「16 个行哑变量 + x」，
    # 64 行对应 64 个 (l, s, d)。第一版这里按 16 行建 A，维度不匹配直接报错。
    rows = []
    for l in range(4):
        for s in range(4):
            for d in range(4):
                r = [0.0] * 16 + [x[l, s, d]]
                r[4 * l + s] = 1.0
                rows.append(r)
    A = np.array(rows)
    t = y.reshape(-1)
    b2 = float(np.linalg.lstsq(A, t, rcond=None)[0][16])
    assert abs(b - b2) < 1e-10, (b, b2)
    # 行内置换后，行内平方和不变 —— 但必须**先去均值再置换的逆过程**，
    # 即对原始 x 做行内置换，再去均值。直接置换已去均值的 xd 会让行均值不再为零，
    # Σxd² 自然变（第一版就是这么写的，断言红，方法没错）。
    xp = x[:, :, [1, 0, 2, 3]]
    xdp = xp - xp.mean(2, keepdims=True)
    assert abs((xd * xd).sum() - (xdp * xdp).sum()) < 1e-12, "行内置换改变了分母 ⇒ 置换群选错"
    return True


def main() -> int:
    selfcheck()
    law = json.loads(LAW.read_text(encoding="utf-8"))
    dirs = law["design"]["real_directions"]
    layers = list(law["design"]["layers"])
    strengths = list(law["design"]["strengths"])
    rows = {(r["layer"], r["strength"]): r for r in law["rows"]}

    # ---------- P1：c 真的被变过吗 ----------
    cos_by_layer = {}
    for L in layers:
        # cos_mean 在同一层内跨 strength 不变（方向与 h 都不随 s 变），所以取任一强度
        cos_by_layer[L] = [rows[(L, strengths[0])]["real"][d]["cos_mean"]
                           for d in dirs]
    dc = {str(L): max(v) - min(v) for L, v in cos_by_layer.items()}
    min_dc = min(dc.values())
    p1_ok = min_dc >= P1_DC_MIN

    # ---------- W1：破坏量残差 vs cos_mean，分块精确置换 ----------
    X = np.zeros((len(layers), len(strengths), len(dirs)))
    Y = np.zeros_like(X)
    for i, L in enumerate(layers):
        for j, s in enumerate(strengths):
            r = rows[(L, s)]
            for k, d in enumerate(dirs):
                X[i, j, k] = r["real"][d]["cos_mean"]
                Y[i, j, k] = r["real"][d]["dev_pct"] - r["real"][d]["pred_pct"]
    xd = X - X.mean(2, keepdims=True)
    yd = Y - Y.mean(2, keepdims=True)
    den = float((xd * xd).sum())

    perm4 = np.array(list(itertools.permutations(range(4))), dtype=np.int8)
    n_perm = perm4.shape[0] ** len(layers)          # 24^4 = 331776
    # 每个置换组合在每层取哪一个 4! 排列
    idx = np.arange(n_perm, dtype=np.int32)
    layer_perm = np.empty((len(layers), n_perm, len(dirs)), dtype=np.int8)
    for i in range(len(layers)):
        layer_perm[i] = perm4[(idx // (perm4.shape[0] ** (len(layers) - 1 - i)))
                               % perm4.shape[0]]

    num = np.zeros(n_perm, dtype=np.float64)
    for i in range(len(layers)):
        q = layer_perm[i]                              # (n_perm, 4) 方向标签
        # G[idx, d] = Σ_s yd[i, s, q[idx, d]] —— 逐行去均值后置换只动标签
        G = np.zeros((n_perm, len(dirs)), dtype=np.float64)
        for s in range(len(strengths)):
            G += yd[i][s][q]
        num += (xd[i][0][None, :] * G).sum(axis=1)
    beta = num / den
    beta_obs = float(beta[0])                         # idx 0 = 四层全取恒等
    assert abs(beta_obs - float((xd * yd).sum() / den)) < 1e-12, "恒等置换不等于直接算"
    ge = int((np.abs(beta) >= abs(beta_obs) - 1e-18).sum())
    p_exact = ge / n_perm
    lo, hi = np.quantile(beta, [0.025, 0.975])

    # ---------- W2：direction_independent 的阈值被记录了吗 ----------
    def has_threshold_key(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if re.search(r"threshold|tol|crit|pass|rule|spread_max|limit",
                             k, re.I) and not isinstance(v, bool):
                    return k
                r = has_threshold_key(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = has_threshold_key(v)
                if r:
                    return r
        return None
    thr_key = has_threshold_key(law)

    # ---------- W3：五个上游产物的生成器在仓库里存在吗 ----------
    ups = law_names = ["linearity_law", "readable_subspace", "heldout_readability",
                       "arm_asymmetry", "cot_texts"]
    skip = {".git", "node_modules", ".next", "dist", "__pycache__"}
    tracked_hits = {u: [] for u in ups}
    untracked_hits = {u: [] for u in ups}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip]
        rel = os.path.relpath(dirpath, ROOT)
        for fn in filenames:
            if not fn.endswith((".py", ".sh", ".ts", ".tsx")):
                continue
            fp = Path(dirpath) / fn
            try:
                txt = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for u in ups:
                if u not in txt:
                    continue
                # 「读这份产物」与「写这份产物」要分开：只有前者+写盘才算生成器
                reads = bool(re.search(rf"(read_text|json\.load|jload|open)\s*\([^)]*{u}",
                                       txt, re.S))
                writes = bool(re.search(rf"write_text|json\.dump|OUTPUT|OUT\b", txt))
                rec = f"{rel}/{fn}" + (" [读+写]" if (reads and writes) else " [仅读/引用]")
                if rel.startswith(".cache"):
                    untracked_hits[u].append(rec)
                else:
                    tracked_hits[u].append(rec)
    gen_found = {u: [h for h in tracked_hits[u] if "[读+写]" in h] for u in ups}

    verdict_w1 = ("H1 否决：存在 c 依赖" if p_exact < W1_P_ALPHA
                  else "未测出 c 依赖")
    verdict = ("不可判定（P1 有层无功效）" if not p1_ok else verdict_w1)

    res = {
        "schema": "steer3d.direction_gap/1",
        "prereg": "R6_RERUN_PREREG.md §48.1 @ a15beb3",
        "source": "frontend/public/latent/data/linearity_law.json",
        "P1": {"dc_min_required": P1_DC_MIN,
               "dc_by_layer": dc, "min_dc": min_dc,
               "every_layer_has_power": p1_ok},
        "W1": {"null": "破坏量残差对 cos_mean 无依赖",
               "x_distinct_values": len(layers) * len(dirs),
               "n_pairs": int(X.size),
               "n_blocks": len(layers) * len(dirs),
               "beta": beta_obs, "beta_ci95": [float(lo), float(hi)],
               "perm_space": int(n_perm), "p_exact_two_sided": p_exact,
               "alpha": W1_P_ALPHA, "verdict": verdict_w1},
        "W2": {"boolean_key": "direction_independent",
               "threshold_key_in_artifact": thr_key,
               "verdict": "口径不可复算" if thr_key is None else "阈值可查"},
        "W3": {"upstreams": ups,
               "generator_found": {u: gen_found[u] for u in ups},
               "n_generators_found": sum(len(v) for v in gen_found.values()),
               "tracked_refs": tracked_hits, "cache_refs": untracked_hits},
        "verdict_overall": verdict,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---------------- 打印 ----------------
    print(f"源: {LAW.relative_to(ROOT)}")
    print(f"方向: {dirs}")
    print("\n[P1] 每层 Δc = max−min 的 cos_mean   阈值 ≥ %s" % P1_DC_MIN)
    for L in layers:
        flag = "有功效" if dc[str(L)] >= P1_DC_MIN else "无功效"
        print(f"   L{L:<3} Δc={dc[str(L)]:.4f}  {flag}")
    print(f"   最小 Δc = {min_dc:.4f} ⇒ P1 {'通过' if p1_ok else '不通过'}")
    print("\n[W1] y = dev_pct − pred_pct, x = cos_mean")
    print(f"   x 不同取值 {len(layers)*len(dirs)} 个 / {int(X.size)} 对"
          f"（按 {len(layers)*len(dirs)} 个块计，不是 {int(X.size)} 个独立样本）")
    print(f"   β = {beta_obs:+.6e}   95% 区间 [{lo:+.6e}, {hi:+.6e}]")
    print(f"   置换空间 {n_perm:,}（精确枚举，无抽样误差）")
    print(f"   p_exact(双侧) = {p_exact:.6f}   α = {W1_P_ALPHA}")
    print(f"   ⇒ {verdict_w1}")
    print("\n[W2] direction_independent 的阈值是否记录在产物里:",
          thr_key if thr_key else "否 ⇒ 口径不可复算")
    print("\n[W3] 五个上游产物的生成器（被 git 跟踪的 .py/.sh/.ts/.tsx）")
    for u in ups:
        print(f"   {u+'.json':28} 生成器 {len(gen_found[u])} 个"
              f"  跟踪内引用 {len(tracked_hits[u])}  .cache 内 {len(untracked_hits[u])}")
    print(f"   ⇒ 仓库内生成器合计 {sum(len(v) for v in gen_found.values())} 个")
    print(f"\n[总判决] {verdict}")
    print(f"写出: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())