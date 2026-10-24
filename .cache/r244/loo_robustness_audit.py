#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""loo_robustness_audit.py —— **类级结论的留一稳健性**（244.85）。

⚖⚖⚖⚖⚖ **这个文件回答什么**
   244.84（对照臂方向污染的类级判读，形态 **E-B**）实测出：

       类级主统计量 T = mean_i cos(v_i, r₀) = +0.026669793515452608
       z_T = +2.2117475056125788   （阈值 2.0 ⇒ ⇒ 判「结构」）

   ⇒ ⇒ 它声称「`r₀` **系统性地**落在 steering 向量的公共方向上」。

⚖⚖⚖⚖⚖ **但 244.84 自己登记的事实让这句话变成危楼**：
   · `w_p2a`（**剂量批用的那把**）对 `r₀` 的余弦 **+0.060171700**，是 6 把里**最大**的；
   · 簇 A（`w_L19_m1`+`w_t1`+`w_p2a`）z=**+2.393**、簇 B（`w_L19_m0`+`w_real`+`w_old`）z=**+0.046**
     ⇒ ⇒ 偏高**只集中在 `w_p2a` 所属的那个簇**。

   ⇒ ⇒ **本轮问的是**：这个「类级结构」，是不是被**剂量批那一把**撑起来的？

⚖⚖⚖⚖⚖ **本轮的手法：留一法（LOO）**
   对 **6 个「去掉第 i 把」的 5 元子集** ＋ **基线全集（n=6）** 各自**重算**：
   `T(S)` / `z_T(S)` / 经验秩 / 参考 sd / 理论 sd / **自己的经验假阳性率 FPR_n**。
   ⛔ **n=6 的 FPR 不许套到 n=5**（参考分布的 sd 随 n 变 ⇒ ⇒ 尾概率也变）。

⚖⚖⚖⚖⚖ **纪律（本文件的形状就是这些纪律）**
   ① **口径只从预登记读**：`.cache/xcheck/R6_LOO_ROBUSTNESS_PREREG.md`（244.85 签）
      ⇒ ⇒ 口径常量集中在 `SPEC`，且**逐条被 `--print-spec` 印出来**（⇒ 变异台能逐条改）。
   ② **期望值从账本读，不从代码读**（⛔ 代码里不写死 244.84 的数）：
      账本读不到 ⇒ ⇒ **HardFail**，⛔ 不用代码里的字面值兜底、⛔ 不静默降级。
   ③ **每条硬判据都有「跨来源」那一半**（只比「两臂相等」的判据在结构上可能恒绿）。
   ④ **每条判据能红**：`--selftest`（G0-1..G0-7 合成夹具，零 bpath、零 GPU）
      ＋ 变异台 `mut_loo_robustness_audit.py`（⛔ 变异台必须能红）＋ **判决形态也被断言**。
   ⑤ **判决只算一次**：印出来的 = 返回的。
   ⑥ ⛔ **未量到 ≠ 没差异 ≠ 失败**。
   ⑦ ⚖ **判别力先于结论**：判决规则**逐 n** 的经验假阳性率是判据（H9），
      ⛔ 超标 ⇒ 形态只能是 **F-E**（未量到），⛔ 不是 FAIL。
   ⑧ ⛔ **判决形态映射写成规则表**（`VERDICT_TABLE`）⇒ ⇒ 变异台改**表**就能红，
      ⛔ 不必依赖真数据的形态 ⇒ ⇒ 死分支藏不住（244.84 的教训）。

⚖⚖⚖⚖⚖ **本文件**不**产出**「污染对改判率的影响」的任何**数值**
   （预登记 §4.1：固定剂量批**没落盘 alpha 轨迹** ⇒ ⇒ 离线算不出来）
   ⇒ ⇒ 那个量本轮只以**条件命题**的形式登记，⛔ 不进判决、⛔ 不进摘要。
"""

import argparse
import json
import math
import os
import re
import struct
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
    "layer": 20,                 # Q8：注入层
    "train_seed": 42,            # Q6：训练种子（6 把 sidecar 全同）
    "rand_seed": 0,              # Q5：rand 臂随机向量的种子
    "marker_ids": [13824, 14190, 6771, 10061, 7196, 88190, 80022],   # Q7
    "gap": 113.47440338134766,   # 剂量批的 --gap

    # ---- 统计口径 ----
    "ref_K": 2000,               # Q9：参考分布规模 K（与 244.84 同口径 ⇒ 可对账）
    "ref_single_seed_lo": 1,     # 单向量参考的种子起点（244.83 口径，H11 的「含 42」那一套）
    "ref_class_seed_lo": 100001,  # Q15：**类级**参考的种子起点（⛔ 与构造种子 42 不相交）
    "ref_sd_rel_tol": 0.05,      # Q10：单向量参考 sd vs 理论 1/√d 的相对差上限
    "class_sd_rel_tol": 0.05,    # Q10：类级参考 sd vs ‖m_S‖/√d 的相对差上限（**逐子集**）
    "z_threshold": 2.0,          # Q13：判决规则的单侧 z 阈值（**逐子集**）
    "fpr_max": 0.05,             # Q14：规则的经验假阳性率上限（**逐子集 n 各自实测**）
    "negctl_z_max": 2.0,         # H10：负控的 |z| 上限（沿用 244.84，⛔ 不许放宽）
    "negctl_paircos_max": 0.15,  # H10：负控置换后两两余弦的上限（= 6.79/√d）
    "shuffle_seed": 24484,       # H10：置换种子（⚖ **沿用 244.84** ⇒ ⇒ 负控的数可跨轮对账）
    "seed2": 42,                 # 描述量：换个 r 的对照

    # ---- 跨轮对账容差（Q18）----
    "cross_rel_tol": 1e-12,      # 全精度登记值：相对差上限
    "cos_print_decimals": 9,     # 账本里 6 条余弦的打印小数位 ⇒ 容差 0.5×10^-9
    "cluster_T_print_decimals": 6,   # 账本里簇 T 的打印小数位 ⇒ 容差 0.5×10^-6
    "cluster_z_print_decimals": 3,   # 账本里簇 z 的打印小数位 ⇒ 容差 0.5×10^-3
    "cluster_cos_thresh": 0.5,   # Q19：两两余弦分簇阈值（> thresh ⇒ 连边）

    # ---- 本轮新增：子集族（Q12，**与预登记 §2.1 逐条相同**）----
    "subset_family": {
        "FULL": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1", "w_p2a", "w_old"],
        "LOO-m0": ["w_L19_m1", "w_real", "w_t1", "w_p2a", "w_old"],
        "LOO-m1": ["w_L19_m0", "w_real", "w_t1", "w_p2a", "w_old"],
        "LOO-real": ["w_L19_m0", "w_L19_m1", "w_t1", "w_p2a", "w_old"],
        "LOO-t1": ["w_L19_m0", "w_L19_m1", "w_real", "w_p2a", "w_old"],
        "LOO-p2a": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1", "w_old"],
        "LOO-old": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1", "w_p2a"],
        "STRAT-A": ["w_L19_m0", "w_L19_m1", "w_real", "w_t1"],
        "CLU-A": ["w_L19_m1", "w_t1", "w_p2a"],
        "CLU-B": ["w_L19_m0", "w_real", "w_old"],
        "SINGLE-m0": ["w_L19_m0"],
        "SINGLE-m1": ["w_L19_m1"],
        "SINGLE-real": ["w_real"],
        "SINGLE-t1": ["w_t1"],
        "SINGLE-p2a": ["w_p2a"],
        "SINGLE-old": ["w_old"],
    },
    # Q16：决策族（**只有它们**决定判决形态）
    "decision_family": ["FULL", "LOO-m0", "LOO-m1", "LOO-real", "LOO-t1",
                        "LOO-p2a", "LOO-old"],
    # Q17：描述族（算出来、登记，⛔ 不决定形态）
    "descriptive_family": ["STRAT-A", "CLU-A", "CLU-B",
                            "SINGLE-m0", "SINGLE-m1", "SINGLE-real",
                            "SINGLE-t1", "SINGLE-p2a", "SINGLE-old"],
    "dose_key": "LOO-p2a",       # 关键位：去掉剂量批那一把
    "full_key": "FULL",          # 基线
}

# ⚖⚖⚖⚖⚖ **判决形态映射 —— 写成规则表**（⛔ 不是 if/elif 链）
#   ⇒ ⇒ 变异台改**这张表**就能让 G0-3 红，⛔ **不必依赖真数据的形态** ⇒ ⇒ 死分支藏不住。
#   规则按顺序判定，第一条命中的给出形态。每条规则 = （条件名, 该条件必须取的值, 形态）。
#   条件名（由 `verdict_conditions` 计算）：
#     hard_ok      ⇒ 除 H9 外的硬判据全绿
#     disc_ok      ⇒ H9（逐 n 判别力）绿
#     full_ok      ⇒ FULL 的形态 == 期望形态
#     dose_ea      ⇒ 关键位子集的形态 == E-A
#     other_loo_ea ⇒ LOO 族里（**除关键位**）另有子集的形态 == E-A
VERDICT_TABLE = [
    ("hard_ok", False, "FAIL"),       # 前提被推翻（⛔ 不是「没量到」）
    ("disc_ok", False, "F-E"),        # 判别力不足 ⇒ ⇒ 未量到（⛔ 不是「无差异」）
    ("full_ok", False, "FAIL"),       # 基线形态与账本登记的不一致 ⇒ ⇒ 前提被推翻
    ("dose_ea", True, "F-B"),         # 由剂量批那一把驱动
    ("other_loo_ea", True, "F-C"),    # 子集敏感（但不是剂量那一把）
    ("else", None, "F-A"),            # 稳健
]

# ⚖ 预登记 §3.1 声明的**有序**形态表（实现必须与它一致 ⇒ H7）
PREREG_FORMS_ORDER = ["FAIL", "F-E", "F-B", "F-C", "F-A"]

# ⚖ 短名映射（子集族命名用）
SHORT = {"w_L19_m0": "m0", "w_L19_m1": "m1", "w_real": "real",
         "w_t1": "t1", "w_p2a": "p2a", "w_old": "old"}


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
    """⚖ 均值 + 样本方差（ddof=1）—— 与 244.84 的写法逐字同构。"""
    n = len(vals)
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / (n - 1)
    return mean, math.sqrt(var)


class Collector(object):
    """⚖ 判据收集器（沿用 244.84 的形状）：印出来的 = 返回的。"""

    def __init__(self):
        self.rows = []

    def check(self, cid, ok, detail):
        ok = bool(ok)
        self.rows.append((cid, ok, detail))
        print("[%s] %-16s %s" % ("PASS" if ok else "FAIL", cid, detail), flush=True)
        return ok

    def failed_ids(self):
        return [r[0] for r in self.rows if not r[1]]

    def pass_ids(self):
        return [r[0] for r in self.rows if r[1]]

    def summary(self):
        np_ = sum(1 for r in self.rows if r[1])
        return "判据汇总：%d 条 ｜ PASS %d ｜ FAIL %d" % (len(self.rows), np_, len(self.rows) - np_)


def ulp_diff(a, b):
    """⚖ 两个 double 之间的 **ULP 距离**（可表示的浮点数之间的步数）。

    ⚖⚖⚖ **为什么要它**：H6 的容差是「相对差 ≤ 1e-12」⇒ ⇒ **差 1 ULP 照样过**
    ⇒ ⇒ 「差 0」和「差几个 ULP」在 H6 里**长得一模一样**
    ⇒ ⇒ H13（位级对账）必须能**把差值单独印出来**，⛔ 不能只说「在容差内」。
    ⚖ 排序键：IEEE-754 双精度的位模式在**同号**内与数值同序 ⇒ ⇒ 负数取补码。
    """
    def key(x):
        u = struct.unpack("<Q", struct.pack("<d", x))[0]
        return (~u + 1) & 0xFFFFFFFFFFFFFFFF if (u >> 63) else (u | 0x8000000000000000)
    return abs(key(float(a)) - key(float(b)))


# =============================================================================
# 随机方向与余弦（⚖ 口径逐字对应探针源码；与 244.84 同构 ⇒ 可跨轮对账）
# =============================================================================
def rand_dir_raw(shape, seed):
    """⚖ 探针的**前半**：`_g.standard_normal(_W0.shape).astype(np.float64)`"""
    g = np.random.default_rng(int(seed))
    return g.standard_normal(shape).astype(np.float64)


def rand_direction(w0, seed):
    """⚖ **探针里的 rand 规则**（逐字对应 `r241_probe.py` 的 `_g = default_rng(0)` 那一支）：
       W = standard_normal(shape).astype(float64) → 归一化 → × ‖w0‖（**float32 口径**）。
    ⚠⚠⚠ `w0` 必须是**原始 float32 数组**（⛔ 不是 float64 转换后的）。"""
    g = np.random.default_rng(int(seed))
    w = g.standard_normal(w0.shape).astype(np.float64)
    w = (w / np.linalg.norm(w)) * float(np.linalg.norm(w0))
    return w


def cos_dot(u, v):
    """⚖ 244.83/244.84 的余弦口径：`<u,v> / ‖u‖`（**v 已归一化**）⇒ ⇒ 标量。"""
    uu = np.asarray(u, dtype=np.float64).ravel()
    vv = np.asarray(v, dtype=np.float64).ravel()
    return float(np.dot(uu, vv) / np.linalg.norm(uu))


def unit(v):
    vv = np.asarray(v, dtype=np.float64).ravel()
    return vv / np.linalg.norm(vv)


def orth_component(v, r):
    """⚖ 把 v 在 r 上的分量**投影掉**再归一化 ⇒ ⇒ 与 r **严格正交**（余弦恒为 0）。
    合成夹具用它把「噪声」压到 0 ⇒ ⇒ 闸门的算术预期可逐位核对。"""
    rr = np.asarray(r, dtype=np.float64).ravel()
    vv = np.asarray(v, dtype=np.float64).ravel()
    w = vv - np.dot(vv, rr) * rr
    return w / np.linalg.norm(w)


def tilted(r, cos_theta, e):
    """⚖ 与 r 余弦恰为 `cos_theta` 的单位向量（e 必须与 r 正交）。"""
    rr = unit(r)
    ee = unit(e)
    c = float(cos_theta)
    return unit(c * rr + math.sqrt(max(0.0, 1.0 - c * c)) * ee)


# =============================================================================
# 子集统计（⚖ 逐子集：自己的零分布、自己的 sd、自己的 FPR_n）
# =============================================================================
def subset_stats(unit_vecs, shape, K, r0, spec, refs):
    """⚖⚖⚖ **一个子集的统计量**（`refs` = 该子集自己的 K 个参考方向）。

    返回：
      T_obs  = mean_i cos(v_i, r0)          （主统计量）
      z_T    = (T_obs − mean(T_ref)) / sd(T_ref)
      rank_T = #{T_s < T_obs} / K
      theo_T = ‖m_S‖ / √d                   （各向同性零假设下 T 的理论 sd，m = mean(v_i)）
      sd_rel_T= |sd(T_ref) − theo_T| / theo_T
      fpr_n  = #{z_s ≥ z_threshold} / K     （**该 n 专属**的经验假阳性率）
    """
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
    for rr in refs:
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
        "n": n, "T_obs": T_obs, "z_T": z_T, "rank_T": rank_T,
        "T_ref_mean": mT, "T_ref_sd": sT, "theo_T": theo_T, "sd_rel_T": sd_rel_T,
        "fpr": fpr, "mnorm": mnorm,
        "U_obs": U_obs, "z_U": z_U,
    }


def make_refs(shape, seed_lo, K):
    """⚖ 造 K 个**归一化**的各向同性参考方向（种子 `seed_lo .. seed_lo+K-1`）。
    ⚠ 与 244.84 的 `full_stats` **逐字同构**（先生成 float64，再除以自身范数）⇒ ⇒ 可跨轮对账。"""
    out = []
    for s in range(int(seed_lo), int(seed_lo) + int(K)):
        rr = rand_dir_raw(shape, s)
        rr = rr / np.linalg.norm(rr)
        out.append(rr)
    return out


def pairwise_cos(unit_vecs):
    """⚖ 两两余弦矩阵（上三角）⇒ 返回 [(i, j, cos)]。"""
    out = []
    n = len(unit_vecs)
    for i in range(n):
        for j in range(i + 1, n):
            out.append((i, j, cos_dot(unit_vecs[i], unit_vecs[j])))
    return out


def shuffle_indep(v, seed):
    """⚖ **独立**坐标置换（保范数、破共享结构）。
    ⚠⚠⚠ 每把向量必须用**各自**的置换：共用同一个 ⇒ ⇒ 正交变换 ⇒ ⇒ 两两余弦原封不动。"""
    v = np.asarray(v, dtype=np.float64).ravel()
    g = np.random.default_rng(int(seed))
    return v[g.permutation(v.shape[0])]


def clusters_from_pairwise(pw, n_m, thr):
    """⚖ 两两余弦 > thr 的**连通分量**（⚖ 与 244.84 的并查集写法同构）。"""
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
    groups = {}
    for i in range(n_m):
        groups.setdefault(_find(i), []).append(i)
    out = []
    for g in groups.values():
        out.append(sorted(g))
    out.sort(key=lambda g: (-len(g), g))
    return out


def build_family(members, strat_a, clu_a, clu_b):
    """⚖ 由成员表**程序化**构造子集族（FULL / LOO-× / SINGLE-× ＋ 三个显式子集）。
    ⚖ 用途：**与 `SPEC["subset_family"]` 的字面表互为独立表达** ⇒ ⇒ 两者不一致 ⇒ H5 红。"""
    fam = {"FULL": list(members)}
    for nm in members:
        fam["LOO-" + SHORT[nm]] = [x for x in members if x != nm]
    fam["STRAT-A"] = list(strat_a)
    fam["CLU-A"] = list(clu_a)
    fam["CLU-B"] = list(clu_b)
    for nm in members:
        fam["SINGLE-" + SHORT[nm]] = [nm]
    return fam


# =============================================================================
# 判决映射（⚖ 规则表驱动）
# =============================================================================
def verdict_conditions(shapes, hard_ok, disc_ok, full_expected, dose_key,
                       decision_family):
    """⚖ 把 §3.1 的条件算成一张「条件名 → 布尔」的字典。"""
    full_key = "FULL"
    full_ok = (shapes.get(full_key) == full_expected)
    dose_ea = (shapes.get(dose_key) == "E-A")
    other_loo_ea = False
    for k in decision_family:
        if k in (full_key, dose_key):
            continue
        if shapes.get(k) == "E-A":
            other_loo_ea = True
            break
    return {
        "hard_ok": bool(hard_ok),
        "disc_ok": bool(disc_ok),
        "full_ok": bool(full_ok),
        "dose_ea": bool(dose_ea),
        "other_loo_ea": bool(other_loo_ea),
    }


def verdict_from_subsets(shapes, hard_ok, disc_ok, full_expected, dose_key,
                         decision_family, table=None):
    """⚖⚖⚖ **判决只算一次**：遍历 `VERDICT_TABLE`，第一条命中的规则给出形态。
    ⛔ 表里的条件名必须与 `verdict_conditions` 返回的键**一一对应**（少一个 ⇒ 死分支）。"""
    tb = VERDICT_TABLE if table is None else table
    cond = verdict_conditions(shapes, hard_ok, disc_ok, full_expected, dose_key,
                              decision_family)
    for name, want, form in tb:
        if name == "else":
            return form, cond
        if name not in cond:
            die("VERDICT_TABLE 的条件名 %r 不在条件集合里 ⇒ ⇒ 规则表与实现脱节" % name)
        if cond[name] == want:
            return form, cond
    die("VERDICT_TABLE 没有 else 兜底 ⇒ ⇒ 判决可能落空")
    return "FAIL", cond


def verdict_why(form, cond, shapes, stats_by, dose_key, decision_family):
    """⚖ 判决理由（**数据驱动**：把「哪些子集掉出阈值」直接算出来，⛔ 不写死措辞）。
    ⚖⚠⚠ 措辞必须**由实测**决定 ⇒ ⇒ 事后不许改口径、只许改措辞（且要登记）。"""
    ea = [k for k in decision_family if shapes.get(k) == "E-A"]
    if form == "FAIL" and not cond["hard_ok"]:
        return "硬判据红（前提被推翻，⛔ 不是「没量到」）"
    if form == "FAIL" and not cond["full_ok"]:
        return "基线 FULL 的形态与账本登记的不一致（前提被推翻）"
    if form == "F-E":
        return "某个子集的 FPR_n 超标（判别力不足）⇒ ⇒ 未量到，⛔ 不是「无差异」"
    if form == "F-B":
        others = [k for k in ea if k != dose_key]
        return ("去掉剂量批那一把（%s，z=%+.4f）后结论掉出阈值 ⇒ ⇒ 类级结论**不稳健**"
                "（决策族里另有 %d 个子集也掉出阈值：%s）⇒ ⇒ 「r₀ 系统性落在 steering 向量的"
                "公共方向上」**未量到**"
                % (dose_key, stats_by[dose_key]["z_T"], len(others),
                   "、".join(others) if others else "无"))
    if form == "F-C":
        return ("LOO 族里另有子集掉出阈值（%s）⇒ ⇒ 类级结论**依赖纳入范围** ⇒ ⇒ "
                "「r₀ 系统性落在 steering 向量的公共方向上」**未量到**" % "、".join(ea))
    return "LOO 族全部仍离群 ⇒ ⇒ 类级结论对去掉任意一把都成立"


# =============================================================================
# 账本期望值（⛔ 代码里不写死 244.84 的数）
# =============================================================================
def ledger_expectations(ledger_path):
    """⚖⚖⚖ **期望值只从账本读**（244.84 段）。⛔ 读不到 ⇒ HardFail。

    读 244.84 段里的：类级 T / z_T / 秩 / 参考 sd / 理论 sd / FPR / 6 条逐条余弦 /
    STRAT-A 的 z / 簇 A·B 的 T 与 z / 负控的 z 与 paircos / 自包含对照的 z /
    判决形态 / `w_p2a.npy` 的 md5（244.78 段）。
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

    sec = section("244.84")
    if sec is None:
        die("账本里没有「## 修订 244.84」段 ⇒ ⇒ 期望值无处可读 ⇒ ⇒ "
            "⛔ 拒绝用代码里的字面值兜底 ⇒ ⇒ **先落账 244.84 再跑本轮**")

    def line_with(kw, what):
        for ln in sec.splitlines():
            if kw in ln:
                return ln
        die("账本 244.84 段里找不到含「%s」的行（%s）⇒ ⇒ 拒绝兜底" % (kw, what))

    def one(pat, what, s, grp=1):
        m = re.search(pat, s)
        if not m:
            die("账本 244.84 段里读不到「%s」（模式 %s）⇒ ⇒ 拒绝兜底" % (what, pat))
        return m.group(grp)

    exp = {}

    # ---- 类级 T / z_T / 秩 / sd / 理论 sd / FPR ----
    # ⚠⚠⚠ 关键字必须**唯一**：§1 的摘要行里也有「类级主统计量」四个字
    #   ⇒ ⇒ 必须用**带粗体标记**的写法，才能只命中 §2 判决面板的那一行。
    ln = line_with("**类级主统计量**", "类级 T")
    exp["T"] = float(one(r"\*\*([-+0-9.eE]+)\*\*", "类级 T", ln))
    ln = line_with("**z_T**（对参考种子分布）", "类级 z_T")
    exp["z"] = float(one(r"\*\*([-+0-9.eE]+)\*\*", "类级 z_T", ln))
    ln = line_with("经验秩 / 参考 sd", "秩/sd")
    mm = re.search(r"\|\s*([-+0-9.eE]+)\s*/\s*([-+0-9.eE]+)\s*/\s*([-+0-9.eE]+)\s*\|", ln)
    if not mm:
        die("账本 244.84 段里读不到「经验秩 / 参考 sd / 理论 sd」三个数 ⇒ ⇒ 拒绝兜底")
    exp["rank"] = float(mm.group(1))
    exp["ref_sd"] = float(mm.group(2))
    exp["theo_sd"] = float(mm.group(3))
    ln = line_with("经验假阳性率", "FPR")
    exp["fpr"] = float(one(r"\*\*([-+0-9.eE]+)\*\*", "FPR", ln))

    # ---- STRAT-A 的 z ----
    ln = line_with("分层稳健性", "STRAT-A 的 z")
    mm = re.search(r"z_T=([-+0-9.eE]+)（判 E-B）vs 全 6 把 z_T=([-+0-9.eE]+)（判 E-B）", ln)
    if not mm:
        die("账本 244.84 段里读不到 STRAT-A 的 z ⇒ ⇒ 拒绝兜底")
    exp["stratA_z"] = float(mm.group(1))
    exp["full_z_again"] = float(mm.group(2))

    # ---- 自包含对照的 z ----
    ln = line_with("自包含闸", "自包含对照的 z")
    mm = re.search(r"含它的参考集 z_T=([-+0-9.eE]+)（判 E-B）vs 不含 ([-+0-9.eE]+)（判 E-B）", ln)
    if not mm:
        die("账本 244.84 段里读不到自包含对照的 z ⇒ ⇒ 拒绝兜底")
    exp["selfincl_z"] = float(mm.group(1))
    exp["selfincl_alt_z"] = float(mm.group(2))

    # ---- 负控 ----
    ln = line_with("**负控**（6 把各自独立坐标置换）", "负控")
    exp["negctl_z"] = float(one(r"z_T=([-+0-9.eE]+)（z 的绝对值上限", "负控 z", ln))
    exp["negctl_paircos"] = float(one(r"置换后两两余弦 max=([-+0-9.eE]+)", "负控 paircos", ln))

    # ---- 6 条逐条余弦 ----
    exp["cos_each"] = {}
    for nm in SPEC["members"]:
        pat = r"-\s*`%s`\s*→\s*\*\*([-+0-9.eE]+)\*\*" % re.escape(nm)
        exp["cos_each"][nm] = float(one(pat, "%s 的余弦" % nm, sec))

    # ---- 簇 A / 簇 B 的成员、T、z ----
    ln = line_with("簇 A（", "簇 A")
    mm = re.search(r"簇 A（([^）]*)）平均余弦 ([-+0-9.eE]+)、z=([-+0-9.eE]+)", ln)
    if not mm:
        die("账本 244.84 段里读不到簇 A 的成员/T/z ⇒ ⇒ 拒绝兜底")
    exp["cluA_members"] = mm.group(1).split("+")
    exp["cluA_T"] = float(mm.group(2))
    exp["cluA_z"] = float(mm.group(3))
    mm = re.search(r"簇 B（([^）]*)）([-+0-9.eE]+)、z=([-+0-9.eE]+)", ln)
    if not mm:
        die("账本 244.84 段里读不到簇 B 的成员/T/z ⇒ ⇒ 拒绝兜底")
    exp["cluB_members"] = mm.group(1).split("+")
    exp["cluB_T"] = float(mm.group(2))
    exp["cluB_z"] = float(mm.group(3))

    # ---- 判决形态（244.84 登记的）----
    mm = re.search(r"判决形态\s*(E-[ABC])", sec)
    if not mm:
        die("账本 244.84 段里读不到「判决形态 E-x」⇒ ⇒ 拒绝兜底")
    exp["verdict84"] = mm.group(1)

    # ---- 244.83 段：w_p2a 的**全精度**余弦（更强的一条锚）----
    #   ⚖⚖⚖ 为什么需要它：244.84 段里那 6 条余弦只印到 **9 位小数**
    #   ⇒ ⇒ 绝对容差只能取 5e-10 ⇒ ⇒ 而「rand 向量的缩放因子从 float32 口径改成 float64 口径」
    #   （244.83 当场抓到的那个真 bug）只造成 **6.4e-10 的相对差** ⇒ ⇒ 在 9 位小数这条锚上**抓不到**
    #   ⇒ ⇒ 必须用 244.83 段里的**全精度** cos0（相对差 ≤ 1e-12）才抓得住。
    sec83 = section("244.83")
    if sec83 is None:
        die("账本里没有「## 修订 244.83」段 ⇒ ⇒ 全精度余弦锚无处可读 ⇒ ⇒ 拒绝兜底")
    m83 = re.search(r"cos0 `([-+0-9.eE]+)`", sec83)
    if not m83:
        die("账本 244.83 段里读不到「cos0 `...`」⇒ ⇒ 拒绝兜底")
    exp["cos0_full"] = float(m83.group(1))

    # ---- 244.78 段：w_p2a.npy 的 md5 ----
    # ⚠⚖⚖⚠ **本轮把 244.84 的「∈ 候选集合」收紧成「== 向量自己的那一个」**：
    #   账本 244.78 段那一行**同时**登记了三个文件的 md5（`w_p2a.npy` / `w_p2a.npy.json` / `train_p2a.log`）
    #   ⇒ ⇒ 244.84 的「实测 md5 ∈ 三个候选」在**形式上**也接受 meta 的 md5 与日志的 md5
    #   ⇒ ⇒ 本轮取「**`w_p2a.npy` 之后出现的第一个 md5**」（＝ 向量自己的那一个）⇒ ⇒ 更严
    #   （⛔ 这是**判据收紧**，⛔ **不动 244.84 的任何实测数**）
    sec78 = section("244.78") or ""
    md5_vec = None
    for line in sec78.splitlines():
        if "w_p2a.npy" in line and "md5" in line:
            pos = line.find("w_p2a.npy")
            mm3 = re.search(r"md5 `([0-9a-f]{32})`", line[pos:])
            if mm3:
                md5_vec = mm3.group(1)
                break
    exp["w_p2a_md5"] = md5_vec
    if md5_vec is None:
        die("账本 244.78 段里读不到 `w_p2a.npy` 的 md5 ⇒ ⇒ 拒绝兜底")
    return exp


# =============================================================================
# Phase-0 闸门（G0-1 .. G0-7）：合成夹具、零 bpath、零 GPU
# =============================================================================
def _fixture_vectors(role_cos, seed, d):
    """⚖ 合成夹具：`role_cos` = {成员名: 与 r 的余弦}（None ⇒ 与 r 严格正交）。
    ⚠ 构造成分种子必须落在所有参考区间之外（900k+）⇒ ⇒ 否则零分布**自包含**。"""
    g = np.random.default_rng(int(seed))
    r = g.standard_normal(d).astype(np.float64)
    r = r / np.linalg.norm(r)
    vs = {}
    for nm in SPEC["members"]:
        c = role_cos.get(nm)
        if c is None:
            vs[nm] = orth_component(g.standard_normal(d).astype(np.float64), r)
        else:
            e = orth_component(g.standard_normal(d).astype(np.float64), r)
            vs[nm] = tilted(r, c, e)
    return vs, r


def _fixture_shared(seed, d, frac=0.8):
    """⚖ 合成夹具：6 把共享一个公共分量 c，r 对准 c。"""
    g = np.random.default_rng(int(seed))
    c = g.standard_normal(d).astype(np.float64)
    c = c / np.linalg.norm(c)
    vs = {}
    for nm in SPEC["members"]:
        e = orth_component(g.standard_normal(d).astype(np.float64), c)
        vs[nm] = unit(frac * c + math.sqrt(max(0.0, 1.0 - frac * frac)) * e)
    return vs, c


def _run_fixture(vs, r0, spec, refs):
    """⚖ 在一套夹具上跑**全部 16 个子集**，返回 {子集名: 统计量} 与形态字典。"""
    fam = spec["subset_family"]
    out, shapes = {}, {}
    for name in sorted(fam):
        uvs = [unit(vs[nm]) for nm in fam[name]]
        st = subset_stats(uvs, (int(spec["dim"]),), int(spec["ref_K"]), r0, spec, refs)
        out[name] = st
        shapes[name] = "E-B" if st["z_T"] >= float(spec["z_threshold"]) else "E-A"
    return out, shapes


def _fixture_verdict(shapes, spec, hard_ok=True, disc_ok=True, full_expected="E-B"):
    return verdict_from_subsets(shapes, hard_ok, disc_ok, full_expected,
                                spec["dose_key"], spec["decision_family"])


def selftest(spec=None):
    """⚖⚖⚖ **Phase-0 闸门**（预登记 §5）：G0-1 .. G0-7。

    G0-1：无结构 ⇒ FULL=E-A（且**每个**子集的参考 sd 都被校准）
    G0-2：有结构 ⇒ FULL=E-B
    G0-3：**判决映射的分支可达性**（规则层）⇒ ⇒ F-A/F-B/F-C/F-E/FAIL 五个都要走到
    G0-4：端到端 ⇒ F-B（去掉剂量位 ⇒ 掉出阈值）
    G0-5：端到端 ⇒ F-C（去掉剂量位仍在、去掉主贡献位掉出）
    G0-6：端到端 ⇒ F-A（LOO 族全部仍在）
    G0-7：参考分布被人为污染 ⇒ 校准判据**必须**能红
    """
    sp = dict(SPEC if spec is None else spec)
    d = int(sp["dim"])
    K = int(sp["ref_K"])
    seed_lo = int(sp["ref_class_seed_lo"])
    fails = []

    def bad_seed(tag):
        """⚖ 构造成分种子必须与**两个**参考区间都不相交。"""
        bad = []
        for lo, hi, nm in ((1, K, "单向量参考 1..K"),
                           (seed_lo, seed_lo + K - 1, "类级参考 %d..%d" % (seed_lo, seed_lo + K - 1))):
            if lo <= tag <= hi:
                bad.append(nm)
        return bad

    refs = make_refs((d,), seed_lo, K)

    # ---- G0-1：无结构 ⇒ E-A ----
    vs1, r1 = _fixture_vectors({nm: None for nm in sp["members"]}, 900001, d)
    bad1 = bad_seed(900001)
    st1, sh1 = _run_fixture(vs1, r1, sp, refs)
    calib1 = all(st1[k]["sd_rel_T"] <= float(sp["class_sd_rel_tol"]) for k in st1)
    ok1 = (sh1["FULL"] == "E-A") and calib1 and (not bad1)
    print("[%s] G0-1（无结构 ⇒ 必须 E-A） FULL z=%+.3f ⇒ 判 %s ｜ 16 个子集的参考 sd 全部被校准 ⇒ %s "
          "｜ 构造成分种子 900001 与参考区间不相交 ⇒ %s"
          % ("PASS" if ok1 else "FAIL", st1["FULL"]["z_T"], sh1["FULL"],
             "是" if calib1 else "⛔否", "成立" if not bad1 else "⛔%s" % bad1), flush=True)
    if not ok1:
        fails.append("G0-1")

    # ---- G0-2：有结构 ⇒ E-B ----
    vs2, r2 = _fixture_shared(900201, d, frac=0.8)
    bad2 = bad_seed(900201)
    st2, sh2 = _run_fixture(vs2, r2, sp, refs)
    ok2 = (sh2["FULL"] == "E-B") and (not bad2)
    print("[%s] G0-2（有结构 ⇒ 必须 E-B） FULL z=%+.3f ⇒ 判 %s ｜ ‖m‖=%.4f "
          "｜ 构造成分种子 900201 ⇒ %s"
          % ("PASS" if ok2 else "FAIL", st2["FULL"]["z_T"], sh2["FULL"],
             st2["FULL"]["mnorm"], "不相交" if not bad2 else "⛔%s" % bad2), flush=True)
    if not ok2:
        fails.append("G0-2")

    # ---- G0-3：判决映射的分支可达性（规则层）----
    base = {k: "E-B" for k in sp["subset_family"]}
    cases = []
    c1 = dict(base)
    cases.append(("F-A", c1, True, True, "E-B"))
    c2 = dict(base)
    c2[sp["dose_key"]] = "E-A"
    cases.append(("F-B", c2, True, True, "E-B"))
    c3 = dict(base)
    c3["LOO-t1"] = "E-A"
    cases.append(("F-C", c3, True, True, "E-B"))
    c4 = dict(base)
    cases.append(("F-E", c4, True, False, "E-B"))
    c5 = dict(base)
    cases.append(("FAIL", c5, False, True, "E-B"))
    got = []
    for want, shapes_c, hok, dok, fexp in cases:
        f, _c = _fixture_verdict(shapes_c, sp, hard_ok=hok, disc_ok=dok, full_expected=fexp)
        got.append((want, f))
    ok3 = all(w == f for w, f in got)
    print("[%s] G0-3（判决映射的分支可达性） 期望/实得：%s ⇒ ⇒ %s"
          % ("PASS" if ok3 else "FAIL",
             "｜".join("%s→%s" % (w, f) for w, f in got),
             "五个分支**全部可达**" if ok3 else "⛔有死分支"), flush=True)
    if not ok3:
        fails.append("G0-3")

    # ---- G0-4：端到端 F-B ----
    role4 = {nm: None for nm in sp["members"]}
    role4[sp["dose_w"]] = 0.25
    vs4, r4 = _fixture_vectors(role4, 900401, d)
    st4, sh4 = _run_fixture(vs4, r4, sp, refs)
    f4, _ = _fixture_verdict(sh4, sp)
    exp4 = (sh4["FULL"] == "E-B") and (sh4[sp["dose_key"]] == "E-A")
    ok4 = (f4 == "F-B") and exp4
    print("[%s] G0-4（端到端 ⇒ 必须 F-B） FULL z=%+.3f（%s）｜ %s z=%+.3f（%s）｜ 形态 %s"
          % ("PASS" if ok4 else "FAIL", st4["FULL"]["z_T"], sh4["FULL"],
             sp["dose_key"], st4[sp["dose_key"]]["z_T"], sh4[sp["dose_key"]], f4), flush=True)
    if not ok4:
        fails.append("G0-4")

    # ---- G0-5：端到端 F-C ----
    role5 = {nm: None for nm in sp["members"]}
    role5["w_t1"] = 0.35
    role5[sp["dose_w"]] = 0.02
    vs5, r5 = _fixture_vectors(role5, 900501, d)
    st5, sh5 = _run_fixture(vs5, r5, sp, refs)
    f5, _ = _fixture_verdict(sh5, sp)
    exp5 = (sh5["FULL"] == "E-B") and (sh5[sp["dose_key"]] == "E-B") and (sh5["LOO-t1"] == "E-A")
    ok5 = (f5 == "F-C") and exp5
    print("[%s] G0-5（端到端 ⇒ 必须 F-C） FULL z=%+.3f（%s）｜ %s z=%+.3f（%s）｜ "
          "LOO-t1 z=%+.3f（%s）｜ 形态 %s"
          % ("PASS" if ok5 else "FAIL", st5["FULL"]["z_T"], sh5["FULL"],
             sp["dose_key"], st5[sp["dose_key"]]["z_T"], sh5[sp["dose_key"]],
             st5["LOO-t1"]["z_T"], sh5["LOO-t1"], f5), flush=True)
    if not ok5:
        fails.append("G0-5")

    # ---- G0-6：端到端 F-A ----
    vs6, r6 = _fixture_shared(900601, d, frac=0.8)
    st6, sh6 = _run_fixture(vs6, r6, sp, refs)
    f6, _ = _fixture_verdict(sh6, sp)
    ok6 = (f6 == "F-A") and all(sh6[k] == "E-B" for k in sp["decision_family"])
    print("[%s] G0-6（端到端 ⇒ 必须 F-A） 决策族 %d 个子集全部 E-B ⇒ %s ｜ 形态 %s"
          % ("PASS" if ok6 else "FAIL", len(sp["decision_family"]),
             "是" if all(sh6[k] == "E-B" for k in sp["decision_family"]) else "⛔否", f6), flush=True)
    if not ok6:
        fails.append("G0-6")

    # ---- G0-7：参考被污染 ⇒ 校准判据能红 ----
    Ts = []
    for rr in refs[:400]:
        Ts.append(sum(cos_dot(unit(vs1[nm]), rr) for nm in sp["members"]) / len(sp["members"]))
    half = len(Ts) // 2
    Ts[:half] = [x * 3.0 for x in Ts[:half]]
    mT, sT = stats(Ts)
    theo = st1["FULL"]["theo_T"]
    sd_rel = abs(sT - theo) / theo
    ok7 = sd_rel > float(sp["class_sd_rel_tol"])
    print("[%s] G0-7（参考被污染 ⇒ 校准必须能红） 污染后 sd 相对差=%.3f（上限 %.3f）⇒ ⇒ %s"
          % ("PASS" if ok7 else "FAIL", sd_rel, float(sp["class_sd_rel_tol"]),
             "判红（⇒ H8 有牙齿）" if ok7 else "⛔没红 ⇒ H8 是恒绿的"), flush=True)
    if not ok7:
        fails.append("G0-7")

    print("自检（Phase-0 G0-1..G0-7）：%d 条 ｜ FAIL %d 条%s"
          % (7, len(fails), ("：%s" % fails) if fails else ""), flush=True)
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
    print("账本期望值（244.84 段）：T=%r ｜ z=%r ｜ 秩=%r ｜ 参考 sd=%r ｜ 理论 sd=%r ｜ FPR=%r ｜ 判决形态=%s"
          % (exp["T"], exp["z"], exp["rank"], exp["ref_sd"], exp["theo_sd"],
             exp["fpr"], exp["verdict84"]), flush=True)
    print("账本 244.78 段登记的 w_p2a.npy md5：%s（⚖ 本轮**收紧**成「== 向量自己那一个」，"
          "⛔ 不接受同行的 meta/日志 md5）" % exp["w_p2a_md5"], flush=True)

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
    md5_ok = (md5_w == exp["w_p2a_md5"])
    cr.check("H1-IDENT", gap_ok and runner_gap_ok and pin_ok and md5_ok,
             "sidecar class_gap=%r == 批 --gap %r ⇒ %s ｜ runner 含该 --gap ⇒ %s ｜ "
             "w 臂日志 PINNED(ARM=w, W_PATH=…%s.npy) ⇒ %s ｜ 实测 md5=%s == 账本登记 %s ⇒ %s"
             % (sc.get("class_gap"), sp["gap"], "一致" if gap_ok else "⛔不一致",
                "有" if runner_gap_ok else "⛔无", sp["dose_w"], "有" if pin_ok else "⛔无",
                md5_w, exp["w_p2a_md5"], "是" if md5_ok else "⛔否"))

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
    m_mk = re.search(r"^MARKER_IDS\s*=\s*\[([^\]]*)\]", probe_text, re.M)
    m_ly = re.search(r"^LAYER\s*=\s*(\d+)", probe_text, re.M)
    src_mk = [int(x) for x in re.findall(r"\d+", m_mk.group(1))] if m_mk else []
    src_ly = int(m_ly.group(1)) if m_ly else -1
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

    # ===================== 两两余弦 / 簇 / 分层（跨来源的派生量）=====================
    unit_vecs = [vecs[nm] for nm in names]
    pw = pairwise_cos(unit_vecs)
    pw_max = max(x[2] for x in pw)
    pw_min = min(x[2] for x in pw)
    for i, j, c in pw:
        print("PAIR|%s|%s|%+.17g" % (names[i], names[j], c), flush=True)
    thr = float(sp["cluster_cos_thresh"])
    groups = clusters_from_pairwise(pw, len(names), thr)
    clu_groups = [sorted(names[i] for i in g) for g in groups]
    # ⚖ 分层 A：**实测**的同 npz 组（⛔ 不写死）
    npz_of = dict((nm, str(metas[nm].get("npz_dir"))) for nm in names)
    npz_counts = {}
    for nm in names:
        npz_counts[npz_of[nm]] = npz_counts.get(npz_of[nm], 0) + 1
    top_npz = sorted(npz_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    strat_a_derived = sorted([nm for nm in names if npz_of[nm] == top_npz])
    clu_a_derived = None
    clu_b_derived = None
    for g in clu_groups:
        if sp["dose_w"] in g:
            clu_a_derived = sorted(g)
        else:
            clu_b_derived = sorted(g)
    # ⚖ **族**：由程序化构造器生成（与 SPEC 的字面表互为独立表达）
    fam_derived = build_family(names, strat_a_derived, clu_a_derived or [], clu_b_derived or [])
    fam_spec = dict(sp["subset_family"])
    fam_same = (sorted(fam_derived.keys()) == sorted(fam_spec.keys()))
    if fam_same:
        for k in fam_spec:
            if sorted(fam_derived[k]) != sorted(fam_spec[k]):
                fam_same = False
                break
    # ⚖ LOO 族必须**恰好**每个成员被去掉一次
    loo_ok = True
    loo_dropped = []
    for nm in names:
        key = "LOO-" + SHORT[nm]
        if key not in fam_spec:
            loo_ok = False
            continue
        if sorted(fam_spec[key]) != sorted([x for x in names if x != nm]):
            loo_ok = False
        loo_dropped.append(nm)
    loo_ok = loo_ok and (len(set(loo_dropped)) == len(names))
    cr.check("H5-FAMILY", fam_same and loo_ok,
             "子集族：程序化构造（FULL/LOO/SINGLE ＋ 派生出的 STRAT-A/CLU-A/CLU-B）"
             "与 SPEC 字面表**逐子集相同** ⇒ %s ｜ LOO 族**恰好**每个成员被去掉一次 ⇒ %s ｜ "
             "实测分层：npz「%s」⇒ %s ｜ 实测簇：%s"
             % ("是" if fam_same else "⛔否", "是" if loo_ok else "⛔否",
                top_npz, "+".join(strat_a_derived),
                " ｜ ".join("{%s}" % "+".join(g) for g in clu_groups)))

    # ===================== 参考分布（**一次生成，全部子集共用**）=====================
    refs = make_refs((d,), int(sp["ref_class_seed_lo"]), K)
    refs_alt = make_refs((d,), int(sp["ref_single_seed_lo"]), K)

    # ===================== 逐子集统计 =====================
    fam = dict(sp["subset_family"])
    stats_by = {}
    shapes = {}
    for name in sorted(fam.keys()):
        uvs = [vecs[nm] for nm in fam[name]]
        st = subset_stats(uvs, (d,), K, r0, sp, refs)
        stats_by[name] = st
        shapes[name] = "E-B" if st["z_T"] >= float(sp["z_threshold"]) else "E-A"
        print("SUBSET|%s|n=%d|T=%+.17g|z=%+.17g|rank=%.17g|sd=%.17g|theo=%.17g|"
              "sdrel=%.17g|fpr=%.17g|shape=%s"
              % (name, st["n"], st["T_obs"], st["z_T"], st["rank_T"], st["T_ref_sd"],
                 st["theo_T"], st["sd_rel_T"], st["fpr"], shapes[name]), flush=True)

    # ===================== H6：跨轮对账 =====================
    rel_tol = float(sp["cross_rel_tol"])

    def rel(a, b):
        return abs(a - b) / abs(b) if b != 0 else float("inf")

    full = stats_by["FULL"]
    checks = []
    checks.append(("类级 T", rel(full["T_obs"], exp["T"]), rel_tol, full["T_obs"], exp["T"]))
    checks.append(("类级 z_T", rel(full["z_T"], exp["z"]), rel_tol, full["z_T"], exp["z"]))
    checks.append(("类级秩", rel(full["rank_T"], exp["rank"]), rel_tol, full["rank_T"], exp["rank"]))
    checks.append(("类级参考 sd", rel(full["T_ref_sd"], exp["ref_sd"]), rel_tol, full["T_ref_sd"], exp["ref_sd"]))
    checks.append(("类级理论 sd", rel(full["theo_T"], exp["theo_sd"]), rel_tol, full["theo_T"], exp["theo_sd"]))
    checks.append(("类级 FPR", rel(full["fpr"], exp["fpr"]), rel_tol, full["fpr"], exp["fpr"]))
    # ---- 6 条逐条余弦（账本印到 9 位小数 ⇒ 绝对差 ≤ 0.5e-9）----
    cos_dec = int(sp["cos_print_decimals"])
    cos_abs_tol = 0.5 * (10.0 ** (-cos_dec))
    for nm in names:
        c = cos_dot(vecs[nm], r0)
        e = exp["cos_each"][nm]
        checks.append(("余弦 %s" % nm, abs(c - e), cos_abs_tol, c, e))
    # ---- w_p2a 的**全精度**余弦（244.83 段；相对差 ≤ 1e-12）——⛔ 9 位小数那条锚抓不到缩放口径的 bug
    cos_p2a = cos_dot(vecs[sp["dose_w"]], r0)
    checks.append(("余弦 w_p2a（全精度锚）", rel(cos_p2a, exp["cos0_full"]), rel_tol,
                   cos_p2a, exp["cos0_full"]))
    # ---- STRAT-A 的 z ----
    checks.append(("STRAT-A z", rel(stats_by["STRAT-A"]["z_T"], exp["stratA_z"]), rel_tol,
                   stats_by["STRAT-A"]["z_T"], exp["stratA_z"]))
    # ---- 簇 A / 簇 B 的 T 与 z（账本印到 6 位 / 3 位小数）----
    ct_dec = int(sp["cluster_T_print_decimals"])
    cz_dec = int(sp["cluster_z_print_decimals"])
    ct_tol = 0.5 * (10.0 ** (-ct_dec))
    cz_tol = 0.5 * (10.0 ** (-cz_dec))
    checks.append(("CLU-A T", abs(stats_by["CLU-A"]["T_obs"] - exp["cluA_T"]), ct_tol,
                   stats_by["CLU-A"]["T_obs"], exp["cluA_T"]))
    checks.append(("CLU-A z", abs(stats_by["CLU-A"]["z_T"] - exp["cluA_z"]), cz_tol,
                   stats_by["CLU-A"]["z_T"], exp["cluA_z"]))
    checks.append(("CLU-B T", abs(stats_by["CLU-B"]["T_obs"] - exp["cluB_T"]), ct_tol,
                   stats_by["CLU-B"]["T_obs"], exp["cluB_T"]))
    checks.append(("CLU-B z", abs(stats_by["CLU-B"]["z_T"] - exp["cluB_z"]), cz_tol,
                   stats_by["CLU-B"]["z_T"], exp["cluB_z"]))
    # ---- 簇成员必须与账本登记的相同 ----
    clu_mem_ok = (sorted(exp["cluA_members"]) == sorted(fam["CLU-A"])
                  and sorted(exp["cluB_members"]) == sorted(fam["CLU-B"]))
    h6_ok = all(dv <= tol for _n, dv, tol, _a, _b in checks) and clu_mem_ok
    cr.check("H6-CROSSROUND", h6_ok,
             "跨轮对账（账本 244.84 段；全精度相对差 ≤ %.0e，印到 k 位的绝对差 ≤ 0.5×10^-k）：%s ｜ "
             "簇成员与账本登记相同 ⇒ %s"
             % (rel_tol,
                " ｜ ".join("%s：实测 %.17g vs 账本 %.17g（差 %.3g，上限 %.3g）%s"
                            % (n, a, b, dv, tol, "✅" if dv <= tol else "⛔超限")
                            for n, dv, tol, a, b in checks),
                "是" if clu_mem_ok else "⛔否"))

    # ===================== H7：基线形态 =====================
    full_ok = (shapes["FULL"] == exp["verdict84"])
    cr.check("H7-FULLFORM", full_ok,
             "FULL 的判决形态 = %s ｜ 账本 244.84 段登记的形态 = %s ⇒ ⇒ %s"
             % (shapes["FULL"], exp["verdict84"],
                "**一致**（基线可复现）" if full_ok else "⛔**不一致**（前提被推翻）"))

    # ===================== H8：逐子集校准 =====================
    bad_cal = [(k, stats_by[k]["sd_rel_T"]) for k in sorted(stats_by)
               if stats_by[k]["sd_rel_T"] > float(sp["class_sd_rel_tol"])]
    h8_ok = (not bad_cal)
    cr.check("H8-CALIB", h8_ok,
             "逐子集零分布校准（参考 sd vs 理论 ‖m_S‖/√d，相对差上限 %.2f）：%s ｜ 超限的子集：%s"
             % (float(sp["class_sd_rel_tol"]),
                " ｜ ".join("%s:%.6f" % (k, stats_by[k]["sd_rel_T"]) for k in sorted(stats_by)),
                ("%d 个" % len(bad_cal)) if bad_cal else "无"))

    # ===================== H9：逐 n 判别力 =====================
    bad_fpr = [(k, stats_by[k]["fpr"]) for k in sorted(stats_by)
               if stats_by[k]["fpr"] > float(sp["fpr_max"])]
    h9_ok = (not bad_fpr)
    cr.check("H9-DISC", h9_ok,
             "判决规则「z_T ≥ %.1f」在**每个子集自己的** K=%d 参考种子下的经验假阳性率"
             "（上限 %.2f）：%s ｜ 超限的子集：%s"
             % (float(sp["z_threshold"]), K, float(sp["fpr_max"]),
                " ｜ ".join("%s:%.5f" % (k, stats_by[k]["fpr"]) for k in sorted(stats_by)),
                ("%d 个 ⇒ ⇒ 形态只能是 F-E" % len(bad_fpr)) if bad_fpr else "无"))

    # ===================== H10：负控 =====================
    sh = [unit(shuffle_indep(vecs[nm], int(sp["shuffle_seed"]) + i)) for i, nm in enumerate(names)]
    st_sh = subset_stats(sh, (d,), K, r0, sp, refs)
    pw_sh = pairwise_cos(sh)
    pw_sh_max = max(x[2] for x in pw_sh)
    negctl_ok = (abs(st_sh["z_T"]) <= float(sp["negctl_z_max"])) and \
                (pw_sh_max <= float(sp["negctl_paircos_max"]))
    cr.check("H10-NEGCTL", negctl_ok,
             "6 把各自独立坐标置换（种子 %d+i）后：z_T=%+.17g（|z| 上限 %.1f；账本 244.84 登记 %+.17g）"
             "｜ 置换后两两余弦 max=%+.17g（上限 %.2f；账本登记 %+.17g）⇒ ⇒ %s"
             % (int(sp["shuffle_seed"]), st_sh["z_T"], float(sp["negctl_z_max"]),
                exp["negctl_z"], pw_sh_max, float(sp["negctl_paircos_max"]),
                exp["negctl_paircos"],
                "负控通过（无结构时不该触发）" if negctl_ok else "⛔负控异常"))

    # ===================== H11：自包含闸 =====================
    ctor_seeds = sorted(set(int(metas[nm].get("seed")) for nm in names))
    class_lo = int(sp["ref_class_seed_lo"])
    class_hi = class_lo + K - 1
    overlap = [s for s in ctor_seeds if class_lo <= s <= class_hi]
    st_alt = subset_stats(unit_vecs, (d,), K, r0, sp, refs_alt)
    shape_alt = "E-B" if st_alt["z_T"] >= float(sp["z_threshold"]) else "E-A"
    h11_ok = (not overlap) and (shape_alt == shapes["FULL"])
    cr.check("H11-SELFINCLUDE", h11_ok,
             "构造种子（6 把 sidecar 读出）= %s ｜ 类级参考种子区间 %d..%d ⇒ 交集 = %s ⇒ %s ｜ "
             "含构造种子的参考集（%d..%d）算出的 z_T=%+.17g（判 %s；账本登记 %+.17g）vs "
             "不含的 z_T=%+.17g（判 %s）⇒ ⇒ 判决形态%s"
             % (ctor_seeds, class_lo, class_hi, (overlap if overlap else "∅"),
                "∅（无自包含）" if not overlap else "⛔自包含！",
                int(sp["ref_single_seed_lo"]), int(sp["ref_single_seed_lo"]) + K - 1,
                st_alt["z_T"], shape_alt, exp["selfincl_z"], full["z_T"], shapes["FULL"],
                "**相同**（自包含没有影响判决）" if h11_ok else "⛔不同（自包含影响了判决）"))

    # ===================== H12：关键位的依据 =====================
    cos_each = dict((nm, cos_dot(vecs[nm], r0)) for nm in names)
    max_nm = max(names, key=lambda nm: cos_each[nm])
    exp_max_nm = max(names, key=lambda nm: exp["cos_each"][nm])
    h12_ok = (max_nm == sp["dose_w"]) and (max_nm == exp_max_nm)
    cr.check("H12-MAXCOS", h12_ok,
             "本轮实测：余弦最大的那把 = %s（%+.17g）｜ 账本 244.84 登记的 6 条里最大的那把 = %s（%+.9f）"
             "｜ 剂量批用的那把 = %s ⇒ ⇒ %s"
             % (max_nm, cos_each[max_nm], exp_max_nm, exp["cos_each"][exp_max_nm],
                sp["dose_w"],
                "**关键位就是它**（留一法因此以 %s 为准）" % sp["dose_key"]
                if h12_ok else "⛔关键位**不是**剂量那一把 ⇒ ⇒ 留一法的关键位失效"))

    # ===================== H13：位级对账（比 H6 更严一档）=====================
    # ⚖⚖⚖ **为什么必须单独有这条**：
    #   H6 的容差是「相对差 ≤ 1e-12」⇒ ⇒ **差 1 ULP（约 1.3e-16 相对）照样过**
    #   ⇒ ⇒ 「H6 绿」**不能**推出「本轮的类级统计量与账本 244.84 主表是**同一个 double**」
    #   ⇒ ⇒ 而 244.85 的基线行要写「**逐位相同**」⇒ ⇒ 就必须有判据**真的在比位**
    # ⚖⚖⚖ **口径边界（预登记 §0.5 发现 ②）**：本条比的是**同一条实现路线**
    #   （本文件的 numpy 路线 vs 244.84 主表的 numpy 路线）⇒ ⇒ 「逐位」这个说法
    #   **只在这一条路线内成立**；跨路线（numpy vs 纯 Python）实测差 3 ULP / 2 ULP
    #   ⇒ ⇒ ⛔ 不许把本条的绿推广成「跨实现逐位可复现」。
    bit_items = [
        ("类级 T", full["T_obs"], exp["T"]),
        ("类级 z_T", full["z_T"], exp["z"]),
        ("类级秩", full["rank_T"], exp["rank"]),
        ("类级参考 sd", full["T_ref_sd"], exp["ref_sd"]),
        ("类级理论 sd", full["theo_T"], exp["theo_sd"]),
        ("类级 FPR", full["fpr"], exp["fpr"]),
    ]
    bit_bad = [(n, a, b) for n, a, b in bit_items if a != b]
    h13_ok = (not bit_bad)
    cr.check("H13-BITIDENT", h13_ok,
             "位级对账（FULL 的 6 项 vs 账本 244.84 主表；⛔ **不是**「相对差 ≤ %.0e」，"
             "是**同一个 double**）：%s ｜ %s"
             % (rel_tol,
                " ｜ ".join("%s：实测 %.17g vs 账本 %.17g（ULP 差 %d）%s"
                           % (n, a, b, ulp_diff(a, b), "✅逐位相同" if a == b else "⛔**不同**")
                           for n, a, b in bit_items),
                "⇒ ⇒ **同一条实现路线内逐位可复现**（⛔ 不许推广到跨实现路线）"
                if h13_ok else
                "⇒ ⇒ **不是同一个 double** ⇒ ⇒ 基线**不是**逐位复现 ⇒ ⇒ 前提被推翻"))

    # ===================== 判决形态 =====================
    failed = list(cr.failed_ids())
    failed_other = [x for x in failed if x != "H9-DISC"]
    hard_ok = (not failed_other)
    disc_ok = h9_ok
    verdict, cond = verdict_from_subsets(shapes, hard_ok, disc_ok, exp["verdict84"],
                                         sp["dose_key"], sp["decision_family"])
    why = verdict_why(verdict, cond, shapes, stats_by, sp["dose_key"], sp["decision_family"])
    if failed_other:
        why = "硬判据红（**不是** H9 ⇒ ⇒ 前提被推翻，⛔ 不是「没量到」）：%s" % ", ".join(failed_other)

    # ===================== 面板 =====================
    print("")
    print("=== 判决面板（类级 · 留一） ===")
    print("| 子集 | n | T | z_T | FPR_n | 形态 |")
    print("|---|---|---|---|---|---|")
    for k in ["FULL"] + [x for x in sp["decision_family"] if x != "FULL"]:
        s = stats_by[k]
        print("| %s | %d | %+.9f | %+.4f | %.5f | %s |"
              % (k, s["n"], s["T_obs"], s["z_T"], s["fpr"], shapes[k]))
    print("")
    print("=== 描述族（算出来、登记，⛔ 不进判决） ===")
    for k in sp["descriptive_family"]:
        s = stats_by[k]
        print("| %s | %d | %+.9f | %+.4f | %.5f | %s |"
              % (k, s["n"], s["T_obs"], s["z_T"], s["fpr"], shapes[k]))
    print("")
    print("=== 描述量 ===")
    print("  D1 决策族：LOO 族 %d 个子集的形态：%s"
          % (len(sp["decision_family"]) - 1,
             " ｜ ".join("%s=%s" % (k, shapes[k]) for k in sp["decision_family"] if k != "FULL")))
    print("  D2 描述族：%s"
          % " ｜ ".join("%s=%s" % (k, shapes[k]) for k in sp["descriptive_family"]))
    print("  D3 FPR_n 随 n：%s"
          % " ｜ ".join("%s(n=%d):%.5f" % (k, stats_by[k]["n"], stats_by[k]["fpr"])
                       for k in sorted(stats_by, key=lambda x: (stats_by[x]["n"], x))))
    print("  D4 单向量族（n=1，⛔ **不进判决**：n=1 时「类」与「个」是两个命题）：%s"
          % " ｜ ".join("%s: cos=%+.6f z=%+.3f" % (k, cos_each[fam[k][0]], stats_by[k]["z_T"])
                       for k in sp["descriptive_family"] if k.startswith("SINGLE")))
    print("  D5 两两余弦：max=%+.6f min=%+.6f ｜ 簇：%s"
          % (pw_max, pw_min,
             " ｜ ".join("{%s}" % "+".join(g) for g in clu_groups)))
    w_frac = cos_each[sp["dose_w"]] ** 2
    print("  D6 污染量级（244.84 登记，本轮复算）：cos(w_p2a, r₀)=%+.9f ⇒ w 能量占比 %.6f%% ｜ "
          "w 等效剂量 = %.3f × %.6f = %.3f"
          % (cos_each[sp["dose_w"]], w_frac * 100.0, cos_each[sp["dose_w"]],
             float(sp["gap"]), cos_each[sp["dose_w"]] * float(sp["gap"])))
    print("  ⚠ D7 **条件命题**（前提未实测 ⇒ 不进判决）：污染在 rand 臂最大剂量处等效于一次 "
          "w 剂量 %.3f 的注入；⛔ 固定剂量批**没落盘 alpha 轨迹** ⇒ ⇒ 离线**算不出**「污染最多能翻多少格」"
          % (cos_each[sp["dose_w"]] * float(sp["gap"])))
    print("")
    print("判决形态：%s（%s）" % (verdict, why))
    print("VERDICT=%s" % verdict)
    print("VERDICT_WHY=%s" % why)
    print(cr.summary())
    if verdict == "FAIL":
        print("DATA_RC=1")
        return 1
    print("DATA_RC=0")
    return 0


# =============================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(description="244.85 类级结论的留一稳健性")
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
    ap.add_argument("--class-sd-rel-tol", type=float, default=None, dest="class_sd_rel_tol")
    ap.add_argument("--shuffle-seed", type=int, default=None, dest="shuffle_seed")
    a = ap.parse_args(argv)

    if a.print_spec:
        for k in sorted(SPEC):
            print("%-20s = %r" % (k, SPEC[k]))
        print("%-20s = %r" % ("VERDICT_TABLE", VERDICT_TABLE))
        print("%-20s = %r" % ("PREREG_FORMS_ORDER", PREREG_FORMS_ORDER))
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
        if a.class_sd_rel_tol is not None:
            sp["class_sd_rel_tol"] = a.class_sd_rel_tol
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
        if a.class_sd_rel_tol is not None:
            sp["class_sd_rel_tol"] = a.class_sd_rel_tol
        if a.shuffle_seed is not None:
            sp["shuffle_seed"] = a.shuffle_seed
        return run_data(a)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
