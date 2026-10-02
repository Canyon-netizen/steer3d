#!/usr/bin/env python3
"""主张四的充分性检验：steering 方向是不是某个可观测量的**线性读出方向**。

## 为什么现有装置测不了充分性

`heldout_lag.py` 算的是 `rho(u·h_t, obs_{t+Δ})`。它只给出**必要条件**：
「方向上有信号」不足以说明「方向就是这个量的实现」——任何与该方向相关的量都相关。

而且它踩了两个已知的坑：

1. **二元标签的基率上限**。对稀有二元标签 Spearman 量的不是方向而是基率，
   上限 `d·sqrt(p(1-p))`。confidence/caution 只能改用 AUC。
2. **逐步观测量对 t 循环**。`step_frac` = t/(T−1) 是步号的确定函数。

## 这个脚本换成什么

不问「相关吗」，问「**方向是不是读出方向**」：

    留一轨迹的岭回归（在 PCA 子空间里）    w_{-i} = argmin ‖X_{-i}w − y_{-i}(t+Δ)‖² + λ‖w‖²
    然后量                                cos(w_{-i}, u)

若某可观测量的**跨轨迹线性读出方向**就是 u 且超出随机方向零假设，
那才叫「这个方向的实现是它的线性读出」——这是充分性的一个可检验形式。

## 六个设计决定，每个拆掉一个已知陷阱

1. **Δ 真正进配对**：`h_t` 对 `y_{t+Δ}`。第一版把 Δ 漏在回归外面，
   三个 Δ 的 w 完全相同 —— 自检抓到的。Δ 若不进配对，
   「曲线随 Δ 平坦」会被误读成「方向编码持续状态」，那是凭空造出来的结论。
2. **留一的是轨迹**：轨迹内步与步强自相关，留一步会把测试集泄漏进训练集。
   且必须**每折重新解 w**；用全量解再回头评估不是样本外。
3. **中心化**：残差流有巨大恒定分量（rogue dimension），不中心化的探针
   只会找回平均方向。`cos(w, mean_hidden_dir)` 单独报。
4. **PCA 降到 k 维**（只为算得动，不是为了好看）：所以必须同时报
   **天花板 `cos(u, P_k)`** —— 降维把 u 削掉多少是可测量的上限。
   测到的 cos 若贴天花板，含义是「可观测量的读出方向已完全解释」，
   而**不是**「探针分辨不出 u 和别的方向」。这两种解释必须分开写。
5. **零假设取搜索后的最大值**：200 个随机单位方向，统计量取
   `max over 可观测量` 的 |cos|。分母写进输出。
6. **时间打乱对照**：目标在轨迹内按步打乱，cos 应塌到噪声地板。
   真实与打乱同量级 ⇒ 探针什么也没找到。

## 装置自检（硬闸门）

`toy_selfcheck()` 构造已知答案的合成数据 `h = a·y + b·z + 噪声`（外加一个
很大的恒定分量来验中心化）。要求：

- Δ=0 找回 a：cos(a) > 0.8
- Δ 增大 cos(a) **单调下降**且 Δ 大时塌到噪声地板 1/sqrt(k) 附近
- 任何 Δ 都不贴平均方向、不贴干扰因子 b

自检不过就 `abort`，不碰真数据。
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

# macOS Accelerate 的 BLAS 会在正常的 float64 matmul 上抛伪的
# "divide by zero / overflow encountered in matmul" 告警而结果正确。
# 所以：静默告警 + 每步显式 finite 断言。断言才是真正的防线。
_ERR = dict(all="ignore")


def _chk(a, what):
    if not np.all(np.isfinite(a)):
        raise FloatingPointError(f"{what} 出现非有限值（dtype={a.dtype}）")
    return a


ROOT = Path("/Users/zhourui/code/steer3d")
NPZ_DIR = ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime"
VEC_DIR = ROOT / "backend/examples/output/steering_vectors"
OUT = ROOT / ".cache/rolesverify/probe_readout.json"

AXES = {  # 4 条独立轴（confidence_down≡−confidence_up, reasoning_shallow≡−reasoning_deep）
    "confidence": "confidence_up",
    "caution": "caution",
    "creativity": "creativity",
    "reasoning": "reasoning_deep",
}
# 每条轴是由哪个分组谓词做 diff_of_means 造出来的。
# **这一段不许凭记忆填** —— 它逐字来自 backend/examples/output/steering_vectors/
# steering_vectors.json 的 positive_group / negative_group 字段。
AXIS_GROUPING_SOURCE = {
    "confidence": ("low-entropy tokens (p30)", "high-entropy tokens (p75)"),
    "caution": ("self-check tokens (wait/actually/...)", "ordinary generated tokens"),
    "creativity": ("tokens inside <think>", "tokens outside <think>"),
    "reasoning": ("last 25% of long trajectories", "first 25% of long trajectories"),
}
# Δ=0 时与「熵」这个可观测量**按构造同源**的那条轴。
# 它在 Δ=0 命中不是发现，而是装置的阳性对照：不命中就说明装置坏了。
CIRCULAR_AT_DELTA0 = {"entropy": "confidence"}
LAYERS = [12, 14, 20]
DELTAS = [0, 1, 20, 100, 400]
STRIDE = 2
K_PCA = 256
LAMBDA_REL = [1e-4, 1e-3, 1e-2, 1e-1]
N_RANDOM = 200
SEED = 20261003
OBSERVABLES = ["entropy"]
# 两种目标处理。`failed_obs_forensics` 查出：creativity 那行的 +0.74 几乎
# 全是**轨迹间**差（轨迹间 rho 0.8655 / 轨迹内 0.1843），而且一条「轨迹编号
# 奇偶」的语义假观测量就复现出 0.7239。⇒ 必须把那把刀用在自己的结果上：
# `demean_within_traj` 把每条轨迹的目标减去它自己的均值，于是探针**只能**
# 解释轨迹内偏离。留一轨迹本该已经挡住轨迹间均值，但「本该」不是证据。
TARGET_TRANSFORMS = ["raw", "demean_within_traj"]


# ================================================================ 装置自检
def _loo_ridge_fit(Xs, Ys, k, lam_rel):
    """Xs/Ys 是按轨迹分组的已配对数据。返回每折 w、样本外 Pearson 与 R²。

    主判据是 **Pearson 而不是 R²**：各轨迹的 y 尺度可以差一个量级
    （toy 里 y 是随机游走，真实数据里 entropy 的轨迹间水平也不同），
    方向学对了但折外标定必然崩，于是 R² 大幅为负而与对不对无关。
    Pearson 对折间尺度/偏移不变，量的才是「方向能不能预测」。
    R² 仍然报，但它的解读要带上这个前提。
    """
    n_traj = len(Xs)
    d = Xs[0].shape[1]
    for i, (x, y) in enumerate(zip(Xs, Ys)):
        if len(x) == 0 or len(y) == 0:
            raise ValueError(f"第 {i} 条轨迹配对后为空（Δ 过大把短轨迹吃光了）")
    xm = np.mean([x.mean(axis=0) for x in Xs], axis=0)
    ym = np.mean([y.mean(axis=0) for y in Ys], axis=0)
    Gs, Bs = [], []
    with np.errstate(**_ERR):
        for x, y in zip(Xs, Ys):
            xc = x - xm
            yc = y - ym
            Gs.append(_chk(xc.T @ xc, "Gram"))
            Bs.append(_chk(xc.T @ yc, "cross"))
        G = sum(Gs)
        B = sum(Bs)
        ws, per_fold_r, preds, tgts = [], [], [], []
        num = den = 0.0
        for i in range(n_traj):
            Gi, Bi = G - Gs[i], B - Bs[i]
            lam = lam_rel * np.trace(Gi) / d
            wi = _chk(np.linalg.solve(Gi + lam * np.eye(d), Bi)[:, 0], "w_fold")
            ws.append(wi)
            # 这一折的真·样本外：w_{-i} 在没见过的轨迹 i 上评估
            xi, yi = Xs[i] - xm, Ys[i] - ym
            pred = _chk(xi @ wi, "pred")
            num += float(((pred - yi) ** 2).sum())
            den += float((yi**2).sum())
            preds.append(pred.ravel())
            tgts.append(yi.ravel())
            sp = float(np.std(pred)) * float(np.std(yi))
            per_fold_r.append(
                float(((pred - pred.mean()) * (yi - yi.mean())).mean() / sp)
                if sp > 0 else float("nan")
            )
    P_, T_ = np.concatenate(preds), np.concatenate(tgts)
    denom = float(np.std(P_)) * float(np.std(T_))
    oof_pearson = float(((P_ - P_.mean()) * (T_ - T_.mean())).mean() / denom) \
        if denom > 0 else float("nan")
    return np.array(ws), oof_pearson, 1.0 - num / den, per_fold_r


def toy_selfcheck(seed=7):
    rng = np.random.default_rng(seed)
    d, k, n_traj, T, n_obs = 96, 32, 30, 400, 1
    a = rng.normal(size=d)
    a /= np.linalg.norm(a)
    b = rng.normal(size=d)
    b -= a * (a @ b)
    b /= np.linalg.norm(b)

    raw = []
    for _ in range(n_traj):
        y = np.cumsum(rng.normal(size=(T, n_obs)), axis=0) * 0.5   # 随机游走：相关长度有限
        z = rng.normal(size=(T, n_obs))
        h = np.outer(y[:, 0], a) + np.outer(z[:, 0], b) * 0.7
        h += rng.normal(size=(T, d)) * 0.15
        h += 5.0                                                   # 恒定分量：验中心化
        raw.append((h.astype(np.float64), y.astype(np.float64)))

    with np.errstate(**_ERR):
        xm = np.mean([h.mean(axis=0) for h, _ in raw], axis=0)
        C = np.zeros((d, d))
        for h, _ in raw:
            hc = h - xm
            C += hc.T @ hc
        C /= C.trace()
        evals, evecs = np.linalg.eigh(C)
        order = np.argsort(evals)[::-1]
        P = evecs[:, order[:k]]                                     # (d, k)
        var_cum = float(np.sort(evals)[::-1][:k].sum())

    mean_dir = xm / np.linalg.norm(xm)
    noise_floor = 1.0 / np.sqrt(k)
    cases = []
    for delta in (0, 20, 100, 300):
        with np.errstate(**_ERR):
            Xs = [_chk((h - xm) @ P, "toy proj") for h, _ in raw]
        Ys = [(y[delta:] if delta > 0 else y).astype(np.float64) for _, y in raw]
        Xs = [x[: len(y)] for x, y in zip(Xs, Ys)]
        ws, oof_r, oof_r2, _ = _loo_ridge_fit(Xs, Ys, k, 1e-4)
        # 投回原空间并归一化再比：这样天花板自动计入，而不是把它当成额外因子
        wd = _chk(ws @ P.T, "toy w back to d-space")
        wd = wd / np.linalg.norm(wd, axis=1, keepdims=True)
        cos_a = np.abs(wd @ a)
        cos_mean = np.abs(wd @ mean_dir)
        cos_b = np.abs(wd @ b)
        with np.errstate(**_ERR):
            ceil_a = float(np.linalg.norm(_chk(P.T @ a, "ceil")))
        cases.append({
            "delta": delta,
            "cos_true_a": float(np.median(cos_a)),
            "cos_interference_b": float(np.median(cos_b)),
            "cos_mean_dir": float(np.median(cos_mean)),
            "cos_ceiling_a": ceil_a,
            "oof_pearson": float(oof_r),
            "oof_r2": float(oof_r2),
        })

    c = [x["cos_true_a"] for x in cases]
    monotone = all(c[i] >= c[i + 1] - 0.02 for i in range(len(c) - 1))
    checks = {
        "delta0_recovers_a": bool(c[0] > 0.8),
        "delta0_not_mean_dir": bool(cases[0]["cos_mean_dir"] < 0.5),
        "delta0_not_interference": bool(cases[0]["cos_interference_b"] < 0.5),
        "cos_decreases_with_delta": bool(monotone),
        "large_delta_near_noise_floor": bool(c[-1] < max(2.5 * noise_floor, 0.45)),
        "oof_pearson_positive_at_delta0": bool(cases[0]["oof_pearson"] > 0.3),
    }
    return {
        "d": d, "k": k, "n_traj": n_traj, "T": T,
        "pca_var_cum": var_cum, "noise_floor_1_over_sqrt_k": noise_floor,
        "cases": cases, "checks": checks, "pass": all(checks.values()),
        "note": "主判据用样本外 Pearson：R² 对轨迹间尺度差敏感（toy 里 y 是随机游走，"
                "各轨迹幅度差一个量级），方向学对了 R² 也可能大幅为负",
    }


# ================================================================ 真数据
def load_axes():
    out = {}
    for name, fn in AXES.items():
        v = np.load(VEC_DIR / f"{fn}.npy").astype(np.float64).ravel()
        out[name] = v / np.linalg.norm(v)
    return out


def paired_sign_test(cos_axes):
    """同一个 w_fold 同时对四条轴打分，所以两条 cos 是**配对**的。

    逐折比较（`cos(a) > cos(b)` 的折数，精确二项检验，双侧，p0=0.5）比比较
    两个中位数强得多：它消掉了 w_fold 本身的方差 —— 同一个 w 偏好哪条轴
    是一个逐折的成对判断，不会被「这一折的 w 恰好比较长」带偏。
    """
    from math import comb

    names = list(cos_axes.keys())
    out = {}
    n = len(cos_axes[names[0]])
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            va, vb = np.asarray(cos_axes[a]), np.asarray(cos_axes[b])
            wins = int((va > vb).sum())
            ties = int((va == vb).sum())
            m = n - ties
            if m == 0:
                out[f"{a}>{b}"] = {"n": n, "wins": wins, "ties": ties,
                                   "p": 1.0, "note": "全为并列，无法判别"}
                continue
            k = min(wins, m - wins)
            tail = sum(comb(m, r) for r in range(k + 1)) / 2.0**m
            out[f"{a}>{b}"] = {
                "n_total": n, "n_usable": m, "wins": wins, "ties": ties,
                "frac": wins / m,
                "p_two_sided_exact_binomial": min(1.0, 2.0 * tail),
            }
    return out


def collect_layer(layer, stride):
    """只留标签齐全的步，返回 (Xs[list per traj] in PCA space, Ys_raw[list], meta)。"""
    files = sorted(NPZ_DIR.glob("*.npz"))
    H, meta = [], []
    for i, f in enumerate(files):
        d = np.load(f, mmap_mode="r")
        side = json.loads(f.with_suffix(".json").read_text())
        toks = side["tokens"]
        T = len(toks)
        h = np.asarray(d["hidden_states"][::stride, layer, :], dtype=np.float64)
        ent = np.asarray([t["entropy"] for t in toks], dtype=np.float64)[::stride]
        H.append(h)
        meta.append({"trajectory_id": side["trajectory_id"], "T": T,
                     "n_sampled": int(len(h))})
        del d
    return H, meta


def pca_basis(H, k):
    d = H[0].shape[1]
    with np.errstate(**_ERR):
        xm = np.mean([h.mean(axis=0) for h in H], axis=0)
        C = np.zeros((d, d))
        for h in H:
            hc = h - xm
            C += _chk(hc.T @ hc, "C")
        C /= np.trace(C)
        evals, evecs = np.linalg.eigh(C)
        order = np.argsort(evals)[::-1]
        ev = evals[order]
        return xm, evecs[:, order[:k]], ev


def main():
    t0 = time.time()
    res = {
        "schema": "steer3d.probe_readout/2",
        "question": "steering 方向是不是某可观测量的跨轨迹线性读出方向（充分性检验）",
        "config": {
            "axes": AXES, "layers": LAYERS, "deltas": DELTAS, "stride": STRIDE,
            "k_pca": K_PCA, "lambda_rel_sweep": LAMBDA_REL,
            "n_random": N_RANDOM, "seed": SEED, "observables": OBSERVABLES,
            "n_candidates": len(OBSERVABLES),
            "fold": "leave-one-trajectory-out，每折重解 w",
            "axis_grouping_source": AXIS_GROUPING_SOURCE,
            "circular_at_delta0": CIRCULAR_AT_DELTA0,
        },
        "selfcheck": toy_selfcheck(),
    }
    if not res["selfcheck"]["pass"]:
        res["abort"] = "装置自检未通过，拒绝跑真数据"
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
        print("SELFCHECK FAIL:", json.dumps(res["selfcheck"]["checks"],
                                            ensure_ascii=False))
        return 1
    print("selfcheck OK", flush=True)

    axes = load_axes()
    rng = np.random.default_rng(SEED)
    d = 2048
    rand = rng.normal(size=(N_RANDOM, d))
    rand /= np.linalg.norm(rand, axis=1, keepdims=True)

    res["per_layer"] = {}
    for layer in LAYERS:
        tl = time.time()
        res["per_layer"][str(layer)] = {}      # 目标诊断要写在这里，先建好
        H, meta = collect_layer(layer, STRIDE)
        n_traj = len(H)
        with np.errstate(**_ERR):
            xm, P, evals = pca_basis(H, K_PCA)
        var_cum = float(evals[:K_PCA].sum())
        # 天花板：u 有多少落在 PCA 子空间里。这是可测 cos 的上限，必须显式报。
        # cos(w_k, Pᵀu) / ‖Pᵀu‖ 就是原空间里 w 与 u 的真 cos，所以先归一化再比。
        with np.errstate(**_ERR):
            axes_k = {k: _chk(P.T @ v, f"L{layer} axis {k}")
                      for k, v in axes.items()}
            ceiling = {k: float(np.linalg.norm(x)) for k, x in axes_k.items()}
            axes_k = {k: x / ceiling[k] for k, x in axes_k.items()}
            mean_k = _chk(P.T @ (xm / np.linalg.norm(xm)), "mean_k")
            mean_k = mean_k / np.linalg.norm(mean_k)
            rand_k = _chk(rand @ P, "rand_k")            # (N_RANDOM, k)
        Xp = [_chk((h - xm) @ P, f"L{layer} proj") for h in H]
        del H

        ent = []
        for i in range(n_traj):
            f = sorted(NPZ_DIR.glob("*.npz"))[i]
            side = json.loads(f.with_suffix(".json").read_text())
            e = np.asarray([t["entropy"] for t in side["tokens"]], np.float64)[::STRIDE]
            ent.append(e)

        # 用 failed_obs_forensics 那把尺子先验证明目标是好的，而不是口头断言。
        # lag_invariance = obs(t+Δ) 与 obs(t) 恰好相等的步占比；它高说明这个
        # 量在 Δ 尺度上根本不变，探针测不到东西。entropy 在 Δ=20 应当很低。
        lag_inv = {}
        for delta in DELTAS:
            if delta == 0:
                lag_inv[str(delta)] = 0.0
                continue
            num = den = 0
            for e in ent:
                if len(e) - delta < 50:
                    continue
                num += int((e[delta:] == e[:-delta]).sum())
                den += len(e) - delta
            lag_inv[str(delta)] = num / den
        # ICC（轨迹间方差占比）：~0 表示逐步在变，~1 表示其实是轨迹级标签
        gm = float(np.mean([e.mean() for e in ent]))
        ss_between = sum(len(e) * (e.mean() - gm) ** 2 for e in ent)
        ss_total = sum(float(((e - gm) ** 2).sum()) for e in ent)
        icc = ss_between / ss_total if ss_total > 0 else float("nan")
        res["per_layer"][str(layer)]["target_diagnostics"] = {
            "icc_between_traj": icc,
            "lag_invariance_frac_equal": lag_inv,
            "n_traj_zero_within_traj_variance": int(sum(
                1 for e in ent if float(np.std(e)) == 0.0)),
            "max_n_distinct_per_traj": int(max(len(np.unique(e)) for e in ent)),
            "criterion": "ICC≈0 且 lag_invariance 低 ⇒ 目标是逐步量，可以拿来测",
        }
        td = res["per_layer"][str(layer)]["target_diagnostics"]
        print(f"--- L{layer} 目标诊断: ICC={icc:.4f} "
              f"lag_inv@20={lag_inv.get('20', float('nan')):.4f} "
              f"max_distinct/traj={td['max_n_distinct_per_traj']} "
              f"恒定轨迹={td['n_traj_zero_within_traj_variance']}/{n_traj}",
              flush=True)

        rows = []
        print(
            f"--- L{layer} 天花板 cos(u,P_{K_PCA}): "
            + " ".join(f"{k}={v:.3f}" for k, v in ceiling.items())
            + f"  pca_var_cum={var_cum:.4f}",
            flush=True,
        )
        for transform, delta in [
            (t, d) for t in TARGET_TRANSFORMS for d in DELTAS
        ]:
            # Δ 大会把短轨迹吃光。空数组的 y.mean() 是 NaN，会污染全局中心化，
            # 所以这里先按最小步数筛掉，并把**筛掉的数量记进分母**。
            MIN_STEPS = 50
            keep = [
                i for i in range(n_traj)
                if len(ent[i]) - (delta if delta > 0 else 0) >= MIN_STEPS
            ]
            Ys = []
            for i in keep:
                yy = (ent[i][delta:] if delta > 0 else ent[i]).astype(np.float64)
                if transform == "demean_within_traj":
                    # 减去这条轨迹自己的均值：探针此后**只能**解释轨迹内偏离，
                    # 轨迹间差一律被拿掉。这是把 failed_obs_forensics 的批评
                    # 用在自己结果上的那把刀。
                    yy = yy - yy.mean()
                Ys.append(yy[:, None])
            Xs = [Xp[i][: len(y)] for i, y in zip(keep, Ys)]
            for lam_rel in LAMBDA_REL:
                ws, oof_r, oof_r2, fold_r = _loo_ridge_fit(Xs, Ys, K_PCA, lam_rel)
                wn = ws / np.linalg.norm(ws, axis=1, keepdims=True)
                cos_axes_np = {k: np.abs(wn @ axes_k[k]) for k in axes}
                cos_axes = {k: v.tolist() for k, v in cos_axes_np.items()}
                cos_mean = np.abs(wn @ mean_k).tolist()
                cr = np.abs(wn @ rand_k.T)                 # (n_fold, n_random)
                rand_max = cr.max(axis=1)
                # 时间打乱对照
                rg2 = np.random.default_rng(SEED + 7)
                Ysh = [y[rg2.permutation(len(y))] for y in Ys]
                ws_s, oof_r_shuf, oof_r2_shuf, _ = _loo_ridge_fit(
                    Xs, Ysh, K_PCA, lam_rel
                )
                wn_s = ws_s / np.linalg.norm(ws_s, axis=1, keepdims=True)
                cos_shuf = {k: float(np.median(np.abs(wn_s @ axes_k[k])))
                            for k in axes}
                row = {
                    "delta": delta, "lambda_rel": lam_rel,
                    "target_transform": transform,
                    "n_traj_used": len(keep),
                    "n_traj_dropped_short": n_traj - len(keep),
                    "min_steps_per_traj": MIN_STEPS,
                    "n_steps_used": int(sum(len(y) for y in Ys)),
                    "cos_ceiling": ceiling,
                    "cos_axes_median": {k: float(np.median(v)) for k, v in cos_axes.items()},
                    "cos_axes_per_fold": cos_axes,
                    "paired_sign_test": paired_sign_test(cos_axes),
                    "cos_axes_per_fold_iqr": {
                        k: float(np.subtract(*np.percentile(v, [75, 25])))
                        for k, v in cos_axes.items()
                    },
                    "cos_with_mean_dir_median": float(np.median(cos_mean)),
                    "rand_cos_max_median": float(np.median(rand_max)),
                    "rand_cos_max_p95": float(np.percentile(rand_max, 95)),
                    "oof_pearson": float(oof_r),
                    "oof_pearson_per_fold_median": float(np.median(fold_r)),
                    "oof_r2": float(oof_r2),
                    "oof_pearson_shuffled_target": float(oof_r_shuf),
                    "oof_r2_shuffled_target": float(oof_r2_shuf),
                    "cos_axes_shuffled_target": cos_shuf,
                }
                row["p_per_axis"] = {
                    k: float((cr >= c[:, None]).mean())
                    for k, c in cos_axes_np.items()
                }
                # 装置的阳性对照：Δ=0 时，与该可观测量按构造同源的那条轴必须排第一。
                # 不排第一就说明装置坏了，后面所有 Δ 的结果都不必看。
                obs0 = OBSERVABLES[0]
                if delta == 0 and obs0 in CIRCULAR_AT_DELTA0:
                    want = CIRCULAR_AT_DELTA0[obs0]
                    top = max(cos_axes, key=lambda k: row["cos_axes_median"][k])
                    row["positive_control"] = {
                        "observable": obs0,
                        "expected_top_axis": want,
                        "expected_top_axis_reason": (
                            f"{want} = diff_of_means({AXIS_GROUPING_SOURCE[want][0]} vs "
                            f"{AXIS_GROUPING_SOURCE[want][1]})，与 {obs0} 按构造同源"
                        ),
                        "observed_top_axis": top,
                        "pass": bool(top == want),
                        "interpretation": (
                            "命中只说明装置能找回构造上就该找到的方向，"
                            "**不是**发现；非循环的证据在 Δ>0"
                        ),
                    }
                rows.append(row)
                print(
                    f"L{layer} [{transform[:6]}] Δ={delta:<4d} lam={lam_rel:<7g} "
                    f"oofR={oof_r:+.4f} oofRshuf={oof_r_shuf:+.4f} cos="
                    + " ".join(f"{k[:5]}:{v:.3f}" for k, v in row["cos_axes_median"].items())
                    + f" ceil={np.mean(list(ceiling.values())):.3f}"
                    + f" rmax={row['rand_cos_max_median']:.3f}",
                    flush=True,
                )
        res["per_layer"][str(layer)] = {
            "rows": rows, "n_traj": n_traj,
            "n_steps_total": int(sum(m["n_sampled"] for m in meta)),
            "pca_var_cum": var_cum, "cos_ceiling": ceiling,
            "mean_hidden_norm": float(np.linalg.norm(xm)),
            "trajectories": meta, "sec": round(time.time() - tl, 1),
        }
        del Xp

    res["elapsed_sec"] = round(time.time() - t0, 1)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
