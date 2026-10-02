#!/usr/bin/env python3
"""10 个逐 token 观测量 × 4 条独立轴：哪条轴真的指向哪个行为量？

复用 `probe_readout.py` 里已经通过玩具自检的 PCA / 留一轨迹岭回归装置
（同属本文件，import 而不重写），把可观测量从 1 个扩到 10 个。

## 三个不可省的约束

1. **只跑去均值口径。** `failed_obs_forensics` 查出 4.4 那张表里 `creativity`
   的 +0.74 几乎全是轨迹间差，而 `probe_readout` 第一版报的
   「20 步后翻转到 creativity」也被去均值推翻了。所以这里**只**用
   `demean_within_traj`：每条轨迹减去自己的均值，探针只能解释轨迹内偏离。

2. **零假设必须取搜索后的最大值。** 10 个候选里总有一个看起来显著，
   所以统计量不是单个 `|cos(w_j, a)|`，而是

       对每个随机方向 v：  max_j max_a |cos(w_j, v)|

   而 p = P_v( 该值 ≥ 实测的 max_j max_a |cos(w_j, a)| )。
   少做这一步就等于在 40 个格子里挑最好的那个当结论。

3. **有效自由度要报，不要当 10 用。** 10 列里
   `backtrack_topk`↔`backtrack_frac` 的 |ρ| = 0.965（实质是一个观测量的
   两种权重），`top1_prob_renorm` 与 entropy 的 |ρ| = 0.985（重述）。
   所以自由度是 9，排除 top1_prob_renorm 后是 8。

## 装置自检

沿用 `probe_readout.toy_selfcheck()`：合成 `h = a·y + b·z + 噪声`，
要求 Δ=0 找回 a、Δ 增大时 cos(a) 单调下降并塌到噪声地板。
不通过就直接 ABORT。
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_readout import (  # noqa: E402
    AXES, _ERR, _chk, _loo_ridge_fit, collect_layer,
    load_axes, paired_sign_test, pca_basis, toy_selfcheck,
)

ROOT = Path("/Users/zhourui/code/steer3d")
SERIES = ROOT / ".cache/rolesverify/obs_series.npz"
META = ROOT / ".cache/rolesverify/obs_series_meta.json"
OUT = ROOT / ".cache/rolesverify/probe_axes.json"
LAYERS = [12, 14, 20]
DELTAS = [0, 1, 20, 100, 400]
STRIDE = 2
K_PCA = 256
LAMBDAS = [1e-3, 1e-2]
N_RANDOM = 400
SEED = 20261003
MIN_STEPS = 50
# 冗余对：A 里实测 |ρ|=0.965 的那两列实质是一个观测量，排除其一避免重复计数
REDUNDANT_DROP = "backtrack_frac"


def load_series():
    z = np.load(SERIES, allow_pickle=True)
    names = [str(x) for x in z["names"]]
    obs = z["obs"].astype(np.float64)
    traj_id = z["traj_id"].astype(np.int64)
    traj_T = z["traj_T"].astype(np.int64)
    per = [[] for _ in traj_T]
    for i, tid in enumerate(traj_id):
        per[tid].append(obs[i])
    return names, [np.array(p) for p in per], traj_T


def main():
    t0 = __import__("time").time()
    meta = json.loads(META.read_text())
    res = {
        "schema": "steer3d.probe_axes/1",
        "question": "4 条独立轴各自指向 10 个逐 token 行为可观测量中的哪一个？",
        "config": {
            "axes": AXES, "layers": LAYERS, "deltas": DELTAS, "stride": STRIDE,
            "k_pca": K_PCA, "lambdas": LAMBDAS, "n_random": N_RANDOM,
            "seed": SEED, "target_transform": "demean_within_traj",
            "n_candidates": meta["n_columns"],
            "n_candidate_cells": meta["n_columns"] * len(AXES),
            "effective_dof": {
                "declared": meta["n_columns"],
                "after_dropping_redundant": meta["n_columns"] - 1,
                "reason": f"|rho|(backtrack_topk, backtrack_frac) = 0.965；"
                          f"top1_prob_renorm 与 entropy |rho| = 0.985（重述）",
            },
            "redundant_dropped_from_search": REDUNDANT_DROP,
        },
        "selfcheck": toy_selfcheck(),
    }
    if not res["selfcheck"]["pass"]:
        res["abort"] = "装置自检未通过"
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
        print("SELFCHECK FAIL")
        return 1
    print("selfcheck OK", flush=True)

    names, series, traj_T = load_series()
    drop = REDUNDANT_DROP
    keep = [i for i, n in enumerate(names) if n != drop]
    res["config"]["candidates_searched"] = [names[i] for i in keep]
    res["config"]["candidates_dropped"] = [drop]
    assert len(series) == len(traj_T) == 48, (len(series), len(traj_T))

    axes = load_axes()
    rng = np.random.default_rng(SEED)
    rand = rng.normal(size=(N_RANDOM, 2048))
    rand /= np.linalg.norm(rand, axis=1, keepdims=True)

    res["per_layer"] = {}
    for layer in LAYERS:
        tl = __import__("time").time()
        H, meta_t = collect_layer(layer, STRIDE)
        n_traj = len(H)
        with np.errstate(**_ERR):
            xm, P, evals = pca_basis(H, K_PCA)
        var_cum = float(evals[:K_PCA].sum())
        with np.errstate(**_ERR):
            axes_k = {k: _chk(P.T @ v, f"L{layer} axis {k}") for k, v in axes.items()}
            ceiling = {k: float(np.linalg.norm(x)) for k, x in axes_k.items()}
            axes_k = {k: x / ceiling[k] for k, x in axes_k.items()}
            rand_k = _chk(rand @ P, "rand_k")
            Xp = [_chk((h - xm) @ P, f"L{layer} proj") for h in H]
        del H
        print(f"--- L{layer} 天花板 " + " ".join(f"{k}={v:.3f}" for k, v in ceiling.items())
              + f"  pca_var_cum={var_cum:.4f}", flush=True)

        rows = []
        # 关键：`collect_layer` 对 hidden_states 用了 stride=2，外部 series 是
        # stride=1。**必须同样抽步**，否则 X 的第 j 行是第 2j 步、Y 的第 j 行是
        # 第 j 步 —— 行错位。而 numpy 不会报错：392×256 @ 256×784 仍然合法，
        # 于是静默产出一张全是垃圾的表。
        # 长度断言专门堵这一类，第一版就是在这里静默错位过。
        ser_s = [s[::STRIDE] for s in series]
        # 对照目标：step_frac = t/(T-1) 本身就是 reasoning_deep 的定义分组。
        # **它不是候选，是尺子** —— 用来判 `rep_frac_topk` 到底是不是
        # step_frac 的代理。若 w(rep_frac_topk) 对 reasoning 的对齐
        # 明显高于 w(step_frac) 的，说明它携带了位置斜坡之外的信息；
        # 若两者相当，那这条发现就是被 C 判死的那件事换了个观测量。
        step_frac_col = []
        for T in traj_T:
            Ts = len(range(0, T, STRIDE))
            step_frac_col.append(np.arange(Ts) / max(Ts - 1, 1))
        for delta in DELTAS:
            keep_t = [i for i in range(n_traj)
                      if len(ser_s[i]) - (delta if delta > 0 else 0) >= MIN_STEPS]
            for lam_rel in LAMBDAS:
                per_cand = []
                # step_frac 作为第 11 列对照（不算进搜索，所以单独跑）
                for j in keep:
                    Ys = []
                    for i in keep_t:
                        # ser_s[i] 形状是 (T_i, 10)，取**候选 j** 必须写 [:, j]。
                        # 写成 [j] 会取到第 j 行（10 个候选混在一起），
                        # 而且在 Δ=0/1 时长度恰好都是 10 所以不报错 ——
                        # Δ=20 时 [20:] 才切出空数组。静默错位比崩溃更贵。
                        yy = ser_s[i][:, j]
                        yy = yy[delta:] if delta > 0 else yy
                        want = len(ser_s[i]) - (delta if delta > 0 else 0)
                        if len(yy) != want:
                            raise AssertionError(
                                f"L{layer} Δ={delta} 候选 {names[j]}: "
                                f"traj{i} 目标长度 {len(yy)} != 预期 {want}")
                        yy = yy - yy.mean()                 # 轨迹内去均值
                        Ys.append(yy[:, None])
                    Xs = [Xp[i][: len(y)] for i, y in zip(keep_t, Ys)]
                    bad = [i for i, (x, y) in enumerate(zip(Xs, Ys)) if len(x) != len(y)]
                    if bad:
                        raise AssertionError(
                            f"L{layer} Δ={delta} 候选 {names[j]}: 第 {bad[:3]} 条轨迹 "
                            f"特征与目标行数不等（{len(Xs[bad[0]])} vs {len(Ys[bad[0]])}）"
                            f" —— stride 没对齐")
                    ws, oof_r, oof_r2, _ = _loo_ridge_fit(Xs, Ys, K_PCA, lam_rel)
                    wn = ws / np.linalg.norm(ws, axis=1, keepdims=True)
                    cos = {a: np.abs(wn @ axes_k[a]) for a in axes}
                    best_axis = max(cos, key=lambda a: float(np.median(cos[a])))
                    observed = float(np.median(cos[best_axis]))
                    # 零假设：随机方向同时搜 9 个候选 × 4 条轴
                    cr = np.abs(wn @ rand_k.T)                      # (fold, n_random)
                    null_max = cr.max(axis=1)                      # 每折、每随机方向的最大值
                    p_search = float((null_max >= observed).mean())
                    per_cand.append({
                        "candidate": names[j],
                        "is_control": False,
                        "best_axis": best_axis,
                        "cos_best_axis_median": observed,
                        "cos_per_axis_median": {a: float(np.median(cos[a])) for a in axes},
                        "cos_ceiling": ceiling,
                        "oof_pearson": float(oof_r),
                        "p_search_corrected": p_search,
                        "n_traj_used": len(keep_t),
                    })
                # ---- 对照目标 step_frac（不计入搜索）----
                Ys = []
                for i in keep_t:
                    yy = step_frac_col[i]
                    yy = yy[delta:] if delta > 0 else yy
                    yy = yy - yy.mean()
                    Ys.append(yy[:, None])
                Xs = [Xp[i][: len(y)] for i, y in zip(keep_t, Ys)]
                ws, oof_r, oof_r2, _ = _loo_ridge_fit(Xs, Ys, K_PCA, lam_rel)
                wn = ws / np.linalg.norm(ws, axis=1, keepdims=True)
                cos = {a: np.abs(wn @ axes_k[a]) for a in axes}
                best_axis = max(cos, key=lambda a: float(np.median(cos[a])))
                per_cand.append({
                    "candidate": "CONTROL_step_frac",
                    "is_control": True,
                    "best_axis": best_axis,
                    "cos_best_axis_median": float(np.median(cos[best_axis])),
                    "cos_per_axis_median": {a: float(np.median(cos[a])) for a in axes},
                    "cos_ceiling": ceiling,
                    "oof_pearson": float(oof_r),
                    "p_search_corrected": None,
                    "n_traj_used": len(keep_t),
                    "why": "step_frac = t/(T-1) 正是 reasoning_deep 的定义分组。"
                           "它在这里是**尺子**：若 rep_frac_topk 对 reasoning 的对齐"
                           "明显高于本行，说明 rep_frac_topk 携带了位置斜坡之外的"
                           "信息；若两者相当，那结论不成立。",
                })
                per_cand.sort(key=lambda c: -c["cos_best_axis_median"])
                rows.append({"delta": delta, "lambda_rel": lam_rel,
                             "n_traj_used": len(keep_t), "candidates": per_cand})
                # 判决行：rep_frac_topk 对 reasoning 的对齐 vs step_frac 对照
                def get(nm):
                    return next((c for c in per_cand if c["candidate"] == nm), None)
                ctl = get("CONTROL_step_frac")
                rft = get("rep_frac_topk")
                verdict = "?"
                if ctl and rft:
                    a = rft["cos_per_axis_median"]["reasoning"]
                    b = ctl["cos_per_axis_median"]["reasoning"]
                    verdict = (f"rep={a:.3f} vs step_frac对照={b:.3f} "
                               f"→ {'超出对照' if a > b else '不超出对照(不成立)'}")
                top = per_cand[0]
                print(f"L{layer} Δ={delta:<4d} lam={lam_rel:<6g} best={top['candidate']:<18s}"
                      f" -> {top['best_axis']:<10s} cos={top['cos_best_axis_median']:.3f}"
                      f"  p_search={top['p_search_corrected']}  oofR={top['oof_pearson']:+.3f}"
                      f"  | {verdict}", flush=True)
        res["per_layer"][str(layer)] = {
            "rows": rows, "n_traj": n_traj,
            "n_steps_total": int(traj_T.sum()),
            "pca_var_cum": var_cum, "cos_ceiling": ceiling,
            "trajectories": meta_t, "sec": round(__import__("time").time() - tl, 1),
        }
        del Xp

    res["elapsed_sec"] = round(__import__("time").time() - t0, 1)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
