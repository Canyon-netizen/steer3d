#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_cross_check_24484.py —— 244.84「对照臂方向污染类级判读」的**第二条独立实现**。

⚖⚖⚖⚖⚖ **为什么要有第二条实现**
   244.83 的教训：同一个口径，两条实现路线，**当场抓到过一个真 bug**
   （rand 向量的缩放因子必须是 float32 口径）⇒ ⇒ 「写对了一遍」不算数
   ⇒ ⇒ 本文件走**纯 Python 路线**（点积 / 范数 / 均值 / 方差 / 秩全部自己实现），
   与被检实现的 **numpy 路线**互证。

⚖⚖⚖⚖⚖ **分界（哪些必须同源、哪些必须独立）**
   · **随机抽样源**（`default_rng(s).standard_normal(d)`）：⚠ **必须同源**
     ⇒ ⇒ 否则两条路线抽的不是同一批「零分布」，根本无从互证。
   · **算术路径**（点积、范数、均值、样本方差、秩、比较）：⚠ **必须独立**
     ⇒ ⇒ 本文件用 `sum(map(mul, ...))` 与 `math.fsum` 等**另一套**实现。

⚖⚖⚖⚖⚖ **互证项（逐位比）**
   ① 6 把 w 对 r₀ 的余弦
   ② w_p2a 的**单向量**余弦（244.83 口径）与秩、z、参考 sd
   ③ 类级主统计量 T₀、参考均值/sd、z_T、秩、假阳性率
   ④ 两两余弦（15 对）
   ⑤ 判决形态

⚖⚖⚖⚖⚖ **纪律**
   · ⛔ 本文件**不改**被检实现、⛔ 不改预登记、⛔ 不改 bpath
   · ⛔ 期望值**从账本读**（⛔ 不写死）
   · ⚖ 互证只输出 `CROSS|key=value` 与一行小结；比对方由调用方做
"""

import json
import math
import os
import re
import sys
from operator import mul

import numpy as np

LEDGER = os.environ.get("R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
BPATH = os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath")

MEMBERS = ["w_L19_m0", "w_L19_m1", "w_real", "w_t1", "w_p2a", "w_old"]
DOSE_W = "w_p2a"
D = 2048
K = 2000
REF_SINGLE_LO = 1          # 与 244.83 逐字同构
REF_CLASS_LO = 100001      # ⛔ 与构造种子 42 不相交（§0.5 更正 ②）
RAND_SEED = 0
TRAIN_SEED = 42
Z_THRESHOLD = 2.0
FPR_MAX = 0.05
SHUFFLE_SEED = 24484
CROSS_REL_TOL = 1e-12


def die(msg):
    sys.stderr.write("⛔ %s\n" % msg)
    sys.exit(3)


def read_text(p):
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


# =============================================================================
# ⚖ 纯 Python 算术路线（⛔ 不用 numpy 的 dot / norm / mean / var）
# =============================================================================
def pdot(a, b):
    """⚖ 纯 Python 点积（`sum(map(mul, ...))`）⇒ 与 numpy 的 BLAS 路径**不同实现**。"""
    return sum(map(mul, a, b))


def pnorm(a):
    """⚖ 纯 Python 范数（`math.sqrt(sum(x*x))`）⇒ 与 numpy 的 `linalg.norm` **不同实现**。"""
    return math.sqrt(sum(x * x for x in a))


def pmean(v):
    return math.fsum(v) / len(v)


def pvar_sample(v):
    """⚖ 样本方差（ddof=1）⇒ 与 244.83 的写法同口径。"""
    m = pmean(v)
    return math.fsum((x - m) ** 2 for x in v) / (len(v) - 1)


def prand_raw(seed, shape):
    """⚖ **随机抽样源与被检实现同源**（numpy 的 PCG64）—— ⚠ 这一处**必须**同源。"""
    g = np.random.default_rng(int(seed))
    return g.standard_normal(shape).astype(np.float64)


def rand_direction_py(w0, seed):
    """⚖ 探针规则（`r241_probe.py` 第 404–406 行）——⚠ **缩放因子必须是 float32 口径**。"""
    g = np.random.default_rng(int(seed))
    w = g.standard_normal(w0.shape).astype(np.float64)
    w = (w / np.linalg.norm(w)) * float(np.linalg.norm(w0))
    return [float(x) for x in w]


def cos_py(u, v):
    """⚖ 244.83 的余弦口径：`<u,v> / ‖u‖`（**v 已归一化**）⇒ ⇒ 纯 Python。"""
    return pdot(u, v) / pnorm(u)


def unit_py(v):
    n = pnorm(v)
    return [x / n for x in v]


def cos0_24483_py(w0, r_vec):
    """⚖ 244.83 的 `cos0` 口径：`⟨w64, r⟩ / (‖w64‖·‖r‖)` —— 纯 Python。"""
    return pdot(w0, r_vec) / (pnorm(w0) * pnorm(r_vec))


def single_reference_py(w0, K, shape):
    """⚖ 与 244.83 **逐字同构**（种子 1..K）：`⟨w64, rr⟩ / ‖w64‖`。
    ⚠ `shape` **单独传进来** ⇒ ⇒ `w0` 可以是纯 Python list（⛔ list 没有 `.shape`）。"""
    ref = []
    nrm_w = pnorm(w0)
    for k in range(REF_SINGLE_LO, REF_SINGLE_LO + K):
        rr = prand_raw(k, shape)
        n = pnorm(rr)
        rr = [float(x) / n for x in rr]
        ref.append(pdot(w0, rr) / nrm_w)
    return ref


def class_stats_py(unit_vecs, r0, K):
    """⚖ 类级统计（纯 Python 路线）—— 参考种子区间 **100001..**（⛔ 与构造种子不相交）。"""
    n = len(unit_vecs)
    m = [sum(v[i] for v in unit_vecs) / n for i in range(len(unit_vecs[0]))]
    mnorm = pnorm(m)
    mc = [x / mnorm for x in m]

    def one(r):
        t = sum(cos_py(v, r) for v in unit_vecs) / n
        u = abs(cos_py(mc, r))
        return t, u

    T0, U0 = one(r0)
    Ts, Us = [], []
    for s in range(REF_CLASS_LO, REF_CLASS_LO + K):
        rr = prand_raw(s, (D,))
        nrm = pnorm(rr)
        rr = [float(x) / nrm for x in rr]
        t, u = one(rr)
        Ts.append(t)
        Us.append(u)
    mT, sT = pmean(Ts), math.sqrt(pvar_sample(Ts))
    mU, sU = pmean(Us), math.sqrt(pvar_sample(Us))
    zT = (T0 - mT) / sT
    rankT = sum(1 for x in Ts if x < T0) / float(len(Ts))
    zs = [(x - mT) / sT for x in Ts]
    fpr = sum(1 for z in zs if z >= Z_THRESHOLD) / float(len(Ts))
    theo = mnorm / math.sqrt(float(D))
    return {
        "T0": T0, "zT": zT, "rankT": rankT, "ref_mean": mT, "ref_sd": sT,
        "theo": theo, "sd_rel": abs(sT - theo) / theo, "fpr": fpr,
        "U0": U0, "zU": (U0 - mU) / sU, "mnorm": mnorm,
    }


def ledger_expectations(path):
    """⚖ 期望值从账本读（⛔ 读不到 ⇒ 拒绝兜底）。"""
    text = read_text(path)
    m = re.search(r"^## 修订 244\.83\b", text, re.M)
    if not m:
        die("账本里没有「## 修订 244.83」段 ⇒ 拒绝用字面值兜底")
    sec = text[m.start():]
    m2 = re.search(r"^## 修订 ", sec[10:], re.M)
    if m2:
        sec = sec[:10 + m2.start()]

    def g(pat, what):
        mm = re.search(pat, sec)
        if not mm:
            die("账本里读不到「%s」" % what)
        return mm.group(1)

    return {
        "cos0": float(g(r"cos0 `([-+0-9.eE]+)`", "cos0")),
        "rank": float(g(r"秩 `([-+0-9.eE]+)`", "经验秩")),
        "z": float(g(r"z `([-+0-9.eE]+)`", "z")),
    }


def main():
    if not os.path.isdir(BPATH):
        die("bpath 不存在：%s" % BPATH)
    if not os.path.isfile(LEDGER):
        die("账本不存在：%s" % LEDGER)
    de_path = os.environ.get("R244_DE_OUT", "")
    if not de_path or not os.path.isfile(de_path):
        die("缺被检实现的真数据输出（R244_DE_OUT）⇒ ⇒ 没有它就**无法做两条实现的互证**"
            "（⛔ 只比「同一脚本内的两条路线」是不够的）")

    exp = ledger_expectations(LEDGER)
    print("账本期望值：cos0=%r ｜ 秩=%r ｜ z=%r" % (exp["cos0"], exp["rank"], exp["z"]))

    # ---- 读 6 把向量（⛔ 算术走纯 Python；二进制解析用 numpy）----
    raw = {}
    ul = {}
    for nm in MEMBERS:
        p = os.path.join(BPATH, nm + ".npy")
        if not os.path.isfile(p):
            die("缺向量：%s" % p)
        arr = np.load(p)
        if arr.shape != (D,):
            die("%s shape 不是 (%d,)" % (nm, D))
        raw[nm] = arr
        ul[nm] = unit_py([float(x) for x in arr])
        print("成员 %-10s ‖v‖=%.10f" % (nm, pnorm([float(x) for x in arr])))

    w0 = [float(x) for x in raw[DOSE_W]]
    r0 = rand_direction_py(raw[DOSE_W], RAND_SEED)

    # ---- ① 6 把对 r₀ 的余弦 ----
    cos_each = {}
    for nm in MEMBERS:
        c = cos_py(ul[nm], r0)
        cos_each[nm] = c
        print("CROSS|cos_%s=%.17g" % (nm, c))

    # ---- ② 单向量（244.83 口径）----
    cos0 = cos0_24483_py(w0, r0)
    ref = single_reference_py(w0, K, (D,))
    m1 = pmean(ref)
    s1 = math.sqrt(pvar_sample(ref))
    z1 = (cos0 - m1) / s1
    rank1 = sum(1 for x in ref if x < cos0) / float(len(ref))
    print("CROSS|cos0=%.17g" % cos0)
    print("CROSS|cos_rank=%.17g" % rank1)
    print("CROSS|cos_z=%.17g" % z1)
    print("CROSS|ref_sd=%.17g" % s1)
    print("CROSS|theo_sd=%.17g" % (1.0 / math.sqrt(float(D))))

    # ---- ③ 类级 ----
    st = class_stats_py([ul[nm] for nm in MEMBERS], r0, K)
    print("CROSS|class_T0=%.17g" % st["T0"])
    print("CROSS|class_z=%.17g" % st["zT"])
    print("CROSS|class_rank=%.17g" % st["rankT"])
    print("CROSS|class_ref_mean=%.17g" % st["ref_mean"])
    print("CROSS|class_ref_sd=%.17g" % st["ref_sd"])
    print("CROSS|class_theo_sd=%.17g" % st["theo"])
    print("CROSS|class_sd_rel=%.17g" % st["sd_rel"])
    print("CROSS|class_fpr=%.17g" % st["fpr"])
    print("CROSS|class_U0=%.17g" % st["U0"])
    print("CROSS|class_zU=%.17g" % st["zU"])

    # ---- ④ 两两余弦 ----
    pair = {}
    for i in range(len(MEMBERS)):
        for j in range(i + 1, len(MEMBERS)):
            c = cos_py(ul[MEMBERS[i]], ul[MEMBERS[j]])
            pair[(i, j)] = c
            print("CROSS|pair_%d_%d=%.17g" % (i, j, c))

    # ---- ⑤ 判决形态 ----
    verdict = "E-B" if st["zT"] >= Z_THRESHOLD else "E-A"
    if st["fpr"] > FPR_MAX or st["sd_rel"] > 0.05:
        verdict = "E-C"
    print("CROSS|verdict=%s" % verdict)

    # =====================================================================
    # ⚖⚖⚖ **两条实现逐项互证**：纯 Python 路线（本文件） vs 被检实现（de.out）
    #   ⇒ ⇒ 这才是「第二条独立实现」的**真正**含义：
    #   ⛔ 只比「同一脚本内的两条路线」**不够**（那是算术自检，不是实现互证）
    # =====================================================================
    de = read_text(de_path)
    ok_n, bad_n = 0, 0

    def cmp(name, a, b, note="", atol=None):
        """⚖ 逐项对比：浮点用**相对差**（⛔ 除非给了 `atol`，那就用**绝对差**）。"""
        nonlocal ok_n, bad_n
        if isinstance(a, float) or isinstance(b, float):
            try:
                fa, fb = float(a), float(b)
            except (TypeError, ValueError):
                fa = fb = float("nan")
            if atol is not None:
                same = (fa == fb) or (abs(fa - fb) <= atol)
            else:
                same = (fa == fb) or (abs(fa - fb) <= CROSS_REL_TOL * max(abs(fa), abs(fb), 1e-300))
            sa, sb = repr(fa), repr(fb)
        else:
            same = (a == b)
            sa, sb = repr(a), repr(b)
        if same:
            ok_n += 1
            print("OK       %-24s %s  ==  %s %s" % (name, sa, sb, note))
        else:
            bad_n += 1
            print("MISMATCH %-24s %s  !=  %s %s" % (name, sa, sb, note))
        return same

    def dgrab(pat, what):
        m = re.search(pat, de, re.M)
        if not m:
            print("MISMATCH %-24s （被检实现里核不到「%s」）" % (what, what))
            return None
        return m

    # ---- 被检实现那边读出来的数 ----
    m = dgrab(r"^\[PASS\] H5-CLASSCOS\s+6 把对 r₀ 的余弦：(.+?) ｜ w_p2a 那一条 = ([-+0-9.eE]+)",
              "de.H5 存在")
    if m:
        for nm, c in re.findall(r"([A-Za-z0-9_]+)=([-+0-9.eE]+)", m.group(1)):
            cmp("cos_%s" % nm, cos_each.get(nm), float(c), "（纯 Python vs numpy）")
        cmp("cos_w_p2a", cos0, float(m.group(2)), "（纯 Python vs numpy）")

    m = dgrab(r"^\[PASS\] H10-CLASSSTAT\s+主统计量 T=[^=]*=([-+0-9.eE]+) ｜ 参考 K=\d+："
              r"mean=([-+0-9.eE]+) sd=([-+0-9.eE]+) ｜ 理论 sd=[^=]*=([-+0-9.eE]+)"
              r"（相对差 ([-+0-9.eE]+)，上限 ([-+0-9.eE]+)）｜ z_T=([-+0-9.eE]+) ｜ "
              r"秩=([-+0-9.eE]+) ｜ 共同分量投影 U₀=([-+0-9.eE]+) z_U=([-+0-9.eE]+)", "de.H10 存在")
    if m:
        cmp("class_T0", st["T0"], float(m.group(1)))
        cmp("class_ref_mean", st["ref_mean"], float(m.group(2)))
        cmp("class_ref_sd", st["ref_sd"], float(m.group(3)))
        cmp("class_theo_sd", st["theo"], float(m.group(4)))
        cmp("class_sd_rel", st["sd_rel"], float(m.group(5)), "（绝对差口径：它本身是 ~1e-3 的小量）",
            atol=1e-9)
        cmp("class_z_T", st["zT"], float(m.group(7)))
        cmp("class_rank_T", st["rankT"], float(m.group(8)))
        cmp("class_U0", st["U0"], float(m.group(9)))
        cmp("class_z_U", st["zU"], float(m.group(10)))

    m = dgrab(r"^\[PASS\] H12-FPR\s+判决规则「z_T ≥ ([-+0-9.eE]+)」在 K=\d+ 个参考种子下的"
              r"\*\*经验假阳性率\*\* = ([-+0-9.eE]+)", "de.H12 存在")
    if m:
        cmp("class_fpr", st["fpr"], float(m.group(2)))

    m = dgrab(r"^两两余弦明细：(.+)$", "de.两两余弦明细 存在")
    if m:
        for a, b, c in re.findall(r"([A-Za-z0-9_]+)-([A-Za-z0-9_]+)=([-+0-9.eE]+)", m.group(1)):
            i = MEMBERS.index(a)
            j = MEMBERS.index(b)
            cmp("pair_%d_%d" % (i, j), pair.get((i, j)), float(c))

    m = dgrab(r"^VERDICT=(\S+)$", "de.VERDICT 存在")
    if m:
        cmp("verdict", verdict, m.group(1), "（纯 Python vs numpy）")

    # ---- 跨轮对账（纯 Python 路线 vs 账本里 244.83 的值）----
    dcos = abs(cos0 - exp["cos0"]) / abs(exp["cos0"])
    dz = abs(z1 - exp["z"]) / abs(exp["z"])
    ok_rank = (rank1 == exp["rank"])
    ok = (dcos <= CROSS_REL_TOL) and (dz <= CROSS_REL_TOL) and ok_rank
    print("CROSS|ledger_cos_rel=%.17g" % dcos)
    print("CROSS|ledger_z_rel=%.17g" % dz)
    print("CROSS|ledger_rank_same=%d" % (1 if ok_rank else 0))
    if ok:
        ok_n += 1
        print("OK       %-24s %s  ==  %s （与账本 244.83 登记值）"
              % ("ledger_cos_rel<=tol", "%.3g" % dcos, "%.0e" % CROSS_REL_TOL))
    else:
        bad_n += 1
        print("MISMATCH %-24s cos_rel=%.3g z_rel=%.3g rank_same=%d （与账本 244.83 登记值）"
              % ("ledger_crossround", dcos, dz, 1 if ok_rank else 0))
    print("互证：%d 项 ｜ OK %d ｜ MISMATCH %d" % (ok_n + bad_n, ok_n, bad_n))
    print("CROSS_RC=%d" % (0 if bad_n == 0 else 1))
    return 0 if bad_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
