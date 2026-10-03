"""留出观测量家族：这套方法是「通用」的吗？两个测试。

测试一（跨家族非循环，最狠的一个）
  `digit_mass` = top-64 里数字 token 的**重归一化质量**（obs_extract.py:223 class_mass）。
  这里造三个**同底层分类、不同函数形式**的量：
      digit_top8_presence  top-8 里**有没有**数字（不 weighting、取更浅的 8 个）
      digit_frac_top64     top-64 里数字的**个数占比**（count，不 weighting）
      digit_top1           top-1 是不是数字
  如果 w*(digit_mass) 在样本外能预测这三个，那它编码的是
  「模型接下来要产出数值内容」这个**内容事实**，
  而不是「top-64 质量在数字上高」这个**加权方式的副产品**。
  这是不占 GPU 就能做到的最强非循环检验。

测试二（完全不同的家族）
  从**已输出**的 token 文本造量（不是下一步分布）：
      emitted_tok_len      发出 token 的字符长度
      emitted_has_digit    发出的 token **含**任意数字（原版用 all，所以这也不重复）
      emitted_is_upper     发出 token 首字母大写
  这三个从头到尾没参与过任何调参。跑同一套（非循环地板 + 专属 + Δ=20 塌不塌）。

顺带：用扩大的观测量集合重数一遍可读维度，看 12 这个数对不对得上。
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
CACHE = ROOT / ".cache/xcheck/dir_cache"
OUT = ROOT / ".cache/xcheck/heldout_family.json"
LAYER, STRIDE, D_MODEL, K = 14, 2, 2048, 256
LAMBDAS = [1e-3, 1e-2]
MIN_STEPS = 50
AX = ["confidence", "caution", "creativity", "reasoning_deep"]
AX_FILE = {"confidence": "confidence_up", "caution": "caution",
           "creativity": "creativity", "reasoning_deep": "reasoning_deep"}

man = json.loads((CACHE / "manifest.json").read_text())


def load_ragged(name):
    flat = np.load(CACHE / f"{name}_flat.npy")
    off = np.load(CACHE / f"{name}_off.npy")
    return [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]


Xp = load_ragged("Xp0")
P = np.load(CACHE / "P.npy")
AXES = np.load(CACHE / "axes.npy")

# ---------- 造留出观测量 ----------
vocab = json.loads((ROOT / "frontend/public/latent/data/vocab.json").read_text())["ids"]
is_digit = np.zeros(len(vocab), dtype=bool)
for i, s in enumerate(vocab):
    w = s.strip()
    if w and all(c in "0123456789" for c in w):
        is_digit[i] = True
print("数字 token 占词表比例：%.3f%%（%d / %d）"
      % (100 * is_digit.mean(), int(is_digit.sum()), len(vocab)))

new, new_names = [], []
for f in NPZ:
    z = np.load(f, mmap_mode="r")
    ti = np.asarray(z["topk_indices"])                 # (T, 64)
    am = np.asarray(z["attention_mask"]).ravel()
    side = json.loads(f.with_suffix(".json").read_text())["tokens"]
    n = min(ti.shape[0], len(side))
    tk = ti[:n]
    keep = np.nonzero(am[:n] == 1)[0][::STRIDE]
    tk = tk[keep]
    toks = [side[i]["token"] for i in keep]

    d = is_digit[tk]                                    # (T', 64) bool
    new.append(np.column_stack([
        d[:, :8].any(axis=1).astype(np.float64),        # top-8 有没有数字
        d.mean(axis=1),                                  # top-64 个数占比
        d[:, 0].astype(np.float64),                      # top-1 是不是数字
        np.array([len(t) for t in toks], np.float64),   # 发出 token 字符长度
        np.array([any(c.isdigit() for c in t) for t in toks], np.float64),
        np.array([t[:1].isupper() for t in toks], np.float64),
    ]))
    new_names.append(["digit_top8_presence", "digit_frac_top64", "digit_top1",
                      "emitted_tok_len", "emitted_has_digit", "emitted_is_upper"])
    del z
assert all(n == new_names[0] for n in new_names)
NAMES = new_names[0]
NEW = {NAMES[j]: [r[:, j] for r in new] for j in range(len(NAMES))}
print("留出观测量：", NAMES)
for n in NAMES:
    v = np.concatenate(NEW[n])
    print("   %-22s 均值 %.4f  标准差 %.4f  轨迹内零方差 %d/48"
          % (n, v.mean(), v.std(), sum(1 for s in NEW[n] if s.std() < 1e-12)))


# ---------- 沿用同一套装置 ----------
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


axes_k = {}
for k, a in enumerate(AX):
    v = P.T @ AXES[k]
    axes_k[a] = v / np.linalg.norm(v)


def fit(target, delta=0):
    keep = [i for i in range(len(target)) if len(target[i]) - delta >= MIN_STEPS]
    sh = [v[delta:] if delta else v.copy() for v in target]
    Ys = [(sh[i] - sh[i].mean())[:, None] for i in keep]
    Xs = [Xp[i][: len(y)] for i, y in zip(keep, Ys)]
    best = None
    for lam in LAMBDAS:
        ws, PF, TR, pf, tg = loo(Xs, Ys, lam)
        r = pearson(PF, TR)
        if best is None or r > best[1]:
            best = (lam, r, ws, pf, tg, keep)
    return best


def predict_with(ws, target, delta=0):
    keep = [i for i in range(len(target)) if len(target[i]) - delta >= MIN_STEPS]
    sh = [v[delta:] if delta else v.copy() for v in target]
    pf, tg = [], []
    for k, i in enumerate(keep):
        y = sh[i][: len(Xp[i])]
        if len(y) == 0:
            continue
        pf.append(Xp[i] @ ws[k])
        tg.append(y - y.mean())
    return pearson(np.concatenate(pf), np.concatenate(tg))


# ---------- 测试一：跨家族非循环 ----------
print()
print("=" * 78)
print("测试一  w*(digit_mass) 能不能预测**同底层、不同函数形式**的数字量？")
lam, rho0, ws_dm, *_ = fit(NEW["digit_top8_presence"])   # 先占位
z = np.load(ROOT / ".cache/rolesverify/obs_series.npz", allow_pickle=True)
obs = z["obs"].astype(np.float64)
names_old = [str(x) for x in z["names"]]
j_dm = names_old.index("digit_mass")
per = [[] for _ in z["traj_T"]]
for i, t in enumerate(z["traj_id"].astype(int)):
    per[t].append(obs[i])
series = [np.array(p) for p in per]
OLD = {n: [p[::STRIDE, j] for p in series] for j, n in enumerate(names_old)}

lam, rho0, ws_dm, *_ = fit(OLD["digit_mass"])
print("   w*(digit_mass) 自己那格 = %.4f" % rho0)
t1 = {}
for n in ["digit_top8_presence", "digit_frac_top64", "digit_top1"]:
    r = predict_with(ws_dm, NEW[n])
    t1[n] = r
    print("   → 预测 %-22s %.4f" % (n, r))
# 地板：把目标打乱
rng = np.random.default_rng(20261003)
fl = {}
for n in t1:
    fake = []
    for v in NEW[n]:
        f = v.copy()
        rng.shuffle(f)
        fake.append(f)
    fl[n] = predict_with(ws_dm, fake)
    print("   地板 %-22s %.4f" % (n, fl[n]))

# ---------- 测试二：完全不同的家族 ----------
print()
print("=" * 78)
print("测试二  从「已输出 token 文本」造的新家族，跑同一套三关")
print("%-22s %8s %8s %8s %8s %9s" %
      ("observable", "对角", "地板", "非对角", "Δ=20", "命名轴max"))
t2 = {}
for n in ["emitted_tok_len", "emitted_has_digit", "emitted_is_upper"]:
    lam, r0, ws, pf, tg, keep = fit(NEW[n])
    fake = []
    for v in NEW[n]:
        f = v.copy()
        rng.shuffle(f)
        fake.append(f)
    lam20, r20, *_ = fit(NEW[n], delta=20)
    u = ws / np.linalg.norm(ws, axis=1, keepdims=True)
    axcos = max(float(np.median(np.abs(u @ axes_k[a]))) for a in AX)
    # 非对角：用同一批目标里最高的那一格（这里的对手是其它留出量）
    others = {m: predict_with(ws, NEW[m]) for m in
              ["digit_top8_presence", "digit_frac_top64", "digit_top1"]}
    off = max(abs(v) for v in others.values()) if others else 0.0
    flr = predict_with(ws, fake)
    t2[n] = {"rho": r0, "floor": flr, "rho_delta20": r20,
             "offdiag_worst": off, "max_cos_named_axes": axcos,
             "cos_to_digit_mass_direction": float(np.median(np.abs(
                 (ws / np.linalg.norm(ws, axis=1, keepdims=True)) @
                 (ws_dm / np.linalg.norm(ws_dm, axis=1, keepdims=True)).T)))}
    print("%-22s %8.4f %8.4f %8.4f %8.4f %9.3f" %
          (n, r0, flr, off, r20, axcos))

OUT.write_text(json.dumps({
    "heldout_same_class_different_form": {"source_w": "digit_mass", **t1, "floors": fl},
    "heldout_new_family": t2,
    "vocab_digit_fraction": float(is_digit.mean()),
    "names": NAMES,
}, ensure_ascii=False, indent=1))
print()
print("已写", OUT)
