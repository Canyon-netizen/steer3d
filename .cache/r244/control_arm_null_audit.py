#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""control_arm_null_audit.py —— **对照臂的零假设地位**（244.86）。

⚖⚖⚖⚖⚖ **这个文件回答什么**
   244.84（对照臂方向污染的类级判读，形态 **E-B**）与 244.85（类级结论的留一稳健性，
   形态 **F-B**）测到了**向量级**的事实：

       `r₀` 与 steering 向量**簇 A** 对齐（`cos(w_p2a, r₀) = +0.060171700088156643`，
       簇 A 的 z = +2.3929）

   ⇒ ⇒ **244.81 那个固定剂量判决**（w 臂 46/56 vs rand 臂 29/56，差 **+30.36 pp**）
   ⇒ ⇒ **它的对照臂是不是被这条对齐「抬起来了」** ⇒ ⇒ **244.84/244.85 都没有回答** ——
   它们只测了**向量**，⛔ **没有测「它有没有改变 rand 臂的改判率」**。

⚖⚖⚖ **244.86 就是补这一口**
   把「rand 臂的**边际**改判率 vs 它自己那层零假设」做成**可判读的五态**（N-A..N-E），
   并把「污染最多能把 +30.36 pp 抬高到多少」从**纯留白**变成**有界命题**。

⚖⚖⚖⚖⚖ **纪律（本文件的形状就是这些纪律）**
   ① **口径只从预登记读**：`.cache/xcheck/R6_CONTROL_ARM_NULL_PREREG.md`（244.86 签）
      ⇒ ⇒ 口径常量集中在 `SPEC`，且**逐条被 `--print-spec` 印出来**（⇒ 变异台能逐条改）。
   ② **期望值从账本读，不从代码读**（⛔ 代码里**不写死任何一个数**）：
      账本读不到 ⇒ ⇒ **HardFail**，⛔ 不用代码里的字面值兜底、⛔ 不静默降级。
      ⇒ ⇒ 连**容差**都不是拍脑袋的：它由**账本自己的打印精度**推导（见 `tol_from`）。
   ③ **每条硬判据都有「跨来源」那一半**：H1–H8 的两个半边**不同源**
      （本轮现算 vs 账本印的；运行前 md5 vs 运行后 md5；解析行号 vs 段范围）。
   ④ **每条判据能红**：`--selftest`（G0-1..G0-7 合成夹具，零 bpath、零 GPU）
      ＋ 变异台 `mut_control_arm_null_audit.py`（⛔ 变异台必须能红）＋ **判决形态也被断言**。
   ⑤ **判决只算一次**：印出来的 = 返回的。
   ⑥ ⛔ **未量到 ≠ 没差异 ≠ 失败**。
   ⑦ ⚖ **「每格公平硬币」这个前提要单独被检验**（Q9/H2 ⇒ ⇒ 244.60 的旧担忧在本批上被正式检验）。
   ⑧ ⛔ **判决形态映射写成规则表**（`VERDICT_TABLE`）⇒ ⇒ 变异台改**表**就能红，
      ⛔ 不必依赖真数据的形态 ⇒ ⇒ 死分支藏不住。

⚖⚖⚖⚖⚖ **本文件的判决措辞必须精确**
   「rand 臂的**边际**改判率**没有可检出的**高于零假设」
   ⛔ **不等于**「rand 臂是干净的」⇒ ⇒ **只准**写成「**在可检出层面**没有」＋「幅度上界是 X pp」。

⚖⚖⚖⚖⚖ **本文件**不**产出**的东西（预登记 §4，逐条留白）
   ① 污染的**精确**幅度；② 「污染最多能翻多少格」的精确值；③ 机制轴；④ 剂量轴；
   ⑤ rand 臂**换种子**后的分布（⇒ ⇒ r 那一侧仍是 **N=1**）；
   ⑥ 「污染存在」的**响应级严格证明**（共享 `w_p2a` 成分与「题目可移动性」**共线**
      ⇒ ⇒ 本轮**只给边际结论**）。
"""

import argparse
import hashlib
import math
import os
import re
import statistics
import sys
from fractions import Fraction

import numpy as np

# =============================================================================
# 口径常量（**逐条对应**预登记 §2；⇒ `--print-spec` 逐条印出 ⇒ 变异台能逐条改）
# =============================================================================
SPEC = {
    # Q5：显著性水平（单侧）
    "alpha": 0.05,
    # Q7：Wilson 区间用的正态分位数（⛔ 不写死字面值 ⇒ 用标准库现算 0.975 分位）
    "wilson_z_from": 0.975,
    # ⚖⚖⚖ **本文件没有别的数字了** —— 其余全部从账本 244.81 段解析。
    #   ⇒ ⇒ 连「容差」也不是拍脑袋的：它由**账本自己的打印精度**推导（`tol_from`）。
}

# ⚖⚖⚖⚖⚖ **判决形态映射 —— 写成规则表**（⛔ 不是 if/elif 链）
#   ⇒ ⇒ 变异台改**这张表**就能让 G0-2 红，⛔ **不必依赖真数据的形态** ⇒ ⇒ 死分支藏不住。
#   规则按顺序判定，第一条命中的给出形态。每条规则 = （条件名, 该条件必须取的值, 形态）。
#   条件名（由 `verdict_conditions` 计算）：
#     base_ok        ⇒ H1（基准可复算）**与** H2（逐格前提）都绿
#     other_hard_ok  ⇒ H3 / H4 / H5 / H6 / H7 / H8 都绿
#     mixed_sig      ⇒ H3 与 H4 的「显著」方向**不一致**
#     both_sig       ⇒ H3 与 H4 **都**显著（rand 被抬高）
VERDICT_TABLE = [
    ("base_ok", False, "N-D"),        # 基准本身不可用 ⇒ ⇒ 前提被推翻（⛔ 不是「没量到」）
    ("other_hard_ok", False, "N-E"),  # 其他硬判据红（数据 / 出处 / 形状类）⇒ ⇒ FAIL
    ("mixed_sig", True, "N-C"),       # 轨迹级与块级方向不一致 ⇒ ⇒ 口径依赖 ⇒ ⇒ 不下结论
    ("both_sig", True, "N-B"),        # rand 显著高于零假设 ⇒ ⇒ 对照臂被污染
    ("else", None, "N-A"),            # rand 与零假设不可区分 ⇒ ⇒ 「在可检出层面」没被抬起
]

# ⚖ 预登记 §3.1 声明的**有序**形态表（实现必须与它一致 ⇒ 预登记对账会查）
PREREG_FORMS_ORDER = ["N-A", "N-B", "N-C", "N-D", "N-E"]


# =============================================================================
# 小工具
# =============================================================================
class HardFail(Exception):
    """⚖ **读不到必需输入** ⇒ ⇒ 硬失败（⛔ 不是判红、⛔ 不是「跳过」）。"""


def die(msg, code=3):
    sys.stderr.write("⛔ %s\n" % msg)
    sys.exit(code)


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


class Collector(object):
    """⚖ 判据收集器（沿用 244.84/244.85 的形状）：印出来的 = 返回的。"""

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
        return "判据汇总：%d 条 ｜ PASS %d ｜ FAIL %d" % (
            len(self.rows), np_, len(self.rows) - np_)


# =============================================================================
# 口径原语（**精确**：能用 Fraction 的地方一律 Fraction；⛔ 不用正态近似）
# =============================================================================
def majority_base_p2(n_nz, n_zero):
    """⚖ **轨迹级零假设概率**（244.81 的口径，⛔ 不许改）。

    · 每个**非零**格的符号是**公平硬币**（`nT` ~ Binomial(n_nz, 0.5)）
    · **零格恒 False**（`d == 0` 不是一次抛硬币）
    · 阈值 `nT·2 > m`，其中 `m = n_nz + n_zero`（⛔ **零格进分母**、不进基准）
    ⇒ ⇒ 返回**精确**有理数（Fraction）。
    """
    nz = int(n_nz)
    m = nz + int(n_zero)
    tot = Fraction(0)
    for k in range(0, nz + 1):
        if 2 * k > m:
            tot += Fraction(math.comb(nz, k), 2 ** nz)
    return tot


def pb_pmf(probs):
    """⚖ **Poisson-binomial 的精确卷积**（Q3：⛔ 不是 Binomial(n, mean)
    ⇒ ⇒ 因为 `base_i` 有 0.25 与 0.5 两种 ⇒ ⇒ 必须用精确卷积，⛔ 不用正态近似）。

    ⚖ 返回 `list[Fraction]`：第 k 项 = P(X = k)。
    """
    dist = [Fraction(1)]
    for p in probs:
        pf = Fraction(p) if isinstance(p, Fraction) else Fraction(str(p))
        nd = [Fraction(0)] * (len(dist) + 1)
        for k, v in enumerate(dist):
            nd[k] += v * (1 - pf)
            nd[k + 1] += v * pf
        dist = nd
    return dist


def pb_pmf_np(probs):
    """⚖ **Poisson-binomial 的 float64 卷积**（numpy 路线 —— 本文件走这一条）。

    ⚖⚖⚖ **为什么走 float64 而不是 Fraction**：本文件是**第一条实现**（numpy 路线），
    第二条实现（`_cross_check_24486.py`）走**纯 Python 精确整数**路线
    ⇒ ⇒ 两条路**算术不同** ⇒ ⇒ 互证才有意义（⛔ 两条都用同一个算法 ⇒ 互证是假的）。
    """
    dist = np.array([1.0], dtype=np.float64)
    for p in probs:
        pf = float(p)
        nd = np.zeros(len(dist) + 1, dtype=np.float64)
        nd[:len(dist)] += dist * (1.0 - pf)
        nd[1:] += dist * pf
        dist = nd
    return dist


def tail_p(pmf, obs):
    """⚖ **单侧上尾** `P(X >= obs)`（Q6：只关心「**高于**零假设」这一个方向）。

    ⚖ `math.fsum` ⇒ 求和的舍入误差被压到 1 ulp 量级（⛔ 不用 `np.sum` 的成对求和）。
    """
    obs = int(obs)
    if obs <= 0:
        return 1.0
    if obs > len(pmf) - 1:
        return 0.0
    return float(math.fsum(float(x) for x in pmf[obs:]))


def wilson_ci(p, n, z):
    """⚖ **Wilson 区间**（中心 ± 半宽的写法）。"""
    n = float(n)
    p = float(p)
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return center - half, center + half


def fisher_exact_two_sided(a, b, c, d):
    """⚖ **Fisher 精确检验（两侧）** —— 条件于「阳性总数」的精确超几何。

    ⚖⚖⚖ **口径核对过**：244.81 段印的 `0.001152`（轨迹级）与 `0.000131`（块级）
    与本函数给出的值在**它们自己的打印精度**上逐位相同
    ⇒ ⇒ 本函数就是 244.81 那两个数所用的口径 ⇒ ⇒ 可拿来做**交叉校验**。
    """
    a, b, c, d = int(a), int(b), int(c), int(d)
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c

    def pmf(x):
        if x < max(0, c1 - r2) or x > min(r1, c1):
            return Fraction(0)
        return Fraction(math.comb(r1, x) * math.comb(r2, c1 - x), math.comb(n, c1))

    lo, hi = max(0, c1 - r2), min(r1, c1)
    obs = pmf(a)
    tot = Fraction(0)
    for x in range(lo, hi + 1):
        px = pmf(x)
        if px <= obs:
            tot += px
    return tot


def newcombe_diff_ci(p1, l1, u1, p2, l2, u2):
    """⚖ **Newcombe95 差区间**（用于与账本印的差区间做交叉校验）。"""
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return lo, hi


def decimals_of(raw):
    """⚖ **从账本自己的打印字符串数出小数位数** ⇒ ⇒ 容差由**外部依据**推导（⛔ 不拍脑袋）。

    例：`"0.4955"` ⇒ 4；`"+70.16"` ⇒ 2；`"0.001152"` ⇒ 6。
    """
    m = re.search(r"\.(\d+)", str(raw))
    return len(m.group(1)) if m else 0


def tol_from(raw):
    """⚖ 容差 = **半个打印单位**（`0.5 × 10^-decimals`）⇒ ⇒ 由账本的打印精度推导。"""
    return 0.5 * (10.0 ** (-decimals_of(raw)))


def reserialize_ratio(raw):
    """⚖ 把 `'**46/56**'` 归一成 `'46/56'`（**逐位**回读用）。"""
    s = str(raw).strip()
    s = s.strip("*").strip()
    return s


# =============================================================================
# 判决形态
# =============================================================================
def verdict_conditions(h):
    """⚖ 把八条硬判据的真假，映射成**规则表**能查的条件。

    ⚖⚖⚖ **「H3 红 = 显著」的约定**：H3/H4 的**定义**是「与零假设**不可区分**⇒⇒绿」，
    ⇒ ⇒ 所以「H3 红」**就是**「rand 显著高于零假设」⇒ ⇒ 下面用 `not h3` 表示显著。
    """
    traj_sig = (not h["H3-TRAJNULL"])
    block_sig = (not h["H4-BLOCKNULL"])
    return {
        "base_ok": bool(h["H1-BASECALC"] and h["H2-CELLBASE"]),
        # ⚖⚖⚖ **「其他硬判据」＝ H5/H6/H7/H8**（⛔ **不含** H3/H4）
        #   理由：H3/H4 的定义是「与零假设**不可区分** ⇒ ⇒ 绿」
        #   ⇒ ⇒ 「H3 红」**就是**「rand 显著高于零假设」⇒ ⇒ 它**是信号**（N-B / N-C），
        #   ⛔ **不是**「其他硬判据红」（那会把 N-B / N-C 变成死分支 —— ⛔ G0-2 就是抓这个的）。
        "other_hard_ok": bool(h["H5-POWER"] and h["H6-MAGNITUDE"]
                              and h["H7-PROVENANCE"] and h["H8-READONLY"]),
        "mixed_sig": bool(traj_sig != block_sig),
        "both_sig": bool(traj_sig and block_sig),
    }


def verdict_from_conditions(cond):
    """⚖ **按规则表**取形态（⛔ 不是 if/elif 链 ⇒ ⇒ 变异台改表就能红）。"""
    for name, want, form in VERDICT_TABLE:
        if want is None:
            return form
        if cond.get(name) == want:
            return form
    return "N-E"


def verdict_why(form, cond, h):
    """⚖ 形态的**理由**（一句话结论 + 触发它的那条判据）。"""
    if form == "N-D":
        bad = [k for k in ("H1-BASECALC", "H2-CELLBASE") if not h[k]]
        return "零假设基准本身不可用（%s 红）⇒ ⇒ 前面全部不许写 ⇒ ⇒ FAIL（前提被推翻）" % "/".join(bad)
    if form == "N-E":
        bad = [k for k in ("H5-POWER", "H6-MAGNITUDE",
                           "H7-PROVENANCE", "H8-READONLY") if not h[k]]
        return "其他硬判据红（%s）⇒ ⇒ FAIL" % "/".join(bad)
    if form == "N-C":
        return ("轨迹级与块级**方向不一致**（一个显著一个不显著）⇒ ⇒ **口径依赖** "
                "⇒ ⇒ ⛔ 不下结论（N-A / N-B 都不许写）")
    if form == "N-B":
        return ("rand 臂的**边际**改判率**显著**高于零假设 ⇒ ⇒ 对照臂被污染 "
                "⇒ ⇒ +30.36 pp 是**下界**（真实差更大）")
    return ("rand 臂的**边际**改判率**没有可检出的**高于零假设 ⇒ ⇒ 对照臂在改判率这一层"
            "**在可检出层面**没被抬起 ⇒ ⇒ ⚠ 功效有限 ⇒ ⇒ 只给**上界**（⛔ 不是「对照臂干净」）")


# =============================================================================
# 账本解析（⛔ 代码里不写死任何一个数 ⇒ ⇒ 全部从 244.81 段逐行解析）
# =============================================================================
def find_section(lines, rev):
    """⚖ 找到 `## 修订 <rev>` 段的**行号范围**（1-based，两端都含）。

    ⚖ 找不到 / 命中多处 ⇒ ⇒ **HardFail**（⛔ 不许猜）。
    """
    pat = re.compile(r"^## 修订 %s\b" % re.escape(rev))
    hits = [i for i, l in enumerate(lines) if pat.match(l)]
    if len(hits) != 1:
        raise HardFail("账本里「## 修订 %s」段命中 %d 次（⛔ 必须恰好 1 次）" % (rev, len(hits)))
    s = hits[0]
    e = len(lines)
    for j in range(s + 1, len(lines)):
        if re.match(r"^## 修订 ", lines[j]):
            e = j
            break
    return s + 1, e          # 1-based；sec_end = 下一段标题行的前一行


def find_section_end_alt(lines, rev):
    """⚖ **第二种独立**的段尾算法（供 H8 交叉核对 ⇒ ⇒ 两种算法必须**逐位一致**）。

    ⚖ 方法甲（`find_section`）：正则 `^## 修订 ` 找下一段标题。
    ⚖ 方法乙（本函数）：**字符串**判定「这一行是 `## ` 开头**且**标题非空」⇒ ⇒ 两种**写法不同**。
    ⇒ ⇒ 若两法不一致 ⇒ ⇒ 说明「段尾」这件事本身没被钉死 ⇒ ⇒ H8 必须红。
    """
    pat = re.compile(r"^## 修订 %s\b" % re.escape(rev))
    start = None
    for i, l in enumerate(lines):
        if pat.match(l):
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("## ") and s.split("## ", 1)[1].strip():
            return j          # 0-based ⇒ 1-based 的「下一段标题行 − 1」＝ 段尾
    return len(lines)


def _find_row(rows, keys, what, unique=True):
    """⚖ 在段内找**唯一**一行（同时含所有 keys）⇒ ⇒ 返回 (行号, 行文本)。"""
    hit = [(ln, tx) for ln, tx in rows if all(k in tx for k in keys)]
    if not hit:
        raise HardFail("244.81 段里找不到含 %s 的行（%s）⇒ ⇒ 拒绝兜底" % (list(keys), what))
    if unique and len(hit) > 1:
        raise HardFail("244.81 段里含 %s 的行有 %d 行（%s）⇒ ⇒ 锚点不唯一 ⇒ ⇒ 中止"
                       % (list(keys), len(hit), [h[0] for h in hit]))
    return hit[0]


def _cells(line):
    """⚖ 取表格行的各格（⚠ 行首的 `|` 会让 cells[0] 为空串 ⇒ ⇒ 值从 cells[2] 起）。"""
    return line.split("|")


def _ratio(cell):
    """⚖ `'**46/56**'` ⇒ `(46, 56)`；同时回读**原文**（供「逐位」校验）。"""
    raw = reserialize_ratio(cell)
    m = re.match(r"^(\d+)/(\d+)$", raw)
    if not m:
        raise HardFail("读不到比例（%r）⇒ ⇒ 拒绝兜底" % cell)
    return int(m.group(1)), int(m.group(2)), raw


def _parse_dist(text):
    """⚖ `'{(2,0)×1, (3,0)×55}'` ⇒ `[(2,0,1), (3,0,55)]` + 原文。

    ⚖⚖⚖ **必须先把 `{…}` 那一段抠出来再切逗号** —— 否则整行（`· (n_nz,n_zero) 分布：{…}`）
    会被逗号切碎（`(n_nz` / `n_zero)` / `0)×1` …）⇒ ⇒ 这是**实测踩到过**的坑。
    """
    raw = text.strip()
    m = re.search(r"\{[^}]*\}", raw)
    if not m:
        raise HardFail("读不到 (n_nz,n_zero) 分布的 {…} 部分（%r）⇒ ⇒ 拒绝兜底" % text)
    body = m.group(0)
    # ⚖⚖⚖ **必须用正则抽取，不能按逗号切** —— `(2,0)` **自身就带逗号** ⇒ ⇒ 切碎
    items = re.findall(r"\((\d+),(\d+)\)×(\d+)", body)
    if not items:
        raise HardFail("读不到 (n_nz,n_zero) 分布的任何一项（%r）⇒ ⇒ 拒绝兜底" % body)
    out = [(int(a), int(b), int(c)) for a, b, c in items]
    # ⚖ **逐位回读**：拼回去必须与原文**完全相同** ⇒ ⇒ 才认这一段
    if _parse_dist_str(out) != body:
        raise HardFail("分布串逐位回读不上（原文 %r ／ 拼回 %r）⇒ ⇒ 拒绝兜底"
                       % (body, _parse_dist_str(out)))
    return out, body


def _parse_dist_str(raw):
    """⚖ 把分布**逐位**重新拼回去（供「逐位对上」校验）。"""
    return "{" + ", ".join("(%d,%d)×%d" % (a, b, c) for a, b, c in raw) + "}"


def parse_inputs(ledger_text):
    """⚖⚖⚖ **从账本 244.81 段解析 I1–I12**（⛔ 代码里不写死任何一个数）。

    ⇒ ⇒ 读不到任何一个 ⇒ ⇒ **HardFail**（⛔ 不用代码里的字面值兜底、⛔ 不静默降级）。
    ⇒ ⇒ 返回的每个输入都带**行号**（供 H8 判「解析到的行号是否落在 244.81 段内」）。
    """
    lines = ledger_text.split("\n")
    sec_start, sec_end = find_section(lines, "244.81")
    rows = [(i, lines[i - 1]) for i in range(sec_start, sec_end + 1)]

    P = {"sec_start": sec_start, "sec_end": sec_end, "raw": {}, "line": {},
         "_lines": lines}

    # ---- I1 / I2：轨迹级改判（判决面板那行）----
    ln, tx = _find_row(rows, ("改判（主口径",), "I1/I2 轨迹级改判")
    cs = _cells(tx)
    if len(cs) < 5:
        raise HardFail("判决面板「改判」那行的表格结构异常（%d 格）⇒ ⇒ 中止" % len(cs))
    cw, cr = _ratio(cs[2]), _ratio(cs[3])
    P["obs_w"], P["n_w"], P["raw"]["I1"] = cw
    P["obs_r"], P["n_r"], P["raw"]["I2"] = cr
    P["line"]["I1"] = P["line"]["I2"] = ln

    # ---- I3 / I4：零假设基准（判决面板那行）----
    ln, tx = _find_row(rows, ("零假设基准（逐轨迹平均）",), "I3/I4 零假设基准")
    cs = _cells(tx)
    P["base_w_printed"] = float(cs[2].strip())
    P["base_r_printed"] = float(cs[3].strip())
    P["raw"]["I3"] = cs[2].strip()
    P["raw"]["I4"] = cs[3].strip()
    P["line"]["I3"] = P["line"]["I4"] = ln

    # ---- I10 / I11：Wilson95 区间（判决面板那行）----
    ln, tx = _find_row(rows, ("比例区间（Wilson95）",), "I10/I11 Wilson95 区间")
    cs = _cells(tx)

    def _wil(cell):
        s = cell.strip()
        m = re.match(r"^\[\s*([-+0-9.]+)\s*,\s*([-+0-9.]+)\s*\]$", s)
        if not m:
            raise HardFail("读不到 Wilson 区间（%r）⇒ ⇒ 拒绝兜底" % cell)
        return float(m.group(1)), float(m.group(2)), s

    P["wil_w_lo"], P["wil_w_hi"], P["raw"]["I11"] = _wil(cs[2])
    P["wil_r_lo"], P["wil_r_hi"], P["raw"]["I10"] = _wil(cs[3])
    P["line"]["I10"] = P["line"]["I11"] = ln

    # ---- I12：观测差（【2】末尾那行，含 Newcombe 区间与跨臂 Fisher）----
    #   ⚖⚖⚖ **锚点必须够狠**：`跨臂 Fisher` 在 244.81 段里命中 **4 行**
    #   （41382 段标题、41404 本行、41428 口径行、41473 补印行）⇒ ⇒ 单个关键词**不唯一**
    #   ⇒ ⇒ 用「配对置换 **且** Newcombe95」两条同时命中 ⇒ ⇒ 段内**唯一**。
    ln, tx = _find_row(rows, ("配对置换", "Newcombe95"), "I12 观测差")
    m = re.search(r"差\s*([-+0-9.]+)\s*pp", tx)
    if not m:
        raise HardFail("244.81 段里读不到「差 +xx.xx pp」⇒ ⇒ 拒绝兜底")
    P["delta_pp"] = float(m.group(1))
    P["raw"]["I12"] = m.group(1)
    m = re.search(r"Newcombe95）\[\s*([-+0-9.]+)\s*,\s*([-+0-9.]+)\s*\]", tx)
    if not m:
        raise HardFail("244.81 段里读不到轨迹级的 Newcombe95 差区间 ⇒ ⇒ 拒绝兜底")
    P["nc_traj_lo"], P["nc_traj_hi"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"p\s*=\s*([0-9.]+)", tx)
    if not m:
        raise HardFail("244.81 段里读不到跨臂 Fisher 的 p ⇒ ⇒ 拒绝兜底")
    P["fisher_traj_p_printed"] = float(m.group(1))
    P["line"]["I12"] = ln

    # ---- I5 / I6：块级（【3】那行）----
    ln, tx = _find_row(rows, ("**块数**",), "I5/I6 块级")
    mw = re.search(r"w\s*\*\*(\d+)/(\d+)\*\*", tx)
    mr = re.search(r"rand\s*\*\*(\d+)/(\d+)\*\*", tx)
    if not (mw and mr):
        raise HardFail("244.81 段里读不到块级的 w / rand 格数 ⇒ ⇒ 拒绝兜底")
    P["blk_w"], P["blk_n_w"] = int(mw.group(1)), int(mw.group(2))
    P["blk_r"], P["blk_n_r"] = int(mr.group(1)), int(mr.group(2))
    P["raw"]["I5"] = "%d/%d" % (P["blk_w"], P["blk_n_w"])
    P["raw"]["I6"] = "%d/%d" % (P["blk_r"], P["blk_n_r"])
    m = re.search(r"差\s*([-+0-9.]+)\s*pp", tx)
    if not m:
        raise HardFail("244.81 段里读不到块级的「差 +xx.xx pp」⇒ ⇒ 拒绝兜底")
    P["blk_delta_pp_printed"] = float(m.group(1))
    m = re.search(r"差区间\s*\[\s*([-+0-9.]+)\s*,\s*([-+0-9.]+)\s*\]", tx)
    if not m:
        raise HardFail("244.81 段里读不到块级的差区间 ⇒ ⇒ 拒绝兜底")
    P["nc_blk_lo"], P["nc_blk_hi"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"Fisher p\s*=\s*([0-9.]+)", tx)
    if not m:
        raise HardFail("244.81 段里读不到块级的 Fisher p ⇒ ⇒ 拒绝兜底")
    P["fisher_blk_p_printed"] = float(m.group(1))
    P["line"]["I5"] = P["line"]["I6"] = ln

    # ---- I7 / I8：(n_nz,n_zero) 分布（【9】那行）----
    ln, tx = _find_row(rows, ("(n_nz,n_zero) 分布",), "I7/I8 (n_nz,n_zero) 分布")
    parts = tx.split("｜")
    if len(parts) < 2:
        raise HardFail("244.81 段里读不到 (n_nz,n_zero) 分布的两臂 ⇒ ⇒ 拒绝兜底")
    P["dist_w"], P["raw"]["I7"] = _parse_dist(parts[0])
    P["dist_r"], P["raw"]["I8"] = _parse_dist(parts[1])
    P["line"]["I7"] = P["line"]["I8"] = ln

    # ---- I9：rand 臂逐档逐格正/负/零（【8】第三条路径的 rand 那三行）----
    #   ⚖ 结构定位：段内「缺读数=0」出现**两次**（先是 w 臂、再是 rand 臂）⇒ ⇒ 取**第二**次。
    marks = [(ln2, tx2) for ln2, tx2 in rows if "缺读数=0" in tx2]
    if len(marks) != 2:
        raise HardFail("244.81 段里「缺读数=0」出现 %d 次（⛔ 期望 2 次：w 臂一次、rand 臂一次）"
                       % len(marks))
    start_idx = rows.index(marks[1])
    cell_rows = []
    for off in range(1, 4):
        if start_idx + off >= len(rows):
            raise HardFail("rand 臂的 awk 三行读不全 ⇒ ⇒ 拒绝兜底")
        ln3, tx3 = rows[start_idx + off]
        mf = re.search(r"pos_frac=([0-9.]+)", tx3)
        mc = re.search(r"格数=(\d+)", tx3)
        mp = re.search(r"正=(\d+)", tx3)
        mn = re.search(r"负=(\d+)", tx3)
        mz = re.search(r"零=(\d+)", tx3)
        if not (mf and mc and mp and mn and mz):
            raise HardFail("rand 臂的 awk 行结构异常（%r）⇒ ⇒ 拒绝兜底" % tx3)
        cell_rows.append({
            "pos_frac": mf.group(1),
            "n_cells": int(mc.group(1)),
            "n_pos": int(mp.group(1)),
            "n_neg": int(mn.group(1)),
            "n_zero": int(mz.group(1)),
            "raw": ("pos_frac=%s  格数=%d  正=%d  负=%d  零=%d"
                    % (mf.group(1), int(mc.group(1)), int(mp.group(1)),
                       int(mn.group(1)), int(mz.group(1)))),
            "line": ln3,
        })
    P["cell_rows"] = cell_rows
    P["raw"]["I9"] = " ｜ ".join(c["raw"] for c in cell_rows)
    P["line"]["I9"] = cell_rows[0]["line"]

    # ---- 派生：每条轨迹的零假设概率（Q2 的口径，⛔ 不许改）----
    P["base_w_list"] = []
    for nz, zero, mult in P["dist_w"]:
        P["base_w_list"] += [majority_base_p2(nz, zero)] * mult
    P["base_r_list"] = []
    for nz, zero, mult in P["dist_r"]:
        P["base_r_list"] += [majority_base_p2(nz, zero)] * mult
    return P


# =============================================================================
# 块级零分布（Q4）：配对未知 ⇒ ⇒ 取**两个极端情形**
# =============================================================================
def block_scenarios(bases):
    """⚖⚖⚖ **块级零分布的两个极端情形**（Q4）。

    块 = think + no_think；块内两条都正才算正 ⇒ ⇒ 块的零假设概率 = `base_a × base_b`。
    ⚖ 账本**没登记**哪两条轨迹配成一块 ⇒ ⇒ 取两端：

    · **低基准轨迹数 = 2** ⇒ ⇒ 两个情形：
        - `同块`：两条低基准轨迹配在**同一**块（⇒ ⇒ 那一块 = base²）；
        - `异块`：两条低基准轨迹**各配**一条高基准轨迹。
      ⇒ ⇒ 在 rand 臂上这两个情形**穷尽**了所有可能配对（低基准只有 2 条 ⇒ 只有这两种）。
    · **低基准轨迹数 = 0 / 1** ⇒ ⇒ 配对**唯一** ⇒ ⇒ 只有一个情形。
    · **低基准轨迹数 > 2** ⇒ ⇒ **HardFail**（⛔ 预登记只写死了两个极端 ⇒ 不得外推）。
    """
    n = len(bases)
    if n % 2 != 0:
        raise HardFail("轨迹数 %d 是奇数 ⇒ ⇒ 块（2 条轨迹）不成对 ⇒ ⇒ 中止" % n)
    nb = n // 2
    cnt = {}
    for b in bases:
        cnt[b] = cnt.get(b, 0) + 1
    modal = max(sorted(cnt), key=lambda k: cnt[k])
    lows = [b for b in bases if b != modal]
    if len(lows) > 2:
        raise HardFail("低基准轨迹有 %d 条（>2）⇒ ⇒ 预登记只写死两个极端 ⇒ ⇒ 不得外推" % len(lows))
    hi = modal
    if len(lows) == 0:
        return [("唯一（全部高基准）", [hi * hi] * nb)]
    if len(lows) == 1:
        return [("唯一（1 条低基准）", [lows[0] * hi] + [hi * hi] * (nb - 1))]
    lo = lows[0]
    same = [lo * lo] + [hi * hi] * (nb - 1)
    split = [lo * hi] * 2 + [hi * hi] * (nb - 2)
    return [("同块（两条低基准同块）", same), ("异块（两条低基准异块）", split)]


# =============================================================================
# 核心：算八条硬判据 + 判决形态
# =============================================================================
def evaluate(st, sp):
    """⚖⚖⚖ **核心**：给定输入，算出 H1–H8 与判决形态。

    ⚖ `st` 的字段见 `build_state`；`sp` 是口径（`SPEC`）。
    ⚖⚖⚖ **判决只算一次**：印出来的 = 返回的。
    """
    cr = Collector()
    alpha = float(sp["alpha"])
    z = statistics.NormalDist().inv_cdf(float(sp["wilson_z_from"]))

    # ---------- H1：基准可复算 ----------
    base_w_calc = sum(st["base_w"]) / len(st["base_w"])
    base_r_calc = sum(st["base_r"]) / len(st["base_r"])
    tol_b = tol_from(st["raw_base_w"])
    ok1 = (abs(base_w_calc - st["base_w_printed"]) <= tol_b
           and abs(base_r_calc - st["base_r_printed"]) <= tol_b)
    cr.check("H1-BASECALC", ok1,
             "现算基准 w=%.10f / rand=%.10f ｜ 账本印 %.4f / %.4f ｜ 容差 %.1e（= 账本打印精度的半个单位）"
             % (base_w_calc, base_r_calc, st["base_w_printed"], st["base_r_printed"], tol_b))

    # ---------- H2：逐格前提（单侧**下尾** ⇒ ⇒ 只判「明显偏低」红）----------
    n_nz_cells = st["n_cells"] - st["n_zero"]
    p_cell = binom_lower_tail(n_nz_cells, st["n_pos"])
    ok2 = not (float(p_cell) < alpha)
    cr.check("H2-CELLBASE", ok2,
             "rand 非零格 %d 个 ｜ 正号 %d ｜ 单侧下尾 p=%.12e ｜ 阈值 %.2f ⇒ ⇒ %s"
             % (n_nz_cells, st["n_pos"], float(p_cell), alpha,
                "不判红（⛔「不显著」是**弱**证据：格不独立 ⇒ p 反保守 ⇒ 不许当「基准没问题」的证明）"
                if ok2 else "**明显偏低** ⇒ ⇒ 244.60 的旧担忧在本批上成立 ⇒ ⇒ FAIL"))

    # ---------- H3：轨迹级（rand vs 零假设）----------
    pmf_r = pb_pmf_np(st["base_r"])
    p_traj_r = tail_p(pmf_r, st["obs_r"])
    ok3 = not (p_traj_r < alpha)
    cr.check("H3-TRAJNULL", ok3,
             "rand 轨迹级 观测 %d ｜ 零分布均值 %.4f（Poisson-binomial，%d 个 base）｜ 单侧上尾 p=%.12e "
             "⇒ ⇒ %s"
             % (st["obs_r"], sum(st["base_r"]) / len(st["base_r"]), len(st["base_r"]), p_traj_r,
                "与零假设不可区分 ⇒ ⇒ 绿" if ok3 else "**显著高于**零假设 ⇒ ⇒ 红"))

    # ---------- H4：块级（rand vs 零假设；**两端都绿**才算绿）----------
    scen_r = block_scenarios(st["base_r"])
    p_blk = []
    for name, qs in scen_r:
        pm = pb_pmf_np(qs)
        p = tail_p(pm, st["blk_r"])
        p_blk.append((name, p))
    ok4 = all(p >= alpha for _n, p in p_blk)
    cr.check("H4-BLOCKNULL", ok4,
             "rand 块级 观测 %d/%d ｜ %s ⇒ ⇒ %s"
             % (st["blk_r"], st["n_blocks"],
                " ｜ ".join("%s：均值 %.4f、单侧上尾 p=%.12e" % (nm, sum(qs) / len(qs), p)
                            for (nm, qs), (_n2, p) in zip(scen_r, p_blk)),
                "**两端都**与零假设不可区分 ⇒ ⇒ 绿（对配对不确定性稳健）" if ok4
                else "至少一端显著高于零假设 ⇒ ⇒ 红"))

    # ---------- H5：判别力（不是恒绿）：w 臂在**同一条**检验下必须显著 ----------
    pmf_w = pb_pmf_np(st["base_w"])
    p_traj_w = tail_p(pmf_w, st["obs_w"])
    scen_w = block_scenarios(st["base_w"])
    p_blk_w = []
    for name, qs in scen_w:
        pm = pb_pmf_np(qs)
        p_blk_w.append((name, tail_p(pm, st["blk_w"])))
    ok5 = (p_traj_w < alpha) and all(p < alpha for _n, p in p_blk_w)
    cr.check("H5-POWER", ok5,
             "w 臂在同一检验下：轨迹级 观测 %d、单侧上尾 p=%.12e ｜ 块级 观测 %d/%d、%s ⇒ ⇒ %s"
             % (st["obs_w"], p_traj_w, st["blk_w"], st["n_blocks"],
                " ｜ ".join("%s p=%.12e" % (n, p) for n, p in p_blk_w),
                "**显著** ⇒ ⇒ 这套检验有判别力（不是恒绿）" if ok5
                else "⛔ **不显著** ⇒ ⇒ 这套检验没有判别力 ⇒ ⇒ FAIL"))

    # ---------- H6：幅度上界 + 真实差区间（Q7 / Q8 的两条都印）----------
    base_r_pp = 100.0 * st["base_r_printed"]
    c_hi = st["wil_r_hi_pp"] - base_r_pp
    c_lo = st["wil_r_lo_pp"] - base_r_pp
    c_max = st["wil_r_hi_pp"] - base_r_pp
    d_obs = st["delta_pp"]
    iv_no_lo, iv_no_hi = d_obs + c_lo, d_obs + c_hi
    iv_up_lo, iv_up_hi = d_obs, d_obs + c_hi
    finite = all(math.isfinite(x) for x in (c_hi, c_lo, c_max, iv_no_lo, iv_no_hi,
                                            iv_up_lo, iv_up_hi))
    # ⚖⚖⚖ **Q8 的两条区间是两种「不同假设」下的结果，不是嵌套关系**：
    #   ①「不假定方向」⇒ c ∈ [c_lo, c_hi]（Wilson 区间给的**全部**可能）
    #   ②「假定污染方向为抬高」⇒ c ≥ 0 ⇒ c ∈ [0, c_hi]（⛔ 更**弱**的假设 ⇒ 可能更宽）
    #   ⇒ ⇒ ⛔ **不许**断言「② ⊆ ①」（当 c_lo > 0 时正好反过来 ⇒ 那是一条**错的**判据）
    #   ⇒ ⇒ 真正的恒等式是：**上端点相同** ＋ **两个下端点各自等于 Q8 的公式**。
    same_hi = abs(iv_no_hi - iv_up_hi) <= 1e-12
    lo_ok = abs(iv_no_lo - (d_obs + c_lo)) <= 1e-12
    anchored = abs(iv_up_lo - d_obs) <= 1e-12
    ok6 = finite and same_hi and lo_ok and anchored
    cr.check("H6-MAGNITUDE", ok6,
             "c_max（污染最多能把 rand 抬高）= %+.2f pp ｜ c_lo=%+.2f pp、c_hi=%+.2f pp "
             "｜ 真实差（**不假定方向**）[%+.2f, %+.2f] pp ｜ 真实差（**假定污染抬高**）[%+.2f, %+.2f] pp "
             "⇒ ⇒ %s"
             % (c_max, c_lo, c_hi, iv_no_lo, iv_no_hi, iv_up_lo, iv_up_hi,
                "有限且两条区间自洽（同一上端点、两个下端点各合公式）" if ok6
                else "⛔ 区间不自洽或非有限"))

    # ---------- H7：输入出处（逐位对上 + 跨来源交叉校验）----------
    prov = st["prov"]
    ok7, prov_detail = provenance_ok(st, prov, sp)
    cr.check("H7-PROVENANCE", ok7, prov_detail)

    # ---------- H8：只读与不越界 ----------
    in_range = all(st["sec_start"] <= st["line"][k] <= st["sec_end"]
                   for k in ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8",
                             "I9", "I10", "I11", "I12"))
    # ⚖⚖⚖ **第二半边的牙齿在哪**：解析被**限制在段内** ⇒ ⇒ 「行号落在段内」这一半
    #   **结构上恒真** ⇒ ⇒ 恒真的护栏比没有护栏更危险 ⇒ ⇒ 因此**必须**再加一条
    #   「段尾由**第二种独立算法**算出且逐位一致」⇒ ⇒ 否则这一半等于没有。
    sec_end_alt = find_section_end_alt(st["_lines"], "244.81")
    two_ways = (sec_end_alt == st["sec_end"])
    md5_same = (st["md5_before"] == st["md5_after"])
    ok8 = in_range and two_ways and md5_same
    cr.check("H8-READONLY", ok8,
             "账本 md5 运行前 %s / 运行后 %s ⇒ ⇒ %s ｜ 12 个输入的解析行号全部落在 244.81 段 "
             "[%d, %d] 内 ⇒ ⇒ %s ｜ 段尾两法（正则 / 字符串）%s / %d ⇒ ⇒ %s"
             % (st["md5_before"], st["md5_after"], "逐位不变" if md5_same else "⛔变了",
                st["sec_start"], st["sec_end"], "是" if in_range else "⛔否",
                sec_end_alt, st["sec_end"], "一致" if two_ways else "⛔不一致"))

    h = {r[0]: r[1] for r in cr.rows}
    cond = verdict_conditions(h)
    form = verdict_from_conditions(cond)
    # ⚖ Wilson 的**重算值**也要进机器可读块 ⇒ ⇒ 第二条实现能拿「重算 vs 重算」比对
    #   （⛔ 光比「重算 vs 账本印的两位小数」是不够的 ⇒ ⇒ 那只验了账本，没验两条实现）
    wl_c, wh_c = wilson_ci(st["obs_w"] / float(st["n_w"]), st["n_w"], z)
    rl_c, rh_c = wilson_ci(st["obs_r"] / float(st["n_r"]), st["n_r"], z)
    extra = {
        "wil_w_calc": (100.0 * wl_c, 100.0 * wh_c),
        "wil_r_calc": (100.0 * rl_c, 100.0 * rh_c),
        "p_traj_r": p_traj_r, "p_traj_w": p_traj_w,
        "p_blk_r": p_blk, "p_blk_w": p_blk_w, "p_cell": float(p_cell),
        "base_w_calc": base_w_calc, "base_r_calc": base_r_calc,
        "c_max_pp": c_max, "c_lo_pp": c_lo, "c_hi_pp": c_hi,
        "iv_no": (iv_no_lo, iv_no_hi), "iv_up": (iv_up_lo, iv_up_hi),
        "n_nz_cells": n_nz_cells,
    }
    return cr, form, h, extra


def binom_lower_tail(n, k):
    """⚖ **Binomial(n, 0.5) 的单侧下尾** `P(X <= k)`（精确，⛔ 不用正态近似）。"""
    n = int(n)
    k = int(k)
    if k < 0:
        return Fraction(0)
    if k >= n:
        return Fraction(1)
    tot = Fraction(0)
    for i in range(0, k + 1):
        tot += Fraction(math.comb(n, i), 2 ** n)
    return tot


# =============================================================================
# H7 的交叉校验（**逐位**回读 ＋ **跨来源**交叉核对）
# =============================================================================
def provenance_ok(st, prov, sp):
    """⚖⚖⚖ **H7 的两个半边**：

    · **半 A「逐位」**：每一个输入解析出来的**结构化值**，必须能**逐位**拼回账本印的**原文**
      （例：`'**46/56**'` ⇒ `(46,56)` ⇒ 拼回 `'46/56'` ⇒ 与原文（去粗体后）**逐位相同**）。
    · **半 B「跨来源」**：本轮**现算**的量，必须与账本**同段印出的伴随值**对上
      （差 / Wilson 区间 / Newcombe 区间 / Fisher p / 基准 / 格数一致性）。

    ⇒ ⇒ 两个半边**不同源**：半 A 比的是「解析 ↔ 原文」，半 B 比的是「现算 ↔ 账本印的伴随值」。
    ⇒ ⇒ **改账本里任何一个数 ⇒ 至少一条必红**。
    """
    bad = []
    details = []

    # ---------- 半 A：逐位回读 ----------
    raw = st["raw"]
    if reserialize_ratio(raw["I1"]) != "%d/%d" % (st["obs_w"], st["n_w"]):
        bad.append("I1")
    if reserialize_ratio(raw["I2"]) != "%d/%d" % (st["obs_r"], st["n_r"]):
        bad.append("I2")
    if reserialize_ratio(raw["I5"]) != "%d/%d" % (st["blk_w"], st["blk_n_w"]):
        bad.append("I5")
    if reserialize_ratio(raw["I6"]) != "%d/%d" % (st["blk_r"], st["blk_n_r"]):
        bad.append("I6")
    if _parse_dist_str(st["dist_w"]) != raw["I7"]:
        bad.append("I7")
    if _parse_dist_str(st["dist_r"]) != raw["I8"]:
        bad.append("I8")
    if raw["I3"] != ("%.*f" % (decimals_of(raw["I3"]), st["base_w_printed"])):
        bad.append("I3")
    if raw["I4"] != ("%.*f" % (decimals_of(raw["I4"]), st["base_r_printed"])):
        bad.append("I4")
    if raw["I10"] != ("[%+.2f, %+.2f]" % (st["wil_r_lo_pp"], st["wil_r_hi_pp"])):
        bad.append("I10")
    if raw["I11"] != ("[%+.2f, %+.2f]" % (st["wil_w_lo_pp"], st["wil_w_hi_pp"])):
        bad.append("I11")
    if raw["I12"] != ("%+.2f" % st["delta_pp"]):
        bad.append("I12")
    if raw["I9"] != " ｜ ".join(c["raw"] for c in st["cell_rows"]):
        bad.append("I9")
    details.append("逐位回读 %d/12 个输入" % (12 - len([b for b in bad if b in
                                                           ("I1", "I2", "I3", "I4", "I5", "I6",
                                                            "I7", "I8", "I9", "I10", "I11", "I12")])))

    # ---------- 半 B：跨来源交叉核对 ----------
    cross = []

    def cmp_num(name, got, want, tol):
        d = abs(got - want)
        cross.append((name, d <= tol, got, want, d, tol))
        if d > tol:
            bad.append(name)

    # ① 分母：轨迹数、块数
    n_from_dist_w = sum(m for _a, _b, m in st["dist_w"])
    n_from_dist_r = sum(m for _a, _b, m in st["dist_r"])
    if not (st["n_w"] == st["n_r"] == n_from_dist_w == n_from_dist_r):
        bad.append("分母(轨迹)")
    if not (st["blk_n_w"] == st["blk_n_r"] == st["n_w"] // 2):
        bad.append("分母(块)")
    cross.append(("分母自洽（轨迹 %d/%d/%d/%d、块 %d/%d）" % (
        st["n_w"], st["n_r"], n_from_dist_w, n_from_dist_r, st["blk_n_w"], st["blk_n_r"]),
        not ("分母(轨迹)" in bad or "分母(块)" in bad), 0, 0, 0, 0))

    # ② 观测差 vs 由 I1/I2 现算的差
    d_calc = 100.0 * (st["obs_w"] / float(st["n_w"]) - st["obs_r"] / float(st["n_r"]))
    cmp_num("差(+30.36pp)", d_calc, st["delta_pp"], tol_from(raw["I12"]))

    # ③ Wilson 区间（w / rand）vs 由 I1/I2 现算
    #   ⚖⚖⚖ **容差不许再乘 100**：账本印的是**百分点**（`+70.16`），而现算值先乘了 100
    #   （`100*wl`）⇒ ⇒ **两边单位已经一致**（都是百分点）⇒ ⇒ 容差就是
    #   `tol_from(原文)` ＝ 半个打印单位 ＝ 0.005 pp
    #   ⚠⚠⚠ **本轮实测抓到**：原先这里写成 `tol_from(...) * 100.0` ⇒ ⇒ 容差被放大 **100 倍**
    #   （0.005 pp ⇒ 0.5 pp）⇒ ⇒ 那条护栏**松了 100 倍** ⇒ ⇒ 已收紧（收紧后实测**仍然绿**）
    z = statistics.NormalDist().inv_cdf(float(sp["wilson_z_from"]))
    wl, wh = wilson_ci(st["obs_w"] / float(st["n_w"]), st["n_w"], z)
    rl, rh = wilson_ci(st["obs_r"] / float(st["n_r"]), st["n_r"], z)
    tol_w = tol_from(raw["I11"])
    tol_r = tol_from(raw["I10"])
    cmp_num("Wilson(w)", 100.0 * wl, st["wil_w_lo_pp"], tol_w)
    cmp_num("Wilson(w)", 100.0 * wh, st["wil_w_hi_pp"], tol_w)
    cmp_num("Wilson(rand)", 100.0 * rl, st["wil_r_lo_pp"], tol_r)
    cmp_num("Wilson(rand)", 100.0 * rh, st["wil_r_hi_pp"], tol_r)

    # ④ Newcombe95 差区间（轨迹级 / 块级）vs 账本印的
    ncl, nch = newcombe_diff_ci(st["obs_w"] / float(st["n_w"]), wl, wh,
                                st["obs_r"] / float(st["n_r"]), rl, rh)
    cmp_num("Newcombe(轨迹)", 100.0 * ncl, st["nc_traj_lo"], tol_from(raw["I12"]))
    cmp_num("Newcombe(轨迹)", 100.0 * nch, st["nc_traj_hi"], tol_from(raw["I12"]))
    bwl, bwh = wilson_ci(st["blk_w"] / float(st["blk_n_w"]), st["blk_n_w"], z)
    brl, brh = wilson_ci(st["blk_r"] / float(st["blk_n_r"]), st["blk_n_r"], z)
    ncl2, nch2 = newcombe_diff_ci(st["blk_w"] / float(st["blk_n_w"]), bwl, bwh,
                                  st["blk_r"] / float(st["blk_n_r"]), brl, brh)
    cmp_num("Newcombe(块)", 100.0 * ncl2, st["nc_blk_lo"], 0.5e-2)
    cmp_num("Newcombe(块)", 100.0 * nch2, st["nc_blk_hi"], 0.5e-2)

    # ⑤ Fisher 精确（两侧）vs 账本印的
    ft = fisher_exact_two_sided(st["obs_w"], st["n_w"] - st["obs_w"],
                                 st["obs_r"], st["n_r"] - st["obs_r"])
    fb = fisher_exact_two_sided(st["blk_w"], st["blk_n_w"] - st["blk_w"],
                                 st["blk_r"], st["blk_n_r"] - st["blk_r"])
    cmp_num("Fisher(轨迹)", float(ft), st["fisher_traj_p_printed"], tol_from("0.000000"))
    cmp_num("Fisher(块)", float(fb), st["fisher_blk_p_printed"], tol_from("0.000000"))

    # ⑥ 格数一致性：I9 的逐档格数/正/负/零 vs I8 的 (n_nz,n_zero) 分布
    tot_cells = sum(c["n_cells"] for c in st["cell_rows"])
    tot_pos = sum(c["n_pos"] for c in st["cell_rows"])
    tot_neg = sum(c["n_neg"] for c in st["cell_rows"])
    tot_zero = sum(c["n_zero"] for c in st["cell_rows"])
    exp_cells = sum((a + b) * m for a, b, m in st["dist_r"])
    exp_nz = sum(a * m for a, b, m in st["dist_r"])
    exp_zero = sum(b * m for a, b, m in st["dist_r"])
    if not (tot_cells == exp_cells and tot_pos + tot_neg == exp_nz and tot_zero == exp_zero):
        bad.append("格数一致性")
    cross.append(("格数一致性（逐档 格%d/正%d/负%d/零%d vs 分布 %d/%d/%d）"
                  % (tot_cells, tot_pos, tot_neg, tot_zero, exp_cells, exp_nz, exp_zero),
                  "格数一致性" not in bad, 0, 0, 0, 0))

    ok = (len(bad) == 0)
    d1 = " ｜ ".join("%s %s" % (n, "✓" if o else "⛔(差 %.3g > %.3g)" % (d, tol))
                     for n, o, g, w, d, tol in cross)
    detail = ("12 个输入全部解析自 244.81 段；逐位回读 %s ｜ 跨来源交叉核对：%s"
              % ("全部逐位相同" if not [b for b in bad if b.startswith("I")] else
                 "⛔ %s" % [b for b in bad if b.startswith("I")], d1))
    return ok, detail


# =============================================================================
# 真数据路径（⛔ 只读账本、⛔ 零 GPU）
# =============================================================================
def build_state(P, md5_before, md5_after):
    """⚖ 把解析结果整成 `evaluate` 需要的输入。"""
    st = dict(P)
    st["base_w"] = [float(b) for b in P["base_w_list"]]
    st["base_r"] = [float(b) for b in P["base_r_list"]]
    st["raw_base_w"] = P["raw"]["I3"]
    st["raw_base_r"] = P["raw"]["I4"]
    st["wil_w_lo_pp"] = P["wil_w_lo"]
    st["wil_w_hi_pp"] = P["wil_w_hi"]
    st["wil_r_lo_pp"] = P["wil_r_lo"]
    st["wil_r_hi_pp"] = P["wil_r_hi"]
    st["n_cells"] = sum(c["n_cells"] for c in P["cell_rows"])
    st["n_pos"] = sum(c["n_pos"] for c in P["cell_rows"])
    st["n_neg"] = sum(c["n_neg"] for c in P["cell_rows"])
    st["n_zero"] = sum(c["n_zero"] for c in P["cell_rows"])
    st["n_blocks"] = P["blk_n_r"]
    st["md5_before"] = md5_before
    st["md5_after"] = md5_after
    st["prov"] = {}
    return st


def run_data(ledger_path):
    sp = dict(SPEC)
    md5_before = md5_of(ledger_path)
    try:
        P = parse_inputs(read_text(ledger_path))
    except HardFail as e:
        print("HARD_FAIL: %s" % e, flush=True)
        print("DATA_RC=3", flush=True)
        return 3
    md5_after_parse = md5_of(ledger_path)

    st = build_state(P, md5_before, md5_after_parse)
    cr, form, h, extra = evaluate(st, sp)

    # ⚖ 判决面板（⛔ 措辞按预登记 §3.1：一个字不许改口）
    print("")
    print("---- 判决面板（244.86：对照臂的零假设地位）----")
    print("判决形态：**%s**" % form)
    print("理由：%s" % verdict_why(form, verdict_conditions(h), h))
    print("")
    print("· 零假设（Q2/Q3）：非零格公平硬币、零格恒 False、阈值 nT·2 > m")
    print("  · rand 轨迹级零分布（Poisson-binomial，%d 个 base：%s）"
          % (len(st["base_r"]), _dist_summary(st["dist_r"])))
    print("    · 观测 %d/%d ｜ 单侧上尾 p = %.12e" % (st["obs_r"], st["n_r"], extra["p_traj_r"]))
    print("  · rand 块级零分布（%s）" % " ｜ ".join(n for n, _p in extra["p_blk_r"]))
    for (n, _p), (_nm, qs) in zip(extra["p_blk_r"], block_scenarios(st["base_r"])):
        print("    · %s：均值 %.4f ｜ 单侧上尾 p = %.12e" % (n, sum(qs) / len(qs), _p))
    print("  · 逐格前提（Q9/H2）：rand 非零格 %d、正号 %d ｜ 单侧下尾 p = %.12e"
          % (extra["n_nz_cells"], st["n_pos"], extra["p_cell"]))
    print("")
    print("· 幅度上界（N2/Q7/Q8）：c_max = **%+.2f pp**（污染最多能把 rand 臂抬高这么多）"
          % extra["c_max_pp"])
    print("  · 真实差（**不假定方向**）：[%+.2f, %+.2f] pp" % extra["iv_no"])
    print("  · 真实差（**假定污染方向为抬高**）：[%+.2f, %+.2f] pp" % extra["iv_up"])
    print("")
    print("⚖⚖⚖ **措辞纪律**：本形态**只**说「rand 臂的**边际**改判率**没有可检出的**高于零假设」")
    print("   ⇒ ⇒ ⛔ **不许**写成「对照臂干净」⇒ ⇒ 只准写「**在可检出层面**没有」＋「幅度上界是 X pp」")
    print("⚖⚖⚖ **本轮⛔ 不产出**（预登记 §4）：污染的精确幅度 ｜ 污染最多翻多少格的精确值 ｜ 机制轴 ｜ "
          "剂量轴 ｜ rand 换种子后的分布 ｜ 污染存在的响应级严格证明（共线）")
    print("")
    print(cr.summary())
    print("VERDICT=%s" % form, flush=True)

    # ---- 机器可读键值块（给第二条实现互证用）----
    print("")
    print("===== AUDIT_KEYS =====")
    kv = [
        ("LEDGER_MD5_BEFORE", md5_before),
        ("LEDGER_MD5_AFTER", md5_after_parse),
        ("SEC_START", st["sec_start"]),
        ("SEC_END", st["sec_end"]),
        ("N_TRAJ", st["n_r"]),
        ("OBS_W", st["obs_w"]),
        ("OBS_R", st["obs_r"]),
        ("N_BLOCKS", st["n_blocks"]),
        ("BLK_W", st["blk_w"]),
        ("BLK_R", st["blk_r"]),
        ("BASE_W_PRINTED", "%.10f" % st["base_w_printed"]),
        ("BASE_R_PRINTED", "%.10f" % st["base_r_printed"]),
        ("BASE_W_CALC", "%.12e" % extra["base_w_calc"]),
        ("BASE_R_CALC", "%.12e" % extra["base_r_calc"]),
        ("P_TRAJ_R", "%.12e" % extra["p_traj_r"]),
        ("P_TRAJ_W", "%.12e" % extra["p_traj_w"]),
        ("P_CELL_LOWER", "%.12e" % extra["p_cell"]),
        ("C_MAX_PP", "%.10f" % extra["c_max_pp"]),
        ("C_LO_PP", "%.10f" % extra["c_lo_pp"]),
        ("C_HI_PP", "%.10f" % extra["c_hi_pp"]),
        ("IV_NO_LO_PP", "%.10f" % extra["iv_no"][0]),
        ("IV_NO_HI_PP", "%.10f" % extra["iv_no"][1]),
        ("IV_UP_LO_PP", "%.10f" % extra["iv_up"][0]),
        ("IV_UP_HI_PP", "%.10f" % extra["iv_up"][1]),
        ("WIL_R_LO_PP", "%.10f" % st["wil_r_lo_pp"]),
        ("WIL_R_HI_PP", "%.10f" % st["wil_r_hi_pp"]),
        ("WIL_W_LO_PP", "%.10f" % st["wil_w_lo_pp"]),
        ("WIL_W_HI_PP", "%.10f" % st["wil_w_hi_pp"]),
        ("WIL_R_LO_PP_CALC", "%.10f" % extra["wil_r_calc"][0]),
        ("WIL_R_HI_PP_CALC", "%.10f" % extra["wil_r_calc"][1]),
        ("WIL_W_LO_PP_CALC", "%.10f" % extra["wil_w_calc"][0]),
        ("WIL_W_HI_PP_CALC", "%.10f" % extra["wil_w_calc"][1]),
        ("N_NZ_CELLS", extra["n_nz_cells"]),
        ("N_POS_CELLS", st["n_pos"]),
    ]
    for (name, qs), (_n2, p) in zip(block_scenarios(st["base_r"]), extra["p_blk_r"]):
        k = _scen_key(name)
        kv.append(("P_BLK_R_%s" % k, "%.12e" % p))
        kv.append(("Q_MEAN_R_%s" % k, "%.10f" % (sum(qs) / len(qs))))
    for (name, qs), (_n2, p) in zip(block_scenarios(st["base_w"]), extra["p_blk_w"]):
        k = _scen_key(name)
        kv.append(("P_BLK_W_%s" % k, "%.12e" % p))
        kv.append(("Q_MEAN_W_%s" % k, "%.10f" % (sum(qs) / len(qs))))
    kv.append(("VERDICT", form))
    for k, v in kv:
        print("%s = %s" % (k, v))
    print("===== END_AUDIT_KEYS =====", flush=True)

    rc = 0 if cr.failed_ids() else 0
    print("DATA_RC=%d" % rc, flush=True)
    return rc


def _scen_key(name):
    """⚖ 块级两个情形的**稳定键**（从情形的名字取 ⇒ ⇒ 互证脚本能对齐）。"""
    if "同块" in name:
        return "SAME"
    if "异块" in name:
        return "SPLIT"
    return "ONLY"


def _dist_summary(dist):
    return ", ".join("(%d,%d)×%d" % (a, b, c) for a, b, c in dist)


# =============================================================================
# Phase-0 闸门（G0-1 .. G0-7）：合成夹具、零 bpath、零 GPU
# =============================================================================
def _dist_from_bases(bases, low_shape):
    """⚖ 从**每条轨迹的 base** 反推 `(n_nz,n_zero)` 分布（base=0.5 ⇒ (3,0)；base=0.25 ⇒ `low_shape`）。

    ⚖⚖⚖ 为什么这么做：**合成夹具也必须自洽** ⇒ ⇒ `(n_nz,n_zero)` 分布、`base` 列表、
    格数三者必须互相吻合 ⇒ ⇒ 否则 H7 的「格数一致性」会先红 ⇒ ⇒ 合成路径就测不到判决映射。
    """
    cnt = {}
    for b in bases:
        cnt[b] = cnt.get(b, 0) + 1
    out = []
    for b in sorted(cnt, reverse=True):
        shape = (3, 0) if abs(b - 0.5) < 1e-12 else low_shape
        out.append((shape[0], shape[1], cnt[b]))
    return out


def _synthetic_state(n_traj, base_r, base_w, obs_r, obs_w, blk_r, blk_w, cells_pos):
    """⚖ 造一个**合成**输入（⛔ 不依赖账本 ⇒ ⇒ 可以进回归执行集）。

    ⚖⚖⚖ **所有伴随值自己算齐**（Wilson / Newcombe / Fisher / 差 / 格数）
    ⇒ ⇒ 合成路径里 **H1–H8 全都真跑**（⛔ 不是「H7 直接绿」的假夹具）。
    """
    sp = dict(SPEC)
    z = statistics.NormalDist().inv_cdf(float(sp["wilson_z_from"]))
    nb = n_traj // 2
    dist_r = _dist_from_bases(base_r, (2, 1))
    dist_w = _dist_from_bases(base_w, (2, 0))
    exp_cells = sum((a + b) * m for a, b, m in dist_r)
    exp_nz = sum(a * m for a, b, m in dist_r)
    exp_zero = sum(b * m for a, b, m in dist_r)

    base_w_printed = sum(base_w) / len(base_w)
    base_r_printed = sum(base_r) / len(base_r)
    wil_w = tuple(100.0 * v for v in wilson_ci(obs_w / float(n_traj), n_traj, z))
    wil_r = tuple(100.0 * v for v in wilson_ci(obs_r / float(n_traj), n_traj, z))
    bwl = wilson_ci(blk_w / float(nb), nb, z)
    brl = wilson_ci(blk_r / float(nb), nb, z)
    nc_traj = newcombe_diff_ci(obs_w / float(n_traj),
                               wilson_ci(obs_w / float(n_traj), n_traj, z)[0],
                               wilson_ci(obs_w / float(n_traj), n_traj, z)[1],
                               obs_r / float(n_traj),
                               wilson_ci(obs_r / float(n_traj), n_traj, z)[0],
                               wilson_ci(obs_r / float(n_traj), n_traj, z)[1])
    nc_blk = newcombe_diff_ci(blk_w / float(nb), bwl[0], bwl[1],
                               blk_r / float(nb), brl[0], brl[1])
    delta_pp = 100.0 * (obs_w / float(n_traj) - obs_r / float(n_traj))
    ft = fisher_exact_two_sided(obs_w, n_traj - obs_w, obs_r, n_traj - obs_r)
    fb = fisher_exact_two_sided(blk_w, nb - blk_w, blk_r, nb - blk_r)
    row_raw = ("pos_frac=0.5  格数=%d  正=%d  负=%d  零=%d"
               % (exp_cells, cells_pos, exp_nz - cells_pos, exp_zero))
    st = {
        "sec_start": 1, "sec_end": 1,
        "_lines": ["## 修订 244.81 —— 合成夹具（⛔ 不是真账本）",
                   "## 修订 244.82 —— 下一段（合成）"],
        "line": {k: 1 for k in ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8",
                                "I9", "I10", "I11", "I12")},
        "raw": {
            "I1": "%d/%d" % (obs_w, n_traj), "I2": "%d/%d" % (obs_r, n_traj),
            "I3": "%.4f" % base_w_printed, "I4": "%.4f" % base_r_printed,
            "I5": "%d/%d" % (blk_w, nb), "I6": "%d/%d" % (blk_r, nb),
            "I7": _parse_dist_str(dist_w), "I8": _parse_dist_str(dist_r),
            "I9": row_raw,
            "I10": "[%+.2f, %+.2f]" % wil_r, "I11": "[%+.2f, %+.2f]" % wil_w,
            "I12": "%+.2f" % delta_pp,
        },
        "raw_base_w": "%.4f" % base_w_printed,
        "raw_base_r": "%.4f" % base_r_printed,
        "dist_w": dist_w, "dist_r": dist_r,
        "cell_rows": [{"pos_frac": "0.5", "n_cells": exp_cells,
                       "n_pos": cells_pos, "n_neg": exp_nz - cells_pos,
                       "n_zero": exp_zero, "raw": row_raw, "line": 1}],
        "base_w": list(base_w), "base_r": list(base_r),
        "base_w_printed": base_w_printed, "base_r_printed": base_r_printed,
        "obs_w": obs_w, "obs_r": obs_r, "n_w": n_traj, "n_r": n_traj,
        "n_blocks": nb, "blk_w": blk_w, "blk_r": blk_r,
        "blk_n_w": nb, "blk_n_r": nb,
        "wil_w_lo_pp": wil_w[0], "wil_w_hi_pp": wil_w[1],
        "wil_r_lo_pp": wil_r[0], "wil_r_hi_pp": wil_r[1],
        "nc_traj_lo": 100.0 * nc_traj[0], "nc_traj_hi": 100.0 * nc_traj[1],
        "nc_blk_lo": 100.0 * nc_blk[0], "nc_blk_hi": 100.0 * nc_blk[1],
        "fisher_traj_p_printed": float(ft), "fisher_blk_p_printed": float(fb),
        "delta_pp": delta_pp,
        "n_cells": exp_cells, "n_pos": cells_pos,
        "n_neg": exp_nz - cells_pos, "n_zero": exp_zero,
        "md5_before": "SYNTH", "md5_after": "SYNTH",
        "prov": {},
    }
    return st


def selftest(spec=None):
    """⚖⚖⚖ **Phase-0 闸门**（预登记 §5）：G0-1 .. G0-7。

    G0-1：Poisson-binomial 的解析基准（均匀 base 必须复现**已知答案**）
    G0-2：**判决映射的分支可达性**（五个形态都必须能被造出来 ⇒ 死分支藏不住）
    G0-3：合成：rand **显著**高于零假设 ⇒ 必须判 **N-B**
    G0-4：合成：rand 与零假设**不可区分** ⇒ 必须判 **N-A**
    G0-5：合成：轨迹级与块级**方向不一致** ⇒ 必须判 **N-C**
    G0-6：合成：基准**不可用**（逐格显著偏低）⇒ 必须判 **N-D**
    G0-7：合成：输入**解析不到** ⇒ 必须 **HardFail**（⛔ 不是判红、⛔ 不是「跳过」）
    """
    sp = dict(SPEC if spec is None else spec)
    fails = []

    # ---- G0-1：Poisson-binomial 的解析基准 ----
    pmf = pb_pmf([Fraction(1, 2)] * 10)
    known = [Fraction(math.comb(10, k), 2 ** 10) for k in range(11)]
    ok1 = (pmf == known)
    pmf2 = pb_pmf([Fraction(1, 4), Fraction(1, 2)])
    ok1b = pmf2 == [Fraction(3, 8), Fraction(1, 2), Fraction(1, 8)]
    ok1 = ok1 and ok1b
    print("[%s] G0-1（Poisson-binomial 的解析基准） 10×0.5 复现 Binomial(10,0.5) ⇒ %s ｜ "
          "[1/4,1/2] ⇒ [3/8,1/2,1/8] ⇒ %s"
          % ("PASS" if ok1 else "FAIL", "是" if pmf == known else "⛔否",
             "是" if ok1b else "⛔否"), flush=True)
    if not ok1:
        fails.append("G0-1")

    # ---- G0-2：判决映射的分支可达性（规则层）----
    base_h = {
        "H1-BASECALC": True, "H2-CELLBASE": True, "H3-TRAJNULL": True,
        "H4-BLOCKNULL": True, "H5-POWER": True, "H6-MAGNITUDE": True,
        "H7-PROVENANCE": True, "H8-READONLY": True,
    }
    cases = []
    c = dict(base_h); cases.append(("N-A", c))
    c = dict(base_h); c["H3-TRAJNULL"] = False; c["H4-BLOCKNULL"] = False; cases.append(("N-B", c))
    c = dict(base_h); c["H3-TRAJNULL"] = False; cases.append(("N-C", c))
    c = dict(base_h); c["H1-BASECALC"] = False; cases.append(("N-D", c))
    c = dict(base_h); c["H7-PROVENANCE"] = False; cases.append(("N-E", c))
    got = []
    for want, hh in cases:
        f = verdict_from_conditions(verdict_conditions(hh))
        got.append((want, f))
    ok2 = all(w == f for w, f in got)
    print("[%s] G0-2（判决映射的分支可达性） 期望/实得：%s ⇒ ⇒ %s"
          % ("PASS" if ok2 else "FAIL", "｜".join("%s→%s" % (w, f) for w, f in got),
             "五个分支**全部可达**" if ok2 else "⛔有死分支"), flush=True)
    if not ok2:
        fails.append("G0-2")

    # ---- G0-3：合成 rand 显著高于零假设 ⇒ N-B ----
    b_r = [0.25, 0.25] + [0.5] * 54
    b_w = [0.25] + [0.5] * 55
    st3 = _synthetic_state(56, b_r, b_w, obs_r=44, obs_w=46, blk_r=22, blk_w=21,
                           cells_pos=83)
    _c3, f3, _h3, _e3 = evaluate(st3, sp)
    ok3 = (f3 == "N-B")
    print("[%s] G0-3（合成：rand 显著高于零假设 ⇒ 必须 N-B） rand 观测 44/56 ⇒ 判 %s"
          % ("PASS" if ok3 else "FAIL", f3), flush=True)
    if not ok3:
        fails.append("G0-3")

    # ---- G0-4：合成 rand 与零假设不可区分 ⇒ N-A ----
    st4 = _synthetic_state(56, b_r, b_w, obs_r=29, obs_w=46, blk_r=6, blk_w=21,
                           cells_pos=85)
    _c4, f4, _h4, _e4 = evaluate(st4, sp)
    ok4 = (f4 == "N-A")
    print("[%s] G0-4（合成：rand 与零假设不可区分 ⇒ 必须 N-A） rand 观测 29/56 ⇒ 判 %s"
          % ("PASS" if ok4 else "FAIL", f4), flush=True)
    if not ok4:
        fails.append("G0-4")

    # ---- G0-5：合成轨迹级与块级方向不一致 ⇒ N-C ----
    #   rand 轨迹级显著（观测 40/56），但块级观测 8/28 在两端都不显著 ⇒ ⇒ 方向不一致
    st5 = _synthetic_state(56, b_r, b_w, obs_r=40, obs_w=46, blk_r=8, blk_w=21,
                           cells_pos=85)
    _c5, f5, _h5, _e5 = evaluate(st5, sp)
    ok5 = (f5 == "N-C")
    print("[%s] G0-5（合成：轨迹级显著、块级不显著 ⇒ 必须 N-C） rand 轨迹 40/56、块 8/28 ⇒ 判 %s"
          % ("PASS" if ok5 else "FAIL", f5), flush=True)
    if not ok5:
        fails.append("G0-5")

    # ---- G0-6：合成基准不可用（逐格显著偏低）⇒ N-D ----
    st6 = _synthetic_state(56, b_r, b_w, obs_r=29, obs_w=46, blk_r=6, blk_w=21,
                           cells_pos=40)
    _c6, f6, _h6, _e6 = evaluate(st6, sp)
    ok6 = (f6 == "N-D")
    print("[%s] G0-6（合成：逐格显著偏低 ⇒ 必须 N-D） rand 非零格 166、正号 40 ⇒ 判 %s"
          % ("PASS" if ok6 else "FAIL", f6), flush=True)
    if not ok6:
        fails.append("G0-6")

    # ---- G0-7：合成输入解析不到 ⇒ HardFail ----
    #   ⚖⚖⚖ **两条子检查都要成立**：
    #   (a) **单点**查找器（`_find_row`）读不到 ⇒ 必须 HardFail；
    #   (b) **整段**解析器（`parse_inputs`）读不到 ⇒ 必须 HardFail。
    #   ⇒ ⇒ ⛔ **不许**只测整段（那样「单点查找器被改成静默兜底」就抓不到 ⇒ ⇒ 判不了红的判据
    #   比没有判据更危险）。
    ok7a = False
    try:
        _find_row([(1, "（一段不含任何锚点的文字）")], ("改判（主口径",), "G0-7 探针")
    except HardFail:
        ok7a = True
    except Exception:
        ok7a = False
    ok7b = False
    try:
        parse_inputs("## 修订 244.81 —— 这是一段空账本\n（什么数都没有）\n")
    except HardFail:
        ok7b = True
    except Exception:
        ok7b = False
    ok7 = ok7a and ok7b
    print("[%s] G0-7（输入解析不到 ⇒ 必须 HardFail） 单点查找器 ⇒ %s ｜ 整段解析器 ⇒ %s "
          "⇒ ⇒ %s"
          % ("PASS" if ok7 else "FAIL", "硬失败" if ok7a else "⛔没硬失败",
             "硬失败" if ok7b else "⛔没硬失败",
             "硬失败（⛔ 不是判红、⛔ 不是「跳过」）" if ok7
             else "⛔ 解析器在静默降级 ⇒ ⇒ 必须 HardFail"), flush=True)
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
# 入口
# =============================================================================
def print_spec():
    for k in sorted(SPEC):
        print("%s = %r" % (k, SPEC[k]))
    print("VERDICT_TABLE = %r" % (VERDICT_TABLE,))
    print("PREREG_FORMS_ORDER = %r" % (PREREG_FORMS_ORDER,))
    print("INPUT_IDS = %r" % (["I%d" % i for i in range(1, 13)],))
    print("CRIT_IDS = %r" % (["H1-BASECALC", "H2-CELLBASE", "H3-TRAJNULL", "H4-BLOCKNULL",
                               "H5-POWER", "H6-MAGNITUDE", "H7-PROVENANCE", "H8-READONLY"],))
    print("GATE_IDS = %r" % (["G0-%d" % i for i in range(1, 8)],))


def main(argv=None):
    ap = argparse.ArgumentParser(description="244.86 对照臂的零假设地位")
    ap.add_argument("--selftest", action="store_true", help="跑 Phase-0 闸门（G0-1..G0-7）")
    ap.add_argument("--data", action="store_true", help="跑真数据路径（只读账本）")
    ap.add_argument("--ledger", default=None, help="账本路径")
    ap.add_argument("--print-spec", action="store_true", help="印出口径常量")
    a = ap.parse_args(argv)

    if a.print_spec:
        print_spec()
        return 0
    if a.selftest:
        return selftest()
    if a.data:
        if not a.ledger:
            die("--data 必须给 --ledger（⛔ 绝不用代码里的字面值兜底）")
        if not os.path.isfile(a.ledger):
            die("账本不存在：%s" % a.ledger)
        return run_data(a.ledger)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
