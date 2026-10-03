#!/usr/bin/env python3
"""S2 — 核心：把读出方向和 steering 向量各自挪一个 block，已发表的两个 cos 变成多少。

## 怎么跑

    cd /Users/zhourui/code/steer3d
    python3 .cache/layerside2/s1_cache_facts.py   # 产出 hidden_L{12..15}.npy
    python3 .cache/layerside2/s1b_vectors.py       # 产出 vecs_L12_L15.npz
    python3 .cache/layerside2/s2_probe.py          # 本脚本

产物：s2_probe.json（全部原始数值，含每折 cos 全量）

## 问的问题

`steering_vectors.json` 的 6 个方向都取自 `hidden_states[:,14]`（block 14 的
**输出**），而在线注入用 `register_forward_pre_hook(block 14)`，扰动的是
`hidden_states[:,13]`（进入 block 14 的流）。差一个 block。

已发表的两条读出方向（`.cache/rolesverify/probe_axes.json`，L14、Δ=0、
λ=0.01、轨迹内去均值）：
    confidence → top1_prob_renorm   cos 0.4125，位置对照 0.0114
    caution    → backtrack_topk     cos 0.3077，位置对照 0.0016
本脚本把**读出层的层号**与**向量的层号**解耦，做 2×4 的网格（Lr ∈ {13,14} ×
Lv ∈ {12,13,14,15}），并要求位置对照在**同一格**里同时给出。

## 四个不可省的约束

1. **位置对照必须同格**。`step_frac = t/(T−1)` 作为第 11 个目标单独跑，
   不计入候选搜索。没有同格对照，0.412 / 0.308 这种数字没有意义。
2. **阴性对照是分布不是单点**：400 个随机单位方向，报 max / p95 / 中位。
3. **判据分辨力单独验**：`layer_resolution_selfcheck()` 造一份**已知**跨层
   旋转角的合成数据，要求装置把它测回来。不通过就 abort。
4. **两种余弦口径都报，且互相核验**。probe_axes 报的是
   `|w_n · normalize(Pᵀv)|`（先按天花板 ‖Pᵀv‖ 归一），真 2048 维余弦是
   `probe_axes 值 × 天花板`。两者对 L14 只差 1.2%，但必须写清用的是哪个。

## 复现 vs 归因：两个函数，不混

`verify_baseline_reproduction()` 只回答「我这套装置复现出已发表的数了吗」，
判据是**全部**格子的通过率；`attribute_deviations()` 只回答「哪些格子偏离了
预期」。基线要看所有输出行，归因只看失败行 —— 混成一个函数就会把
「复现失败」误读成「某条用例红了」。

## 数值口径

BLAS 是 accelerate，会对正常 float64 matmul 抛伪的 divide-by-zero 告警。
沿用 `probe_readout._chk` 的做法：静默告警 + 每步显式 finite 断言。
Gram 矩阵按 (层, Δ, 目标, 变换) 缓存、λ 只改解的代价，但**必须**与
`probe_readout._loo_ridge_fit` 逐折对齐后才允许复用（`assert_gram_cache_matches`）。
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path("/Users/zhourui/code/steer3d")
sys.path.insert(0, str(ROOT / ".cache/rolesverify"))
from probe_readout import _ERR, _chk, _loo_ridge_fit, toy_selfcheck  # noqa: E402

OUT = Path(__file__).resolve().parent
AXES = {"confidence": "confidence_up", "caution": "caution",
        "creativity": "creativity", "reasoning": "reasoning_deep"}
VEC_LAYERS = [12, 13, 14, 15]
READOUT_LAYERS = [13, 14]
STRIDE = 2
K_PCA = 256
LAMBDAS = [1e-4, 1e-3, 1e-2, 1e-1]
DELTAS = [0, 20]
TRANSFORMS = ["demean_within_traj", "raw"]
MIN_STEPS = 50
N_RANDOM = 400
SEED = 20261003
# 候选观测量在 obs_series 里的列号（column_order 见 obs_series_meta.json）
COL = {"backtrack_topk": 3, "top1_prob_renorm": 9}
# 已发表值，来自 .cache/rolesverify/probe_axes.json 的 L14 / Δ=0 / λ=0.01 行
PUBLISHED = {
    ("confidence", "top1_prob_renorm", 0, 1e-2): 0.41250607586097717,
    ("caution", "backtrack_topk", 0, 1e-2): 0.3076629340648651,
}
PUBLISHED_CONTROL = {("confidence", 0, 1e-2): 0.0114, ("caution", 0, 1e-2): 0.0016}
PUBLISHED_PCA_VAR_CUM_L14 = 0.7287951021859504
TOL_REPRO = 2e-3          # 复现容差：与已发表值差小于它算复现成功


def dot(a, b):
    return float(np.sum(np.asarray(a, dtype=np.float64) *
                        np.asarray(b, dtype=np.float64), dtype=np.float64))


# ================================================================ 装置自检
def layer_resolution_selfcheck(seed=11, rho_target=0.9565, tol=0.02):
    """判据分辨力：造**已知**跨层旋转角的数据，要求装置把它测回来。

    这是本项目踩过的坑的直接对策：判据要在**要扫的那个维度**上真的动。
    这里扫的维度是层号，所以合成数据必须让 L13 与 L14 的读出方向差一个
    已知角度 `acos(rho_target)`，装置若测不回来，后面所有层间比较都不可信。

    构造：h13 = c + z·a + w13，h14 = c + z·(cosφ·a + sinφ·b) + w14，
    目标 y = z。于是 L13 的读出方向 ∝ a、L14 的 ∝ a' = cosφ·a + sinφ·b，
    两者夹角恰为 φ，理论 cos = cosφ。噪声各向同性且与 z 无关。
    """
    rng = np.random.default_rng(seed)
    d, k, n_traj, T = 2048, K_PCA, 30, 700
    a = rng.normal(size=d)
    a /= np.linalg.norm(a)
    b = rng.normal(size=d)
    b -= a * (a @ b)
    b /= np.linalg.norm(b)
    phi = float(np.arccos(rho_target))
    ca, sa = float(np.cos(phi)), float(np.sin(phi))
    a2 = ca * a + sa * b                      # 期望的 L14 读出方向

    H13, H14, Y = [], [], []
    for _ in range(n_traj):
        z = np.cumsum(rng.normal(size=T), axis=0) * 0.5
        c0 = rng.normal(size=d) * 5.0         # 恒定分量：验中心化
        H13.append(np.outer(z, a) + rng.normal(size=(T, d)) * 0.15 + c0)
        H14.append(np.outer(z, a2) + rng.normal(size=(T, d)) * 0.15 + c0)
        Y.append(z.astype(np.float64))

    def fit_readout(H):
        xm = np.mean([h.mean(axis=0) for h in H], axis=0)
        mean_dir = xm / np.linalg.norm(xm)
        C = np.zeros((d, d))
        with np.errstate(**_ERR):
            for h in H:
                hc = h - xm
                C += _chk(hc.T @ hc, "toy C")
            C /= C.trace()
            ev, evec = np.linalg.eigh(C)
            P = evec[:, np.argsort(ev)[::-1][:k]]
            Xs = [_chk((h - xm) @ P, "toy proj") for h in H]
        Ys = [(y - y.mean())[:, None] for y in Y]
        ws, oof, _, _ = _loo_ridge_fit(Xs, Ys, k, 1e-3)
        wn = ws / np.linalg.norm(ws, axis=1, keepdims=True)
        wd = _chk(wn @ P.T, "toy w back")
        wd = wd / np.linalg.norm(wd, axis=1, keepdims=True)
        cos_mean = float(np.median([abs(dot(w, mean_dir)) for w in wd]))
        return wd, float(oof), cos_mean

    w13, r13, cm13 = fit_readout(H13)
    w14, r14, cm14 = fit_readout(H14)
    cos_between = float(np.median([dot(x, y) for x, y in zip(w13, w14)]))
    med13 = float(np.median([dot(w, a) for w in w13]))
    med14 = float(np.median([dot(w, a2) for w in w14]))
    # 交叉项：L13 的读出方向对 a2 应恰好等于 cos φ（这是「层号真的动了」的第二个证据）
    cross13 = float(np.median([dot(w, a2) for w in w13]))
    cross14 = float(np.median([dot(w, a) for w in w14]))
    checks = {
        "L13_recovers_a": bool(med13 > 0.95),
        "L14_recovers_a2": bool(med14 > 0.95),
        "recovers_known_rotation": bool(abs(cos_between - rho_target) < tol),
        "cross_cos_L13_vs_a2_equals_rho": bool(abs(cross13 - rho_target) < tol),
        "cross_cos_L14_vs_a_equals_rho": bool(abs(cross14 - rho_target) < tol),
        "oof_pearson_positive_both": bool(r13 > 0.3 and r14 > 0.3),
        # 读出方向不能只是找回恒定分量（rogue dimension）
        "not_confused_by_mean_dir": bool(cm13 < 0.5 and cm14 < 0.5),
    }
    return {
        "rho_target": rho_target, "phi_rad": phi,
        "cos_measured_between_layers": cos_between,
        "abs_error_vs_target": abs(cos_between - rho_target),
        "cross_cos_L13_w_vs_a2": cross13,
        "cross_cos_L14_w_vs_a": cross14,
        "tol": tol,
        "cos_L13_w_vs_a": med13, "cos_L14_w_vs_a2": med14,
        "cos_L13_w_vs_mean_dir": cm13, "cos_L14_w_vs_mean_dir": cm14,
        "oof_pearson_L13": r13, "oof_pearson_L14": r14,
        "checks": checks, "pass": all(checks.values()),
        "why": "扫的维度是层号，所以判据必须在层号上真的动：这份合成数据的两层"
               "读出方向夹角是已知的 acos(0.9565)，装置测不回来就说明后面所有"
               "层间比较都不可信。",
    }


# ================================================================ Gram 缓存
def prepare(Xs, Ys):
    """一次性算出每折的 Gram / cross，供 λ 扫描复用。"""
    d = Xs[0].shape[1]
    xm = np.mean([x.mean(axis=0) for x in Xs], axis=0)
    ym = np.mean([y.mean(axis=0) for y in Ys], axis=0)
    Gs, Bs = [], []
    with np.errstate(**_ERR):
        for x, y in zip(Xs, Ys):
            xc, yc = x - xm, y - ym
            Gs.append(_chk(xc.T @ xc, "Gram"))
            Bs.append(_chk(xc.T @ yc, "cross"))
    return xm, ym, Gs, Bs


def loo_from_prepared(prep, lam_rel, Xs, Ys, d):
    xm, ym, Gs, Bs = prep
    G, B = sum(Gs), sum(Bs)
    ws, preds, tgts = [], [], []
    for i in range(len(Xs)):
        Gi, Bi = G - Gs[i], B - Bs[i]
        lam = lam_rel * np.trace(Gi) / d
        wi = _chk(np.linalg.solve(Gi + lam * np.eye(d), Bi)[:, 0], "w_fold")
        ws.append(wi)
        xi, yi = Xs[i] - xm, Ys[i] - ym
        preds.append((xi @ wi).ravel())
        tgts.append(yi.ravel())
    P_, T_ = np.concatenate(preds), np.concatenate(tgts)
    den = float(np.std(P_)) * float(np.std(T_))
    oof = float(((P_ - P_.mean()) * (T_ - T_.mean())).mean() / den) if den > 0 else float("nan")
    return np.array(ws), oof


def assert_gram_cache_matches(Xs, Ys, lam_rel):
    """复用 Gram 缓存前必须与原实现逐折对齐。"""
    ws_ref, oof_ref, _, _ = _loo_ridge_fit(Xs, Ys, K_PCA, lam_rel)
    ws_new, oof_new = loo_from_prepared(prepare(Xs, Ys), lam_rel, Xs, Ys, K_PCA)
    dw = float(np.abs(ws_ref - ws_new).max())
    dr = abs(oof_ref - oof_new)
    if dw > 1e-8 or dr > 1e-10:
        raise AssertionError(
            f"Gram 缓存与 _loo_ridge_fit 不一致：max|Δw|={dw:.3e} Δoof={dr:.3e}")
    return {"max_abs_diff_w": dw, "abs_diff_oof_pearson": dr,
            "oof_reference": float(oof_ref)}


# ================================================================ 数据
def sampled_layer(layer):
    """按 STRIDE 抽步的逐轨迹隐状态（float64）。口径与 probe_readout.collect_layer 一致。"""
    idx = json.loads((OUT / "traj_index.json").read_text())
    H = np.load(OUT / f"hidden_L{layer}.npy", mmap_mode="r")
    out = []
    for e in idx["traj"]:
        out.append(np.asarray(H[e["start"]:e["stop"]:STRIDE], dtype=np.float64))
    return out


def pca(H, k):
    d = H[0].shape[1]
    with np.errstate(**_ERR):
        xm = np.mean([h.mean(axis=0) for h in H], axis=0)
        C = np.zeros((d, d))
        for h in H:
            hc = h - xm
            C += _chk(hc.T @ hc, "C")
        C /= np.trace(C)
        ev, evec = np.linalg.eigh(C)
        order = np.argsort(ev)[::-1]
        return xm, evec[:, order[:k]], ev[order]


def targets():
    """返回 (names, 逐轨迹观测量, 逐轨迹 step_frac 对照)。

    **观测量必须与 hidden 用同一个 STRIDE 抽步。** hidden_states 用
    `H[start:stop:STRIDE]`，观测量若不抽步，第 j 行的 X 是第 2j 步、
    Y 是第 j 步，而 numpy 不会报错：392×256 @ 256×784 仍然合法，
    于是静默产出一张全是垃圾的表。断言专门堵这一类。
    """
    obs = np.load(OUT / "obs_series.npy")
    idx = json.loads((OUT / "traj_index.json").read_text())
    series = [obs[e["start"]:e["stop"]:STRIDE] for e in idx["traj"]]
    names = [str(x) for x in np.load(
        OUT.parent / "rolesverify/obs_series.npz", allow_pickle=True)["names"]]
    step_frac = []
    for e in idx["traj"]:
        Ts = len(range(0, e["rows"], STRIDE))
        step_frac.append(np.arange(Ts) / max(Ts - 1, 1))
    # 隐状态与观测量的行数必须逐条相等
    H = np.load(OUT / "hidden_L14.npy", mmap_mode="r")
    for e, s in zip(idx["traj"], series):
        want = len(range(0, e["rows"], STRIDE))
        if len(s) != want:
            raise AssertionError(
                f"轨迹 {e['name']}: 观测量 {len(s)} 行 != 隐状态抽步后 {want} 行")
    del H
    return names, series, step_frac


def get_y(series, step_frac, key, i, delta, transform):
    if key == "CONTROL_step_frac":
        yy = step_frac[i]
    else:
        yy = series[i][:, COL[key]].astype(np.float64)
    want = len(series[i]) - (delta if delta > 0 else 0)
    if delta > 0:
        yy = yy[delta:]
    if len(yy) != want:
        raise AssertionError(
            f"目标 {key} traj{i} Δ={delta}: 长度 {len(yy)} != 预期 {want}")
    if transform == "demean_within_traj":
        yy = yy - yy.mean()
    return yy[:, None], want


# ================================================================ 验证 vs 归因
def verify_baseline_reproduction(cells):
    """基线复现：看**全部**格子的通过率。不产生红/绿名单。"""
    checks, n_pass, n_tot = {}, 0, 0
    rows = []
    for (axis, cand, delta, lam), want in PUBLISHED.items():
        got = cells[(14, "demean_within_traj", delta, lam, cand, axis)]
        ok = abs(got - want) <= TOL_REPRO
        n_tot += 1
        n_pass += int(ok)
        rows.append({"layer": 14, "transform": "demean_within_traj", "delta": delta,
                     "lambda_rel": lam, "candidate": cand, "axis": axis,
                     "published": want, "recomputed": got,
                     "abs_diff": abs(got - want), "pass": ok})
    for (axis, delta, lam), want in PUBLISHED_CONTROL.items():
        got = cells[(14, "demean_within_traj", delta, lam, "CONTROL_step_frac", axis)]
        ok = got <= want * 3 + 0.005      # 对照只要求同量级且同向，不得高于
        n_tot += 1
        n_pass += int(ok)
        rows.append({"layer": 14, "transform": "demean_within_traj", "delta": delta,
                     "lambda_rel": lam, "candidate": "CONTROL_step_frac", "axis": axis,
                     "published_max": want, "recomputed": got, "pass": ok})
    checks = {
        "published_cells": len(PUBLISHED),
        "published_reproduced": sum(
            int(abs(cells[(14, "demean_within_traj", d, l, cd, ax)] - w) <= TOL_REPRO)
            for (ax, cd, d, l), w in PUBLISHED.items()),
        "n_checks": n_tot, "n_pass": n_pass,
        "all_pass": bool(n_pass == n_tot),
    }
    return {"checks": checks, "all_rows": rows,
            "policy": "基线复现看全部行；不因部分通过而报喜"}


def attribute_deviations(cells, tol=TOL_REPRO):
    """归因：只列偏离预期的格子。判据方向与基线相反，绝不混用。"""
    out = []
    for (axis, cand, delta, lam), want in PUBLISHED.items():
        got = cells[(14, "demean_within_traj", delta, lam, cand, axis)]
        if abs(got - want) > tol:
            out.append({"kind": "published_cell_mismatch", "axis": axis,
                        "candidate": cand, "delta": delta, "lambda_rel": lam,
                        "expected": want, "got": got, "abs_diff": abs(got - want)})
    return out


# ================================================================ 主流程
def main():
    t0 = time.time()
    res = {
        "schema": "layerside2.s2_probe/1",
        "question": "把读出方向与 steering 向量各自挪一个 block（14 -> 13），"
                    "已发表的 0.412 / 0.308 变成多少？",
        "config": {
            "readout_layers": READOUT_LAYERS, "vector_layers": VEC_LAYERS,
            "axes": AXES, "candidates": COL, "control": "CONTROL_step_frac",
            "deltas": DELTAS, "lambdas": LAMBDAS, "transforms": TRANSFORMS,
            "stride": STRIDE, "k_pca": K_PCA, "min_steps": MIN_STEPS,
            "n_random": N_RANDOM, "seed": SEED, "fold": "leave-one-trajectory-out，每折重解 w",
            "cos_conventions": {
                "pca_norm": "|w_n · normalize(Pᵀv)| —— probe_axes 用的口径，先按天花板归一",
                "dspace": "pca_norm × ceiling —— 真 2048 维余弦",
            },
        },
        "selfcheck_toy": toy_selfcheck(),
        "selfcheck_layer_resolution": layer_resolution_selfcheck(),
    }
    if not res["selfcheck_toy"]["pass"]:
        res["abort"] = "toy 自检未通过"
        (OUT / "s2_probe.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        print("TOY SELFCHECK FAIL")
        return 1
    if not res["selfcheck_layer_resolution"]["pass"]:
        res["abort"] = "层号分辨力自检未通过，装置在要扫的维度上没动"
        (OUT / "s2_probe.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        print("LAYER-RESOLUTION SELFCHECK FAIL",
              json.dumps(res["selfcheck_layer_resolution"]["checks"], ensure_ascii=False))
        return 1
    print("selfcheck OK (toy + layer-resolution)", flush=True)

    vecs = np.load(OUT / "vecs_L12_L15.npz", allow_pickle=True)
    axes_named = [str(x) for x in vecs["axes"]]
    V = {(L, a): vecs[f"L{L}"][i] / np.linalg.norm(vecs[f"L{L}"][i])
         for L in VEC_LAYERS for i, a in enumerate(axes_named)}
    names, series, step_frac = targets()
    assert names[COL["backtrack_topk"]] == "backtrack_topk", names
    assert names[COL["top1_prob_renorm"]] == "top1_prob_renorm", names
    n_sampled = sum(len(range(0, e["rows"], STRIDE))
                    for e in json.loads((OUT / "traj_index.json").read_text())["traj"])

    rng = np.random.default_rng(SEED)
    rand = rng.normal(size=(N_RANDOM, 2048))
    rand /= np.linalg.norm(rand, axis=1, keepdims=True)

    cells, per_fold, res["per_layer"] = {}, {}, {}
    # 读出方向本身（w 投回 2048 维）按 (变换,Δ,λ,候选) 留存，
    # 用来算 cos(w_L13, w_L14) —— 「读出方向自己挪一个 block 变多少」
    readout_dirs = {}
    for Lr in READOUT_LAYERS:
        tl = time.time()
        H = sampled_layer(Lr)
        with np.errstate(**_ERR):
            xm, P, evals = pca(H, K_PCA)
        var_cum = float(evals[:K_PCA].sum())
        # 天花板与每个向量层的投影
        proj, ceil = {}, {}
        for Lv in VEC_LAYERS:
            for a in axes_named:
                pk = _chk(P.T @ V[(Lv, a)], f"L{Lr} P.T v(L{Lv},{a})")
                ceil[(Lv, a)] = float(np.linalg.norm(pk))
                proj[(Lv, a)] = pk / ceil[(Lv, a)]
        with np.errstate(**_ERR):
            Xp = [_chk((h - xm) @ P, f"L{Lr} proj") for h in H]
            rand_k = _chk(rand @ P, f"L{Lr} rand_k")
        del H
        print(f"--- L{Lr} pca_var_cum={var_cum:.7f} sec={time.time()-tl:.0f}", flush=True)

        for transform in TRANSFORMS:
            for delta in DELTAS:
                keep_t = [i for i in range(len(series))
                          if len(series[i]) - (delta if delta > 0 else 0) >= MIN_STEPS]
                for cand in list(COL) + ["CONTROL_step_frac"]:
                    Ys = [get_y(series, step_frac, cand, i, delta, transform)[0]
                          for i in keep_t]
                    Xs = [Xp[i][:len(y)] for i, y in zip(keep_t, Ys)]
                    # 断言检查**等于预期值**，不是两个都错时的等式
                    for k, (x, y) in enumerate(zip(Xs, Ys)):
                        want = len(series[keep_t[k]]) - (delta if delta > 0 else 0)
                        if len(x) != want or len(y) != want:
                            raise AssertionError(
                                f"L{Lr} {transform} Δ={delta} {cand} 第 {k} 条："
                                f"X {len(x)} / Y {len(y)} != 预期 {want}（stride 未对齐）")
                    prep = prepare(Xs, Ys)
                    if (Lr, transform, delta, cand) == (14, "demean_within_traj", 0,
                                                          "top1_prob_renorm"):
                        res["gram_cache_alignment"] = assert_gram_cache_matches(
                            Xs, Ys, 1e-2)
                        print("  gram-cache aligned vs _loo_ridge_fit:",
                              json.dumps(res["gram_cache_alignment"]), flush=True)
                    for lam in LAMBDAS:
                        ws, oof = loo_from_prepared(prep, lam, Xs, Ys, K_PCA)
                        wn = ws / np.linalg.norm(ws, axis=1, keepdims=True)
                        wd = _chk(wn @ P.T, "w back to d-space")
                        wd = wd / np.linalg.norm(wd, axis=1, keepdims=True)
                        # ---- 阴性对照：400 个随机单位方向的余弦**分布** ----
                        # 必须在有 wn 的地方算；报 max / p95 / 中位，不报单点。
                        with np.errstate(**_ERR):
                            cr = np.abs(wn @ rand_k.T)          # (n_fold, 400)
                        cr = np.where(np.isfinite(cr), cr, 0.0)
                        flat = cr.ravel()
                        null_per_fold_max = cr.max(axis=1)     # 每折在 400 个里的最大
                        null_stats = {
                            "n_random": int(N_RANDOM),
                            "n_fold": int(cr.shape[0]),
                            "cos_max": float(flat.max()),
                            "cos_p95": float(np.percentile(flat, 95)),
                            "cos_median": float(np.median(flat)),
                            "cos_p99": float(np.percentile(flat, 99)),
                            "per_fold_max_median": float(np.median(null_per_fold_max)),
                            "per_fold_max_max": float(null_per_fold_max.max()),
                        }
                        for a in axes_named:
                            axis = next(k for k, v in AXES.items() if v == a)
                            c_pca = np.abs(wn @ proj[(Lr, a)])
                            c_ds = np.abs(np.array([dot(w, V[(Lr, a)]) for w in wd]))
                            observed = float(np.median(c_pca))
                            # 已付搜索成本的 p：**零假设只含随机方向**。
                            # 把 4 条真实轴也算进「最大值」会让 search_max ≥ observed
                            # 恒成立，p 恒等于 0.5 —— 那是把对照算进了被检验的对象。
                            null_per_fold_max_cr = cr.max(axis=1)
                            # 跨层：读出方向（Lr）对另一个层（Lv）的向量
                            cross_ds = {Lv2: np.abs(np.array(
                                [dot(w, V[(Lv2, a)]) for w in wd]))
                                for Lv2 in VEC_LAYERS}
                            key = (Lr, transform, delta, lam, cand, axis)
                            cells[key] = observed
                            per_fold[key] = {
                                "cos_pca_norm_per_fold": c_pca.tolist(),
                                "cos_dspace_median": float(np.median(c_ds)),
                                "ceiling": ceil[(Lr, a)],
                                "identity_check_dspace_eq_pca_times_ceiling": float(
                                    abs(float(np.median(c_ds))
                                        - observed * ceil[(Lr, a)])),
                                "oof_pearson": float(oof),
                                "n_traj_used": len(keep_t),
                                "n_steps_used": int(sum(len(y) for y in Ys)),
                                "cross_layer_cos_dspace_median": {
                                    str(k2): float(np.median(v2))
                                    for k2, v2 in cross_ds.items()},
                                "null_random_400": null_stats,
                                "p_search_corrected_median_criterion": float(
                                    (null_per_fold_max_cr >= observed).mean()),
                                "n_folds_above_null_max": int(
                                    (null_per_fold_max_cr >= observed).sum()),
                            }
                        if transform == "demean_within_traj" and lam == 1e-2:
                            readout_dirs[(Lr, transform, delta, lam, cand)] = wd
                    del prep, Ys, Xs
        res["per_layer"][str(Lr)] = {
            "pca_var_cum": var_cum, "n_traj": len(series),
            "n_steps_sampled": n_sampled, "sec": round(time.time() - tl, 1),
            "cos_ceiling": {f"Lv{Lv}/{a}": ceil[(Lv, a)] for (Lv, a) in ceil},
        }
        del Xp

    # ---- 读出方向随层的变化：cos(w_L13, w_L14)，逐折对齐 ----
    # 折的顺序由 keep_t 决定，两层都用同一批轨迹（Δ=0 时 48 条全用），
    # 所以第 i 折在两层里是**同一条留出轨迹**，逐折配对才有意义。
    res["readout_direction_across_layers"] = {}
    for (Lr, tr, dl, lam, cand), wd in readout_dirs.items():
        key2 = None
        for (Lr2, tr2, dl2, lam2, cand2), wd2 in readout_dirs.items():
            if (tr2, dl2, lam2, cand2) == (tr, dl, lam, cand) and Lr2 != Lr:
                key2 = (Lr2, wd2)
        if key2 is None:
            continue
        Lr2, wd2 = key2
        if int(Lr2) <= int(Lr) or wd.shape[0] != wd2.shape[0]:
            continue
        pair = np.abs(np.array([dot(a, b) for a, b in zip(wd, wd2)]))
        res["readout_direction_across_layers"][
            f"L{Lr}_vs_L{Lr2}|{tr}|delta{dl}|lam{lam}|{cand}"] = {
            "cos_median": float(np.median(pair)),
            "cos_min": float(pair.min()), "cos_max": float(pair.max()),
            "n_fold": int(len(pair)),
        }
    res["cells_pca_norm"] = {"|".join(map(str, k)): v for k, v in cells.items()}
    res["per_fold"] = {"|".join(map(str, k)): v for k, v in per_fold.items()}

    # ---- 阴性对照 / 阳性对照（都已随每折统计落盘，这里只做汇总视图） ----
    res["null_random_400"] = null_block(per_fold)
    res["positive_control_step_frac"] = positive_control_block(cells, per_fold)
    # ---- 复现 vs 归因（两个函数） ----
    res["baseline_reproduction"] = verify_baseline_reproduction(cells)
    res["deviations"] = attribute_deviations(cells)
    res["published_pca_var_cum_L14"] = PUBLISHED_PCA_VAR_CUM_L14
    res["pca_var_cum_match"] = abs(
        res["per_layer"]["14"]["pca_var_cum"] - PUBLISHED_PCA_VAR_CUM_L14) < 1e-6
    res["elapsed_sec"] = round(time.time() - t0, 1)
    (OUT / "s2_probe.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"[done] {res['elapsed_sec']}s -> s2_probe.json")
    return 0


def null_block(per_fold):
    """汇总 400 随机方向对照。只列 λ=0.01 / 轨迹内去均值，与已发表格同口径。"""
    out = {}
    for key, v in per_fold.items():
        Lr, transform, delta, lam, cand, axis = key
        if transform != "demean_within_traj" or lam != 1e-2:
            continue
        out["|".join(map(str, key))] = {
            **v["null_random_400"],
            "p_search_corrected_median_criterion":
                v["p_search_corrected_median_criterion"],
            "n_folds_above_null_max": v["n_folds_above_null_max"],
            "observed_cos": None,
        }
    return out


def positive_control_block(cells, per_fold):
    """阳性对照：step_frac 本身必须测得出。测不出 = 装置坏了。"""
    out = {}
    for key, v in per_fold.items():
        Lr, transform, delta, lam, cand, axis = key
        if cand != "CONTROL_step_frac" or transform != "demean_within_traj":
            continue
        out["|".join(map(str, key))] = {
            "cos_pca_norm": cells[key], "oof_pearson": v["oof_pearson"],
            "above_null_max": bool(cells[key] > v["null_random_400"]["cos_max"]),
        }
    return out


if __name__ == "__main__":
    sys.exit(main())
