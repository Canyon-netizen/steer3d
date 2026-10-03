"""能不能做出**专一性更高**的配方？—— 同一个方向，三种配方结构对比

§4.10 的结果：`emitted_is_upper` 的朴素 `diff_of_means` 配方，
留一 rho 0.3688（地板 0.0045，82×）过了「有配方」那一关，
但它预测 `entropy` 也有 0.3219 ⇒ **专一性余量只有 1.15×**，没过「可注入」那关。

这一支问的是**配方类**的问题，不是这一条方向的问题：
把配方换一种结构，专一性会不会上去？

三种结构（目标都是 `is_upper`，协变量都是熵）：
  V1 朴素     mean(h|上) − mean(h|下)                    ← §4.10 用的那个
  V2 带内差   熵分 5 带，**每带内**算上−下，按带大小加权
             ⇒ 任何**单调的**熵依赖都被带内差消掉
  V3 残差化   组内把 h 对 [1, 熵] 线性回归取残差，再差均值
             ⇒ 消掉**线性的**熵成分（比 V2 更直接，且不依赖带宽）

**同格对照尺子**：同一套三个变体也套到 `self_check` 上。
如果去混杂对两个方向都有效，那是**配方类的改进**；
如果只对一个有效，那是这个方向的特殊情况，不能推广。

⚠ **margin = own / max(两个竞争者) 是个不稳的量**，这一版才报得出来：
去混杂把熵压下去之后，**最紧的约束方会换人**。第一版只存均值，
于是 V2 的 0.2236(熵) vs 0.2241(self_check) 这个 0.0005 的并列
被 `max` 悄悄判给了一个方向，页面印出「1.68×」看着像干净的结论。
⇒ 这一版逐折存 raw，算 sem，并报 `worst_other_name` / `top2_gap_over_sem`，
让「这个 max 到底选中了谁、这个交叉是不是噪声」变成可判的。

注意 `compute_steering_vectors.py:264-305` 里已有的 `pool_*_matched`
匹配的是**样本量**（n_each），不是**协变量** —— 熵失衡并没有被处理。

自证：同一份加载/差均值代码用 30/75 熵分位造 confidence，
必须复现磁盘上的 `confidence_up.npy`（cos = 1）。
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
OUT = ROOT / ".cache/xcheck/recipe_variants.json"
LAYER, MIN_GEN, LO, HI, BANDS = 14, 20, 30, 75, 5
SELF_CHECK_RE = re.compile(
    r"\b(wait|actually|hmm|hold on|let me check|let me verify|recheck|"
    r"double[- ]check|second thought|alternatively|but wait)\b", re.IGNORECASE)

H, ENT, TOK, NPROMPT = [], [], [], []
for f in sorted((ROOT / "datasets/aime_qwen3_1p7b_16k_fp16/aime").glob("*.npz")):
    d = np.load(f, allow_pickle=True)
    meta_all = json.loads(f.with_suffix(".json").read_text())
    meta = meta_all["tokens"]
    H.append(np.asarray(d["hidden_states"][:, LAYER, :], dtype=np.float32))
    TOK.append([t["token"] for t in meta])
    ENT.append(np.array([t["entropy"] for t in meta], dtype=np.float64))
    NPROMPT.append(int(meta_all.get("n_prompt_tokens", 0) or 0))
    del d
N = len(H)


def gen(k):
    n = NPROMPT[k]
    return H[k][n:], ENT[k][n:], TOK[k][n:]


def f_isupper(k):
    _, _, tk = gen(k)
    return np.array([bool(t[:1].isupper()) for t in tk], dtype=bool)


def f_selfcheck(k):
    _, _, tk = gen(k)
    return np.array([bool(SELF_CHECK_RE.search(t or "")) for t in tk], dtype=bool)


# ---------------- 三种配方结构 ----------------
def v1_naive(idxs, f):
    """mean(h|正) − mean(h|负)，全轨迹汇总。"""
    a, b = [], []
    for i in idxs:
        h, _, _ = gen(i)
        fv = f(i)
        if fv is None or fv.sum() == 0 or fv.sum() == len(fv):
            continue
        a.append(h[fv])
        b.append(h[~fv])
    if len(a) < 2 or sum(len(x) for x in a) < 10 or sum(len(x) for x in b) < 10:
        return None
    return np.concatenate(a).mean(0) - np.concatenate(b).mean(0)


def v2_banded(idxs, f):
    """熵分 BANDS 个带，每带内算上−下，按带内总样本数加权。"""
    num, den = None, 0
    for i in idxs:
        h, e, _ = gen(i)
        fv = f(i)
        if fv is None or fv.sum() < 3 or (~fv).sum() < 3:
            continue
        qs = np.percentile(e, np.linspace(0, 100, BANDS + 1)[1:-1])
        b = np.digitize(e, qs)
        for bi in range(BANDS):
            m = b == bi
            if m.sum() < 8:
                continue
            p, n = fv & m, (~fv) & m
            if p.sum() < 3 or n.sum() < 3:
                continue
            dd = h[p].mean(0) - h[n].mean(0)
            w = float(m.sum())
            num = dd * w if num is None else num + dd * w
            den += w
    if num is None or den == 0:
        return None
    return num / den


def _resid_on_entropy(h, e):
    """组内把 h 对 **熵** 线性回归取残差 —— **不带截距**。

    ⚠ 第一版带上了截距（对 [1, e] 回归），结果整个变体塌成 0：
      最小二乘解满足 `1ᵀ·残差 = 0`，也就是**组均值恒等于零**，
      两组残差均值之差必然是 0（实测 ‖均值‖ = 2.2e-14）。
    ⇒ **带截距的残差化会把组均值直接吃掉**，而我们要的正是那个均值差。
    只对熵回归，保留均值。"""
    b, *_ = np.linalg.lstsq(e[:, None], h, rcond=None)
    return h - e[:, None] * b


def v3_residualized(idxs, f):
    a, b = [], []
    for i in idxs:
        h, e, _ = gen(i)
        fv = f(i)
        if fv is None or fv.sum() < 3 or (~fv).sum() < 3:
            continue
        a.append(_resid_on_entropy(h[fv], e[fv]))
        b.append(_resid_on_entropy(h[~fv], e[~fv]))
    if len(a) < 2 or sum(len(x) for x in a) < 10 or sum(len(x) for x in b) < 10:
        return None
    return np.concatenate(a).mean(0) - np.concatenate(b).mean(0)


VARIANTS = {"V1_naive": v1_naive, "V2_banded": v2_banded, "V3_residualized": v3_residualized}


def loo_vector(builder, f):
    """留一：第 k 条的预测只能用「不含 k」的那一个方向。
    返回 {k: v_k}；第一版把 48 个方向**拼接**了再和单条轨迹的 y 求相关，
    维度对不上（31056 vs 647）—— 留一的定义就是每折一个方向，不是每折 48 个。"""
    out = {}
    for k in range(N):
        v = builder([i for i in range(N) if i != k], f)
        if v is not None and np.all(np.isfinite(v)) and np.linalg.norm(v) > 1e-6:
            out[k] = v
    return out


def rho_on(vecs, k, target):
    """用「不含 k」的方向在 k 上算 rho。"""
    v = vecs.get(k)
    if v is None:
        return None
    h, _, _ = gen(k)
    y = target(k).astype(np.float64)
    if y.std() == 0 or h.shape[0] != y.shape[0]:
        return None
    return float(np.corrcoef(h @ (v / np.linalg.norm(v)), y)[0, 1])


def t_isupper(k):
    return f_isupper(k).astype(np.float64)


def t_selfcheck(k):
    return f_selfcheck(k).astype(np.float64)


def t_entropy(k):
    return gen(k)[1]


# ---------- 自证：30/75 熵分位造出的 confidence 必须复现磁盘向量 ----------
def conf_pool(idxs):
    a, b = [], []
    for i in idxs:
        h, e, _ = gen(i)
        if len(h) < MIN_GEN:
            continue
        q1, q3 = np.percentile(e, LO), np.percentile(e, HI)
        b.append(h[e <= q1])
        a.append(h[e >= q3])
    if not a or not b:
        return None
    return np.concatenate(a).mean(0) - np.concatenate(b).mean(0)


v_conf = conf_pool(list(range(N)))
ref = np.load(VEC / "confidence_up.npy").astype(np.float64).ravel()
cos_self = float(abs(v_conf @ ref) / (np.linalg.norm(v_conf) * np.linalg.norm(ref)))
print("配方自证：30/75 熵分位 vs 磁盘 confidence_up.npy  cos = %.12f" % cos_self)
if abs(cos_self - 1.0) > 1e-6:
    raise SystemExit("ABORT 配方复现不了已有的 confidence 轴")

TARGETS = {"emitted_is_upper": t_isupper, "entropy": t_entropy, "self_check": t_selfcheck}

# ---- 闭合验证：磁盘上的 caution 轴是不是就是 V1 的 self_check 配方？ ----
# 如果是，那么「caution 的配方方向其实是熵的」这个结论，
# 就是从配方侧独立复现了 §4.6 专属性矩阵从读出侧得到的同一个判断。
v_sc = v1_naive(list(range(N)), f_selfcheck)
ref_caution = np.load(VEC / "caution.npy").astype(np.float64).ravel()
closure = (float(abs(v_sc @ ref_caution)
                 / (np.linalg.norm(v_sc) * np.linalg.norm(ref_caution)))
           if v_sc is not None else None)
if closure is not None:
    print("闭合验证：V1(self_check) 配方 vs 磁盘 caution.npy  cos = %.12f" % closure)
rng = np.random.default_rng(20261003)
res = {"what": "同一个方向换三种配方结构，专一性余量会怎么变",
       "recipe_selfcheck_cos": cos_self,
       # ⚠ cos = 0.9903，**不是 1**。同一族、不同配方实现（compute_steering_vectors.py
       # 有自己的 MIN_GEN 过滤与池化口径）。所以只能写「同族」，不能写「就是」。
       "closure_v1_selfcheck_vs_caution_axis": closure,
       "targets": {}}

for concept, flagfn in [("emitted_is_upper", f_isupper), ("self_check", f_selfcheck)]:
    res["targets"][concept] = {}
    for vname, builder in VARIANTS.items():
        vs = loo_vector(builder, flagfn)
        r_own = [rho_on(vs, k, TARGETS[concept]) for k in range(N)]
        r_own = [r for r in r_own if r is not None]
        # 逐折留着不只为了取均值：**margin = own / max(others)**，
        # 而两个竞争者常常只差 0.0005 量级（V2 的 0.2236 vs 0.2241）。
        # 不报逐折离散度就没法说这个 max 到底选中了谁、这个交叉是不是噪声。
        others, others_raw = {}, {}
        for tname, tfn in TARGETS.items():
            if tname == concept:
                continue
            r = [x for x in (rho_on(vs, k, tfn) for k in range(N)) if x is not None]
            others_raw[tname] = r
            others[tname] = float(np.mean(r)) if r else float("nan")
        # 打乱地板只对自家目标算
        fl = []
        for k in range(N):
            v = vs.get(k)
            if v is None:
                continue
            h, _, _ = gen(k)
            y = TARGETS[concept](k).copy()
            rng.shuffle(y)
            if y.std() == 0:
                continue
            fl.append(float(np.corrcoef(h @ (v / np.linalg.norm(v)), y)[0, 1]))
        # 范数诊断：V3 残差化可能整类塌掉（若 is_upper 的效应大部分经由熵中介，
        # 去掉熵的线性成分后差均值就接近 0）。这要**报出来**，不能当成崩溃。
        vnorm = float(np.mean([np.linalg.norm(v) for v in vs.values()])) if vs else 0.0
        if not r_own or not others or any(
                not np.isfinite(x) for x in others.values()):
            # 塌掉分支也必须返回**完整**的键，否则下游 build 会 KeyError
            # —— 而异常会把后面的判据一起吞掉，看着像「只报了一部分」。
            print("  %-14s %-16s **无有效折**（范数均值 %.4f）—— 该变体在这个方向上塌了"
                  % (concept, vname, vnorm))
            res["targets"][concept][vname] = {
                "n_folds": len(vs), "rho_own": None, "floor_mean": None,
                "rho_others": others, "rho_others_raw": others_raw,
                "worst_other": None, "worst_other_name": None, "margin": None,
                "mean_vector_norm": vnorm, "collapsed": True,
                "n_positive_total": int(sum(flagfn(k).sum() for k in range(N))),
            }
            continue
        own = float(np.mean(r_own))
        worst_name = max(others, key=lambda k: others[k])
        worst_other = others[worst_name]
        margin = own / worst_other if worst_other > 0 else None
        # 第二名的身份也要报出来：margin 涨了可能只是**约束方换人**，
        # 而不是配方变干净了。把两个竞争者都印出来，读者自己看得出。
        runner_up = sorted(others, key=lambda k: others[k])[-2] if len(others) > 1 else None
        res["targets"][concept][vname] = {
            "n_folds": len(vs), "rho_own": own,
            "rho_own_min": float(np.min(r_own)), "rho_own_max": float(np.max(r_own)),
            "rho_own_sem": (float(np.std(r_own, ddof=1) / np.sqrt(len(r_own)))
                            if len(r_own) > 1 else None),
            "floor_mean": float(np.mean(fl)),
            "rho_others": others, "rho_others_raw": others_raw,
            "rho_others_sem": {k: (float(np.std(v, ddof=1) / np.sqrt(len(v)))
                                   if len(v) > 1 else None)
                               for k, v in others_raw.items()},
            "worst_other": worst_other, "worst_other_name": worst_name,
            "runner_up_name": runner_up,
            # 约束方两名的差，以及这个差相对合并 sem 的倍数：
            # |差| < 2×sem ⇒ 这个 max 的归属**分不出来**，margin 是个不稳健的数。
            "top2_gap": (worst_other - others[runner_up]) if runner_up else None,
            "top2_gap_over_sem": None,
            "margin": margin,
            "mean_vector_norm": vnorm, "collapsed": False,
            "n_positive_total": int(sum(flagfn(k).sum() for k in range(N))),
        }
        if runner_up:
            se = res["targets"][concept][vname]["rho_others_sem"]
            gapsem = float(np.sqrt(sum((se[k] or 0.0) ** 2 for k in (worst_name, runner_up))))
            if gapsem > 0:
                res["targets"][concept][vname]["top2_gap_over_sem"] = \
                    res["targets"][concept][vname]["top2_gap"] / gapsem
        # 顺带报出正组样本量：is_upper 很稀疏（每条轨迹十几到二十几个），
        # 不知道分母的话 0.37 这个数没法判断可信度
        npos = int(sum(flagfn(k).sum() for k in range(N)))
        print("  %-14s %-16s 自身 %.4f±%.4f (地板 %+.4f)  "
              "熵 %.4f  selfchk %.4f  余量 %s (约束方 %s)  ‖v‖ %.2f  正组样本 %d"
              % (concept, vname, own,
                 res["targets"][concept][vname]["rho_own_sem"] or float("nan"),
                 np.mean(fl), others["entropy"], others.get("self_check", float("nan")),
                 ("%.3f×" % margin) if margin else "n/a", worst_name, vnorm, npos))

OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print()
print("已写", OUT)
