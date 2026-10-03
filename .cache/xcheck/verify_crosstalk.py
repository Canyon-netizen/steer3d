"""独立复算 #3：只验最吃重的那两格 —— 串扰。

背景：完备性子智能体（session 后来 lost，但产物齐全）报告在
`backtrack_topk` 那一格，confidence 轴的余弦 0.3341 **高于** caution 轴的 0.3077。
这会推翻我 §4.6 里「caution 测到了回退标记」的主张，所以必须自己验。

它自带的 verify_independent.py 在本机被 OOM killer 杀掉（Killed: 9），
所以本脚本只算两格，内存压到 1 GB 以内。

配方（逐字照 completeness.py）：
  L14 / stride=2 / attention_mask 过滤 / K=256 PCA / 留一轨迹岭回归
  λ=0.01 / 特征与目标各自按轨迹去均值 / cos = median_over_folds |ŵ·â_k|
  其中 â_k = normalize(P.T @ a)，a 是 2048 维单位轴向量。
"""
import json
from pathlib import Path

import numpy as np

np.seterr(all="ignore")
ROOT = Path("/Users/zhourui/code/steer3d")
NPZ = sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz"))
VEC = ROOT / "backend/examples/output/steering_vectors"
LAYER, K, STRIDE, LAM, D = 14, 256, 2, 1e-2, 2048
AX = {"confidence": "confidence_up", "caution": "caution",
      "creativity": "creativity", "reasoning_deep": "reasoning_deep"}


def cos(a, b):
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ---------- 载入 L14，stride=2，attention_mask 过滤 ----------
H, pad_drop = [], 0
for f in NPZ:
    d = np.load(f, mmap_mode="r")
    hs = d["hidden_states"]
    am = np.asarray(d["attention_mask"]).ravel()
    if am.size != hs.shape[0]:
        raise AssertionError(f"{f.name}: mask 与 hidden 行数不等")
    keep = np.nonzero(am == 1)[0]
    pad_drop += hs.shape[0] - int(am.sum())
    keep = keep[::STRIDE]
    H.append(np.asarray(np.asarray(hs[:, LAYER, :])[keep], dtype=np.float64))
    del d
print("载入 %d 条轨迹 / %d 步（padding 丢弃 %d）" % (len(H), sum(len(h) for h in H), pad_drop))

# ---------- 观测量 ----------
z = np.load(ROOT / ".cache/rolesverify/obs_series.npz", allow_pickle=True)
names = [str(x) for x in z["names"]]
obs = z["obs"].astype(np.float64)
per = [[] for _ in z["traj_T"]]
for i, t in enumerate(z["traj_id"].astype(int)):
    per[t].append(obs[i])
series = [np.array(p) for p in per]          # 少了这一步，下面 p[::STRIDE, j] 会按 list 索引
tgt = {names[j]: [p[::STRIDE, j] for p in series] for j in range(len(names))}

# ---------- 轴 ----------
axes_full = {}
for a, fn in AX.items():
    v = np.load(VEC / f"{fn}.npy").astype(np.float64).ravel()
    axes_full[a] = v / np.linalg.norm(v)
print()
print("两两 |cos|（2048 维原空间）")
ks = list(AX)
for i in range(len(ks)):
    for j in range(i + 1, len(ks)):
        print("   %-15s | %-15s = %.4f" % (ks[i], ks[j], abs(cos(axes_full[ks[i]], axes_full[ks[j]]))))

# ---------- PCA（照 build_features）----------
xm = np.mean([h.mean(axis=0) for h in H], axis=0)
C = np.zeros((D, D))
for h in H:
    hc = h - xm
    C += hc.T @ hc
C /= np.trace(C)
evals, evecs = np.linalg.eigh(C)
P = evecs[:, np.argsort(evals)[::-1][:K]]
print()
print("PCA top-%d 累计方差 = %.7f（completeness.json 记 0.7287951）" % (K, np.sort(evals)[::-1][:K].sum()))
axes_k = {}
for a, v in axes_full.items():
    x = P.T @ v
    axes_k[a] = x / np.linalg.norm(x)
Xp = [(h - xm) @ P for h in H]
del H, C, evecs
print("PCA 天花板（轴投到 256 维后的范数）:", {a: round(float(np.linalg.norm(P.T @ v)), 4) for a, v in axes_full.items()})


# ---------- 留一轨迹岭回归 ----------
def cell(name, delta=0):
    src = tgt[name]
    keep = [i for i in range(len(src)) if len(src[i]) - delta >= 50]
    sh = [v[delta:] for v in src] if delta else [v.copy() for v in src]
    Ys = [(sh[i] - sh[i].mean())[:, None] for i in keep]
    Xs = [Xp[i][: len(Ys[j])] for j, i in enumerate(keep)]   # 断言「等于预期值」，不是「两两相等」
    xmL = np.mean([x.mean(0) for x in Xs], 0)
    ymL = np.mean([y.mean(0) for y in Ys], 0)
    G = [ (x - xmL).T @ (x - xmL) for x in Xs ]
    B = [ (x - xmL).T @ (y - ymL) for x, y in zip(Xs, Ys) ]
    Gt, Bt = sum(G), sum(B)
    ws, pf, tg = [], [], []
    for i in range(len(Xs)):
        Gi, Bi = Gt - G[i], Bt - B[i]
        lam = LAM * np.trace(Gi) / Gi.shape[0]
        w = np.linalg.solve(Gi + lam * np.eye(Gi.shape[0]), Bi)[:, 0]
        ws.append(w)
        pf.append((Xs[i] - xmL) @ w)
        tg.append(Ys[i] - ymL)
    wn = np.array(ws) / np.linalg.norm(ws, axis=1, keepdims=True)
    per_axis = {a: float(np.median(np.abs(wn @ axes_k[a]))) for a in axes_k}
    p, t = np.concatenate(pf), np.concatenate(tg)
    rho = float(((p - p.mean()) * (t - t.mean())).mean() / (p.std() * t.std()))
    fold_rho = [float(np.corrcoef(pf[i].ravel(), tg[i].ravel())[0, 1]) for i in range(len(pf))]
    print("   [诊断] n=%d  p.std=%.6g  t.std=%.6g  折内 rho: 首=%.4f 中位=%.4f 末=%.4f"
          % (len(p), p.std(), t.std(), fold_rho[0],
             float(np.median(fold_rho)), fold_rho[-1]))
    return per_axis, rho, len(keep)


print()
print("=" * 74)
for nm, expect in [("backtrack_topk", "caution 报告行 0.308"), ("top1_prob_renorm", "confidence 报告行 0.412")]:
    pa, rho, nk = cell(nm)
    best = max(pa, key=pa.get)
    print("格 %-18s （%s）  OOF Pearson = %.4f  n_traj=%d" % (nm, expect, rho, nk))
    for a in ["confidence", "caution", "creativity", "reasoning_deep"]:
        mark = " <== 最高" if a == best else ""
        print("      cos(w*, %-15s) = %.4f%s" % (a, pa[a], mark))
    print()
print("对照 completeness.json：")
print("   backtrack_topk 格   confidence 0.33406 / caution 0.30770 / creativity 0.03947 / reasoning_deep 0.04433")
print("   top1_prob_renorm 格 confidence 0.41247 / caution 0.26494 / creativity 0.02055 / reasoning_deep 0.02032")
print("=" * 74)
