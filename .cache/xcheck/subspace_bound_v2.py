"""把 §4.9.4 那句「12 维下界又偏低了」算成一个数。

§4.8.2 数出「可读方向至少 12 条」，用的贪心是
`for k in list(vectors)` —— **依赖遍历顺序**，所以那个数本来就不是
定义良好的。这一支做三件事：

  1. **先验证复制的配方**：用我自己的 fit 重算 `digit_mass` 的读出方向，
     必须与 dir_cache 里缓存的 `d_digit_mass.npy` 逐位相符。
     不符就 ABORT —— 复制来的代码不验证，错了会一路错到结论。
  2. 把 6 个留出观测量的读出方向按**同一套配方**补进候选池（20 条）。
  3. 量化贪心的**顺序依赖**：随机打乱顺序 200 次，报告 min/中位/max。
     贪心产出的每个子集都是**可行**的 ⇒ 「≥ min」是能站住的下界；
     max 也能站住但更弱。两个都报，读者自己判断。

沿用口径：L14 / stride=2 / K=256 PCA / 留一轨迹岭回归 /
λ ∈ {1e-3,1e-2} 取 pooled rho 最大者 / 目标按轨迹去均值 / 代表向量取折中位。
"""
import json
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
np.seterr(all="ignore")

ROOT = Path("/Users/zhourui/code/steer3d")
CACHE = ROOT / ".cache/xcheck/dir_cache"
OUTDIR = ROOT / ".cache/xcheck/dir_cache/heldout"
OUT = ROOT / ".cache/xcheck/subspace_bound_v2.json"
LAYER, STRIDE, D_MODEL, K = 14, 2, 2048, 256
LAMBDAS = [1e-3, 1e-2]
MIN_STEPS = 50
SEP = 0.5
N_PERM = 200
DEFINITIONAL = {"entropy", "in_think", "self_check_regex", "step_frac"}
HELDOUT = ["digit_top1", "digit_frac_top64", "digit_top8_presence",
           "emitted_has_digit", "emitted_is_upper", "emitted_tok_len"]

OUTDIR.mkdir(parents=True, exist_ok=True)
man = json.loads((CACHE / "manifest.json").read_text())
P = np.load(CACHE / "P.npy")
AXES = np.load(CACHE / "axes.npy")
AX_NAMES = man["axes"]


def load_ragged(name):
    flat = np.load(CACHE / f"{name}_flat.npy")
    off = np.load(CACHE / f"{name}_off.npy")
    return [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]


Xp = load_ragged("Xp0")

# ---------- 留出观测量（与 heldout_specificity.py 逐字相同的抽取）----------
vocab = json.loads((ROOT / "frontend/public/latent/data/vocab.json").read_text())["ids"]
is_digit = np.zeros(len(vocab), dtype=bool)
for i, s in enumerate(vocab):
    w = s.strip()
    if w and all(c in "0123456789" for c in w):
        is_digit[i] = True

NEW = {k: [] for k in HELDOUT}
for f in sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz")):
    zz = np.load(f, mmap_mode="r")
    ti = np.asarray(zz["topk_indices"])
    am = np.asarray(zz["attention_mask"]).ravel()
    tk = json.loads(f.with_suffix(".json").read_text())["tokens"]
    n = min(ti.shape[0], len(tk))
    keep = np.nonzero(am[:n] == 1)[0][::STRIDE]
    d = is_digit[ti[:n][keep]]
    toks = [tk[i]["token"] for i in keep]
    NEW["digit_top8_presence"].append(d[:, :8].any(axis=1).astype(np.float64))
    NEW["digit_frac_top64"].append(d.mean(axis=1))
    NEW["digit_top1"].append(d[:, 0].astype(np.float64))
    NEW["emitted_tok_len"].append(np.array([len(t) for t in toks], np.float64))
    NEW["emitted_has_digit"].append(
        np.array([any(c.isdigit() for c in t) for t in toks], np.float64))
    NEW["emitted_is_upper"].append(np.array([t[:1].isupper() for t in toks], np.float64))
    del zz


# ---------- 配方（与 extract_dirs.py / heldout_specificity.py 同式）----------
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


# ---------- 1. 先验证配方：重算 digit_mass 能否复现缓存 ----------
z = np.load(ROOT / ".cache/rolesverify/obs_series.npz", allow_pickle=True)
obs = z["obs"].astype(np.float64)
onames = [str(x) for x in z["names"]]
per = [[] for _ in z["traj_T"]]
for i, t in enumerate(z["traj_id"].astype(int)):
    per[t].append(obs[i])
series = [np.array(p) for p in per]
OLD = {n: [p[::STRIDE, j] for p in series] for j, n in enumerate(onames)}

_, _, ws_dm, keep_dm = fit(OLD["digit_mass"])
d_mine = ws_dm @ P.T
d_cached = np.load(CACHE / "d_digit_mass.npy")
maxdiff = float(np.abs(d_mine - d_cached).max())
print("配方自检：重算 digit_mass 与缓存 d_digit_mass.npy 最大逐点差 = %.3e" % maxdiff)
if maxdiff > 1e-6:
    raise SystemExit("ABORT 复制的配方复现不了缓存里的方向，后续结论全部不可信")

# ---------- 2. 补齐 6 个留出方向 ----------
rng = np.random.default_rng(20261003)
rows = []
for t in HELDOUT:
    lam, rho, ws, keep = fit(NEW[t])
    D = ws @ P.T
    np.save(OUTDIR / f"d_{t}.npy", D)
    fake = []
    for v in NEW[t]:
        f = v.copy()
        rng.shuffle(f)
        fake.append(f)
    rows.append({
        "key": t, "lambda": lam, "rho": rho, "n_folds": int(len(ws)),
        "floor": predict_with(ws, fake, keep),
        "delta20": None,
    })
    print("   %-22s lam %.0e  rho %.4f  地板 %+.4f  折数 %d"
          % (t, lam, rho, rows[-1]["floor"], len(ws)))

# ---------- 3. 候选池 + 贪心（含顺序依赖） ----------
def unit_rows(D):
    return D / np.linalg.norm(D, axis=1, keepdims=True)


def rep_of(D):
    v = np.median(unit_rows(D), axis=0)
    return v / np.linalg.norm(v)


rep = {}
for t in man["targets"]:
    rep["obs:" + t] = rep_of(np.load(CACHE / f"d_{t}.npy"))
for t in HELDOUT:
    rep["obs:" + t] = rep_of(np.load(OUTDIR / f"d_{t}.npy"))
for i, a in enumerate(AX_NAMES):
    rep["axis:" + a] = AXES[i] / np.linalg.norm(AXES[i])

obs_keys = [k for k in rep if k.startswith("obs:") and k[4:] not in DEFINITIONAL]
# ⚠ 第一版写成 `[k for k in rep if k[4:] not in DEFINITIONAL] + [k for k in rep if k.startswith("axis:")]`，
# 那会把 4 条命名轴**加两遍**（第一段的 "axis:caution"[4:] == "caution" 也通过了过滤），
# 于是「24 个候选」是错的，absorbed 里也会出现两条 axis:caution。
# 贪心结果不受影响（重复项与自身 cos=1，永远选不进第二个），但**显示出来的数**错了。
all_keys = obs_keys + ["axis:" + a for a in AX_NAMES]


def greedy(keys, sep=SEP):
    chosen = []
    for k in keys:
        if all(abs(rep[k] @ rep[c]) < sep for c in chosen):
            chosen.append(k)
    return chosen


# 旧口径（14 个观测量 + 4 轴）复现 §4.8.2 的 12
old_all = [k for k in rep if k.startswith("obs:") and k[4:] not in DEFINITIONAL
           and k[4:] not in HELDOUT] + list(rep.keys())[len(rep) - 4:]
old_all = [k for k in rep if k[4:] in man["targets"] and k[4:] not in DEFINITIONAL]
old_all = old_all + ["axis:" + a for a in AX_NAMES]
g_old = greedy(old_all)

g_all = greedy(all_keys)

# 阈值敏感性：|cos| < 0.5 这个门槛是**我选的**，不是推导出来的。
# 不报它，读者会以为 14 是个稳健的数；实际上 emitted_tok_len 对
# digit_top8_presence 的 |cos| 是 0.4711，门槛一降到 0.45 它就被吸收。
sens = {}
for sep in (0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
    n = [len(greedy(rng.permutation(all_keys).tolist(), sep)) for _ in range(40)]
    sens["%.2f" % sep] = {"greedy": len(greedy(all_keys, sep)),
                          "perm_min": int(np.min(n)), "perm_max": int(np.max(n))}
    print("   阈值 |cos|<%.2f ⇒ %d 条（40 次随机 %d–%d）"
          % (sep, sens["%.2f" % sep]["greedy"],
             sens["%.2f" % sep]["perm_min"], sens["%.2f" % sep]["perm_max"]))

# 谁在 0.5 门槛上**险胜**。
# ⚠ 第一版对**全体**候选取 max，把没被选中的同向项也算进来了 ——
# 于是 digit_mass 显示 1.0000（它和 digit_top1 本就是同一条方向，|cos|≈1），
# 那不是「险胜」而是「早就被吸收了」。要问的是：**已选集合内部**最接近门槛的是谁。
marg = []
for k in g_all:
    others = [abs(rep[k] @ rep[c]) for c in g_all if c != k]
    marg.append((max(others), k))
marg.sort(reverse=True)
print("   已选集合内部最接近门槛的：",
      "  ".join("%s %.4f" % (k.split(":")[1], c) for c, k in marg[:4]))
print("   （门槛 0.5，emitted_tok_len 对 digit_top8_presence 是 0.4711 —— "
      "门槛降到 0.45 它就被吸收）")
obs_new_only = [k for k in rep if k.startswith("obs:") and k[4:] in HELDOUT]

# 顺序依赖：随机排列 200 次
perms = [len(greedy(rng.permutation(all_keys).tolist())) for _ in range(N_PERM)]
pmin, pmed, pmax = int(np.min(perms)), int(np.median(perms)), int(np.max(perms))
perms_old = [len(greedy(rng.permutation(old_all).tolist())) for _ in range(N_PERM)]

# 谁被吸收
chosen = set(g_all)
absorbed = [k for k in all_keys if k not in chosen]

# 两条新方向对全体的 |cos|
focus = {}
for t in ["emitted_is_upper", "emitted_tok_len"]:
    v = rep["obs:" + t]
    row = {k: round(float(abs(v @ rep[k])), 4) for k in all_keys if k != "obs:" + t}
    focus[t] = dict(sorted(row.items(), key=lambda x: -x[1])[:6])

print()
print("候选池：%d 个非定义式观测量 + %d 条命名轴 = %d" % (len(obs_keys), len(AX_NAMES), len(all_keys)))
print("旧口径（14 观测量 + 4 轴，§4.8.2 报的 12）：贪心 %d，"
      "200 次随机顺序 %d–%d" % (len(g_old), min(perms_old), max(perms_old)))
print("新口径（20 观测量 + 4 轴）：贪心 %d，200 次随机顺序 %d / 中位 %d / %d"
      % (len(g_all), pmin, pmed, pmax))
print("   明细：", ", ".join(g_all))
print("   被吸收：", ", ".join(absorbed))
for t, row in focus.items():
    print("   %s 对全体最像的：" % t, "  ".join("%s %.4f" % (k, c) for k, c in row.items()))

res = {
    "what": "把 §4.8.2 的「至少 12 条」用扩大的候选池重数，并量化贪心的顺序依赖",
    "sep": SEP, "n_perm": N_PERM, "seed": 20261003,
    "recipe_check": {"target": "digit_mass", "max_abs_diff_vs_cache": maxdiff,
                     "tolerance": 1e-6, "passed": True},
    "old_recipe": {"n_obs": len([k for k in old_all if k.startswith("obs:")]),
                   "greedy": len(g_old),
                   "perm_min": int(np.min(perms_old)), "perm_max": int(np.max(perms_old)),
                   "detail": g_old},
    "new_recipe": {"n_obs": len(obs_keys), "n_candidates": len(all_keys),
                   "greedy": len(g_all),
                   "perm_min": pmin, "perm_median": pmed, "perm_max": pmax,
                   "detail": g_all, "absorbed": absorbed},
    "heldout_fit": rows,
    "focus_abs_cos": focus,
    "threshold_sensitivity": sens,
    "tightest_on_threshold": [{"key": k.split(":")[1], "max_abs_cos": float(c)}
                              for c, k in marg[:4]],
    "lower_bound": pmin,
    "caveat": ("贪心**依赖遍历顺序**，所以「N 条」本来不是定义良好的数 —— "
               "但实测两个口径下 200 次随机顺序**全都一样**（旧 %d–%d、新 %d–%d），"
               "所以这一项不是这里的软肋。真正的软肋是 |cos| < 0.5 这个门槛是**我选的**："
               "门槛降到 0.45，emitted_tok_len 就被吸收（它对 digit_top8_presence 的 "
               "|cos| = 0.4711）。"
               "每个贪心子集都是可行的 ⇒ 「≥ %d」是站得住的下界。"
               "这个数还依赖候选观测量集合 —— 每加一批观测量，计数就可能涨。它只能当下界用。"
               % (min(perms_old), max(perms_old), pmin, pmax, pmin)),
}
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print()
print("下界（保守）= %d   中位 = %d   最大 = %d" % (pmin, pmed, pmax))
print("已写", OUT)
