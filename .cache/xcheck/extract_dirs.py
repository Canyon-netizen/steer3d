"""抽出留一轨迹读出方向，供后续分析反复用（不重载 9 GB npz）。

为什么要缓存：`verify_s_share.py` 每次跑都要 mmap 读 48 个 npz（约 3 分钟），
而「轴外方向是什么」这个问题要来回试好几个切法。
所以这一支只做一次重活，把中间量落到 .cache/xcheck/dir_cache/。

口径与 verify_s_share.py 逐字相同（那一支已与 completeness.json 复现到 4 位小数）：
  L14 / stride=2 / attention_mask 过滤 / K=256 PCA / 留一轨迹岭回归
  λ ∈ {1e-3, 1e-2} 取 pooled rho 最大者 / 目标按轨迹去均值
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
CACHE = ROOT / ".cache/xcheck/dir_cache"
CACHE.mkdir(parents=True, exist_ok=True)

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

H, side = [], []
for f in NPZ:
    d = np.load(f, mmap_mode="r")
    hs = d["hidden_states"]
    am = np.asarray(d["attention_mask"]).ravel()
    keep = np.nonzero(am == 1)[0][::STRIDE]
    H.append(np.asarray(np.asarray(hs[:, LAYER, :])[keep], dtype=np.float64))
    side.append(json.loads(f.with_suffix(".json").read_text())["tokens"])
    del d
print("载入 %d 条 / %d 步" % (len(H), sum(len(h) for h in H)))

z = np.load(ROOT / ".cache/rolesverify/obs_series.npz", allow_pickle=True)
names = [str(x) for x in z["names"]]
obs = z["obs"].astype(np.float64)
per = [[] for _ in z["traj_T"]]
for i, t in enumerate(z["traj_id"].astype(int)):
    per[t].append(obs[i])
series = [np.array(p) for p in per]
usable = {names[j]: [p[::STRIDE, j] for p in series] for j in range(len(names))}
control = {
    "entropy": [np.array([t["entropy"] for t in tk], np.float64)[::STRIDE] for tk in side],
    "in_think": [np.array([bool(t["is_in_think_block"]) for t in tk], np.float64)[::STRIDE]
                 for tk in side],
    "self_check_regex": [np.array([bool(SELF_CHECK_RE.search(t["token"] or "")) for t in tk],
                                  np.float64)[::STRIDE] for tk in side],
    "step_frac": [np.arange(len(tk), dtype=np.float64)[::STRIDE] /
                  max((len(tk) - 1) // STRIDE, 1) for tk in side],
}
TARGETS = list(usable.keys()) + list(control.keys())

axes = {}
for a in AX:
    v = np.load(VEC / f"{AX_FILE[a]}.npy").astype(np.float64).ravel()
    axes[a] = v / np.linalg.norm(v)
Amat = np.array([axes[a] for a in AX])


def gram_conditions(S):
    m = S.shape[0]
    Q = np.zeros_like(S)
    dg = np.zeros(m)
    for j in range(m):
        v = S[j].copy()
        for i in range(j):
            v -= (Q[i] @ v) * Q[i]
        dg[j] = np.linalg.norm(v)
        Q[j] = v / dg[j]
    return Q


Q = gram_conditions(Amat)

xm = np.mean([h.mean(axis=0) for h in H], axis=0)
C = np.zeros((D_MODEL, D_MODEL))
for h in H:
    hc = h - xm
    C += hc.T @ hc
C /= np.trace(C)
evals, evecs = np.linalg.eigh(C)
P = evecs[:, np.argsort(evals)[::-1][:K]]
xmA = xm @ Amat.T
Xp, A = [], []
for h in H:
    Xp.append((h - xm) @ P)
    A.append(h @ Amat.T - xmA)
del H, C, evecs
print("PCA top-%d 累计方差 = %.7f" % (K, np.sort(evals)[::-1][:K].sum()))


def pearson(p, t):
    p, t = np.asarray(p, np.float64).ravel(), np.asarray(t, np.float64).ravel()
    den = p.std() * t.std()
    if not np.isfinite(den) or den == 0:
        return float("nan")
    return float(((p - p.mean()) * (t - t.mean())).mean() / den)


def loo(Xs, Ys, lam_rel):
    d = Xs[0].shape[1]
    xmL = np.mean([x.mean(0) for x in Xs], 0)
    ymL = np.mean([y.mean(0) for y in Ys], 0)
    G = [(x - xmL).T @ (x - xmL) for x in Xs]
    B = [(x - xmL).T @ (y - ymL) for x, y in zip(Xs, Ys)]
    Gt, Bt = sum(G), sum(B)
    ws, pf, tg = [], [], []
    for i in range(len(Xs)):
        Gi, Bi = Gt - G[i], Bt - B[i]
        w = np.linalg.solve(Gi + lam_rel * np.trace(Gi) / d * np.eye(d), Bi)[:, 0]
        ws.append(w)
        pf.append((Xs[i] - xmL) @ w)
        tg.append(Ys[i] - ymL)
    return np.array(ws), np.concatenate(pf), np.concatenate(tg), pf, tg


np.save(CACHE / "P.npy", P)
np.save(CACHE / "Q.npy", Q)
np.save(CACHE / "axes.npy", Amat)


def save_ragged(name, seq):
    """轨迹长度不同，不能 np.array 堆成规则数组。存扁平 + 偏移量。"""
    np.save(CACHE / f"{name}_flat.npy", np.concatenate(seq, axis=0))
    np.save(CACHE / f"{name}_off.npy", np.cumsum([0] + [len(x) for x in seq]))


def load_ragged(name):
    flat = np.load(CACHE / f"{name}_flat.npy")
    off = np.load(CACHE / f"{name}_off.npy")
    return [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]


save_ragged("A", A)
save_ragged("Xp0", Xp)                    # Δ=0 用的就是全量
manifest = {"targets": TARGETS, "K": K, "stride": STRIDE, "layer": LAYER,
            "d_model": D_MODEL, "lambdas": LAMBDAS, "min_steps": MIN_STEPS,
            "axes": AX, "n_traj": len(Xp),
            "n_steps": int(sum(len(x) for x in Xp))}

print()
print("%-18s %-7s %-9s %s" % ("target", "lam", "rho", "w* 缓存"))
for tn in TARGETS:
    src = usable[tn] if tn in usable else control[tn]
    keep = [i for i in range(len(src)) if len(src[i]) >= MIN_STEPS]
    sh = [v.copy() for v in src]
    Ys = [(sh[i] - sh[i].mean())[:, None] for i in keep]
    Xs = [Xp[i][: len(y)] for i, y in zip(keep, Ys)]
    best = None
    for lam in LAMBDAS:
        ws, PF, TR, pf, tg = loo(Xs, Ys, lam)
        r = pearson(PF, TR)
        if best is None or r > best[1]:
            best = (lam, r, ws, pf, tg)
    lam, r, ws, pf, tg = best
    np.save(CACHE / f"w_{tn}.npy", ws)             # (48, 256) PCA 空间
    np.save(CACHE / f"d_{tn}.npy", ws @ P.T)       # (48, 2048) 抬回原空间
    save_ragged(f"pred_{tn}", pf)
    save_ragged(f"targ_{tn}", tg)
    manifest[f"meta_{tn}"] = {"lambda": lam, "rho_pooled": r, "keep": keep}
    print("%-18s %-7.0e %-9.4f ok" % (tn, lam, r))

(CACHE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
print()
print("已写", CACHE, " 共", len(TARGETS), "个目标")
