"""这 4 条「表面形式」方向是 token 局部的，还是持续状态？

框架的核心主张（§4.4 / §4.5）是：**4 条命名轴都是 token 局部的** ——
Δ=0 上 0.41/0.31，Δ=20 上塌到 0.039/0.011 且不再显著。
如果 §4.8 找到的这批新方向**不塌**，那这条主张就写得太宽了：
残差流里存在**描述更远未来**的方向。这是个会改写框架的差别，必须测。

复用 dir_cache 里的 Xp（Δ=0 用的就是全量特征；Δ>0 时目标右移、
特征取前 n−Δ 行，特征本身不需重算）⇒ 不用重载 9 GB npz。
装置阳性对照：step_frac 在任何 Δ 都应稳定在 0.6 附近 —— 它测不出的话，
下面所有的「塌了 / 没塌」都是噪声。
"""
import json
import re
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
np.seterr(all="ignore")

ROOT = Path("/Users/zhourui/code/steer3d")
CACHE = ROOT / ".cache/xcheck/dir_cache"
OUT = ROOT / ".cache/xcheck/token_locality.json"
LAMBDAS = [1e-3, 1e-2]
MIN_STEPS = 50
DELTAS = [0, 1, 20, 100]

man = json.loads((CACHE / "manifest.json").read_text())


def load_ragged(name):
    flat = np.load(CACHE / f"{name}_flat.npy")
    off = np.load(CACHE / f"{name}_off.npy")
    return [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]


Xp = load_ragged("Xp0")
NAMES = man["targets"]

z = np.load(ROOT / ".cache/rolesverify/obs_series.npz", allow_pickle=True)
names = [str(x) for x in z["names"]]
obs = z["obs"].astype(np.float64)
per = [[] for _ in z["traj_T"]]
for i, t in enumerate(z["traj_id"].astype(int)):
    per[t].append(obs[i])
series = [np.array(p) for p in per]
usable = {names[j]: [p[::2, j] for p in series] for j in range(len(names))}

SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b", re.IGNORECASE)
side = [json.loads(p.with_suffix(".json").read_text())["tokens"]
        for p in sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz"))]
control = {
    "entropy": [np.array([t["entropy"] for t in tk], np.float64)[::2] for tk in side],
    "in_think": [np.array([bool(t["is_in_think_block"]) for t in tk], np.float64)[::2]
                 for tk in side],
    "self_check_regex": [np.array([bool(SELF_CHECK_RE.search(t["token"] or "")) for t in tk],
                                  np.float64)[::2] for tk in side],
    "step_frac": [np.arange(len(tk), dtype=np.float64)[::2] /
                  max((len(tk) - 1) // 2, 1) for tk in side],
}
TARGET = {**usable, **control}

FOCUS = ["digit_mass", "op_mass", "newline_mass", "latex_mass",     # §4.8 的 4 条
         "top1_prob_renorm", "backtrack_topk",                       # 两条命名轴的读出
         "step_frac"]                                              # 装置阳性对照


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
    return np.array(ws), np.concatenate(pf), np.concatenate(tg)


res = {}
print("读出方向与目标在 Δ 步之后的样本外 Pearson（每格都是**重新拟合**的 w*）")
print()
print("%-18s %s" % ("target", "".join("%12s" % ("Δ=%d" % d) for d in DELTAS)))
print("-" * 74)
for tn in FOCUS:
    row = []
    for delta in DELTAS:
        src = TARGET[tn]
        keep = [i for i in range(len(src)) if len(src[i]) - delta >= MIN_STEPS]
        if not keep:
            row.append(float("nan"))
            continue
        sh = [v[delta:] if delta else v.copy() for v in src]
        Ys = [(sh[i] - sh[i].mean())[:, None] for i in keep]
        Xs = [Xp[i][: len(y)] for i, y in zip(keep, Ys)]
        if any(len(x) == 0 for x in Xs):
            row.append(float("nan"))
            continue
        best = None
        for lam in LAMBDAS:
            ws, PF, TR = loo(Xs, Ys, lam)
            r = pearson(PF, TR)
            if best is None or r > best[1]:
                best = (lam, r, ws)
        res.setdefault(tn, {})[f"delta{delta}"] = {
            "lambda": best[0], "rho": best[1],
            "n_traj": len(keep), "n_steps": int(len(PF))}
        row.append(best[1])
    print("%-18s %s" % (tn, "".join("%12.4f" % v for v in row)))

print()
print("衰减倍数（Δ=0 ÷ Δ=20）：")
for tn in FOCUS:
    a = res[tn]["delta0"]["rho"]
    b = res[tn]["delta20"]["rho"]
    if np.isfinite(a) and np.isfinite(b) and abs(b) > 1e-6:
        print("   %-18s %.4f → %.4f   （%5.1f× 衰减）" % (tn, a, b, a / abs(b)))
    else:
        print("   %-18s %.4f → %.4f" % (tn, a, b))

OUT.write_text(json.dumps({"deltas": DELTAS, "focus": FOCUS, "results": res},
                          ensure_ascii=False, indent=1))
print()
print("已写", OUT)
