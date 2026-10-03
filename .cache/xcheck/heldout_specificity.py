"""把留出家族的专属性矩阵对**全部**观测量算一遍。

第一版只让新家族的 3 个量互相对质（off-diagonal 只取 digit_*），
结果 `emitted_has_digit` 的非对角 0.8540 **高于**它自己的对角 0.8455。
两种解释：
  ① 它是 digit_top1 的时间邻居（发出的 token 就是上一步 top-1 落下来的东西）
     ⇒ 它不是一条新方向，仪器是对的
  ② 我的比较集选窄了，漏掉了真正的对手
这里把 17 个观测量全部放进同一张表，看是哪一种。
"""
import json
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
np.seterr(all="ignore")

ROOT = Path("/Users/zhourui/code/steer3d")
CACHE = ROOT / ".cache/xcheck/dir_cache"
OUT = ROOT / ".cache/xcheck/heldout_specificity.json"
LAYER, STRIDE, D_MODEL, K = 14, 2, 2048, 256
LAMBDAS = [1e-3, 1e-2]
MIN_STEPS = 50
AX = ["confidence", "caution", "creativity", "reasoning_deep"]

man = json.loads((CACHE / "manifest.json").read_text())


def load_ragged(name):
    flat = np.load(CACHE / f"{name}_flat.npy")
    off = np.load(CACHE / f"{name}_off.npy")
    return [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]


Xp = load_ragged("Xp0")
P = np.load(CACHE / "P.npy")
AXES = np.load(CACHE / "axes.npy")

# ---- 原来的 14 个 ----
z = np.load(ROOT / ".cache/rolesverify/obs_series.npz", allow_pickle=True)
obs = z["obs"].astype(np.float64)
onames = [str(x) for x in z["names"]]
per = [[] for _ in z["traj_T"]]
for i, t in enumerate(z["traj_id"].astype(int)):
    per[t].append(obs[i])
series = [np.array(p) for p in per]
OLD = {n: [p[::STRIDE, j] for p in series] for j, n in enumerate(onames)}

import re
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b", re.IGNORECASE)
side = [json.loads(p.with_suffix(".json").read_text())["tokens"]
        for p in sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz"))]
CTRL = {
    "entropy": [np.array([t["entropy"] for t in tk], np.float64)[::STRIDE] for tk in side],
    "in_think": [np.array([bool(t["is_in_think_block"]) for t in tk], np.float64)[::2]
                 for tk in side],
    "self_check_regex": [np.array([bool(SELF_CHECK_RE.search(t["token"] or "")) for t in tk],
                                  np.float64)[::2] for tk in side],
    "step_frac": [np.arange(len(tk), dtype=np.float64)[::2] /
                  max((len(tk) - 1) // 2, 1) for tk in side],
}
# ---- 留出的 6 个 ----
vocab = json.loads((ROOT / "frontend/public/latent/data/vocab.json").read_text())["ids"]
is_digit = np.zeros(len(vocab), dtype=bool)
for i, s in enumerate(vocab):
    w = s.strip()
    if w and all(c in "0123456789" for c in w):
        is_digit[i] = True
NEW = {k: [] for k in ["digit_top8_presence", "digit_frac_top64", "digit_top1",
                      "emitted_tok_len", "emitted_has_digit", "emitted_is_upper"]}
for f in sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz")):
    zz = np.load(f, mmap_mode="r")
    ti = np.asarray(zz["topk_indices"])
    am = np.asarray(zz["attention_mask"]).ravel()
    tk_meta = json.loads(f.with_suffix(".json").read_text())["tokens"]
    n = min(ti.shape[0], len(tk_meta))
    keep = np.nonzero(am[:n] == 1)[0][::STRIDE]
    d = is_digit[ti[:n][keep]]
    toks = [tk_meta[i]["token"] for i in keep]
    NEW["digit_top8_presence"].append(d[:, :8].any(axis=1).astype(np.float64))
    NEW["digit_frac_top64"].append(d.mean(axis=1))
    NEW["digit_top1"].append(d[:, 0].astype(np.float64))
    NEW["emitted_tok_len"].append(np.array([len(t) for t in toks], np.float64))
    NEW["emitted_has_digit"].append(np.array([any(c.isdigit() for c in t) for t in toks], np.float64))
    NEW["emitted_is_upper"].append(np.array([t[:1].isupper() for t in toks], np.float64))
    del zz

TARGET = {**OLD, **CTRL, **NEW}
ROWS = list(NEW.keys())          # 只给留出家族拟合方向
COLS = list(TARGET.keys())       # 但对全部 17 个做专属性


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


def fit(target):
    keep = [i for i in range(len(target)) if len(target[i]) >= MIN_STEPS]
    Ys = [(target[i] - target[i].mean())[:, None] for i in keep]
    Xs = [Xp[i][: len(y)] for i, y in zip(keep, Ys)]
    best = None
    for lam in LAMBDAS:
        ws, PF, TR = loo(Xs, Ys, lam)
        r = pearson(PF, TR)
        if best is None or r > best[1]:
            best = (lam, r, ws, keep)
    return best


def predict_with(ws, target, keep):
    pf, tg = [], []
    for k, i in enumerate(keep):
        y = target[i][: len(Xp[i])]
        if len(y) == 0:
            continue
        pf.append(Xp[i] @ ws[k])
        tg.append(y - y.mean())
    return pearson(np.concatenate(pf), np.concatenate(tg))


axes_k = {}
for k, a in enumerate(AX):
    v = P.T @ AXES[k]
    axes_k[a] = v / np.linalg.norm(v)

rng = np.random.default_rng(20261003)
res = {}
for r_ in ROWS:
    lam, rho, ws, keep = fit(TARGET[r_])
    row = {c: predict_with(ws, TARGET[c], keep) for c in COLS}
    fake = []
    for v in TARGET[r_]:
        f = v.copy()
        rng.shuffle(f)
        fake.append(f)
    floor = predict_with(ws, fake, keep)
    u = ws / np.linalg.norm(ws, axis=1, keepdims=True)
    axcos = {a: float(np.median(np.abs(u @ axes_k[a]))) for a in AX}
    off = {c: abs(v) for c, v in row.items() if c != r_}
    worst = max(off, key=lambda k: off[k])
    res[r_] = {"rho_self": rho, "floor": floor, "worst_other": worst,
               "worst_other_value": row[worst],
               "margin": rho / off[worst] if off[worst] else None,
               "max_cos_named_axes": max(axcos.values()),
               "cos_to_named_axes": axcos, "matrix": row}
    print("%-22s 对角 %.4f  地板 %+.4f  最高别人 %-20s %.4f  余量 %s  命名轴max %.3f"
          % (r_, rho, floor, worst, row[worst],
             ("%.2f×" % (rho / off[worst])) if off[worst] else "n/a",
             max(axcos.values())))

print()
print("专项：emitted_has_digit 与三个 digit 留出量的关系")
for c in ["digit_top8_presence", "digit_frac_top64", "digit_top1", "emitted_tok_len"]:
    print("   w*(emitted_has_digit) → %-20s %.4f" % (c, res["emitted_has_digit"]["matrix"][c]))
# 它们有多像？直接量观测量的步间相关
a = np.concatenate(NEW["emitted_has_digit"])
b = np.concatenate(NEW["digit_top1"])
print("   观测量本身：corr(emitted_has_digit_t, digit_top1_t) = %.4f" % np.corrcoef(a, b)[0, 1])
print("   观测量本身：corr(emitted_has_digit_t, digit_top1_t-1) = %.4f"
      % np.corrcoef(a[1:], b[:-1])[0, 1])

OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print()
print("已写", OUT)
