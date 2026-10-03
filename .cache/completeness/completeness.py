#!/usr/bin/env python3
"""4 条命名轴是不是 layer 14 残差流里可解释逐 token 行为的完备描述？

跑法（仓库根目录 /Users/zhourui/code/steer3d）：

    python3 .cache/completeness/completeness.py            # 主分析（stride=2）-> completeness.json
    python3 .cache/completeness/completeness.py --stride 1 # 抽样复核（不复现 PROBE_AXES 的 0.412）
    python3 .cache/completeness/completeness.py --quick     # 只跑 Δ=0 / Δ=20

报告由 `make_report.py` 从 completeness.json 渲染，**数字不手写**。

## 复现的靶子（PROBE_AXES_REPORT.md §3–4，同装置：L14 / K=256 PCA / stride=2 /
轨迹内去均值 / 留一轨迹岭回归 / λ=0.01）

    confidence  → top1_prob_renorm  cos 0.412（位置对照 0.011）
    caution     → backtrack_topk    cos 0.308（位置对照 0.002）
    creativity  → backtrack_topk    cos 0.039（位置对照 0.057 ⇒ 测不出）
    reasoning_deep → rep_ngram4     cos 0.339（位置对照 0.628 ⇒ 测不出）
    CONTROL step_frac → reasoning_deep  cos 0.628 / 0.625(Δ=20) / 0.614(Δ=400)

这五个复现不出来就 `abort`，不继续（脚本里是硬断言）。

## 硬性纪律 → 实现位置
 1. attention_mask 过滤 padding：load_layer14()，过滤步数写进 padding_audit
 2. float16 → float32 存储、float64 参与统计：load_layer14()
 3. ICC 是区分逐步量/轨迹级标签的单数判据：icc_table()
 4. 冗余列当重复处理：redundancy_audit() + 搜索剔除 backtrack_frac
 5. 同格对照尺子：axis_readout_summary() 把每条轴的**定义式目标**与最优候选并排
 6. 循环性必须用语义无关假观测量证伪：fake_controls()
 7. 阴性结论带分母：null_stats() / indep_count() 都带 n_directions / 分位数
 8. 阈值基于实测噪声：全部阈值是 240 个随机单位方向零分布的分位数
 9. Pearson 而非 R² 作主判据：oof_pearson()；R² 只附带且带 caveat 字段
10. rho 分轨迹算再汇总：rho_split() 报 pooled / 轨迹内合并 / 轨迹间，异号标 Simpson
"""
import argparse
import json
import re
import sys
import time
import warnings
from pathlib import Path

import numpy as np

# FAILED_OBS_FORENSICS §10：本机 numpy 2.0 的 matmul 会发 divide-by-zero /
# overflow / invalid 假告警（已验证与 float64 逐位相同、数据本身无 inf/nan）。
# 这里统一屏蔽，但保留 _chk() 的有限性断言作为真检查。
np.seterr(all="ignore")
warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = Path("/Users/zhourui/code/steer3d")
NPZ_DIR = ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime"
VEC_DIR = ROOT / "backend/examples/output/steering_vectors"
SERIES = ROOT / ".cache/rolesverify/obs_series.npz"
META = ROOT / ".cache/rolesverify/obs_series_meta.json"
EXTRACT = ROOT / ".cache/rolesverify/obs_extract.json"
OUT = ROOT / ".cache/completeness/completeness.json"

LAYER, D_MODEL, K = 14, 2048, 256
DELTAS = [0, 1, 20, 100, 400]
LAMBDAS = [1e-3, 1e-2]
LAM_MAIN = 1e-2
SEED = 20261003
MIN_STEPS = 50
N_RAND, N_PCA, N_PERT = 240, 80, 80          # 合计 400 个方向
COS_SEP = 0.5
COS_SEP_ALT = [0.3, 0.5, 0.7]
OUTSIDE_RATIO = 0.5                          # 「基本在 4 条轴之外」的残差范数占比门槛

AXES = {"confidence": "confidence_up", "caution": "caution",
        "creativity": "creativity", "reasoning_deep": "reasoning_deep"}
AXIS_DEFINITION = {  # 逐字来自 steering_vectors.json 的 positive/negative_group
    "confidence": ("low-entropy tokens (p30)", "high-entropy tokens (p75)"),
    "caution": ("self-check tokens (wait/actually/…)", "ordinary generated tokens"),
    "creativity": ("tokens inside <think>", "tokens outside <think>"),
    "reasoning_deep": ("last 25% of long trajectories", "first 25% of long trajectories"),
}
AXIS_DEFINITION_TARGET = {"confidence": "entropy", "caution": "self_check_regex",
                          "creativity": "in_think", "reasoning_deep": "step_frac"}
REPRO_TARGETS = {
    "confidence": {"target": "top1_prob_renorm", "delta": 0, "lam": LAM_MAIN, "cos": 0.412,
                   "role": "已测读出方向", "control_cell": 0.011},
    "caution": {"target": "backtrack_topk", "delta": 0, "lam": LAM_MAIN, "cos": 0.308,
                "role": "已测读出方向", "control_cell": 0.002},
    "creativity": {"target": "backtrack_topk", "delta": 0, "lam": LAM_MAIN, "cos": 0.039,
                   "role": "对照组（< 位置对照 0.057 ⇒ 测不出）", "control_cell": 0.057},
    "reasoning_deep": {"target": "rep_ngram4", "delta": 0, "lam": LAM_MAIN, "cos": 0.339,
                       "role": "对照组（< 位置对照 0.628 ⇒ 测不出）", "control_cell": 0.628},
}
STEP_FRAC_REPRO = {0: 0.628, 20: 0.625, 400: 0.614}

_ERR = dict(all="ignore")   # FAILED_OBS_FORENSICS §10：本机 numpy matmul 假告警
# **必须是定义 caution 轴的那份正则**：`compute_steering_vectors.py` 的 11 词项版本。
# 它在这 48 条轨迹上给出 391 个正例 / 21 条轨迹零正例，与 FAILED_OBS_FORENSICS §5
# 记录的数字一致。`backend/core/model_runner.py` 的 8 词项版本只给 326 / 25，
# 用它会让 caution 的「定义式那一格」不再是真正的阳性对照。
_SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b", re.IGNORECASE)


def _chk(a, what):
    if not np.all(np.isfinite(a)):
        raise FloatingPointError(f"{what} 出现非有限值")
    return a


# ============================================================ 载入
def load_layer14(stride):
    H, meta = [], []
    dropped = 0
    for f in sorted(NPZ_DIR.glob("*.npz")):
        d = np.load(f, mmap_mode="r")
        side = json.loads(f.with_suffix(".json").read_text())
        hs = d["hidden_states"]
        T_rows = hs.shape[0]
        am = np.asarray(d["attention_mask"]).ravel()
        if am.size != T_rows:
            raise AssertionError(f"{f.name}: attention_mask 与 hidden_states 行数不等")
        keep = np.nonzero(am == 1)[0]                       # 显式 padding 过滤
        dropped += T_rows - int(am.sum())
        keep = keep[::stride]                              # 抽步在过滤之后
        h = np.asarray(np.asarray(hs[:, LAYER, :])[keep], dtype=np.float64)
        del hs
        if int(am.sum()) != len(side["tokens"]):
            raise AssertionError(f"{f.name}: 有效 token 数 {int(am.sum())} != sidecar "
                                 f"{len(side['tokens'])}（sidecar 未经 padding 过滤？）")
        if len(h) != len(keep):
            raise AssertionError(f"{f.name}: 抽步后行数 {len(h)} != 预期 {len(keep)}")
        H.append(_chk(h, f"L{LAYER} {f.name}"))
        meta.append({"trajectory_id": side["trajectory_id"], "T_rows": int(T_rows),
                     "T_valid": int(am.sum()), "n_sampled": int(len(h))})
        del d, h
    return H, meta, int(dropped)


def load_targets(stride):
    z = np.load(SERIES, allow_pickle=True)
    names = [str(x) for x in z["names"]]
    obs = z["obs"].astype(np.float64)
    traj_T = z["traj_T"].astype(np.int64)
    per = [[] for _ in traj_T]
    for i, t in enumerate(z["traj_id"].astype(np.int64)):
        per[t].append(obs[i])
    series = [np.array(p) for p in per]
    usable = {names[j]: [s[::stride, j] for s in series] for j in range(len(names))}

    control = {k: [] for k in ("entropy", "in_think", "self_check_regex", "step_frac")}
    for f in sorted(NPZ_DIR.glob("*.npz")):
        toks = json.loads(f.with_suffix(".json").read_text())["tokens"]
        n = len(toks)
        control["entropy"].append(np.array([t["entropy"] for t in toks], np.float64)[::stride])
        control["in_think"].append(
            np.array([bool(t["is_in_think_block"]) for t in toks], np.float64)[::stride])
        control["self_check_regex"].append(
            np.array([bool(_SELF_CHECK_RE.search(t["token"] or "")) for t in toks],
                     np.float64)[::stride])
        control["step_frac"].append(np.arange(n)[::stride] / max((n - 1) // stride, 1))
    return usable, control, {"usable_names": names, "n_usable": len(names),
                             "control_names": list(control), "n_trajectories": len(traj_T),
                             "column_order": json.loads(META.read_text())["column_order"]}


def _self_check_stride1():
    """stride=1 的 self_check 正例统计：用来解释 stride=2 抽步带来的差异。"""
    pos = zero = 0
    for f in sorted(NPZ_DIR.glob("*.npz")):
        toks = json.loads(f.with_suffix(".json").read_text())["tokens"]
        m = [bool(_SELF_CHECK_RE.search(t["token"] or "")) for t in toks]
        pos += int(sum(m))
        zero += int(sum(m) == 0)
    return {"pos": pos, "zero": zero}


def load_axes():
    out = {}
    for a, fn in AXES.items():
        v = np.load(VEC_DIR / f"{fn}.npy").astype(np.float64).ravel()
        assert v.size == D_MODEL
        out[a] = v / np.linalg.norm(v)
    return out


# ============================================================ 特征
def build_features(H, axes_full):
    """xm/P/Xp（PCA 空间）+ A（每条命名轴的逐轨迹中心化投影序列）。"""
    with np.errstate(**_ERR):
        xm = np.mean([h.mean(axis=0) for h in H], axis=0)
        C = np.zeros((D_MODEL, D_MODEL))
        for h in H:
            hc = h - xm
            C += _chk(hc.T @ hc, "C")
        C /= np.trace(C)
        evals, evecs = np.linalg.eigh(C)
        order = np.argsort(evals)[::-1]
        P = evecs[:, order[:K]]
        ev = evals[order]
        Amat = np.array([axes_full[a] for a in AXES])          # (4, 2048)
        xmA = xm @ Amat.T                                       # (4,)
        Xp, A = [], []
        for h in H:
            hc = h - xm
            Xp.append(_chk(hc @ P, "Xp"))
            A.append(_chk(h @ Amat.T - xmA, "A"))
    return xm, P, ev, Xp, A


# ============================================================ 统计
def _shift(per, delta):
    if delta == 0:
        return [v.copy() for v in per]
    out = []
    for v in per:
        n = len(v) - delta
        out.append(v[delta:delta + n] if n > 0 else v[:0])
    return out


def keep_traj(per, delta):
    return [i for i in range(len(per)) if len(per[i]) - delta >= MIN_STEPS]


def oof_pearson(p, t):
    p = np.asarray(p, np.float64).ravel()
    t = np.asarray(t, np.float64).ravel()
    den = float(np.std(p)) * float(np.std(t))
    if den == 0 or not np.isfinite(den):
        return float("nan")
    return float(((p - p.mean()) * (t - t.mean())).mean() / den)


def loo_ridge(Xs, Ys, lam_rel):
    """留一轨迹岭回归。Y 可 (n,1) 或 (n,T)。返回 ws, rho, pred, targ, 逐折 rho。"""
    n_traj = len(Xs)
    d = Xs[0].shape[1]
    for i, (x, y) in enumerate(zip(Xs, Ys)):
        if len(x) == 0 or len(y) == 0:
            raise ValueError(f"第 {i} 条轨迹配对后为空（Δ 过大）")
        if len(x) != len(y):
            raise AssertionError(f"第 {i} 条轨迹特征/目标行数不等 —— stride 没对齐")
    xm = np.mean([x.mean(axis=0) for x in Xs], axis=0)
    ym = np.mean([y.mean(axis=0) for y in Ys], axis=0)
    Gs, Bs = [], []
    with np.errstate(**_ERR):
        for x, y in zip(Xs, Ys):
            xc, yc = x - xm, y - ym
            Gs.append(_chk(xc.T @ xc, "Gram"))
            Bs.append(_chk(xc.T @ yc, "cross"))
        G, B = sum(Gs), sum(Bs)
        ws, preds, tgts, per_fold = [], [], [], []
        for i in range(n_traj):
            Gi, Bi = G - Gs[i], B - Bs[i]
            lam = lam_rel * np.trace(Gi) / d
            wi = _chk(np.linalg.solve(Gi + lam * np.eye(d), Bi), "w_fold")
            ws.append(wi[:, 0] if Bi.shape[1] == 1 else wi)
            pr = (Xs[i] - xm) @ wi
            preds.append(pr)
            tgts.append(Ys[i] - ym)
            per_fold.append(oof_pearson(pr, Ys[i] - ym))
    P_, T_ = np.concatenate(preds), np.concatenate(tgts)
    return np.array(ws), oof_pearson(P_, T_), P_, T_, per_fold


def rho_split(P_, T_, tid, keep):
    pooled = oof_pearson(P_, T_)
    Pc, Tc = P_.copy(), T_.copy()
    for i in keep:
        m = tid == i
        Pc[m] -= Pc[m].mean()
        Tc[m] -= Tc[m].mean()
    within = oof_pearson(Pc, Tc)
    pm = np.array([P_[tid == i].mean() for i in keep])
    tm = np.array([T_[tid == i].mean() for i in keep])
    between = oof_pearson(pm, tm)
    return {"pooled": pooled, "within_traj_merged": within, "between_traj": between,
            "simpson_flag": bool(np.isfinite(within) and np.isfinite(between)
                                 and within * between < 0)}


def oof_fixed(Zs, Ytraj):
    """固定方向（不拟合）的留一 Pearson。Zs: [(n_i, n_dir)]，Ytraj: [(n_i, n_targ)]。
    每 (折, 方向, 目标) 的斜率只用其余轨迹拟合。返回 (oof[n_dir,n_targ],
    per_traj_rho[n_traj,n_dir,n_targ], pid[n_steps])。"""
    n_traj, n_dir, n_targ = len(Zs), Zs[0].shape[1], Ytraj[0].shape[1]
    szz = np.zeros((n_traj, n_dir))
    szy = np.zeros((n_traj, n_dir, n_targ))
    syy = np.zeros((n_traj, n_targ))
    with np.errstate(**_ERR):
        for i in range(n_traj):
            Z, Y = Zs[i], Ytraj[i]
            szz[i] = (Z * Z).sum(axis=0)
            szy[i] = Z.T @ Y
            syy[i] = (Y * Y).sum(axis=0)
        tzz, tzy, tyy = szz.sum(0), szy.sum(0), syy.sum(0)
        # 留一斜率 b[i,k,t] = (总 szy − 本轨迹 szy) / (总 szz − 本轨迹 szz)
        b = (tzy[None, :, :] - szy) / (tzz[None, :] - szz)[:, :, None]
        spp, spy = (b * b) * szz[:, :, None], b * szy
        den_p = np.sqrt(spp.sum(0) * tyy[None, :])
        oof = np.where(den_p > 0, spy.sum(0) / np.where(den_p > 0, den_p, 1.0), np.nan)
        den_f = np.sqrt(spp * syy[:, None, :])
        pf = np.where(den_f > 0, spy / np.where(den_f > 0, den_f, 1.0), np.nan)
    pid = np.concatenate([np.full(len(z), i) for i, z in enumerate(Zs)])
    return oof, pf, pid


def icc_table(targets, min_steps=50):
    rows = {}
    for name, per in targets.items():
        keep = [i for i in range(len(per)) if len(per[i]) >= min_steps]
        y = [per[i] for i in keep]          # **不去均值**：SSB 要用原始逐轨迹值，
        n = np.array([len(v) for v in y], float)   # 先去均值会让所有轨迹均值=0、SSB≡0
        N, k = n.sum(), len(keep)
        grand = np.concatenate(y).mean()
        ssb = float((n * (np.array([v.mean() for v in y]) - grand) ** 2).sum())
        ssw = float(sum(((v - v.mean()) ** 2).sum() for v in y))
        msb, msw = ssb / (k - 1), ssw / (N - k)
        n0 = (N - (n ** 2).sum() / N) / (k - 1)
        icc1 = (msb - msw) / (msb + (n0 - 1) * msw) if (msb + (n0 - 1) * msw) > 0 else float("nan")
        zf = int(sum(1 for v in y if float(((v - v.mean()) ** 2).sum()) == 0.0))
        rows[name] = {
            "icc1_anova": float(icc1),
            "var_share_between_traj": float(ssb / (ssb + ssw)) if ssw + ssb > 0 else None,
            "n_traj_zero_variance": zf, "n_traj": k, "frac_traj_zero_variance": zf / k,
            "max_within_traj_distinct_values": int(max(len(np.unique(v)) for v in y)),
            "n_steps": int(N),
            "usable_as_stepwise": bool(zf / k < 0.2 and icc1 < 0.5),
        }
    return rows


def _abs_rho(x, y):
    return float(abs(np.corrcoef(x, y)[0, 1]))


def _abs_spearman(x, y):
    """obs_series_meta.json 的 redundancy_matrix 存的是 |Spearman|（它自己的
    `definition_pooled` 字段写明 '|Spearman rho| over all 69155 steps pooled'），
    但键名叫 `abs_rho_pooled`。本任务的统计量是线性探针的 Pearson，
    所以两列都要报 —— 秩高不等于线性高。"""
    try:
        from scipy.stats import spearmanr
        return float(abs(spearmanr(x, y).statistic))
    except ImportError:
        rx = np.argsort(np.argsort(x)).astype(float)
        ry = np.argsort(np.argsort(y)).astype(float)
        return float(abs(np.corrcoef(rx, ry)[0, 1]))


def redundancy_audit(targets, thresh=0.8):
    names = list(targets)
    flat = {n: np.concatenate(targets[n]) for n in names}
    pairs = {}
    for a, b in [("backtrack_topk", "backtrack_frac"),
                 ("top1_prob_renorm", "entropy")]:
        pe, sp = _abs_rho(flat[a], flat[b]), _abs_spearman(flat[a], flat[b])
        pairs[f"{a}__{b}"] = {
            "abs_pearson_pooled": pe, "abs_spearman_pooled": sp,
            "pearson_exceeds_0.8": pe > thresh, "spearman_exceeds_0.8": sp > thresh,
            "treatment": ("线性探针口径下视为重复，不作独立证据" if pe > thresh else
                          "秩相关高但线性相关低 ⇒ 对**线性**探针不是重复，"
                          "不能据此从搜索里剔除"),
            "cited_value_in_prior_reports": 0.965 if "backtrack" in a else 0.985,
            "cited_value_is_spearman": True}
    Mp = np.eye(len(names))
    Ms = np.eye(len(names))
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            Mp[i, j] = _abs_rho(flat[a], flat[b])
            Ms[i, j] = _abs_spearman(flat[a], flat[b])
    off = ~np.eye(len(names), dtype=bool)
    # (M > t).sum()//2 会把对角线的 1.0 也算进去，必须显式剔掉
    hot_p = [[names[i], names[j], float(Mp[i, j]), float(Ms[i, j])]
             for i in range(len(names)) for j in range(i + 1, len(names)) if Mp[i, j] > thresh]
    hot_s = [[names[i], names[j], float(Mp[i, j]), float(Ms[i, j])]
             for i in range(len(names)) for j in range(i + 1, len(names))
             if Ms[i, j] > thresh and Mp[i, j] <= thresh]
    return {"pairs": pairs, "names": names, "abs_pearson_matrix": Mp.tolist(),
            "abs_spearman_matrix": Ms.tolist(),
            "n_names": len(names), "threshold": thresh,
            "pairs_pearson_exceeding": hot_p,
            "pairs_spearman_exceeding_but_pearson_not": hot_s,
            "n_pairs_pearson_exceeding": len(hot_p),
            "n_pairs_spearman_exceeding_but_pearson_not": len(hot_s)}


def gram_conditions(S, names=None):
    m = S.shape[0]
    names = list(names) if names is not None else [f"v{i}" for i in range(m)]
    Q = np.zeros_like(S)
    dg = np.zeros(m)
    for j in range(m):
        v = S[j].copy()
        for i in range(j):
            v -= (Q[i] @ v) * Q[i]
        dg[j] = np.linalg.norm(v)
        Q[j] = v / dg[j]
    sv = np.linalg.svd(S, compute_uv=False)
    return {
        "gram_schmidt_diag": dg.tolist(),
        "gram_schmidt_orthonormality_err": float(np.abs(Q @ Q.T - np.eye(m)).max()),
        "condition_number_gram_schmidt": float(dg.max() / dg.min()),
        "singular_values": sv.tolist(),
        "condition_number_S": float(sv[0] / sv[-1]),
        "pairwise_abs_cos": {f"{names[i]}|{names[j]}": float(abs(S[i] @ S[j]))
                             for i in range(m) for j in range(i + 1, m)},
        "Q": Q,
    }


# ============================================================ 阶段 0 装置复现
def apparatus_repro(Xp, usable, control, axes_k, notes, stride, tol=0.02):
    out = {"tolerance_cos": tol, "rows": {}, "step_frac_ruler": {}, "pass": True}
    for ax, sp in REPRO_TARGETS.items():
        per = usable[sp["target"]]
        keep = keep_traj(per, sp["delta"])
        sh = _shift(per, sp["delta"])
        Ys = [(sh[i] - sh[i].mean())[:, None] for i in keep]
        Xs = [Xp[i][:len(y)] for i, y in zip(keep, Ys)]
        ws, rho, *_ = loo_ridge(Xs, Ys, sp["lam"])
        wn = ws / np.linalg.norm(ws, axis=1, keepdims=True)
        cos = {a: float(np.median(np.abs(wn @ axes_k[a]))) for a in axes_k}
        # 复现对象是**报告那一行的轴**在那一格上的余弦，不是该格的 argmax 轴
        got = cos[ax]
        other = max((v, a) for a, v in cos.items() if a != ax)
        ok = abs(got - sp["cos"]) <= tol
        out["rows"][ax] = {"target": sp["target"], "delta": sp["delta"], "lam": sp["lam"],
                           "claimed_cos": sp["cos"], "axis_of_report_row": ax,
                           "observed_cos": got, "abs_diff": abs(got - sp["cos"]),
                           "within_tol": bool(ok), "role": sp["role"],
                           "position_control_cell": sp["control_cell"],
                           "cos_per_axis_median": cos,
                           "strongest_other_axis_on_same_cell": other[1],
                           "strongest_other_axis_cos": other[0],
                           "cross_talk_flag": bool(other[0] > got),
                           "oof_pearson": rho, "n_traj": len(keep)}
        out["pass"] &= bool(ok)
    for d, want in STEP_FRAC_REPRO.items():
        src = control["step_frac"]
        keep = keep_traj(src, d)
        sh = _shift(src, d)
        Ys = [(sh[i] - sh[i].mean())[:, None] for i in keep]
        Xs = [Xp[i][:len(y)] for i, y in zip(keep, Ys)]
        ws, rho, *_ = loo_ridge(Xs, Ys, LAM_MAIN)
        wn = ws / np.linalg.norm(ws, axis=1, keepdims=True)
        got = float(np.median(np.abs(wn @ axes_k["reasoning_deep"])))
        ok = abs(got - want) <= tol
        out["step_frac_ruler"][f"delta{d}"] = {
            "claimed_cos": want, "observed_cos": got, "abs_diff": abs(got - want),
            "within_tol": bool(ok), "oof_pearson": rho, "is_positive_control": True}
        out["pass"] &= bool(ok)
    out["note"] = ("step_frac 行是**装置阳性对照**：step_frac = t/(T−1) 正是 reasoning_deep "
                   "的 positive_group（原文 last 25% of long trajectories）。")
    out["pca"] = notes
    out["stride"] = stride
    return out


# ============================================================ 方向采样
def sample_directions(axes_full, P, seed):
    rng = np.random.default_rng(seed)
    with np.errstate(**_ERR):
        R = rng.normal(size=(N_RAND, D_MODEL))
        R /= np.linalg.norm(R, axis=1, keepdims=True)
        Dp = np.array([P[:, i] for i in range(N_PCA)])
        Dp *= rng.choice([-1.0, 1.0], size=N_PCA)[:, None]     # 主方向符号任意
        Dp /= np.linalg.norm(Dp, axis=1, keepdims=True)
        Dx, pn = [], []
        per_axis = N_PERT // len(axes_full)
        for a, v in axes_full.items():
            for _ in range(per_axis):
                sig = float(rng.choice([0.3, 0.6, 1.0]))
                g = rng.normal(size=D_MODEL)
                g /= np.linalg.norm(g)
                u = v + sig * g
                Dx.append(u / np.linalg.norm(u))
                pn.append(f"{a}@{sig}")
    D = np.vstack([R, Dp, np.array(Dx)])
    kinds = ["random"] * N_RAND + ["pca_top"] * N_PCA + ["axis_perturbed"] * len(Dx)
    assert D.shape == (N_RAND + N_PCA + N_PERT, D_MODEL), D.shape
    return D, kinds, pn


# ============================================================ 阶段 4 读出 + 投影
def readout_block(Xp, A, P, per, target, delta, axes_full, axes_k, Q, split_tol=None):
    keep = keep_traj(per, delta)
    # Ys 必须按 keep 取，不能对全部轨迹算完再 zip —— Δ 大到有短轨迹掉出 keep 时
    # zip 会把第 i 条轨迹的特征配到第 i 条目标上（长度不等时被断言挡住，
    # 长度恰好相等时就是静默错位）。
    sh = _shift(per, delta)
    Ys = [(sh[i] - sh[i].mean())[:, None] for i in keep]
    Xs = [Xp[i][:len(y)] for i, y in zip(keep, Ys)]
    assert all(len(a) == len(b) for a, b in zip(Xs, Ys))
    best = None
    for lam in LAMBDAS:
        ws, rho, P_, T_, _ = loo_ridge(Xs, Ys, lam)
        if best is None or rho > best[1]:
            best = (lam, rho, ws, P_, T_)
    lam, rho, ws, P_, T_ = best
    wn = ws / np.linalg.norm(ws, axis=1, keepdims=True)
    cos_ax = {a: float(np.median(np.abs(wn @ axes_k[a]))) for a in axes_k}

    Dfull = ws @ P.T                                    # (n_fold, 2048)
    dn = np.linalg.norm(Dfull, axis=1)
    Dn = Dfull / dn[:, None]
    Dn = Dn * np.sign(np.where(Dn[:, 0] < 0, -1.0, 1.0))[:, None]   # 只为可读性，cos 用绝对值
    coef = Dfull @ Q.T                                   # (n_fold, 4) 投影系数
    Rdir = Dfull - coef @ Q
    resid_frac = np.linalg.norm(Rdir, axis=1) / dn

    pid = np.concatenate([np.full(len(Ys[k]), i) for k, i in enumerate(keep)])
    pred_full, pred_res = [], []
    for k, i in enumerate(keep):
        # 关键：特征必须截到 Δ 之后的目标长度。Xp[i] 是全长的，不截会静默错位
        xi = Xp[i][:len(Ys[k])]
        ai = A[i][:len(Ys[k])]
        if len(xi) != len(Ys[k]) or len(ai) != len(Ys[k]):
            raise AssertionError(f"轨迹 {i} Δ={delta}: 特征/轴投影/目标行数不等")
        pf = xi @ ws[k]
        pred_full.append(pf)
        pred_res.append(pf - ai @ coef[k])
    PF, PR, TR = np.concatenate(pred_full), np.concatenate(pred_res), T_
    rho_f, rho_r = oof_pearson(PF, TR), oof_pearson(PR, TR)
    return {
        "target": target, "delta": delta, "lambda_rel": lam, "n_traj": len(keep),
        "n_steps": int(len(TR)),
        "oof_pearson_full": rho_f, "oof_pearson_residual_outside_S": rho_r,
        "oof_r2_full": float(1 - ((PF - TR) ** 2).sum() / (TR ** 2).sum()),
        "oof_r2_residual": float(1 - ((PR - TR) ** 2).sum() / (TR ** 2).sum()),
        "r2_caveat": "R² 对轨迹间尺度差极敏感，只附带不作主判据",
        "cos_per_axis_median": cos_ax,
        "cos_per_axis_per_fold_median": {a: float(np.median(np.abs(Dn @ axes_full[a])))
                                         for a in axes_full},
        "best_axis": max(cos_ax, key=cos_ax.get), "cos_best_axis": max(cos_ax.values()),
        "residual_norm_fraction_median": float(np.median(resid_frac)),
        "residual_norm_fraction_per_fold": resid_frac.tolist(),
        "pearson2_share_explained_by_S": float(1 - rho_r ** 2 / rho_f ** 2)
        if abs(rho_f) > 1e-12 else None,
        "rho_split_full": rho_split(PF, TR, pid, list(range(len(keep)))),
        "rho_split_residual": rho_split(PR, TR, pid, list(range(len(keep)))),
        "_keep": keep, "_ws": ws, "_PF": PF, "_PR": PR, "_TR": TR, "_pid": pid,
    }


# ============================================================ 阶段 5 互检
def mutual_check(Xp, A, P, usable, control, axes_full, axes_k, Q, axis_readout, delta=0):
    """每条轴用它自己的读出方向 d*(a)，被「其他 3 条」张成去投影。"""
    Smat = np.array([axes_full[a] for a in AXES])
    out = {"method": ("对每条轴 a：取它自己的最优读出方向 d*(a)（Δ=0，λ=0.01，K=256 PCA），"
                      "用**其余 3 条**轴的 Gram-Schmidt 正交基投影，看 |r|/|d*| 与残差样本外 Pearson"),
           "rows": {}}
    for a, tn in axis_readout.items():
        per = usable[tn] if tn in usable else control[tn]
        others = [b for b in AXES if b != a]
        col = [list(AXES).index(b) for b in others]
        Qm = np.array([Smat[c] for c in col])
        gm = gram_conditions(Qm, others)
        Qm = gm["Q"]
        Ai = [A[i][:, col] for i in range(len(A))]
        r = readout_block(Xp, Ai, P, per, tn, delta, axes_full, axes_k, Qm)
        Dfull = r["_ws"] @ P.T
        dn = np.linalg.norm(Dfull, axis=1)
        coef = Dfull @ Qm.T
        rf = np.linalg.norm(Dfull - coef @ Qm, axis=1) / dn
        out["rows"][a] = {
            "axis": a, "its_own_readout_target": tn, "delta": delta,
            "projected_out": others,
            "residual_norm_fraction_median": float(np.median(rf)),
            "residual_norm_fraction_per_fold": rf.tolist(),
            "oof_pearson_full": r["oof_pearson_full"],
            "oof_pearson_residual": r["oof_pearson_residual_outside_S"],
            "pearson2_share_explained_by_other3": r["pearson2_share_explained_by_S"],
            "condition_number_of_other3": gm["condition_number_gram_schmidt"],
        }
    return out


# ============================================================ 阶段 6 独立方向计数
def indep_count(Dfull, kinds, rho_by_tgt, tau_by_tgt, Q, tgt_names, deltas, axes_full,
                dstar=None):
    """贪心选出一组互相低余弦、且超出零分布尾部的方向。给出**下界**。

    dstar: {(target, delta): (oof_pearson, 2048 维单位方向)} —— 把「该观测量自己的
    最优读出方向」也放进候选池，否则计数只反映随机采样池，不反映最优解。
    """
    out = {"threshold_basis": "τ = 240 个随机单位方向 OOF |Pearson| 的分位数（逐目标逐 Δ）",
           "thresholds_reported": [95, 99],
           "cos_separation": COS_SEP, "cos_separation_alt": COS_SEP_ALT,
           "outside_S_ratio_threshold": OUTSIDE_RATIO,
           "method": ("对每个观测量：把候选方向按 |OOF Pearson| 降序贪心，"
                      "取到方向 d 后剔除所有与 d 的 |cos| ≥ 阈值的候选，重复直到候选空。"
                      "得到的是**互相近正交的可读方向数的下界**（只搜了这么多方向，"
                      "且贪心不等于最优子集）。"),
           "rows": {}}
    outside = np.linalg.norm(Dfull - (Dfull @ Q.T) @ Q, axis=1)
    for dn in deltas:
        for tn in tgt_names:
            rho = np.asarray(rho_by_tgt[(tn, dn)], float)
            kk = list(kinds)
            DD, outside_l = Dfull, outside
            if dstar and (tn, dn) in dstar:
                rr, dv = dstar[(tn, dn)]
                DD = np.vstack([Dfull, dv[None, :]])
                outside_l = np.concatenate(
                    [outside, [np.linalg.norm(dv - (dv @ Q.T) @ Q)]])
                rho = np.concatenate([rho, [rr]])
                kk = kk + ["dstar_fitted"]
            Cs = np.abs(DD @ DD.T)          # 加了 d* 之后必须重算
            nrm = np.linalg.norm(DD, axis=1)
            base = {"n_directions_pooled": int(DD.shape[0]), "n_random_in_null": N_RAND,
                    "pool_composition": {k: kk.count(k) for k in sorted(set(kk))},
                    "tau_p99_random": tau_by_tgt[(tn, dn)][99],
                    "tau_p95_random": tau_by_tgt[(tn, dn)][95]}
            for q in (99, 95):
                keep_i = np.nonzero(np.abs(rho) >= tau_by_tgt[(tn, dn)][q])[0]
                base[f"q{q}"] = {"n_exceeding_null": int(len(keep_i)),
                                 "frac_exceeding_null": len(keep_i) / DD.shape[0],
                                 "denominator": int(DD.shape[0])}
            for sep in COS_SEP_ALT:
                keep_i = np.nonzero(np.abs(rho) >= tau_by_tgt[(tn, dn)][99])[0]
                picked, pool = [], list(keep_i)
                while pool:
                    b = max(pool, key=lambda i: abs(rho[i]))
                    picked.append(b)
                    pool = [i for i in pool if Cs[b, i] < sep]
                base[f"sep{sep}"] = {
                    "n_exceeding_null": int(len(keep_i)),
                    "frac_exceeding_null": len(keep_i) / DD.shape[0],
                    "n_independent_directions": len(picked),
                    "n_outside_S": int(sum(1 for i in picked
                                           if outside_l[i] / nrm[i] >= OUTSIDE_RATIO)),
                    "outside_S_ratio_of_picked": [float(outside_l[i] / nrm[i])
                                                  for i in picked],
                    "kinds_of_picked": [kk[i] for i in picked],
                    "abs_rho_of_picked": [float(abs(rho[i])) for i in picked],
                    "cos_to_named_axes_of_picked": [
                        {a: float(abs(DD[i] @ v)) for a, v in axes_full.items()} for i in picked],
                }
            out["rows"][f"{tn}|delta{dn}"] = base
    return out


# ============================================================ 假观测量
def fake_observables(control, seed):
    rng = np.random.default_rng(seed + 1)
    ent, sf = control["entropy"], control["step_frac"]
    return {
        "fake_rev_ramp": {"semantics": "1 − step_frac：与真信号**语义相反**的 t 斜坡",
                          "series": [1.0 - v for v in sf]},
        "fake_sqrt_ramp": {"semantics": "√step_frac：t 的另一单调变换",
                           "series": [np.sqrt(v) for v in sf]},
        "fake_shuffle_within_traj": {
            "semantics": "轨迹内随机打乱真实 entropy（破坏时间-语义对应，保留边缘分布）",
            "series": [rng.permutation(v) for v in ent]},
        "fake_anti_entropy_perm": {
            "semantics": "轨迹内打乱 −entropy：检验 0.412 是否只是 |rho| 的方向无关性",
            "series": [rng.permutation(-v) for v in ent]},
        "fake_traj_const_rand": {
            "semantics": "按轨迹随机的常数（只有轨迹级结构，无逐步信息）",
            "series": [np.full(len(v), float(rng.normal())) for v in ent]},
        "fake_white": {"semantics": "纯 i.i.d. 高斯噪声（零假设地板）",
                       "series": [rng.normal(size=len(v)) for v in ent]},
    }


def _fit_dir(Xp, series, lam=LAM_MAIN):
    keep = keep_traj(series, 0)
    Ys = [(v - v.mean())[:, None] for v in series]
    Ys = [Ys[i] for i in keep]
    Xs = [Xp[i][:len(y)] for i, y in zip(keep, Ys)]
    ws, rho, *_ = loo_ridge(Xs, Ys, lam)
    return ws, keep, rho


def cross_score(Xp, ws, keep, series, delta=0):
    """方向由**另一个**观测量拟合得到，这里用它给 `series` 打分。
    w_{-i} 在没见过的轨迹 i 上评估 ⇒ 仍是样本外。"""
    preds, tgts = [], []
    for k, i in enumerate(keep):
        n = len(Xp[i]) - delta
        y = _shift(series, delta)[i][:n]
        if len(y) < n:
            return float("nan")
        preds.append(Xp[i][:n] @ ws[k])
        tgts.append(y - y.mean())
    return oof_pearson(np.concatenate(preds), np.concatenate(tgts))


def fake_controls(Xp, usable, control, fakes, axes_k):
    out = {"principle": ("循环性必须由**语义无关**的假观测量证伪。两个口径都做："
                         "(a) fit-real / score-fake：方向由真观测量拟合，去打语义无关的假信号；"
                         "(b) fit-fake：直接用假信号拟合。两者 |rho| 都与真信号相当 ⇒ 测的是假信号本身"),
           "note": "FAILED_OBS_FORENSICS §4 的协议是 (a)；比值应为 1.0 且符号相反"}

    # ---- (a) step_frac 尺子：fit step_frac → score 1−step_frac / sqrt(step_frac)
    ws_sf, keep_sf, rho_sf = _fit_dir(Xp, control["step_frac"])
    wn = ws_sf / np.linalg.norm(ws_sf, axis=1, keepdims=True)
    cos_sf = float(np.median(np.abs(wn @ axes_k["reasoning_deep"])))
    cs = [{"observable": "step_frac (fit & score)", "role": "真信号",
           "oof_pearson": rho_sf, "cos_reasoning_deep": cos_sf}]
    for nm in ("fake_rev_ramp", "fake_sqrt_ramp"):
        r = cross_score(Xp, ws_sf, keep_sf, fakes[nm]["series"])
        cs.append({"observable": nm, "role": "语义无关假信号（同一 d*，换打分目标）",
                   "protocol": "fit_real_score_fake", "semantics": fakes[nm]["semantics"],
                   "oof_pearson": r,
                   "abs_ratio_vs_real": abs(r) / abs(rho_sf) if rho_sf else None,
                   "sign_flipped": bool(np.sign(r) != np.sign(rho_sf))})
    # ---- (b) fit-fake：假信号自己拟合
    for nm in ("fake_rev_ramp",):
        w2, k2, r2 = _fit_dir(Xp, fakes[nm]["series"])
        w2n = w2 / np.linalg.norm(w2, axis=1, keepdims=True)
        cs.append({"observable": nm, "role": "语义无关假信号（自己拟合）",
                   "protocol": "fit_fake", "oof_pearson": r2,
                   "cos_reasoning_deep": float(np.median(np.abs(w2n @ axes_k["reasoning_deep"]))),
                   "abs_ratio_vs_real": abs(float(np.median(np.abs(w2n @ axes_k["reasoning_deep"]))))
                   / cos_sf if cos_sf else None})
    rev = [c for c in cs if c["observable"] == "fake_rev_ramp"
           and c.get("protocol") == "fit_real_score_fake"][0]
    out["step_frac_circularity"] = {
        "rows": cs,
        "reproduction_ratio_fake_rev_ramp_over_step_frac": rev["abs_ratio_vs_real"],
        "expected_ratio_per_FAILED_OBS_FORENSICS": 1.0000000000000004,
        "verdict": ("1−step_frac（语义相反的 t 斜坡）以等幅反号复现 step_frac 的全部信号 "
                    "⇒ 测到的是「随 t 单调漂移」，不含任何哪一端更晚的信息。"
                    "该行只能当装置尺子，不能当发现。")}

    # ---- confidence × 熵那一格的假观测量地板
    ws_c, keep_c, rho_c = _fit_dir(Xp, usable["top1_prob_renorm"])
    wn = ws_c / np.linalg.norm(ws_c, axis=1, keepdims=True)
    c_true = float(np.median(np.abs(wn @ axes_k["confidence"])))
    tests = [{"observable": "(真) top1_prob_renorm", "is_control": False,
              "oof_pearson": rho_c, "cos_confidence": c_true}]
    for fn in ("fake_shuffle_within_traj", "fake_anti_entropy_perm",
               "fake_traj_const_rand", "fake_white"):
        w2, k2, r2 = _fit_dir(Xp, fakes[fn]["series"])
        w2n = w2 / np.linalg.norm(w2, axis=1, keepdims=True)
        c2 = float(np.median(np.abs(w2n @ axes_k["confidence"])))
        cross = cross_score(Xp, ws_c, keep_c, fakes[fn]["series"])
        tests.append({"observable": fn, "is_control": True, "semantics": fakes[fn]["semantics"],
                      "oof_pearson_fit_fake": r2, "cos_confidence_fit_fake": c2,
                      "oof_pearson_score_fake_with_real_d": cross,
                      "reproduction_ratio_vs_real": c2 / c_true if c_true else None})
    out["confidence_circularity"] = {
        "rows": tests,
        "floor_cos_confidence_of_semantically_irrelevant_fakes":
            max(t["cos_confidence_fit_fake"] for t in tests if t["is_control"]),
        "verdict": ("confidence 的定义式就是 entropy 的 30/75 分位差（steering_vectors.json），"
                    "⇒ Δ=0 上 confidence×熵那一格是**构造恒等式**，只能当装置阳性对照。"
                    "语义无关的假观测量给出的 cos 地板见 "
                    "floor_cos_confidence_of_semantically_irrelevant_fakes，"
                    "0.412 比该地板高出一个量级 ⇒ 不是装置噪声，但仍是构造循环。")}
    return out


# ============================================================ 轴读出总表（对照尺子）
def axis_readout_summary(readout, tgt_names, deltas, all_targets):
    out = {"rule": ("每个高余弦格子都要问「这条轴自己的定义式在这个格子上是多少」。"
                    "定义式目标那一行是**阳性对照**，不是发现。"), "rows": {}}
    for a, dt in AXIS_DEFINITION_TARGET.items():
        rk = {d: readout.get(f"{dt}|delta{d}") for d in deltas}
        row = {"axis": a, "definition": AXIS_DEFINITION[a],
               "definition_target": dt, "cos_on_definition_target": {}}
        for d in deltas:
            r = rk.get(d)
            row["cos_on_definition_target"][f"delta{d}"] = (
                r["cos_per_axis_median"][a] if r else None)
            row.setdefault("oof_pearson_on_definition_target", {})[f"delta{d}"] = (
                r["oof_pearson_full"] if r else None)
        best_nd, best_td = None, None
        for d in deltas:
            for tn in tgt_names:
                r = readout.get(f"{tn}|delta{d}")
                if not r or tn == dt:
                    continue
                c = r["cos_per_axis_median"][a]
                if best_nd is None or c > best_nd:
                    best_nd, best_td = c, (tn, d)
        row["best_non_definition_cell"] = (
            {"observable": best_td[0], "delta": best_td[1], "cos": best_nd} if best_nd else None)
        row["definitional_ceiling_minus_best_non_definition"] = (
            max(v for v in row["cos_on_definition_target"].values() if v is not None)
            - best_nd) if best_nd else None
        # 最佳非定义式格与定义式目标之间的 Pearson：|ρ| 高 ⇒ 两格其实是同一个观测量，
        # 「定义式 − 最佳非定义式」这一列就没有意义（不是「定义式追不上」）。
        row["rho_between_two_cells"] = None
        if best_td:
            a_, b_ = dt, best_td[0]
            src = all_targets[a_] if a_ in all_targets else control[a_]
            src2 = all_targets[b_] if b_ in all_targets else control[b_]
            if len(src) == len(src2):
                row["rho_between_two_cells"] = _abs_rho(np.concatenate(src),
                                                        np.concatenate(src2))
        row["is_positive_control_cell"] = True
        out["rows"][a] = row
    return out


# ============================================================ 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()
    t0 = time.time()
    deltas = [0, 20] if a.quick else DELTAS
    res = {
        "schema": "steer3d.completeness/1",
        "question": "4 条命名轴是不是 layer 14 残差流里可解释逐 token 行为的完备描述？",
        "config": {"layer": LAYER, "k_pca": K, "stride": a.stride, "deltas": deltas,
                   "lambdas": LAMBDAS, "lambda_main": LAM_MAIN, "seed": a.seed, "axes": AXES,
                   "axis_definition": AXIS_DEFINITION,
                   "axis_definition_target": AXIS_DEFINITION_TARGET,
                   "n_random": N_RAND, "n_pca_top": N_PCA, "n_axis_perturbed": N_PERT,
                   "n_directions_total": N_RAND + N_PCA + N_PERT,
                   "cos_separation_threshold": COS_SEP, "cos_separation_alt": COS_SEP_ALT,
                   "outside_S_ratio_threshold": OUTSIDE_RATIO,
                   "main_statistic": "留一轨迹样本外 Pearson（不用 R²：对轨迹间尺度差敏感）",
                   "target_transform": "轨迹内去均值", "min_steps_per_traj": MIN_STEPS},
        "data_source": {"npz": str(NPZ_DIR), "obs_series": str(SERIES),
                        "obs_extract_summary": json.loads(EXTRACT.read_text())["summary"]},
    }

    print("[1/9] L14 载入（attention_mask 过滤）", flush=True)
    H, hmeta, dropped = load_layer14(a.stride)
    usable, control, tmeta = load_targets(a.stride)
    res["padding_audit"] = {
        "n_files": len(hmeta), "rows_dropped_by_attention_mask": dropped,
        "n_steps_total_valid": int(sum(m["T_valid"] for m in hmeta)),
        "n_rows_total": int(sum(m["T_rows"] for m in hmeta)),
        "n_steps_after_stride": int(sum(m["n_sampled"] for m in hmeta)),
        "stride": a.stride, "traj_example": hmeta[:3],
        "note": "attention_mask 全 1 ⇒ 实测过滤掉 0 步；过滤仍显式执行并断言与行数一致"}
    res["targets"] = tmeta
    _sf1 = _self_check_stride1()
    _sf1_zero = {"zero": _sf1["zero"], "pos": _sf1["pos"]}
    res["definition_target_diagnostics"] = {
        "self_check_regex_source": ("backend/examples/compute_steering_vectors.py 的 11 词项版本"
                                    "（定义 caution 轴的那一份）"),
        "self_check_positive_steps": int(sum(float(v.sum()) for v in control["self_check_regex"])),
        "self_check_zero_positive_traj": int(sum(
            1 for v in control["self_check_regex"] if float(v.sum()) == 0)),
        "self_check_zero_positive_traj_stride1": _sf1_zero["zero"],
        "self_check_positive_steps_stride1": _sf1_zero["pos"],
        "stride_note": ("本表用 stride=2 抽步后的序列；抽步会丢掉落在奇数步上的正例，"
                        "所以 stride=2 的零正例轨迹数比 stride=1 多。"
                        "两个数都在这里，不取一个。"),
        "n_traj": len(control["self_check_regex"]),
        "failed_obs_forensics_recorded": "391 个正例 / 21 条轨迹零正例",
        "in_think_zero_variance_traj": int(sum(
            1 for v in control["in_think"] if float(v.std()) == 0)),
        "caution_axis_n_positive_in_json": 379,
    }
    all_targets = {**usable, **control}

    print("[2/9] PCA + 轴", flush=True)
    axes_full = load_axes()
    with np.errstate(**_ERR):
        xm, P, evals, Xp, A = build_features(H, axes_full)
        axes_k = {a: _chk(P.T @ v, a) for a, v in axes_full.items()}
        ceiling = {a: float(np.linalg.norm(x)) for a, x in axes_k.items()}
        axes_k = {a: x / ceiling[a] for a, x in axes_k.items()}
    del H
    res["pca"] = {"k": K, "var_cum_top256": float(evals[:K].sum()),
                  "cos_ceiling_named_axes": ceiling,
                  "note": "cos_ceiling = 命名轴在 256 维 PCA 子空间保留的范数占比"}
    S = np.array([axes_full[a] for a in AXES])
    gs = gram_conditions(S, list(AXES))
    Q = gs.pop("Q")
    res["named_span_S"] = gs
    res["named_span_S"].update({"m_vectors": len(S),
                                "linearly_independent": bool(gs["condition_number_S"] < 1e6)})
    print("  var_cum=%.4f cond(S)=%.4f cond(GS)=%.4f"
          % (res["pca"]["var_cum_top256"], gs["condition_number_S"],
             gs["condition_number_gram_schmidt"]), flush=True)

    print("[3/9] ICC / 冗余", flush=True)
    res["icc_table"] = icc_table(all_targets)
    res["icc_table"]["_gate"] = ("合格 = 轨迹内零方差 <20% 且 ICC1<0.5。已知靶子："
                                 "entropy≈0.045 / self_check_regex≈0.006 / in_think≈0.955")
    res["redundancy_audit"] = redundancy_audit(all_targets)
    # **10 个可用观测量全部进搜索。** probe_axes.py 剔掉了 backtrack_frac，
    # 理由是 |ρ|(backtrack_topk, backtrack_frac)=0.965 —— 但那个 0.965 是
    # **Spearman**（见 redundancy_audit），同一对观测量在 **Pearson** 下只有 0.27。
    # 本任务的统计量是线性探针的 Pearson，所以按秩剔列不成立，全部保留。
    search_names = list(tmeta["usable_names"])
    res["effective_dof"] = {
        "n_usable_declared": len(tmeta["usable_names"]),
        "n_searched_observables": len(search_names),
        "all_usable_kept": True,
        "deviation_from_probe_axes": (
            "probe_axes.py 以 |ρ|(backtrack_topk,backtrack_frac)=0.965 为由把 "
            "backtrack_frac 剔出搜索、把有效自由度记成 9。实测该 0.965 是 Spearman；"
            "Pearson 只有 0.27。对线性探针而言二者不是重复，故本轮 10 个全留，"
            "有效自由度按 10 记。"),
        "top1_prob_renorm_treatment": (
            "与 entropy 的 Pearson |ρ| 也 >0.8，两者合计算一份证据（这一条在两种口径下都成立）"),
        "effective_dof_excluding_entropy_restate": len(search_names) - 1,
        "control_targets_not_in_search": list(control)}

    print("[4/9] 装置复现", flush=True)
    res["apparatus_repro"] = apparatus_repro(Xp, usable, control, axes_k,
                                             {"var_cum_top256": res["pca"]["var_cum_top256"],
                                              "cos_ceiling": ceiling}, a.stride)
    print("  pass =", res["apparatus_repro"]["pass"], flush=True)
    if not res["apparatus_repro"]["pass"]:
        res["abort"] = ("装置复现失败（0.412 / 0.308 / 0.628-0.614 对不上）。"
                        "按纪律先修装置，不继续。")
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
        print("ABORT:", res["abort"])
        return 1

    print("[5/9] 读出 + 投影检验", flush=True)
    tgt_names = search_names + list(control)
    readout = {}
    for d in deltas:
        for tn in tgt_names:
            per = usable[tn] if tn in usable else control[tn]
            r = readout_block(Xp, A, P, per, tn, d, axes_full, axes_k, Q)
            readout[f"{tn}|delta{d}"] = r
        print(f"  Δ={d} ok", flush=True)

    print("[6/9] 400 方向搜索 + 零分布", flush=True)
    D, kinds, pert_names = sample_directions(axes_full, P, a.seed)
    # 搜索空间 = 残差流 top-256 PCA 子空间。
    # 随机 2048 维单位方向 d 映到 PCA 空间是 Pᵀd ~ N(0, I₂₅₆)（因为 PᵀP = I），
    # 即**恰好**是这个搜索空间里的各向同性随机方向 ⇒ 零分布与搜索空间严格同分布。
    Dk = _chk(D @ P, "dirs_pca")
    Dk /= np.linalg.norm(Dk, axis=1, keepdims=True)
    Dfull = Dk @ P.T                              # 抬回 2048 维，用于与命名轴算余弦
    Dfull /= np.linalg.norm(Dfull, axis=1, keepdims=True)
    res["search_space"] = {
        "space": "layer14 残差流的 top-256 PCA 子空间（K=256, var_cum="
                 f"{res['pca']['var_cum_top256']:.4f}）",
        "why_ok": ("随机 2048 维单位方向映入该子空间后是各向同性高斯 ⇒ 零分布与搜索"
                   "空间同分布；命名轴在该子空间里保留 "
                   + ", ".join(f"{a}={c:.4f}" for a, c in ceiling.items()) + " 的范数"),
        "n_directions": int(D.shape[0]),
        "kinds": {"random": N_RAND, "pca_top": N_PCA, "axis_perturbed": N_PERT}}
    search = {}
    rho_by_tgt, tau99_by_tgt, tau95_by_tgt, tau_by_tgt = {}, {}, {}, {}
    for d in deltas:
        keep = [i for i in range(len(Xp)) if len(Xp[i]) - d >= MIN_STEPS]
        shifts = {tn: _shift(usable[tn] if tn in usable else control[tn], d)
                  for tn in tgt_names}
        Yt = []                                  # 每轨迹 (n_i, n_targ)
        for i in keep:
            n_i = len(Xp[i]) - d
            cols = []
            for tn in tgt_names:
                v = shifts[tn][i]
                if len(v) != n_i:
                    raise AssertionError(f"Δ={d} 轨迹 {i} 目标 {tn}: "
                                         f"长度 {len(v)} != 预期 {n_i}（stride/Δ 没对齐）")
                cols.append(v - v.mean())
            Yt.append(np.stack(cols, axis=1))
        Zs = [Xp[i][:len(Xp[i]) - d] @ Dk.T for i in keep]
        oof, per_traj, pid = oof_fixed(Zs, Yt)
        n_steps_used = int(sum(len(z) for z in Zs))
        rmask = np.array([k == "random" for k in kinds])
        nulls = {}
        for t, tn in enumerate(tgt_names):
            na = np.abs(oof[rmask, t])
            nulls[tn] = {"abs_rho_mean": float(na.mean()),
                         "abs_rho_p95": float(np.quantile(na, .95)),
                         "abs_rho_p99": float(np.quantile(na, .99)),
                         "abs_rho_max": float(na.max())}
            rho_by_tgt[(tn, d)] = oof[:, t]
            tau95_by_tgt[(tn, d)] = nulls[tn]["abs_rho_p95"]
            tau99_by_tgt[(tn, d)] = nulls[tn]["abs_rho_p99"]
            tau_by_tgt[(tn, d)] = {95: nulls[tn]["abs_rho_p95"],
                                    99: nulls[tn]["abs_rho_p99"]}
        outside = np.linalg.norm(Dfull - (Dfull @ Q.T) @ Q, axis=1)
        outside_ratio = outside / np.linalg.norm(Dfull, axis=1)
        entry = {"n_directions": int(D.shape[0]), "n_traj": len(keep),
                 "n_steps": n_steps_used, "n_random_directions_in_null": int(rmask.sum()),
                 "null_note": "零分布只用 240 个随机单位方向；PCA 主方向与轴扰动方向不是零假设",
                 "perturbed_dirs": {"n_per_axis": N_PERT // len(AXES),
                                    "sigmas": [0.3, 0.6, 1.0]},
                 "null": nulls, "per_target": {}}
        for t, tn in enumerate(tgt_names):
            col = oof[:, t]
            ac = np.abs(col)
            b = int(np.argmax(ac))
            om = outside_ratio >= OUTSIDE_RATIO
            bo = int(np.argmax(ac * om)) if om.any() else -1
            r = readout[f"{tn}|delta{d}"]
            entry["per_target"][tn] = {
                "is_definition_target_of": [ax for ax, t2 in AXIS_DEFINITION_TARGET.items()
                                            if t2 == tn],
                "oof_pearson_max": float(col[b]), "dir_max": kinds[b],
                "null_p95_random": nulls[tn]["abs_rho_p95"],
                "null_p99_random": nulls[tn]["abs_rho_p99"],
                "p_search_corrected": float((np.abs(oof[rmask, t]) >= ac[b]).mean()),
                "n_directions_searched": int(D.shape[0]),
                "n_random_directions_in_null": int(rmask.sum()),
                "oof_pearson_max_outside_S": float(col[bo]) if bo >= 0 else None,
                "dir_max_outside_S": kinds[bo] if bo >= 0 else None,
                "outside_S_ratio_of_that_dir": float(outside_ratio[bo]) if bo >= 0 else None,
                "p_search_corrected_outside_S":
                    float((np.abs(oof[rmask, t]) >= ac[bo]).mean()) if bo >= 0 else None,
                "n_directions_outside_S": int(om.sum()),
                "cos_of_max_dir_to_axes": {ax: float(abs(Dfull[b] @ axes_full[ax]))
                                            for ax in axes_full},
                "per_kind_max_abs_oof": {kk: float(np.abs(
                    col[[i for i, kk2 in enumerate(kinds) if kk2 == kk]]).max())
                    for kk in ("random", "pca_top", "axis_perturbed")},
                "per_traj_rho_of_max_dir_median": float(np.median(per_traj[:, b, t])),
                "per_traj_rho_positive_frac": float(np.nanmean(per_traj[:, b, t] > 0)),
            }
        search[f"delta{d}"] = entry
        print(f"  Δ={d} 搜索完成", flush=True)
    res["direction_search"] = search

    print("[7/9] 假观测量", flush=True)
    fakes = fake_observables(control, a.seed)
    res["fake_observable_controls"] = fake_controls(Xp, usable, control, fakes, axes_k)
    res["fake_observable_semantics"] = {k: v["semantics"] for k, v in fakes.items()}

    print("[8/9] 互检 + 独立方向计数", flush=True)
    axis_readout = {"confidence": "entropy", "caution": "backtrack_topk",
                    "creativity": "backtrack_topk", "reasoning_deep": "rep_ngram4"}
    axis_readout["confidence"] = "top1_prob_renorm"   # PROBE §3 声称的那一格
    res["axis_readout_targets"] = axis_readout
    res["mutual_redundancy"] = mutual_check(Xp, A, P, usable, control, axes_full,
                                            axes_k, Q, axis_readout, delta=0)
    res["axis_readout_summary"] = axis_readout_summary(readout, tgt_names, deltas,
                                                          all_targets)
    # 把每个观测量自己的最优读出方向也放进独立方向候选池
    dstar = {}
    for d in deltas:
        for tn in tgt_names:
            r = readout[f"{tn}|delta{d}"]
            dv = r["_ws"].mean(axis=0) @ P.T
            dstar[(tn, d)] = (r["oof_pearson_full"], dv / np.linalg.norm(dv))
    res["dstar_pool"] = {
        "note": "每个观测量自己的 LOO 最优读出方向（256 维权重的均值抬到 2048 维）"
                "也作为独立方向计数的一个候选",
        "n_added": len(dstar)}
    res["independent_direction_count"] = indep_count(
        Dfull, kinds, rho_by_tgt, tau_by_tgt, Q, tgt_names, deltas, axes_full, dstar)

    print("[9/9] 汇总", flush=True)
    res["headline"] = headline(res, readout, tgt_names, deltas, tau99_by_tgt, D, Q)
    res["readout"] = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                      for k, v in readout.items()}
    res["elapsed_sec"] = round(time.time() - t0, 1)
    res["environment"] = {"python": sys.version.split()[0], "numpy": np.__version__,
                          "device": "cpu"}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("wrote", OUT, f"({res['elapsed_sec']}s)")
    return 0


def headline(res, readout, tgt_names, deltas, tau99_by_tgt, D, Q):
    h = {"completeness_per_target": {}, "completeness_verdict": None}
    for d in deltas:
        for tn in tgt_names:
            r = readout[f"{tn}|delta{d}"]
            tau = tau99_by_tgt[(tn, d)]
            h["completeness_per_target"][f"{tn}|delta{d}"] = {
                "is_definition_target_of": [ax for ax, t in AXIS_DEFINITION_TARGET.items()
                                            if t == tn],
                "residual_norm_fraction": r["residual_norm_fraction_median"],
                "oof_pearson_full": r["oof_pearson_full"],
                "oof_pearson_residual": r["oof_pearson_residual_outside_S"],
                "pearson2_share_explained_by_S": r["pearson2_share_explained_by_S"],
                "residual_exceeds_null_p99": bool(
                    abs(r["oof_pearson_residual_outside_S"]) >= tau),
                "null_p99": tau, "n_random_in_null": N_RAND,
            }
    # 完备性判定：所有非定义式目标在 Δ=0 上都必须出现「残差仍超零分布」
    viol, ok = [], []
    for d in deltas:
        for tn in tgt_names:
            if tn in AXIS_DEFINITION_TARGET.values():
                continue
            e = h["completeness_per_target"][f"{tn}|delta{d}"]
            (viol if e["residual_exceeds_null_p99"] else ok).append(
                {"target": tn, "delta": d, "oof_pearson_residual": e["oof_pearson_residual"],
                 "null_p99": e["null_p99"],
                 "pearson2_share_explained_by_S": e["pearson2_share_explained_by_S"],
                 "residual_norm_fraction": e["residual_norm_fraction"]})
    h["non_definitional_targets_with_readable_residual"] = viol
    h["non_definitional_targets_with_residual_at_noise"] = ok
    h["n_non_definitional_cells"] = len(viol) + len(ok)
    h["n_non_definitional_cells_with_readable_residual"] = len(viol)
    h["n_directions_searched_per_cell"] = N_RAND + N_PCA + N_PERT
    # 独立方向计数的聚合（只用非定义式目标；定义式目标是阳性对照，不计入）
    idc = res["independent_direction_count"]
    sep = f"sep{res['config']['cos_separation_threshold']}"
    agg = {}
    for dn in deltas:
        rows = {k.split("|")[0]: v for k, v in idc["rows"].items()
                if k.endswith(f"delta{dn}")
                and k.split("|")[0] not in AXIS_DEFINITION_TARGET.values()}
        vals = [r[sep]["n_independent_directions"] for r in rows.values()]
        outs = [r[sep]["n_outside_S"] for r in rows.values()]
        agg[f"delta{dn}"] = {
            "n_observables": len(rows),
            "n_directions_pooled": list(rows.values())[0]["n_directions_pooled"],
            "n_random_in_null": list(rows.values())[0]["n_random_in_null"],
            "independent_min": int(min(vals)), "independent_max": int(max(vals)),
            "independent_median": float(np.median(vals)),
            "outside_S_min": int(min(outs)), "outside_S_max": int(max(outs)),
            "outside_S_median": float(np.median(outs)),
            "per_observable": {k: r[sep]["n_independent_directions"] for k, r in rows.items()},
            "per_observable_outside_S": {k: r[sep]["n_outside_S"] for k, r in rows.items()},
        }
    h["independent_direction_summary"] = agg
    h["independent_direction_lower_bound_statement"] = (
        f"候选池 = {res['config']['n_directions_total']} 个采样方向 + 1 个该观测量自己的最优读出方向；"
        f"门槛 = 240 个随机方向 OOF |Pearson| 的 p99；去重 = 贪心取 |cos| < "
        f"{res['config']['cos_separation_threshold']}。"
        f"在 Δ={deltas[0]} 上，10 个非定义式观测量每一个都还剩至少 "
        f"{agg[f'delta{deltas[0]}']['outside_S_min']} 个互相近正交、"
        f"且落在 4 条命名轴张成之外的可读方向（下界），中位数 "
        f"{agg[f'delta{deltas[0]}']['outside_S_median']:.1f} 个。")
    h["completeness_verdict"] = (
        "不完备" if viol else
        "在本次搜索的分母下未见不完备证据（{} 个非定义式目标 × {} 个 Δ 全部落在零分布内）"
        .format(len(viol) + len(ok), len(deltas)))
    return h


if __name__ == "__main__":
    sys.exit(main())
