#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 49 取数：修正口径后的 c 依赖检验，**先算功效再判决**。

判据写在 `.cache/xcheck/R6_RERUN_PREREG.md` §49.1，取数前已单独提交并推送
（`24432ef`）。本脚本只执行，不改判。

修订 48 的教训：它拿到 `p_exact = 3.0×10⁻⁶` 就当成判决，却没先问
「这个判据测得出我要找的东西吗」。§48.4.7 已经写明待检出的效应量与噪声同量级。
本脚本第一件事算 **δ\\***（最小可检出效应），第二件事才算 p。

## 四条口径缺陷的修正，对应 R1/R2

| 版本 | 行范围 | y | 用途 |
|---|---|---|---|
| a | 16 行 | `dev − pred`（百分点） | §48.4.1 那个，只作对照 |
| b | 12 行（s ≤ safe_max） | `dev − pred` | 只修口径 |
| c | 16 行 | `(dev−pred)/pred` | 只修量纲 |
| **d** | **12 行** | **`(dev−pred)/pred`** | **判决只看这个** |

## ⚠ 零分布不是 β 的平移

注入 `y' = y + δ·(x − x̄)` 之后，置换零分布**必须重新枚举**。
第一版想当然以为「β 只是平移了 δ」—— 不对：置换把 x 的标签也换了，
`Σ_d xd[d]·(x[π(d)] − x̄)` 依赖 π，只有 π = 恒等时它才等于 `Σ xd²`。
本脚本对每个 δ 都重跑一遍完整枚举。
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend/public/latent/data"
LAW = DATA / "linearity_law.json"
OUT = Path(__file__).resolve().parent.parent / "mutbak/direction_power.json"

ALPHA = 0.01          # R3 的拒绝阈值，与 §48.1 W1 一致
BISECT_TOL = 1e-5     # δ* 的二分收敛精度
DELTA_CAP = 0.5       # δ 的搜索上界（y 是相对偏差，0.5 = 50% 已远超任何合理效应）

sys.path.insert(0, str(ROOT / ".cache/pylibs"))
import numpy as np  # noqa: E402


def selfcheck() -> None:
    """等式先推导再写。

    **注入不破坏行内零均值**：`Σ_d (x[d] − x̄) = 0` ⇒ 注入后行均值不变
    ⇒ 「行固定效应」口径没有被注入破坏。若这条不成立，δ 的大小会同时
    改变行内对比和行间对比，注入就不再是一个单轴效应。

    **恒等置换 ⇒ 注入项的斜率恰为 1**：`Σ_d xd[d]·(x[d] − x̄) = Σ_d xd[d]·x[d]`
    （因 `Σ_d xd[d] = 0`）`= Σ_d (x[d]−x̄)² = den` ⇒ β(δ) − β(0) = δ。
    这给了 δ\* 一个闭式起点，但**零分布仍须重算**（见模块 docstring）。
    """
    rng = np.random.default_rng(11)
    x = rng.normal(size=(4, 4, 4))
    y = rng.normal(size=(4, 4, 4))
    xd = x - x.mean(2, keepdims=True)
    yd = y - y.mean(2, keepdims=True)
    den = float((xd * xd).sum())
    b0 = float((xd * yd).sum()) / den
    for delta in (0.05, 0.2):
        yd2 = yd + delta * xd
        assert abs(yd2.mean(2).max()) < 1e-12, "注入破坏了行内零均值"
        b1 = float((xd * yd2).sum()) / den
        assert abs((b1 - b0) - delta) < 1e-12, "β 对 δ 的斜率不是 1"
    # 非恒等置换下注入项的斜率**不等于** 1 —— 这正是不能假设零分布平移的理由
    xd_p = xd[:, :, [1, 0, 2, 3]]
    slope = float((xd * xd_p).sum()) / den
    assert abs(slope - 1.0) > 1e-3, "非恒等置换的注入斜率居然也是 1"


class Perm:
    """(4!)^4 全枚举的分块置换：每层内整体置换 4 个方向标签。"""

    def __init__(self, n_layers: int, n_dir: int):
        p4 = np.array(list(itertools.permutations(range(n_dir))), dtype=np.int8)
        self.n = p4.shape[0] ** n_layers
        idx = np.arange(self.n, dtype=np.int64)
        self.by_layer = np.empty((n_layers, self.n, n_dir), dtype=np.int8)
        for i in range(n_layers):
            k = (idx // (p4.shape[0] ** (n_layers - 1 - i))) % p4.shape[0]
            self.by_layer[i] = p4[k]

    def betas(self, xd: np.ndarray, yd: np.ndarray) -> np.ndarray:
        """所有置换下的 β。xd 固定、yd 被置换（等价于置换 x 的标签）。"""
        nl, ns, nd = xd.shape
        num = np.zeros(self.n, dtype=np.float64)
        for i in range(nl):
            q = self.by_layer[i]
            G = np.zeros((self.n, nd), dtype=np.float64)
            for s in range(ns):
                G += yd[i][s][q]
            num += (xd[i][0][None, :] * G).sum(axis=1)
        return num / float((xd * xd).sum())


def exact_p(beta_obs: float, beta_null: np.ndarray) -> float:
    ge = int((np.abs(beta_null) >= abs(beta_obs) - 1e-18).sum())
    return ge / beta_null.size


def main() -> int:
    selfcheck()
    law = json.loads(LAW.read_text(encoding="utf-8"))
    dirs = law["design"]["real_directions"]
    layers = list(law["design"]["layers"])
    strengths = list(law["design"]["strengths"])
    safe_max = law["conclusions"]["safe_regime"]["strength_max"]   # R1：不写死
    rows = {(r["layer"], r["strength"]): r for r in law["rows"]}

    raw = np.zeros((len(layers), len(strengths), len(dirs)))
    rel = np.zeros_like(raw)
    cosv = np.zeros_like(raw)
    amean = np.zeros_like(raw)
    for i, L in enumerate(layers):
        for j, s in enumerate(strengths):
            r = rows[(L, s)]
            for k, d in enumerate(dirs):
                e = r["real"][d]
                pred = e["pred_pct"]
                raw[i, j, k] = e["dev_pct"] - pred
                rel[i, j, k] = (e["dev_pct"] - pred) / pred
                cosv[i, j, k] = e["cos_mean"]
                amean[i, j, k] = e["a_mean"]

    safe_mask = np.array([s <= safe_max for s in strengths])
    perm = Perm(len(layers), len(dirs))

    def run(Y: np.ndarray, mask: np.ndarray):
        Ys = Y[:, mask, :]
        Xs = cosv[:, mask, :]
        xd = Xs - Xs.mean(2, keepdims=True)
        yd = Ys - Ys.mean(2, keepdims=True)
        b_null = perm.betas(xd, yd)
        b_obs = float(b_null[0])
        return b_obs, exact_p(b_obs, b_null), b_null, xd, yd

    # ---------------- R4 对照：四个版本只报不判 ----------------
    all_mask = np.array([True] * len(strengths))
    versions = {
        "a_16行_百分点": (raw, all_mask),
        "b_12行_百分点": (raw, safe_mask),
        "c_16行_相对": (rel, all_mask),
        "d_12行_相对": (rel, safe_mask),
    }
    table = {}
    for nm, (Y, m) in versions.items():
        b, p, null, _, _ = run(Y, m)
        table[nm] = {"beta": b, "p_exact": p,
                     "beta_ci95": [float(np.quantile(null, .025)),
                                   float(np.quantile(null, .975))]}

    # ---------------- 判决只用版本 d ----------------
    b0, p0, null0, xd_d, yd_d = run(rel, safe_mask)

    # ---------------- R3 功效：二分 δ*（每个 δ 重新全枚举）----------------
    cache: dict[float, float] = {}

    def p_at(delta: float) -> float:
        key = round(delta, 9)
        if key in cache:
            return cache[key]
        yd2 = yd_d + delta * xd_d
        bn = perm.betas(xd_d, yd2)
        val = exact_p(float(bn[0]), bn)
        cache[key] = val
        return val

    lo, hi = 0.0, DELTA_CAP
    if p_at(lo) <= ALPHA:
        delta_star = 0.0        # δ=0 就已显著 ⇒ 功效不是瓶颈
    else:
        while hi - lo > BISECT_TOL:
            mid = (lo + hi) / 2
            if p_at(mid) <= ALPHA:
                hi = mid
            else:
                lo = mid
        delta_star = hi

    # ---------------- D1 δ_th：生成器自己写的二阶展开 ----------------
    # ⚠ 第一版写 `j_top = argmax(strengths)`，取到的是全局最大强度 0.5
    #   （a = 0.52468）—— 那在安全区**之外**，而且 f(c) 的分母 1+ac 在那里已经
    #   不该当真。R1 的口径是安全区，D1 必须跟着走：取**安全区上界**那一档。
    # ⚠ δ_th 按 §49.1 只当尺度基准、不参与判决，所以这个索引错误**没有**
    #   改动本修订的判决（δ*=0 ≤ δ_th 两边都成立）。两个值都报出来。
    def f_spread(a: float, L: int) -> float:
        cs = cosv[[layers.index(L)], 0, :]
        f = (1 - a * cs) / (1 + a * cs)
        return float(f.max() - f.min())

    safe_top = max(s for s in strengths if s <= safe_max)
    j_safe = strengths.index(safe_top)
    j_all = int(np.argmax(strengths))
    a_safe = float(amean[:, j_safe, :].max())
    a_all = float(amean[:, j_all, :].max())

    per_layer = {}
    for i, L in enumerate(layers):
        cs = cosv[i, 0, :]
        f = (1 - a_safe * cs) / (1 + a_safe * cs)
        per_layer[str(L)] = {"cos": [float(c) for c in cs],
                             "f_minus_1": [float(v - 1) for v in f],
                             "spread": float(f.max() - f.min())}
    delta_th = max(v["spread"] for v in per_layer.values())
    delta_th_wrong_a = max(f_spread(a_all, L) for L in layers)

    # ---------------- 独立核对：观测残差 vs 生成器自己预测的 f(c)−1 ----------------
    # ⚠ 这一段**不参与判决**（§49.3：判决只看 δ* 与 p_exact(0)）。
    #   它的作用是回答「这个 c 依赖是随便什么方向都能拟合，还是正是
    #   生成器 docstring 里写下的那个二阶修正？」—— 后者才是可信的机制。
    obs, pred, by_strength = [], [], {}
    for i, L in enumerate(layers):
        for j, s in enumerate(strengths):
            if s > safe_max:
                continue
            a = amean[i, j, :]
            pj = (1 - a * cosv[i, j, :]) / (1 + a * cosv[i, j, :]) - 1
            yj = rel[i, j, :]
            obs.extend(yj.tolist())
            pred.extend(pj.tolist())
            so = sorted(range(len(dirs)), key=lambda k: yj[k])
            sp = sorted(range(len(dirs)), key=lambda k: pj[k])
            agree = (so == sp) or (so == sp[::-1])
            by_strength[f"L{L}_s{s}"] = {
                "obs_range": float(yj.max() - yj.min()),
                "pred_range": float(pj.max() - pj.min()),
                "same_order": bool(so == sp), "reverse_order": bool(so == sp[::-1]),
                "any_order_match": bool(agree)}
    obs_a, pred_a = np.array(obs), np.array(pred)
    corr = float(np.corrcoef(obs_a, pred_a)[0, 1])
    slope = float(np.polyfit(pred_a, obs_a, 1)[0])

    # ---------------- 判决 ----------------
    if delta_star > delta_th:
        verdict = "不可判定"
        action = "既不加也不删 L1 任何措辞；把「功效不足、不可判定」写进文档"
    elif p0 < ALPHA:
        verdict = "存在 c 依赖"
        action = "L1 措辞须加限定（更正，披露 §48.4.1 旧数字）"
    else:
        verdict = f"未测出 c 依赖（δ ≥ {delta_star:.4f} 才测得出）"
        action = "不动 claim；可把测不出的下界写进 note"

    res = {
        "schema": "steer3d.direction_power/1",
        "prereg": "R6_RERUN_PREREG.md §49.1 @ 24432ef",
        "source": "frontend/public/latent/data/linearity_law.json",
        "R1_safe_max_from_artifact": safe_max,
        "R2_y": "(dev_pct - pred_pct) / pred_pct",
        "R4_versions": table,
        "verdict_version": "d_12行_相对",
        "beta": b0, "p_exact": p0,
        "beta_ci95": table["d_12行_相对"]["beta_ci95"],
        "R3_delta_star": delta_star, "R3_alpha": ALPHA,
        "R3_perm_space": int(perm.n),
        "R3_n_evaluations": len(cache),
        "D1_a_safe": a_safe, "D1_a_global_max_strength": a_all,
        "D1_delta_th": delta_th,
        "D1_delta_th_with_buggy_a": delta_th_wrong_a,
        "D1_per_layer": per_layer,
        "CONFIRM_corr_obs_vs_pred_f": corr,
        "CONFIRM_slope": slope,
        "CONFIRM_by_row": by_strength,
        "verdict": verdict, "action": action,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"源: {LAW.relative_to(ROOT)}")
    print(f"R1 安全区上界（从产物读）= {safe_max} ⇒ {safe_mask.sum()}/4 个强度纳入，"
          f"共 {len(layers) * int(safe_mask.sum())} 行")
    print(f"R3 置换空间 {perm.n:,}（全枚举），δ 搜索共评估 {len(cache)} 个点\n")
    print("[R4] 四个版本对照（只报不判，判决只看 d）")
    print(f"{'版本':<16} {'β':>12} {'p_exact':>10}  95% 置换区间")
    for nm, v in table.items():
        print(f"{nm:<16} {v['beta']:>+12.6f} {v['p_exact']:>10.6f}  "
              f"[{v['beta_ci95'][0]:+.6f}, {v['beta_ci95'][1]:+.6f}]")
    print(f"\n[R3] δ* = {delta_star:.5f}  （y 单位 = 相对偏差；α={ALPHA}）")
    print(f"     δ=0 处的 p_exact = {p0:.6f}")
    print(f"[D1] a（安全区上界 s={safe_top}，从产物读）= {a_safe:.5f}")
    print(f"     ⚠ 第一版误取全局最大强度 s={strengths[j_all]} 的 a={a_all:.5f}，"
          f"得 δ_th={delta_th_wrong_a:.5f}；修正后 δ_th={delta_th:.5f}。"
          f"δ_th 不参与判决，判决未变。")
    for L, v in per_layer.items():
        print(f"     L{L}: c={[round(c,4) for c in v['cos']]} "
              f"f−1 的极差={v['spread']:.5f}")
    print(f"\n[独立核对] 观测残差 vs 生成器 docstring 自己写的 f(c)−1"
          f"（安全区 {len(obs)} 个点）")
    print(f"     corr = {corr:+.4f}   斜率 = {slope:+.4f}")
    for k, v in by_strength.items():
        tag = ("同序" if v["same_order"] else "逆序" if v["reverse_order"] else "不一致")
        print(f"     {k:<12} 观测极差={v['obs_range']:.5f} "
              f"预测极差={v['pred_range']:.5f}  四方向排序={tag}")
    print(f"\n⚠ δ_th 只当尺度基准，不当判决依据（§48.4.7：a≈0.2 时一阶与二阶同阶）")
    print(f"\n[判决] δ*={delta_star:.5f} vs δ_th={delta_th:.5f} ⇒ **{verdict}**")
    print(f"[动作] {action}")
    print(f"写出: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())