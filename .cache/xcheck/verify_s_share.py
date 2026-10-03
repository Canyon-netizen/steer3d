"""独立复核完备性那张「S 解释份额」表 —— 内存受限版。

背景：完备性子任务（session lost，产物齐全）给出了 50 格的投影份额，
但它自带的 verify_independent.py 在本机被 OOM killer 杀掉（Killed: 9）。
文档 §4.7 已把那一列标注为「单一实现的读数」。这是那个缺口的补法。

本脚本不 import completeness.py 的任何东西，按它公开的口径自己重写一遍：
  L14 / stride=2 / attention_mask 过滤 / K=256 PCA / 留一轨迹岭回归
  λ ∈ {1e-3, 1e-2} 取 pooled rho 最大者 / 轨迹内去均值
  份额 = 1 − ρ(残差)² / ρ(全量)²
其中：
  Dfull = w @ P.T                 （折权重抬回 2048 维）
  Q     = 4 条命名轴的 Gram-Schmidt 正交基
  残差  = Dfull − (Dfull @ Q.T) @ Q
  残差预测 = 全量预测 − (逐 token 的 4 轴投影) @ 系数

诊断：本脚本上一版把跨折 pooled Pearson 打成 0.0000，而逐折中位是 0.68。
本版同时输出 pooled / 折内中位，并打印每折均值，用来定位那个矛盾。
"""
import json
import re
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
np.seterr(all="ignore")

ROOT = Path("/Users/zhourui/code/steer3d")
NPZ = sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz"))
VEC = ROOT / "backend/examples/output/steering_vectors"
SRC = ROOT / ".cache/completeness/completeness.json"
OUT = ROOT / ".cache/xcheck/s_share_verify.json"

LAYER, K, STRIDE, D_MODEL = 14, 256, 2, 2048
LAMBDAS = [1e-3, 1e-2]
MIN_STEPS = 50
AX = ["confidence", "caution", "creativity", "reasoning_deep"]
AX_FILE = {"confidence": "confidence_up", "caution": "caution",
           "creativity": "creativity", "reasoning_deep": "reasoning_deep"}
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b",
    re.IGNORECASE)

# ---------- 载入 ----------
H, side_tokens = [], []
dropped = 0
for f in NPZ:
    d = np.load(f, mmap_mode="r")
    hs = d["hidden_states"]
    am = np.asarray(d["attention_mask"]).ravel()
    if am.size != hs.shape[0]:
        raise AssertionError(f"{f.name}: mask 与 hidden 行数不等")
    keep = np.nonzero(am == 1)[0]
    dropped += hs.shape[0] - int(am.sum())
    keep = keep[::STRIDE]
    H.append(np.asarray(np.asarray(hs[:, LAYER, :])[keep], dtype=np.float64))
    side_tokens.append(json.loads(f.with_suffix(".json").read_text())["tokens"])
    del d
print("载入 %d 条 / %d 步（padding 丢 %d）" % (len(H), sum(len(h) for h in H), dropped))

# ---------- 观测量 + 四个定义式/尺子目标 ----------
z = np.load(ROOT / ".cache/rolesverify/obs_series.npz", allow_pickle=True)
names = [str(x) for x in z["names"]]
obs = z["obs"].astype(np.float64)
per = [[] for _ in z["traj_T"]]
for i, t in enumerate(z["traj_id"].astype(int)):
    per[t].append(obs[i])
series = [np.array(p) for p in per]
usable = {names[j]: [p[::STRIDE, j] for p in series] for j in range(len(names))}
control = {
    "entropy": [np.array([t["entropy"] for t in tk], np.float64)[::STRIDE] for tk in side_tokens],
    "in_think": [np.array([bool(t["is_in_think_block"]) for t in tk], np.float64)[::STRIDE]
                 for tk in side_tokens],
    "self_check_regex": [np.array([bool(SELF_CHECK_RE.search(t["token"] or "")) for t in tk],
                                  np.float64)[::STRIDE] for tk in side_tokens],
    "step_frac": [np.arange(len(tk), dtype=np.float64)[::STRIDE] /
                  max((len(tk) - 1) // STRIDE, 1) for tk in side_tokens],
}
TARGETS = list(usable.keys()) + list(control.keys())

# ---------- 轴 + 正交基 Q ----------
axes = {}
for a in AX:
    v = np.load(VEC / f"{AX_FILE[a]}.npy").astype(np.float64).ravel()
    axes[a] = v / np.linalg.norm(v)
Amat = np.array([axes[a] for a in AX])          # (4, 2048)，行 = 一条条轴


def gram_conditions(S):
    """逐行 Gram-Schmidt，Q 是**行正交基** (m, 2048)。
    注意 Q.T @ x 才是坐标 —— 源脚本用 Dfull @ Q.T，所以必须是行正交。"""
    m = S.shape[0]
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
        "Q": Q, "diag": dg,
        "orthonormality_err": float(np.abs(Q @ Q.T - np.eye(m)).max()),
        "cond_gram_schmidt": float(dg.max() / dg.min()),
        "cond_S": float(sv[0] / sv[-1]),
    }


GS = gram_conditions(Amat)
Q = GS["Q"]
print("cond(S) = %.4f  cond(GS) = %.4f  正交误差 = %.2e" % (
    GS["cond_S"], GS["cond_gram_schmidt"], GS["orthonormality_err"]))
print("  completeness.json 记 cond(S)=2.1595  cond(GS)=1.2009  err=4.44e-16")
assert Q.shape == (4, D_MODEL), Q.shape

# ---------- PCA ----------
xm = np.mean([h.mean(axis=0) for h in H], axis=0)
C = np.zeros((D_MODEL, D_MODEL))
for h in H:
    hc = h - xm
    C += hc.T @ hc
C /= np.trace(C)
evals, evecs = np.linalg.eigh(C)
P = evecs[:, np.argsort(evals)[::-1][:K]]
axes_k = {a: P.T @ axes[a] / np.linalg.norm(P.T @ axes[a]) for a in AX}
Xp, A = [], []
xmA = xm @ Amat.T
for h in H:
    hc = h - xm
    Xp.append(hc @ P)
    A.append(h @ Amat.T - xmA)
del H, C, evecs
print("PCA top-%d 累计方差 = %.7f" % (K, np.sort(evals)[::-1][:K].sum()))


# ---------- 留一轨迹岭回归 ----------
def pearson(p, t):
    p, t = np.asarray(p, np.float64).ravel(), np.asarray(t, np.float64).ravel()
    den = p.std() * t.std()
    if den == 0 or not np.isfinite(den):
        return float("nan")
    return float(((p - p.mean()) * (t - t.mean())).mean() / den)


def loo(Xs, Ys, lam_rel):
    n = len(Xs)
    d = Xs[0].shape[1]
    xmL = np.mean([x.mean(0) for x in Xs], 0)
    ymL = np.mean([y.mean(0) for y in Ys], 0)
    G = [(x - xmL).T @ (x - xmL) for x in Xs]
    B = [(x - xmL).T @ (y - ymL) for x, y in zip(Xs, Ys)]
    Gt, Bt = sum(G), sum(B)
    ws, pf, tg = [], [], []
    for i in range(n):
        Gi, Bi = Gt - G[i], Bt - B[i]
        w = np.linalg.solve(Gi + lam_rel * np.trace(Gi) / d * np.eye(d), Bi)[:, 0]
        ws.append(w)
        pf.append((Xs[i] - xmL) @ w)
        tg.append(Ys[i] - ymL)
    return (np.array(ws), np.concatenate(pf), np.concatenate(tg), pf, tg)


rows = {}
print()
print("%-18s %-6s %-7s %-7s %-8s %-8s %-9s" %
      ("target", "lam", "rho_fold", "rho_pool", "rho_res", "residfrac", "S-share"))
print("-" * 78)
for tn in TARGETS:
    src = usable[tn] if tn in usable else control[tn]
    keep = [i for i in range(len(src)) if len(src[i]) >= MIN_STEPS]
    sh = [v.copy() for v in src]
    Ys = [(sh[i] - sh[i].mean())[:, None] for i in keep]
    Xs = [Xp[i][: len(y)] for i, y in zip(keep, Ys)]
    best = None
    for lam in LAMBDAS:
        ws, PF, TR, pf, tg = loo(Xs, Ys, lam)
        r_pool = pearson(PF, TR)
        if best is None or r_pool > best[1]:
            best = (lam, r_pool, ws, pf, tg)
    lam, r_pool, ws, pf, tg = best
    r_fold = float(np.median([pearson(pf[k], tg[k]) for k in range(len(pf))]))

    Dfull = ws @ P.T
    dn = np.linalg.norm(Dfull, axis=1)
    coef = Dfull @ Q.T
    Rdir = Dfull - coef @ Q
    resid_frac = float(np.median(np.linalg.norm(Rdir, axis=1) / dn))

    pf_res, tg_res = [], []
    for k, i in enumerate(keep):
        pf_res.append(pf[k] - A[i][: len(Ys[k])] @ coef[k])
        tg_res.append(tg[k])
    PR, TR2 = np.concatenate(pf_res), np.concatenate(tg_res)
    r_res_pool = pearson(PR, TR2)
    r_res_fold = float(np.median([pearson(pf_res[k], tg_res[k]) for k in range(len(pf))]))

    def share(rf, rr):
        if not np.isfinite(rf) or abs(rf) < 1e-12:
            return None
        return 1 - rr ** 2 / rf ** 2

    wn = ws / np.linalg.norm(ws, axis=1, keepdims=True)
    cos_ax = {a: float(np.median(np.abs(wn @ axes_k[a]))) for a in AX}
    rows[tn] = {
        "lambda": lam, "rho_fold_median": r_fold, "rho_pooled": r_pool,
        "rho_residual_fold_median": r_res_fold, "rho_residual_pooled": r_res_pool,
        "residual_norm_fraction_median": resid_frac,
        "s_share_fold_median": share(r_fold, r_res_fold),
        "s_share_pooled": share(r_pool, r_res_pool),
        "cos_per_axis_median": cos_ax,
        "n_traj": len(keep), "n_steps": int(len(TR2)),
    }
    f = lambda v: ("%8.4f" % v) if v is not None else "     n/a"
    print("%-18s %-6.0e %-7.4f %-7.4f %-8.4f %-8.4f %-9s" % (
        tn, lam, r_fold, r_pool, r_res_fold, resid_frac,
        ("%.4f" % rows[tn]["s_share_fold_median"])
        if rows[tn]["s_share_fold_median"] is not None else "n/a"))

OUT.write_text(json.dumps({
    "recipe": {"layer": LAYER, "K": K, "stride": STRIDE, "lambdas": LAMBDAS,
               "min_steps": MIN_STEPS,
               "cond_S": GS["cond_S"], "cond_gram_schmidt": GS["cond_gram_schmidt"],
               "gram_schmidt_diag": GS["diag"].tolist(),
               "gram_schmidt_orthonormality_err": GS["orthonormality_err"],
               "pca_var_cum": float(np.sort(evals)[::-1][:K].sum()),
               "padding_dropped": dropped},
    "targets": rows,
}, ensure_ascii=False, indent=1))
print()
print("已写", OUT)
