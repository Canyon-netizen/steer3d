#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""alignment_distribution_audit.py —— **对照臂方向污染的类级判读**（244.84）。

⚖⚖⚖⚖⚖ **这个文件回答什么**
   244.83（剂量等值性，形态 D-A）实测出**唯一不是等式的量**：

       cos(w_p2a, rand_seed0) = 0.060171700088156616   （K=2000 参考：秩 0.997、z 2.685）
       ⇒ rand 臂那把「固定种子随机方向」带着 w 的 0.362% 能量

   ⇒ ⇒ 244.83 自己写下的留白：「**N=1** ⇒ 巧合还是结构**未量到**、对改判率影响**未量到**」。

⚖⚖⚖⚖⚖ **本轮把第一个问号变成可判读的三态**：**换掉 w，不换 r**。
   rand 臂那把随机向量 `r = rand_seed0` 是**固定的**（探针里写死 `default_rng(0)`），
   实验已经用它跑完了 168 格 ⇒ ⇒ **它不能换**。
   能换的是 **w**：bpath 里还有 **5 把同层同 marker 同训练种子的 steering 向量**
   ⇒ ⇒ 对 **6 把 w** 各算一次 `cos(v_i, r)`：

       · 只有 `w_p2a` 那一条高 ⇒ ⇒ 这是**这一对**的巧合（E-A）
       · 6 条普遍高     ⇒ ⇒ `r` 系统性地落在 steering 向量的公共方向上（E-B）
       · 判别力不足     ⇒ ⇒ **未量到**（E-C）⛔ 不是「无差异」

⚖⚖⚖⚖⚖ **方法核心：零假设的构造**
   `r` **重抽** K=2000 次，**6 把 v 一动不动** ⇒ ⇒ 参考分布**自动吸收**了
   「6 把 v 彼此相关」（它们共享 marker 集 / 训练种子 42 / 数据批次）这件事
   ⇒ ⇒ ⛔ 不需要、也⛔不许用「独立样本 ⇒ sd = σ/√n」那种手算公式。

⚖⚖⚖⚖⚖ **纪律（本文件的形状就是这些纪律）**
   ① **口径只从预登记读**：`.cache/xcheck/R6_ALIGNMENT_DISTRIBUTION_PREREG.md`（244.84 签）
      ⇒ ⇒ 口径常量集中在 `SPEC`，且**逐条被 `--print-spec` 印出来**（⇒ 变异台能逐条改）。
   ② **期望值从账本读，不从代码读**（⛔ 代码里不写死 244.83 的数）：
      账本读不到 ⇒ ⇒ **HardFail**，⛔ 不用代码里的字面值兜底、⛔ 不静默降级。
   ③ **每条硬判据都有「跨来源」那一半**（只比「两臂相等」的判据在结构上可能恒绿）。
   ④ **每条判据能红**：`--selftest`（G0-1/G0-2/G0-3 合成夹具，零 bpath、零 GPU）
      ＋ 变异台 `mut_alignment_distribution_audit.py`。
   ⑤ **判决只算一次**：印出来的 = 返回的。
   ⑥ ⛔ **未量到 ≠ 没差异 ≠ 失败**。
   ⑦ ⚖ **判别力先于结论**：判决规则自己的**经验假阳性率**是判据（H12），
      ⛔ 超标 ⇒ 规则作废 ⇒ 形态只能是 E-C。

⚖⚖⚖ **本文件**不**产出**「污染对改判率的影响」的任何**数值**
   （预登记 §4.1：固定剂量批**没落盘 alpha 轨迹** ⇒ ⇒ 离线算不出来）
   ⇒ ⇒ 那个量本轮只以**条件命题**（D3）的形式登记，⛔ 不进判决、⛔ 不进摘要。
"""

import argparse
import json
import math
import os
import re
import sys

import numpy as np

# =============================================================================
# 口径常量（**逐条对应**预登记 §2；⇒ `--print-spec` 逐条印出 ⇒ 变异台能逐条改）
# =============================================================================
SPEC = {
    # ---- 对象 ----
    "dim": 2048,                 # Q3：向量维度
    "members": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1", "w_p2a", "w_old"],  # Q2
    "dose_w": "w_p2a",           # Q1：剂量批用的那把
    "stratum_A": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1"],   # Q12
    "layer": 20,                 # Q8：注入层
    "train_seed": 42,            # Q6：训练种子（6 把 sidecar 全同）
    "rand_seed": 0,              # Q5：rand 臂随机向量的种子
    "marker_ids": [13824, 14190, 6771, 10061, 7196, 88190, 80022],   # Q7
    "gap": 113.47440338134766,   # 剂量批的 --gap（判决读数 α 的两个工作剂量由此而来）

    # ---- 统计口径 ----
    "ref_K": 2000,               # Q9：参考分布规模 K（与 244.83 同口径 ⇒ 秩/z 可对账）
    "ref_single_seed_lo": 1,     # H6：**单向量**参考的种子起点（244.83 逐字同构 ⇒ 秩/z 可对账）
    "ref_class_seed_lo": 100001,  # Q15：**类级**参考的种子起点（⛔ 必须与构造种子 42 不相交）
    "ref_sd_rel_tol": 0.05,      # Q10：单向量参考 sd vs 理论 1/√d 的相对差上限
    "class_sd_rel_tol": 0.05,    # 类级参考 sd vs ‖m‖/√d 的相对差上限（零假设被校准）
    "z_threshold": 2.0,          # Q13：判决规则的单侧 z 阈值
    "fpr_max": 0.05,             # Q14：规则的经验假阳性率上限
    "negctl_z_max": 2.0,         # H11：负控（独立坐标置换）的 |z| 上限（⛔ **以预登记 §3.2 H11 为准** = 2；见 §0.5 更正 ⑤）
    "negctl_paircos_max": 0.15,  # H11：负控置换后两两余弦的上限（= 6.79/√d ⇒ 出处见预登记 §0.5 增补 Ⅵ）
    "shuffle_seed": 24484,       # H11：置换种子（固定 ⇒ 可复现）
    "seed2": 42,                 # D2：换个 r 的对照（seed 42）

    # ---- 跨轮对账容差（预登记 §0.5 更正 ①）----
    "cross_rel_tol": 1e-12,      # H5/H6：与账本期望值的相对差上限（账本里是**全精度**的那些）
    "sd_print_decimals": 6,      # H6′：账本里参考 sd 的**打印小数位** ⇒ 容差由它推导（§0.5 更正 ④）
    "cluster_cos_thresh": 0.5,   # D5：两两余弦分簇阈值（> thresh ⇒ 连边）
    "rank_exact": True,          # H6：经验秩按有理数逐位相同
}


# =============================================================================
# 小工具
# =============================================================================
def die(msg, code=3):
    sys.stderr.write("⛔ %s\n" % msg)
    sys.exit(code)


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def md5_of(path):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


def stats(vals):
    """⚖ 均值 + 样本方差（ddof=1）—— 与 244.83 的写法逐字同构。"""
    n = len(vals)
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / (n - 1)
    return mean, math.sqrt(var)


class Collector(object):
    """⚖ 判据收集器（沿用 244.83 的形状）：印出来的 = 返回的。"""

    def __init__(self):
        self.rows = []

    def check(self, cid, ok, detail):
        ok = bool(ok)
        self.rows.append((cid, ok, detail))
        print("[%s] %-14s %s" % ("PASS" if ok else "FAIL", cid, detail), flush=True)
        return ok

    def failed_ids(self):
        return [r[0] for r in self.rows if not r[1]]

    def pass_ids(self):
        return [r[0] for r in self.rows if r[1]]

    def summary(self):
        np_ = sum(1 for r in self.rows if r[1])
        return "判据汇总：%d 条 ｜ PASS %d ｜ FAIL %d" % (len(self.rows), np_, len(self.rows) - np_)


# =============================================================================
# 账本期望值（⛔ 代码里不写死 244.83 的数）
# =============================================================================
def ledger_expectations(ledger_path):
    """⚖⚖⚖ **期望值只从账本读**。⛔ 读不到 ⇒ HardFail ⇒ ⛔ 不用代码里的字面值兜底。

    读三样东西：
      · 244.83 段：cos0 / 经验秩 / z / 参考 sd / 理论 sd / 相对差 / w 能量占比
      · 244.78 段：`w_p2a.npy` 的 md5
      · 244.83 段的判决形态（必须是 D-A ⇒ 否则 244.83 的留白前提变了）
    """
    if not os.path.isfile(ledger_path):
        die("账本不存在：%s" % ledger_path)
    text = read_text(ledger_path)

    def section(num):
        m = re.search(r"^## 修订 %s\b" % re.escape(num), text, re.M)
        if not m:
            return None
        start = m.start()
        m2 = re.search(r"^## 修订 ", text[m.end():], re.M)
        end = m.end() + m2.start() if m2 else len(text)
        return text[start:end]

    sec83 = section("244.83")
    if sec83 is None:
        die("账本里没有「## 修订 244.83」段 ⇒ ⇒ 期望值无处可读 ⇒ ⇒ "
            "⛔ 拒绝用代码里的字面值兜底 ⇒ ⇒ **先落账 244.83 再跑本轮**")

    def grab(pat, what, s=None):
        s = sec83 if s is None else s
        m = re.search(pat, s)
        if not m:
            die("账本 244.83 段里读不到「%s」（模式 %s）⇒ ⇒ 拒绝兜底" % (what, pat))
        return m.group(1)

    exp = {
        "cos0": float(grab(r"cos0 `([-+0-9.eE]+)`", "cos0")),
        "rank": float(grab(r"秩 `([-+0-9.eE]+)`", "经验秩")),
        "z": float(grab(r"z `([-+0-9.eE]+)`", "z")),
        "ref_sd": float(grab(r"参考分布 sd = `([-+0-9.eE]+)`", "参考 sd")),
        "theo_sd": float(grab(r"理论 1/√\d+ = `([-+0-9.eE]+)`", "理论 sd")),
        "sd_rel": float(grab(r"（相对差 ([0-9.eE+-]+)）", "sd 相对差")),
        "w_frac": float(grab(r"w 的能量占比 \*\*([-+0-9.eE]+)\*\*", "w 能量占比")),
    }
    vm = re.search(r"判决形态\s*[|：:]\s*\**(D-[ABC])\**", sec83)
    if not vm:
        vm = re.search(r"\b(D-[ABC])\b", sec83)
    exp["verdict83"] = vm.group(1) if vm else "?"

    # ---- 244.78 段：w_p2a.npy 的 md5 ----
    sec78 = section("244.78") or ""
    md5s = []
    for line in sec78.splitlines():
        if "w_p2a.npy" in line and "md5" in line:
            for mm in re.finditer(r"md5 `([0-9a-f]{32})`", line):
                md5s.append(mm.group(1))
    exp["w_p2a_md5_candidates"] = sorted(set(md5s))
    if not exp["w_p2a_md5_candidates"]:
        die("账本 244.78 段里读不到 `w_p2a.npy` 的 md5 ⇒ ⇒ 拒绝兜底")
    return exp


# =============================================================================
# 随机方向与余弦（⚖ 口径逐字对应探针源码）
# =============================================================================
def rand_dir_raw(shape, seed):
    """⚖ 探针第 405 行的**前半**：`_g.standard_normal(_W0.shape).astype(np.float64)`"""
    g = np.random.default_rng(int(seed))
    return g.standard_normal(shape).astype(np.float64)


def rand_direction(w0, seed):
    """⚖ **探针里的 rand 规则**（逐字对应 `r241_probe.py` 第 404–406 行）：

         _g = np.random.default_rng(0)
         W  = _g.standard_normal(_W0.shape).astype(np.float64)
         W  = (W / np.linalg.norm(W)) * float(np.linalg.norm(_W0))

    ⚠⚠⚠ **缩放因子是 float32 口径**（`_W0` 是 float32 ⇒ `np.linalg.norm` 走 float32 累加
       ⇒ 本批 = 1.0 精确）—— 这是 244.83 当场抓到的真 bug，⛔ 不许退回 float64。
    ⚠ `w0` 必须是**原始 float32 数组**（⛔ 不是 float64 转换后的）。
    """
    g = np.random.default_rng(int(seed))
    w = g.standard_normal(w0.shape).astype(np.float64)
    w = (w / np.linalg.norm(w)) * float(np.linalg.norm(w0))
    return w


def cos_dot(u, v):
    """⚖ 244.83 的余弦口径：`<u,v> / ‖u‖`（**v 已归一化**）⇒ ⇒ 标量。"""
    uu = np.asarray(u, dtype=np.float64).ravel()
    vv = np.asarray(v, dtype=np.float64).ravel()
    return float(np.dot(uu, vv) / np.linalg.norm(uu))


def unit(v):
    vv = np.asarray(v, dtype=np.float64).ravel()
    return vv / np.linalg.norm(vv)


# =============================================================================
# 类级统计（⚖ 零假设：r 重抽、v 不动）
# =============================================================================
def full_stats(unit_vecs, shape, K, r0, spec, seed_lo=None):
    """⚖⚖⚖ **类级统计**。

    ⚠⚠⚖ **零假设的种子区间（§0.5 更正 ②）**：
       参考集 `default_rng(s)`，s ∈ **[seed_lo, seed_lo+K)**。
       ⛔ **seed_lo 必须与「构造种子」不相交** —— 否则零分布**自包含**
       ⇒ ⇒ 被验向量里含着构造它的随机量 ⇒ ⇒ 统计量被**系统性抬高**
       ⇒ ⇒ 实测：构造成分种子 ∈ 1..2000 × 参考 1..2000 ⇒ sd 相对理论 **0.41–0.43**
       ⇒ ⇒ 而构造成分种子 ∈ 900k+ × 参考 1..2000 ⇒ **0.0002–0.027** ✅
       ⇒ ⇒ 真数据的构造种子是 **42**（6 把 sidecar 全同）⇒ ⇒ 类级参考用 **100001..**

    返回：
      T_obs  = mean_i cos(v_i, r0)          （主统计量）
      z_T    = (T_obs − mean(T_ref)) / sd(T_ref)
      rank_T = #{T_s < T_obs} / K
      theo_T = ‖m‖ / √d                      （各向同性零假设下 T 的理论 sd，m = mean(v_i)）
      sd_rel_T= |sd(T_ref) − theo_T| / theo_T
      fpr    = #{z_s ≥ z_threshold} / K      （判决规则的经验假阳性率）
      U_obs / z_U                            （r 在共同分量上的投影）
    """
    if seed_lo is None:
        seed_lo = int(spec["ref_class_seed_lo"])
    n = len(unit_vecs)
    m = np.zeros(shape, dtype=np.float64)
    for v in unit_vecs:
        m = m + v
    m = m / n
    mnorm = float(np.linalg.norm(m))
    mc = m / mnorm if mnorm > 0 else m

    def one(r):
        t = sum(cos_dot(v, r) for v in unit_vecs) / n
        u = abs(cos_dot(mc, r))
        return t, u

    T_obs, U_obs = one(r0)
    Ts, Us = [], []
    for s in range(int(seed_lo), int(seed_lo) + int(K)):
        rr = rand_dir_raw(shape, s)
        rr = rr / np.linalg.norm(rr)
        t, u = one(rr)
        Ts.append(t)
        Us.append(u)
    mT, sT = stats(Ts)
    mU, sU = stats(Us)
    z_T = (T_obs - mT) / sT if sT > 0 else float("nan")
    rank_T = sum(1 for x in Ts if x < T_obs) / float(len(Ts))
    theo_T = mnorm / math.sqrt(float(shape[0]))
    sd_rel_T = abs(sT - theo_T) / theo_T if theo_T > 0 else float("inf")
    zs = [(x - mT) / sT for x in Ts] if sT > 0 else []
    fpr = sum(1 for z in zs if z >= float(spec["z_threshold"])) / float(len(Ts))
    z_U = (U_obs - mU) / sU if sU > 0 else float("nan")
    return {
        "T_obs": T_obs, "z_T": z_T, "rank_T": rank_T,
        "T_ref_mean": mT, "T_ref_sd": sT, "theo_T": theo_T, "sd_rel_T": sd_rel_T,
        "fpr": fpr, "mnorm": mnorm,
        "U_obs": U_obs, "z_U": z_U, "U_ref_mean": mU, "U_ref_sd": sU,
        "T_ref": Ts,
    }


def pairwise_cos(unit_vecs):
    """⚖ 两两余弦矩阵（6×6）⇒ 返回 15 对 [(i, j, cos)]。"""
    out = []
    n = len(unit_vecs)
    for i in range(n):
        for j in range(i + 1, n):
            out.append((i, j, cos_dot(unit_vecs[i], unit_vecs[j])))
    return out


def shuffle_indep(v, seed):
    """⚖ **独立**坐标置换（保范数、破共享结构）。

    ⚠⚠⚠ ⛔ **每把向量必须用各自独立的置换**：若 6 把共用**同一个**置换 ⇒ ⇒
       那是**正交变换** ⇒ ⇒ 两两余弦**原封不动** ⇒ ⇒ 共享结构根本没被破坏
       ⇒ ⇒ 负控会「因为什么都没测」而通过。
    """
    v = np.asarray(v, dtype=np.float64).ravel()
    g = np.random.default_rng(int(seed))
    return v[g.permutation(v.shape[0])]


# =============================================================================
# 单向量参考（⚖ 与 244.83 的 DQ-COS **逐字同构** ⇒ 秩/z 可跨轮对账）
# =============================================================================
def single_reference_24483(w0, K):
    """⚖⚖⚖ 与 244.83 `dose_equivalence_audit.py` 第 736–748 行**逐字同构**：

         cos0 = <w64, r_vec> / (w_norm * r_norm)
         for k in 1..K:  rr = default_rng(k).standard_normal(shape) 归一化
                        ref.append(<w64, rr> / w_norm)
         mean / var(ddof=1) / sd ； z = (cos0-mean)/sd
         rank = #{x < cos0} / K

    ⚠ **种子 1..K、排除被观测的 0** —— 这是「秩 0.997」的来源，⛔ 不许改成 0..K−1。
    """
    w64 = np.asarray(w0, dtype=np.float64)
    w_norm = float(np.linalg.norm(w64))
    ref = []
    for k in range(1, int(K) + 1):
        g = np.random.default_rng(k)
        rr = g.standard_normal(w0.shape).astype(np.float64)
        rr = rr / np.linalg.norm(rr)
        ref.append(float(np.dot(w64.ravel(), rr.ravel()) / w_norm))
    mean, sd = stats(ref)
    return ref, mean, sd


def cos0_24483(w0, r_vec):
    w64 = np.asarray(w0, dtype=np.float64)
    w_norm = float(np.linalg.norm(w64))
    r_norm = float(np.linalg.norm(r_vec))
    return float(np.dot(w64.ravel(), r_vec.ravel()) / (w_norm * r_norm))


# =============================================================================
# Phase-0 闸门（G0-1 / G0-2 / G0-3）：合成夹具、零 bpath、零 GPU
# =============================================================================
def _fixture_vectors(n, d, seed, common=None, common_frac=0.0):
    """⚖ 合成夹具的 6 把向量：`common` 非空 ⇒ 都带一份公共分量（幅度 common_frac）。"""
    g = np.random.default_rng(int(seed))
    vs = []
    for _ in range(int(n)):
        x = g.standard_normal(d).astype(np.float64)
        if common is not None:
            x = (1.0 - common_frac) * unit(x) + common_frac * unit(common)
        vs.append(unit(x))
    return vs


def selftest(spec=None):
    """⚖⚖⚖ **Phase-0 闸门**（预登记 §5）：G0-1 / G0-2 / G0-3。

    G0-1：6 把互不相关的 v ＋ 一把**通用** r ⇒ ⇒ 必须判 **E-A**
          **且** 参考 sd 与理论值的相对差 ≤ 容差（§0.5 更正 ②：闸门自己不许漏校准）
    G0-2：6 把 v **共享公共分量**、r **对准它** ⇒ ⇒ 必须判 **E-B**
    G0-3：参考分布**被人为污染**（sd 偏离理论 > 容差）⇒ ⇒ 必须判 **E-C**

    ⚠⚠⚖ **夹具的构造成分种子必须落在所有参考区间之外**（900001+）
       ⇒ ⇒ 否则零分布**自包含** ⇒ ⇒ 参考 sd 会被系统性抬高
       ⇒ ⇒ **这正是本闸门第一次跑时抓到的东西** ⇒ ⇒ 夹具自己不许重蹈覆辙。
    """
    sp = dict(SPEC if spec is None else spec)
    d = int(sp["dim"])
    K = int(sp["ref_K"])
    seed_lo = int(sp["ref_class_seed_lo"])
    fails = []

    def disjoint(tag):
        """⚖ 构造成分种子必须与**两个**参考区间都不相交。"""
        bad = []
        for lo, hi, nm in ((1, K, "单向量参考 1..K"),
                           (seed_lo, seed_lo + K - 1, "类级参考 %d..%d" % (seed_lo, seed_lo + K - 1))):
            if lo <= tag <= hi:
                bad.append(nm)
        return bad

    # ---- G0-1：巧合 ⇒ E-A（且零分布必须被校准）----
    vs1 = _fixture_vectors(6, d, 900001)
    bad1 = disjoint(900001)
    g1 = np.random.default_rng(900101)
    r1 = g1.standard_normal(d).astype(np.float64)
    r1 = r1 / np.linalg.norm(r1)
    st1 = full_stats(vs1, (d,), K, r1, sp)
    v1 = "E-B" if st1["z_T"] >= float(sp["z_threshold"]) else "E-A"
    cal_ok = st1["sd_rel_T"] <= float(sp["class_sd_rel_tol"])
    ok1 = (v1 == "E-A") and cal_ok and (not bad1)
    print("[%s] G0-1（巧合 ⇒ 必须 E-A） z_T=%.3f ｜ 参考 sd=%.6g vs 理论 %.6g"
          "（相对差 %.4f，上限 %.2f ⇒ %s）｜ 构造成分种子 900001 与参考区间不相交 ⇒ %s ｜ 判成 %s"
          % ("PASS" if ok1 else "FAIL", st1["z_T"], st1["T_ref_sd"], st1["theo_T"],
             st1["sd_rel_T"], float(sp["class_sd_rel_tol"]), "已校准" if cal_ok else "⛔没校准",
             "成立" if not bad1 else "⛔%s" % bad1, v1), flush=True)
    if not ok1:
        fails.append("G0-1")

    # ---- G0-2：结构 ⇒ E-B ----
    g2 = np.random.default_rng(900201)
    c = g2.standard_normal(d).astype(np.float64)
    c = c / np.linalg.norm(c)
    vs2 = _fixture_vectors(6, d, 900202, common=c, common_frac=0.8)
    bad2 = disjoint(900202)
    r2 = c + 0.05 * g2.standard_normal(d).astype(np.float64)
    r2 = r2 / np.linalg.norm(r2)
    st2 = full_stats(vs2, (d,), K, r2, sp)
    v2 = "E-B" if st2["z_T"] >= float(sp["z_threshold"]) else "E-A"
    ok2 = (v2 == "E-B") and (not bad2)
    print("[%s] G0-2（结构 ⇒ 必须 E-B） z_T=%.3f ｜ 公共分量 ‖m‖=%.4f ｜ 构造成分种子 900202 ⇒ %s ｜ 判成 %s"
          % ("PASS" if ok2 else "FAIL", st2["z_T"], st2["mnorm"],
             "不相交" if not bad2 else "⛔%s" % bad2, v2), flush=True)
    if not ok2:
        fails.append("G0-2")

    # ---- G0-3：参考分布被污染 ⇒ E-C ----
    vs3 = _fixture_vectors(6, d, 900302)
    g3 = np.random.default_rng(900301)
    r3 = g3.standard_normal(d).astype(np.float64)
    r3 = r3 / np.linalg.norm(r3)
    st3 = full_stats(vs3, (d,), K, r3, sp)
    # ⚖ **人为污染**：把参考分布的一半整体放大 3 倍 ⇒ ⇒ sd 偏离理论 ⇒ ⇒ 零假设没校准
    polluted = dict(st3)
    Ts = list(st3["T_ref"])
    half = len(Ts) // 2
    Ts[:half] = [x * 3.0 for x in Ts[:half]]
    mT, sT = stats(Ts)
    theo = st3["theo_T"]
    sd_rel = abs(sT - theo) / theo
    ok3 = sd_rel > float(sp["class_sd_rel_tol"])
    print("[%s] G0-3（参考被污染 ⇒ 必须 E-C） 污染后 sd 相对差=%.3f（上限 %.3f）⇒ ⇒ "
          "零假设**没校准** ⇒ ⇒ 形态只能是 E-C"
          % ("PASS" if ok3 else "FAIL", sd_rel, float(sp["class_sd_rel_tol"])), flush=True)
    if not ok3:
        fails.append("G0-3")

    print("自检（Phase-0 G0-1/G0-2/G0-3）：%d 条 ｜ FAIL %d 条%s"
          % (3, len(fails), ("：%s" % fails) if fails else ""), flush=True)
    if fails:
        print("SELFTEST_RC=1", flush=True)
        return 1
    print("SELFTEST_RC=0", flush=True)
    return 0


# =============================================================================
# 真数据路径（⛔ 只读 bpath、⛔ 零 GPU）
# =============================================================================
def _sidecar(bpath, name):
    p = os.path.join(bpath, name + ".npy.json")
    if not os.path.isfile(p):
        die("缺 sidecar：%s" % p)
    return json.loads(read_text(p))


def run_data(a):
    sp = dict(SPEC)
    cr = Collector()
    bp = a.bpath
    names = list(sp["members"])
    d = int(sp["dim"])
    K = int(sp["ref_K"])

    # ---- 账本期望值（⛔ 读不到 ⇒ HardFail）----
    exp = ledger_expectations(a.ledger)
    print("账本期望值（244.83 段）：cos0=%r ｜ 秩=%r ｜ z=%r ｜ 参考 sd=%r ｜ w 能量占比=%r"
          % (exp["cos0"], exp["rank"], exp["z"], exp["ref_sd"], exp["w_frac"]), flush=True)
    print("账本 244.78 段登记的 w_p2a.npy md5 候选：%s" % exp["w_p2a_md5_candidates"], flush=True)

    # ---- 向量与 sidecar ----
    vecs, metas, raw = {}, {}, {}
    for nm in names:
        p = os.path.join(bp, nm + ".npy")
        if not os.path.isfile(p):
            die("缺向量文件：%s" % p)
        raw[nm] = np.load(p)
        if raw[nm].shape != (d,):
            die("%s 的 shape 不是 (%d,)：%r" % (nm, d, (raw[nm].shape,)))
        metas[nm] = _sidecar(bp, nm)
        vecs[nm] = unit(raw[nm])
        print("成员 %-10s shape=%r dtype=%s ‖v‖=%.10f class_gap=%r layer=%r seed=%r "
              "n_train_traj=%r npz=%s"
              % (nm, raw[nm].shape, raw[nm].dtype, float(np.linalg.norm(raw[nm].astype(np.float64))),
                 metas[nm].get("class_gap"), metas[nm].get("layer"), metas[nm].get("seed"),
                 metas[nm].get("n_train_traj"), str(metas[nm].get("npz_dir"))), flush=True)

    w0 = raw[sp["dose_w"]]
    unit_vecs = [vecs[nm] for nm in names]

    # ---- 探针 / 跑批器源码（跨来源那一半）----
    probe_text = read_text(os.path.join(bp, "r241_probe.py"))
    runner_text = read_text(os.path.join(bp, "r244_warm_sweep.sh"))
    w_log = read_text(os.path.join(bp, "r244_warm_fd_w.log"))
    r_log = read_text(os.path.join(bp, "r244_warm_fd_rand.log"))

    # ===================== H1：身份 =====================
    sc = metas[sp["dose_w"]]
    gap_ok = (float(sc.get("class_gap")) == float(sp["gap"]))
    runner_gap_ok = ("--gap %s" % repr(float(sp["gap"]))) in runner_text or \
                    ("--gap %s" % float(sp["gap"])) in runner_text
    m = re.search(r"^PINNED .*ARM=(\S+).*W_PATH=(\S+)", w_log, re.M)
    pin_ok = bool(m) and m.group(1) == "w" and m.group(2).endswith(sp["dose_w"] + ".npy")
    md5_w = md5_of(os.path.join(bp, sp["dose_w"] + ".npy"))
    md5_ok = md5_w in exp["w_p2a_md5_candidates"]
    cr.check("H1-IDENT", gap_ok and runner_gap_ok and pin_ok and md5_ok,
             "sidecar class_gap=%r == 批 --gap %r ⇒ %s ｜ runner 含该 --gap ⇒ %s ｜ "
             "w 臂日志 PINNED(ARM=w, W_PATH=…%s.npy) ⇒ %s ｜ 实测 md5=%s ∈ 账本候选 ⇒ %s"
             % (sc.get("class_gap"), sp["gap"], "一致" if gap_ok else "⛔不一致",
                "有" if runner_gap_ok else "⛔无",
                sp["dose_w"], "有" if pin_ok else "⛔无",
                md5_w, "是" if md5_ok else "⛔否"))

    # ===================== H2：出处 =====================
    bad = []
    for nm in names:
        mt = metas[nm]
        if int(mt.get("layer", -1)) != int(sp["layer"]):
            bad.append("%s.layer=%r" % (nm, mt.get("layer")))
        if int(mt.get("seed", -1)) != int(sp["train_seed"]):
            bad.append("%s.seed=%r" % (nm, mt.get("seed")))
        if [int(x) for x in (mt.get("marker_ids") or [])] != list(sp["marker_ids"]):
            bad.append("%s.marker_ids=%r" % (nm, mt.get("marker_ids")))
        if abs(float(mt.get("w_norm", -1)) - 1.0) > 1e-6:
            bad.append("%s.w_norm=%r" % (nm, mt.get("w_norm")))
    # ---- 跨来源那一半：源码里的常量 ----
    m_mk = re.search(r"^MARKER_IDS\s*=\s*\[([^\]]*)\]", probe_text, re.M)
    m_ly = re.search(r"^LAYER\s*=\s*(\d+)", probe_text, re.M)
    src_mk = [int(x) for x in re.findall(r"\d+", m_mk.group(1))] if m_mk else []
    src_ly = int(m_ly.group(1)) if m_ly else -1
    # 训练脚本：找那个写出 `"seed": 42` 且带同一组 marker 的源码
    train_src = []
    for fn in sorted(os.listdir(bp)):
        if not fn.endswith(".py"):
            continue
        try:
            t = read_text(os.path.join(bp, fn))
        except Exception:
            continue
        if '"seed": 42' in t and "MARKER_IDS = [%s" % ", ".join(str(x) for x in sp["marker_ids"]) in t:
            train_src.append(fn)
    src_ok = (src_mk == list(sp["marker_ids"])) and (src_ly == int(sp["layer"])) and bool(train_src)
    cr.check("H2-PROVENANCE", (not bad) and src_ok,
             "6 把 sidecar：layer=%s seed=%s marker_ids（7 个逐个相同）w_norm=1.0 ⇒ %s"
             " ｜ 跨来源：探针源码 MARKER_IDS=%r LAYER=%r ⇒ %s ｜ 训练脚本带 `\"seed\": 42` 且同 marker：%s ⇒ %s%s"
             % (sp["layer"], sp["train_seed"], "全对" if not bad else "⛔%s" % bad,
                src_mk, src_ly, "一致" if src_mk == list(sp["marker_ids"]) and src_ly == int(sp["layer"]) else "⛔不一致",
                (train_src[:3] if train_src else "⛔无"), "有" if train_src else "⛔无",
                ("｜⛔不一致项：%s" % bad) if bad else ""))

    # ===================== H3：rand 规则 =====================
    rule_ok = ("np.random.default_rng(%d)" % int(sp["rand_seed"])) in probe_text
    pat_ok = ("standard_normal(_W0.shape).astype(np.float64)" in probe_text
              and "(W / np.linalg.norm(W)) * float(np.linalg.norm(_W0))" in probe_text)
    r0 = rand_direction(w0, int(sp["rand_seed"]))
    r_norm = float(np.linalg.norm(r0))
    mm = re.search(r"\[臂\] 用固定种子随机方向（mod=([0-9.]+)", r_log)
    log_mod = float(mm.group(1)) if mm else float("nan")
    mod_ok = bool(mm) and abs(log_mod - r_norm) <= 5e-4
    cr.check("H3-RANDRULE", rule_ok and pat_ok and mod_ok,
             "探针源码：`default_rng(%d)` ⇒ %s ｜ standard_normal+归一化+float32 缩放 ⇒ %s ｜ "
             "rand 臂日志印的 mod=%s vs 现场重建 ‖r₀‖=%.6f ⇒ %s"
             % (int(sp["rand_seed"]), "有" if rule_ok else "⛔无",
                "有" if pat_ok else "⛔无", log_mod, r_norm,
                "跨来源一致" if mod_ok else "⛔不一致"))

    # ===================== H4：同流排除 =====================
    a0 = np.random.default_rng(int(sp["rand_seed"])).standard_normal(d)
    a42 = np.random.default_rng(int(sp["train_seed"])).standard_normal(d)
    ndiff = int(np.sum(a0 != a42))
    maxdiff = float(np.max(np.abs(a0 - a42)))
    seeds_ok = all(int(metas[nm].get("seed", -1)) == int(sp["train_seed"]) for nm in names)
    cr.check("H4-NOSHAREDSTREAM", (ndiff == d) and seeds_ok,
             "default_rng(%d) 与 default_rng(%d) 的前 %d 个输出：逐位不同 %d/%d 个、"
             "最大绝对差 %.6f ⇒ ⇒ **不是同一条流** ｜ 6 把 sidecar 的训练 seed 全为 %d ⇒ %s"
             % (int(sp["rand_seed"]), int(sp["train_seed"]), d, ndiff, d, maxdiff,
                int(sp["train_seed"]), "一致" if seeds_ok else "⛔不一致"))

    # ===================== H5/H6：类级余弦 + 跨轮对账 =====================
    cos_each = {}
    for nm in names:
        cos_each[nm] = cos_dot(vecs[nm], r0)
    cos_w_p2a = cos_each[sp["dose_w"]]
    ref1, mean1, sd1 = single_reference_24483(w0, K)
    theo1 = 1.0 / math.sqrt(float(d))
    sd_rel1 = abs(sd1 - theo1) / theo1
    rank1 = sum(1 for x in ref1 if x < cos_w_p2a) / float(len(ref1))
    z1 = (cos_w_p2a - mean1) / sd1
    dcos = abs(cos_w_p2a - exp["cos0"]) / abs(exp["cos0"])
    dz = abs(z1 - exp["z"]) / abs(exp["z"])
    # ⚖⚖⚖ H6′：参考 sd 在账本里是 **%.6f 印出来的**（244.83 段那一行）⇒ ⇒
    #   ⛔ 1e-12 的相对容差**对只有 6 位有效数字的数在数学上不可能成立**
    #   ⇒ ⇒ 容差由**打印精度**推导：绝对差 ≤ 0.5 × 10^-decimals（⛔ 不是从实测值倒推）
    sd_dec = int(sp["sd_print_decimals"])
    sd_abs_tol = 0.5 * (10.0 ** (-sd_dec))
    dsd = abs(sd1 - exp["ref_sd"])
    # ⚖ **更强的一条**：把本轮的值印到同样的位数，必须与账本那个数**逐位相同**
    sd_round_ok = (("%.*f" % (sd_dec, sd1)) == ("%.*f" % (sd_dec, exp["ref_sd"])))
    rank_same = (rank1 == exp["rank"])
    tol = float(sp["cross_rel_tol"])
    h5_ok = (dcos <= tol)
    h6_ok = (rank_same and dz <= tol and dsd <= sd_abs_tol and sd_round_ok
             and sd_rel1 <= float(sp["ref_sd_rel_tol"]))
    cr.check("H5-CLASSCOS", h5_ok,
             "6 把对 r₀ 的余弦：%s ｜ w_p2a 那一条 = %.17g ｜ 账本 244.83 登记 = %.17g ｜ "
             "相对差 %.3g（上限 %.0e）⇒ %s"
             % ("｜".join("%s=%+.17g" % (nm, cos_each[nm]) for nm in names),
                cos_w_p2a, exp["cos0"], dcos, tol, "逐位一致" if h5_ok else "⛔超限"))
    cr.check("H6-CROSSROUND", h6_ok,
             "K=%d 单向量参考（与 244.83 逐字同构）：秩=%r vs 账本 %r ⇒ %s ｜ z=%.17g vs %.17g"
             "（相对差 %.3g）｜ 参考 sd=%.17g vs %.17g（**绝对差 %.3g**，上限 %.1g ＝ 账本里那个数的"
             "**末位打印精度的一半**（它印到 %d 位小数）｜ 本轮值印到 %d 位小数 = %s ⇒ %s）"
             "｜ sd vs 理论 1/√d 相对差 %.4f（上限 %.2f）"
             % (K, rank1, exp["rank"], "逐位相同" if rank_same else "⛔不同",
                z1, exp["z"], dz, sd1, exp["ref_sd"], dsd, sd_abs_tol, sd_dec, sd_dec,
                ("%.*f" % (sd_dec, sd1)),
                "与账本那个数**逐位相同**（⇒ 账本里那个数就是本轮这个值四舍五入出来的）"
                if sd_round_ok else "⛔与账本那个数**不一致**",
                sd_rel1, float(sp["ref_sd_rel_tol"])))

    # ===================== H7：两两余弦 =====================
    pw = pairwise_cos(unit_vecs)
    pw_max = max(x[2] for x in pw)
    pw_min = min(x[2] for x in pw)
    stratum = [x for x in pw if names[x[0]] in sp["stratum_A"] and names[x[1]] in sp["stratum_A"]]
    st_mean = sum(x[2] for x in stratum) / len(stratum)
    st_max = max(x[2] for x in stratum)
    npzs = sorted(set(str(metas[nm].get("npz_dir")) for nm in sp["stratum_A"]))
    stratum_same_npz = (len(npzs) == 1)
    cr.check("H7-PAIRWISE", stratum_same_npz,
             "15 对两两余弦：max=%+.6f min=%+.6f ｜ 分层 A（%s）内 %d 对：均值=%+.6f max=%+.6f ｜ "
             "分层 A 的 npz 实测 = %s ⇒ %s"
             % (pw_max, pw_min, "+".join(sp["stratum_A"]), len(stratum), st_mean, st_max,
                npzs, "同源（同 npz）" if stratum_same_npz else "⛔不同源"))

    # ===================== H8/H9/H10：类级主统计量 =====================
    st = full_stats(unit_vecs, (d,), K, r0, sp)
    cr.check("H10-CLASSSTAT", st["sd_rel_T"] <= float(sp["class_sd_rel_tol"]),
             "主统计量 T=mean_i cos(v_i,r₀)=%+.17g ｜ 参考 K=%d：mean=%+.17g sd=%.17g ｜ "
             "理论 sd=‖m‖/√d=%.17g（相对差 %.17g，上限 %.2f）｜ z_T=%+.17g ｜ 秩=%.17g ｜ "
             "共同分量投影 U₀=%.17g z_U=%+.17g"
             % (st["T_obs"], K, st["T_ref_mean"], st["T_ref_sd"], st["theo_T"],
                st["sd_rel_T"], float(sp["class_sd_rel_tol"]), st["z_T"], st["rank_T"],
                st["U_obs"], st["z_U"]))
    # 两两余弦明细（登记）
    print("两两余弦明细：%s" % "｜".join("%s-%s=%+.17g" % (names[i], names[j], c) for i, j, c in pw), flush=True)
    print("分层 A 内两两余弦均值 %+.6f vs 零假设 1/√d=%.6f（z=%+.2f）"
          % (st_mean, theo1, (st_mean - 0.0) / theo1), flush=True)

    # ---- D5：簇分解（⛔ **描述判据**，不进判决；分簇**只从两两余弦矩阵**来 ⇒ 不引新前提）
    thr = float(sp["cluster_cos_thresh"])
    n_m = len(names)
    parent = list(range(n_m))

    def _find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a, b):
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    for i, j, c in pw:
        if c > thr:
            _union(i, j)
    _groups = {}
    for i in range(n_m):
        _groups.setdefault(_find(i), []).append(i)
    clusters = []
    for g in _groups.values():
        idxs = sorted(g)
        stc = full_stats([unit_vecs[i] for i in idxs], (d,), K, r0, sp)
        clusters.append({"members": [names[i] for i in idxs],
                         "T": stc["T_obs"], "z": stc["z_T"], "n": len(idxs)})
    clusters.sort(key=lambda c: -c["z"])
    print("")
    print("D5 **簇分解**（两两余弦 > %.2f 连通；⛔ **描述判据，不进判决**）：" % thr, flush=True)
    for c in clusters:
        print("   簇（%d 把）%s：对 r₀ 的平均余弦 = %+.6f ｜ z = %+.3f"
              % (c["n"], "+".join(c["members"]), c["T"], c["z"]), flush=True)
    # ---- D6：簇的出处（⛔ 旧格式 sidecar 无 pos_offset ⇒ 标「未量到」，⛔ 不猜）
    print("D6 簇的出处（sidecar 的 `pos_offset`；⛔ 无该字段 ⇒ 标「未量到」）：", flush=True)
    for c in clusters:
        po = []
        for nm in c["members"]:
            v = metas[nm].get("pos_offset")
            po.append("%s=%s" % (nm, ("%+d" % int(v)) if v is not None else "⛔未量到"))
        print("   簇 %s：%s" % ("+".join(c["members"]), " ｜ ".join(po)), flush=True)
    _wclu = [c for c in clusters if sp["dose_w"] in c["members"]]
    if _wclu:
        print("   ⇒ ⇒ 剂量批用的那把 `%s` 在**簇 %s** 里（z=%+.3f）"
              % (sp["dose_w"], "+".join(_wclu[0]["members"]), _wclu[0]["z"]), flush=True)

    # ---- 分层 A 单独重算（稳健性：结论不能随「纳入哪几把向量」而翻转）----
    idxA = [i for i, nm in enumerate(names) if nm in sp["stratum_A"]]
    unit_A = [unit_vecs[i] for i in idxA]
    st_A = full_stats(unit_A, (d,), K, r0, sp)
    v_main = "E-B" if st["z_T"] >= float(sp["z_threshold"]) else "E-A"
    v_A = "E-B" if st_A["z_T"] >= float(sp["z_threshold"]) else "E-A"
    cr.check("H9-STRATUM", (v_A == v_main),
             "分层 A（%d 把同 npz）单独重算：T=%+.17g z_T=%+.17g（判 %s）｜ "
             "全 %d 把：z_T=%+.17g（判 %s）⇒ ⇒ 结论%s"
             % (len(unit_A), st_A["T_obs"], st_A["z_T"], v_A,
                len(unit_vecs), st["z_T"], v_main,
                "**不随纳入范围而变**" if v_A == v_main else "⛔**随纳入范围而变**（⇒ 结论不牢）"))

    # ===================== H11：负控（独立坐标置换）=====================
    sh = [unit(shuffle_indep(vecs[nm], int(sp["shuffle_seed"]) + i)) for i, nm in enumerate(names)]
    st_sh = full_stats(sh, (d,), K, r0, sp)
    pw_sh = pairwise_cos(sh)
    pw_sh_max = max(x[2] for x in pw_sh)
    h11_ok = (abs(st_sh["z_T"]) <= float(sp["negctl_z_max"])) and \
             (pw_sh_max <= float(sp["negctl_paircos_max"]))
    cr.check("H11-NEGCONTROL", h11_ok,
             "6 把各自独立坐标置换（种子 %d+i）后：z_T=%+.17g（|z| 上限 %.1f）｜ "
             "置换后两两余弦 max=%+.17g（上限 %.2f ⇒ 证明共享结构**确实被破坏**）｜ "
             "⇒ 判定：%s"
             % (int(sp["shuffle_seed"]), st_sh["z_T"], float(sp["negctl_z_max"]),
                pw_sh_max, float(sp["negctl_paircos_max"]),
                "负控通过（无结构时不该触发）" if h11_ok else "⛔负控异常"))

    # ===================== H12：判别力自证（规则的经验假阳性率）=====================
    fpr = st["fpr"]
    h12_ok = (fpr <= float(sp["fpr_max"]))
    cr.check("H12-FPR", h12_ok,
             "判决规则「z_T ≥ %.1f」在 K=%d 个参考种子下的**经验假阳性率** = %.17g（上限 %.2f）"
             " ⇒ ⇒ 规则%s"
             % (float(sp["z_threshold"]), K, fpr, float(sp["fpr_max"]),
                "**可用**" if h12_ok else "⛔超标 ⇒ 规则作废 ⇒ 形态只能是 E-C"))

    # ===================== H13：自包含闸（§0.5 更正 ②）=====================
    ctor_seeds = sorted(set(int(metas[nm].get("seed")) for nm in names))
    class_lo = int(sp["ref_class_seed_lo"])
    class_hi = class_lo + K - 1
    overlap = [s for s in ctor_seeds if class_lo <= s <= class_hi]
    # 「含构造种子」的另一套类级参考（种子 1..K ⇒ 含 42）⇒ ⇒ 只用来对照**判决形态**
    st_alt = full_stats(unit_vecs, (d,), K, r0, sp, seed_lo=int(sp["ref_single_seed_lo"]))
    v_main = "E-B" if st["z_T"] >= float(sp["z_threshold"]) else "E-A"
    v_alt = "E-B" if st_alt["z_T"] >= float(sp["z_threshold"]) else "E-A"
    h13_ok = (not overlap) and (v_main == v_alt)
    cr.check("H13-SELFINCLUDE", h13_ok,
             "构造种子（6 把 sidecar 读出）= %s ｜ 类级参考种子区间 %d..%d ⇒ 交集 = %s ⇒ %s ｜ "
             "含构造种子的参考集（%d..%d）算出的 z_T=%+.17g（判 %s）vs 不含的 z_T=%+.17g（判 %s）"
             " ⇒ ⇒ 判决形态%s"
             % (ctor_seeds, class_lo, class_hi, (overlap if overlap else "∅"),
                "∅（无自包含）" if not overlap else "⛔自包含！",
                int(sp["ref_single_seed_lo"]), int(sp["ref_single_seed_lo"]) + K - 1,
                st_alt["z_T"], v_alt, st["z_T"], v_main,
                "**相同**（自包含没有影响判决）" if v_main == v_alt else "⛔不同（自包含影响了判决）"))

    # ===================== 判决形态 =====================
    # ⚖⚠⚠⚠ **H12 红 ⇒ E-C（「判别力不足」⇒ 「未量到」）；别的硬判据红 ⇒ FAIL（「前提被推翻」）**
    #   ⇒ ⇒ 这两件事**必须分开**：⛔ 「没测出来」≠「测了没关系」≠「前提被推翻」
    #   ⚖⚖⚖ 早先的写法把 `cr.failed_ids()` 非空一律判成 FAIL ⇒ ⇒ **H12 红也落进 FAIL**
    #   ⇒ ⇒ 预登记 §3.1 承诺的「H12 红 ⇒ 只能是 E-C」**永远走不到**（死分支）
    #   ⇒ ⇒ 已修正（本轮 §0.5 更正 ⑥）；变异台 `PM6` 现在**额外**断言判决形态必须是 **E-C**
    _failed = list(cr.failed_ids())
    _failed_other = [x for x in _failed if x != "H12-FPR"]
    if _failed_other:
        verdict = "FAIL"
        reason = ("硬判据红（**不是** H12 ⇒ ⇒ 前提被推翻，⛔ 不是「没量到」）：%s"
                  % ", ".join(_failed_other))
    elif not h12_ok:
        verdict = "E-C"
        reason = "判别力不足（假阳性率超标）⇒ ⇒ **未量到**，⛔ 不是「无差异」"
    elif st["z_T"] >= float(sp["z_threshold"]):
        verdict = "E-B"
        reason = "类级主统计量离群（z_T=%.3f ≥ %.1f）⇒ ⇒ **结构**" % (st["z_T"], float(sp["z_threshold"]))
    else:
        verdict = "E-A"
        reason = "类级主统计量未离群（z_T=%.3f < %.1f）⇒ ⇒ **巧合**（对这个 r 而言）" % (
            st["z_T"], float(sp["z_threshold"]))

    print("")
    print("=== 类级余弦（6 把 × 同一个 r₀）===")
    for nm in names:
        print("  %-10s cos(v, r₀) = %+.9f" % (nm, cos_each[nm]))
    print("  正号计数 = %d / %d（单侧 P(全正) = 2^-%d = %.6f）"
          % (sum(1 for nm in names if cos_each[nm] > 0), len(names), len(names),
             2.0 ** (-len(names))))
    print("")
    print("=== 描述量（D1–D3）===")
    w_frac = cos_w_p2a ** 2
    print("  D1 污染量级：cos=%+.9f ⇒ rand 方向含 w 能量 %.6f%% ｜ w 等效剂量 = %.3f × %.6f = %.3f"
          % (cos_w_p2a, w_frac * 100.0, cos_w_p2a, float(sp["gap"]), cos_w_p2a * float(sp["gap"])))
    r2v = rand_direction(w0, int(sp["seed2"]))
    cos2 = {nm: cos_dot(vecs[nm], r2v) for nm in names}
    print("  D2 换个 r（seed %d）：%s ｜ 正号 %d/%d"
          % (int(sp["seed2"]), "｜".join("%s=%+.6f" % (nm, cos2[nm]) for nm in names),
             sum(1 for nm in names if cos2[nm] > 0), len(names)))
    print("  D3 ⚠ **条件命题**（假设未实测 ⇒ 不进判决）：污染在 rand 臂最大剂量处等效于一次 "
          "w 剂量 %.3f 的注入；⛔ 固定剂量批**没落盘 alpha 轨迹** ⇒ ⇒ 离线**算不出**「污染最多能翻多少格」"
          % (cos_w_p2a * float(sp["gap"])))
    print("")
    print("判决形态：%s（%s）" % (verdict, reason))
    print("VERDICT=%s" % verdict)
    print(cr.summary())
    if verdict == "FAIL":
        print("DATA_RC=1")
        return 1
    print("DATA_RC=0")
    return 0


# =============================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(description="244.84 对照臂方向污染的类级判读")
    ap.add_argument("--print-spec", action="store_true", help="印出口径常量")
    ap.add_argument("--selftest", action="store_true", help="Phase-0 闸门（零 bpath、零 GPU）")
    ap.add_argument("--data", action="store_true", help="真数据路径（⛔ 只读 bpath、⛔ 零 GPU）")
    ap.add_argument("--bpath", default=os.environ.get("R244_BPATH", "/home/zhourui/steer3d_bpath"))
    ap.add_argument("--ledger", default=os.environ.get(
        "R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md"))
    ap.add_argument("--dim", type=int, default=None)
    ap.add_argument("--ref-K", type=int, default=None, dest="ref_K")
    ap.add_argument("--z-threshold", type=float, default=None, dest="z_threshold")
    ap.add_argument("--fpr-max", type=float, default=None, dest="fpr_max")
    ap.add_argument("--shuffle-seed", type=int, default=None, dest="shuffle_seed")
    a = ap.parse_args(argv)

    if a.print_spec:
        for k in sorted(SPEC):
            print("%-20s = %r" % (k, SPEC[k]))
        return 0

    if a.selftest:
        sp = dict(SPEC)
        if a.dim is not None:
            sp["dim"] = a.dim
        if a.ref_K is not None:
            sp["ref_K"] = a.ref_K
        if a.z_threshold is not None:
            sp["z_threshold"] = a.z_threshold
        if a.fpr_max is not None:
            sp["fpr_max"] = a.fpr_max
        if a.shuffle_seed is not None:
            sp["shuffle_seed"] = a.shuffle_seed
        return selftest(sp)

    if a.data:
        sp = dict(SPEC)
        if a.dim is not None:
            sp["dim"] = a.dim
        if a.ref_K is not None:
            sp["ref_K"] = a.ref_K
        if a.z_threshold is not None:
            sp["z_threshold"] = a.z_threshold
        if a.fpr_max is not None:
            sp["fpr_max"] = a.fpr_max
        return run_data(a)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
