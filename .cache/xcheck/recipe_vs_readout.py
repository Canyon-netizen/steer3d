"""「可读方向」是不是就是「可写下来的干预配方」？

现有 4 条命名轴全部是 `diff_of_means(mean(h|正组), mean(h|负组))` 造出来的
（`compute_steering_vectors.py:175-223`）—— 也就是**有配方、可直接注入**。
而 §4.9 找到的 `emitted_is_upper` 目前只是一条岭回归读出方向 w*，没有配方。
这是两件不同的事：前者可以拿去注入，后者只能拿去看。

这一支问：**能不能给它也写出一份配方**？
配方 = 按逐轨迹熵分位切正负组（与现有 4 条轴同一口径）取差均值。

关键设计：组谓词 P 与被预测的观测量 P **同源**，所以在 P 上测它
必然是构造恒等式，**那个数没有意义**。有意义的是两件事：
  ① **留一轨迹**：在 47 条轨迹上算差均值，第 48 条上预测。
     跨轨迹还成立 ⇒ 这份配方不只是把本轨迹的均值分开。
  ② **它与 w* 是不是同一条方向**（cos）。

自证：同一段代码用 `entropy` 做正负组，产出的向量必须与磁盘上已有的
`confidence_up.npy` 逐位对得上（cos = 1.000000000000）。
对不上就 ABORT —— 复制来的配方不复现，后面所有比较都不可信。
"""
import json
import re
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
np.seterr(all="ignore")

ROOT = Path("/Users/zhourui/code/steer3d")
VEC = ROOT / "backend/examples/output/steering_vectors"
OUT = ROOT / ".cache/xcheck/recipe_vs_readout.json"
LAYER, STRIDE = 14, 2
MIN_GEN = 20
LO, HI = 30, 75
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b", re.IGNORECASE)

NPZ = sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz"))
H, ENT, TOK, NPROMPT = [], [], [], []
for f in NPZ:
    d = np.load(f, allow_pickle=True)
    meta_all = json.loads(f.with_suffix(".json").read_text())
    meta = meta_all["tokens"]
    # ⚠ 这里必须与 compute_steering_vectors.py:89 **逐字一致**：
    #   gen_hidden = hs[:, layer, :].astype(np.float32)
    #   —— 全 token、**不做 stride**、**不做 mask 过滤**、转 float32。
    #   第一版我按分析侧口径用了 stride=2 + attention_mask 过滤，
    #   配方自证 cos = 0.99957 而不是 1.0：stride 会改变哪些 token 落进
    #   30/75 分位组，差均值因此不同。**先怀疑自己的脚本，不是统计量有性质。**
    # prompt 段在 pool_* 内部才裁（`gen_h = h[n_p:]`），这里保留全长。
    H.append(np.asarray(d["hidden_states"][:, LAYER, :], dtype=np.float32))
    TOK.append([t["token"] for t in meta])
    ENT.append(np.array([t["entropy"] for t in meta], dtype=np.float64))
    NPROMPT.append(int(meta_all.get("n_prompt_tokens", 0) or 0))
    del d
N = len(H)
print("载入 %d 条轨迹 / %d 步（与原脚本同口径：全 token、无 stride）"
      % (N, sum(len(h) for h in H)))


def gen_slice(k):
    """pool_* 内部做的事：先裁掉 prompt 段。"""
    n = NPROMPT[k]
    return H[k][n:], ENT[k][n:], TOK[k][n:]


def flags_entropy(k):
    h, e, tk = gen_slice(k)
    if len(h) < MIN_GEN:
        return None, None
    q1, q3 = np.percentile(e, LO), np.percentile(e, HI)
    return (e >= q3), (e <= q1)


def flags_isupper(k):
    h, e, tk = gen_slice(k)
    if len(h) < MIN_GEN:
        return None, None
    f = np.array([bool(t[:1].isupper()) for t in tk], dtype=bool)
    # 空的正组/负组直接返回 None，避免差均值退化成「0 − 全体均值」
    if f.sum() == 0 or f.sum() == len(f):
        return None, None
    return f, ~f


def flags_selfcheck(k):
    h, e, tk = gen_slice(k)
    if len(h) < MIN_GEN:
        return None, None
    f = np.array([bool(SELF_CHECK_RE.search(t or "")) for t in tk], dtype=bool)
    if f.sum() == 0 or f.sum() == len(f):
        return None, None
    return f, ~f


def diff_means(idxs, pos, neg):
    """pos/neg 是与 idxs 平行的布尔掩码（None = 该条轨迹的该组为空，跳过）。"""
    a = np.concatenate([gen_slice(i)[0][pos[j]]
                        for j, i in enumerate(idxs) if pos[j] is not None])
    b = np.concatenate([gen_slice(i)[0][neg[j]]
                        for j, i in enumerate(idxs) if neg[j] is not None])
    if len(a) < 10 or len(b) < 10:
        return None, 0, 0
    return a.mean(0) - b.mean(0), len(a), len(b)


def leave_one_out(flagfn, target_fn, shuffle_target=False):
    """在 47 条轨迹上算差均值 → 预测第 48 条。返回逐折 rho 与方向。"""
    rng = np.random.default_rng(20261003)
    rhos, vecs = [], []
    for k in range(N):
        idx = [i for i in range(N) if i != k]
        F = [flagfn(i) for i in idx]
        pos = [f[0] for f in F]
        neg = [f[1] for f in F]
        v, na, nb = diff_means(idx, pos, neg)
        if v is None:
            continue
        p, _ = flagfn(k)
        h_k, _, _ = gen_slice(k)
        if p is None or h_k.shape[0] != p.shape[0]:
            continue
        pred = h_k @ (v / np.linalg.norm(v))
        y = target_fn(k).astype(np.float64)
        if shuffle_target:
            y = y.copy()
            rng.shuffle(y)
        if y.std() == 0:
            continue
        rhos.append(float(np.corrcoef(pred, y)[0, 1]))
        vecs.append(v)
    return np.array(rhos), np.array(vecs)


def tgt_entropy(k):
    return gen_slice(k)[1]


def tgt_isupper(k):
    return np.array([bool(t[:1].isupper()) for t in gen_slice(k)[2]], dtype=np.float64)


def tgt_selfcheck(k):
    return np.array([bool(SELF_CHECK_RE.search(t or "")) for t in gen_slice(k)[2]],
                    dtype=np.float64)


# ---------- 自证：用 entropy 复现磁盘上的 confidence_up ----------
F_ENT = [flags_entropy(i) for i in range(N)]
v_ent, na, nb = diff_means(list(range(N)), [f[0] for f in F_ENT], [f[1] for f in F_ENT])
ref = np.load(VEC / "confidence_up.npy").astype(np.float64).ravel()
cos_self = float(abs(v_ent @ ref) / (np.linalg.norm(v_ent) * np.linalg.norm(ref)))
print("配方自证：entropy 差均值 vs 磁盘 confidence_up.npy  cos = %.12f" % cos_self)
if abs(cos_self - 1.0) > 1e-6:
    raise SystemExit("ABORT 配方复现不了已有的 confidence 轴，后续比较都不可信")
r_self = ref
print("           （磁盘向量是 float32，残差 %.1e 是精度差，不是口径差）"
      % (1.0 - cos_self))

AXES = {a: np.load(VEC / f"{a}.npy").astype(np.float64).ravel()
        for a in ["confidence_up", "caution", "creativity", "reasoning_deep"]}

# ---------- 新方向：emitted_is_upper 能不能写出配方 ----------
rho_up, vecs_up = leave_one_out(flags_isupper, tgt_isupper)
shuf_rho, _ = leave_one_out(flags_isupper, tgt_isupper, shuffle_target=True)

# 同一套代码在已有的两条轴上也跑一遍，作为「同格对照尺子」
rho_conf, _ = leave_one_out(flags_entropy, tgt_entropy)
rho_sc, _ = leave_one_out(flags_selfcheck, tgt_selfcheck)

# 与岭回归读出方向 w* 的关系（注意 w* 是在 stride=2 的分析口径上拟合的，
# 与这里的全 token 口径不同，所以 cos 不要求为 1，只看是否同一族）
Dw = np.load(ROOT / ".cache/xcheck/dir_cache/heldout/d_emitted_is_upper.npy")
w_star = np.median(Dw / np.linalg.norm(Dw, axis=1, keepdims=True), axis=0)
w_star = w_star / np.linalg.norm(w_star)
v_mean = vecs_up.mean(0)
v_mean = v_mean / np.linalg.norm(v_mean)          # ⚠ 第一版忘了归一化 v_mean，
#                                                  # 于是「余弦」算出 20.99 —— 超过 1
cos_wstar = float(abs(v_mean @ w_star))
cos_axes = {a: float(abs(v_mean @ (x / np.linalg.norm(x))))
            for a, x in AXES.items()}

norm_h = float(np.mean([np.linalg.norm(gen_slice(i)[0], axis=1).mean()
                        for i in range(N)]))
norm_v = float(np.linalg.norm(vecs_up.mean(0)))    # 归一化前的真实幅度

# ---- 这条配方到底朝哪：caution 轴、还是 caution 的读出方向？ ----
# 0.7266 的余弦是个必须解释的数 —— 岭回归 w* 对 caution 只有 0.301。
# 两种可能：
#  ① 配方向量本身就是 caution 的一部分 ⇒ 注入它等于注入 caution
#  ② 配方与 caution 轴近，但与 caution 的**读出方向**不近（轴 ≠ 读出）
# 判据：算 cos(配方, w*(caution))，以及配方对 caution 的定义式目标
#      self_check_regex 的留一 rho。若 ① 成立，两项都该高。
w_caution = np.median(
    np.load(ROOT / ".cache/xcheck/dir_cache/d_self_check_regex.npy")
    / np.linalg.norm(np.load(ROOT / ".cache/xcheck/dir_cache/d_self_check_regex.npy"),
                     axis=1, keepdims=True), axis=0)
w_caution = w_caution / np.linalg.norm(w_caution)
cos_recipe_vs_caution_readout = float(abs(v_mean @ w_caution))
rho_recipe_on_selfcheck, _ = leave_one_out(flags_isupper, tgt_selfcheck)
rho_recipe_on_entropy, _ = leave_one_out(flags_isupper, tgt_entropy)
print()
print("配方朝哪：cos(配方, caution 轴) = %.4f   cos(配方, w*(caution 读出)) = %.4f"
      % (cos_axes["caution"], cos_recipe_vs_caution_readout))
print("         同一份配方去预测 caution 的定义式目标 self_check_regex：LOO rho %.4f"
      % rho_recipe_on_selfcheck.mean())
print("         同一份配方去预测 confidence 的定义式目标 entropy：      LOO rho %.4f"
      % rho_recipe_on_entropy.mean())

res = {
    "what": "可读方向 vs 可写下来的干预配方：emitted_is_upper 能不能用同一套 diff_of_means 造出来",
    "recipe_selfcheck": {"target": "confidence_up", "cos": cos_self, "tolerance": 1e-6,
                         "passed": True},
    "loo_rho": {
        "emitted_is_upper": {"mean": float(rho_up.mean()), "min": float(rho_up.min()),
                             "max": float(rho_up.max()), "n_folds": int(len(rho_up)),
                             "floor_mean": float(shuf_rho.mean())},
        "confidence_same_code": {"mean": float(rho_conf.mean()), "n_folds": int(len(rho_conf))},
        "self_check_same_code": {"mean": float(rho_sc.mean()), "n_folds": int(len(rho_sc))},
    },
    "cos_recipe_vs_ridge_wstar": cos_wstar,
    "cos_recipe_vs_named_axes": cos_axes,
    "where_does_the_recipe_point": {
        "cos_recipe_vs_caution_axis": cos_axes["caution"],
        "cos_recipe_vs_caution_readout": cos_recipe_vs_caution_readout,
        "recipe_loo_on_self_check": float(rho_recipe_on_selfcheck.mean()),
        "recipe_loo_on_entropy": float(rho_recipe_on_entropy.mean()),
    },
    "scale": {"mean_norm_h": norm_h, "norm_diff_means": norm_v,
              "relative": norm_v / norm_h},
    "note": ("留一轨迹是这一支唯一有意义的数字：组谓词与被预测量同源，"
             "在同轨迹上测必然是构造恒等式。跨轨迹还成立才说明这份配方"
             "不只是把本轨迹的均值分开。"),
}
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))

print()
print("留一轨迹 rho（配方 → 观测量）")
print("   emitted_is_upper   %.4f  (折间 %.4f–%.4f, %d 折)  打乱地板 %.4f"
      % (rho_up.mean(), rho_up.min(), rho_up.max(), len(rho_up), shuf_rho.mean()))
print("   confidence 同一套代码  %.4f  (%d 折)" % (rho_conf.mean(), len(rho_conf)))
print("   self_check 同一套代码  %.4f  (%d 折)" % (rho_sc.mean(), len(rho_sc)))
print()
print("配方向量 vs 岭回归 w*          cos = %.4f" % cos_wstar)
print("配方向量 vs 4 条命名轴        " + "  ".join("%s %.4f" % (k, v) for k, v in cos_axes.items()))
print("‖diff_means‖ / mean‖h‖      %.4f" % (norm_v / norm_h))
print()
print("已写", OUT)
