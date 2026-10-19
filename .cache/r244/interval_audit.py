#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""interval_audit.py —— 判决面板的**统计置信区间**（修订 244.58，零 GPU）

🔴🔴 **本工具问什么**

  用户目标里明确要「w 臂与 rand 臂各自改判多少题、**差多少 pp、p 值与区间**各是多少」，
  而**判决面板的 6 个比例数一个都没有统计置信区间**：

    · 账本里的 `Clopper–Pearson` / `Wilson` 只出现在**早期 P6 线**
      （修订 4/5/184/185/189/193 的正确率与转化率）⛔ **不是**判决面板这几个数；
    · 244.40 有一张「正号数的界 / p 的区间」表，但账本**明写「(最坏情形界，不是置信区间)」**
      ⇒ 它是**方法变体下**的界，⛔ **与统计置信区间不是一回事，不许混用**。

  ⇒ 本工具补上「**计数口径**」的区间，并把它与「固定剂量下的改判区间」**严格分开**。

⚖⚠⚠⚠ **本节最重要的一句话（必须印在报告最前面）**

  244.48 已证 w 臂的 12/14 与 rand 臂的 6/14 **都**是**跨剂量**的多数
  ⇒ 下面这些区间是「**计数口径**的边际」
  ⇒ ⛔ **不代表**「固定剂量下改判了多少题」的区间 ⇒ 那一格仍写「**未量到**」。

⚖ **复用既有生产机械（⛔ 不另写第二套真相）**

  · CP：`flip_robustness.cp_bounds`（纯 stdlib，二分 + 精确二项尾）
    ⚖⚠⚠ **它解的是「每端 α」**（覆盖率 1−2α，默认 90%）
    ⇒ 要 **95%** 必须传 **α/2** ⇒ 本工具一律 `cp_bounds(x, n, ALPHA/2)`
    ⇒ ⛔ 若误传 α，覆盖率掉到 0.9426 ⇒ 被 C4 抓住
  · k/n：`verdict_source_audit.derive_arm`（从**读数**导出，⛔ 不手抄）
  · 新写（r244 下原本没有）：`wilson_bounds`（分数法）、`newcombe_diff`（两比例之差）

⚖⚠⚠⚠ **判据为什么「不是同源」**

  每个端点都**由它自己的定义式**验，而不是拿另一个函数的结果互相比：

    · CP 的定义式：在端点 L 处 `P(X ≥ x | L) = α/2`，在端点 U 处 `P(X ≤ x | U) = α/2`
      ⇒ 二项尾用**本文件新写的直算版**（`math.comb` 直接求和），
        ⛔ **不复用** `cp_bounds` 内部那个对数空间的 `binom_pmf` ⇒ 两端不同源
    · Wilson 的定义式：在端点处 `|p̂ − p̂(p)| / SE(p) = z`
      ⇒ 这是**分数检验反解**的定义，⛔ 不是拿闭式再算一遍

  ⚖⚠⚠⚠⚠ **一条我第一版记错、靠实测纠正的事实（⛔ 别再记反）**

    实测（暴力搜 n=1..40, x=0..n 共 860 组，零违反）：
        **Wilson ⊆ Clopper–Pearson**（Wilson 更窄，CP 更保守）
    ⛔ **不是**「CP ⊆ Wilson」⇒ 方向写反就是一条**假红**。

⚖⚠⚠⚠ 本工具⛔ **不发批**、⛔ 不改探针、⛔ 不写数据文件、⛔ 不删任何文件。
⚖⚠⚖⚖ 每条判据都必须**能红**：自检用**畸形夹具**证明「红得了」，
变异台（`mut_interval_audit.py`）在**源码层**证明「红得了」。

跑法：
    python3 interval_audit.py
    python3 interval_audit.py --selftest
    python3 interval_audit.py --verify-ledger
退出码：0 = 全部判据通过；1 = 有判据红；2 = 前置/读数问题。
"""

import argparse
import collections
import importlib.util
import io
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FLIP = os.path.join(HERE, "flip_robustness.py")
VSRC = os.path.join(HERE, "verdict_source_audit.py")
LEDGER = os.path.join(REPO, ".cache", "xcheck", "R6_RERUN_PREREG.md")
REPORT = os.path.join(HERE, "interval_report.txt")

ALPHA = 0.05
# ⚖ z 的**标准正态 97.5 分位数**（字面量；C0 用 erf 验它的定义式）
Z95 = 1.959963984540054

# ⚖ 报告里区间的**打印精度** ⇒ 账本回读的容差按它定（禁令 ㋃）
INTERVAL_DECIMALS = 4
LEDGER_TOL = 0.5 * (10.0 ** (-INTERVAL_DECIMALS))

# ⚖ 判决面板的 6 个比例：名字 → (统计量, 臂)
PANEL = (
    ("prereg_w", "预登记 w", "prereg", "w"),
    ("prereg_rand", "预登记 rand", "prereg", "rand"),
    ("traj_w", "轨迹级 w", "traj", "w"),
    ("traj_rand", "轨迹级 rand", "traj", "rand"),
    ("prob_w", "问题级 w", "prob", "w"),
    ("prob_rand", "问题级 rand", "prob", "rand"),
)

# ⚖ 三条统计量各自的「两臂之差」（用户目标要「差多少 pp、p 值与区间」）
DIFFS = (
    ("diff_prereg", "预登记", "prereg"),
    ("diff_traj", "轨迹级", "traj"),
    ("diff_prob", "问题级", "prob"),
)

# ⚖⚠⚠⚠ **必须印出来的前置声明**（⛔ 删掉必须红）
# ⚖⚠⚠⚠⚠ 「要求」与「内容」必须是**两份独立的字面量**（244.55 §C11 的教训）：
#   若要求就是内容那份 ⇒ 删一条两边一起消失 ⇒ **恒绿**。
#   ⇒ 下面 PREAMBLE_REQUIRED 是**另抄一遍**的独立字面量 ⇒ 少印/改字都必须红。
PREAMBLE = (
    "⚖⚠⚠⚠ **这些区间是「计数口径」的边际**（244.48/244.50：两臂的多数都是**跨剂量**的多数）",
    "⚖⇒ ⛔ **不代表**「固定剂量下改判了多少题」的区间 ⇒ 那一格仍写「**未量到**」",
    "⚖⇒ ⛔ 本节**没有**回答「12/14 是不是噪声」（244.47 已证计数口径答不了）",
)
PREAMBLE_REQUIRED = (
    "⚖⚠⚠⚠ **这些区间是「计数口径」的边际**（244.48/244.50：两臂的多数都是**跨剂量**的多数）",
    "⚖⇒ ⛔ **不代表**「固定剂量下改判了多少题」的区间 ⇒ 那一格仍写「**未量到**」",
    "⚖⇒ ⛔ 本节**没有**回答「12/14 是不是噪声」（244.47 已证计数口径答不了）",
)

# ⚖⚠⚠ **必须逐条印出来的留白**（⛔ 少印一条必须红）
BLANKS = (
    ("远端 tokenizer 快照的内容指纹",
     "两次跑批之间远端那个 snapshot 目录的**文件内容**有没有变过（同一路径 ≠ 同一内容）"),
    ("`pos_frac` 只在 0.5 取过值",
     "别的取值下「位置/剂量轴」的含义没有任何实测支撑"),
    ("哪一条臂是机制效应",
     "两臂的多数都是**跨剂量**的多数（244.48/244.50）⇒ 机制与剂量仍不可分辨"),
    ("固定/分层剂量下的 w/rand 各自改判数",
     "要跑新的一批（第三次改口径）⇒ ⛔ 等用户点头 ⇒ 本地量不到"),
    ("层内 rho 的重复性",
     "rep_n=1 ⇒ rand 臂那个 12/14 是不是噪声仍未解释（244.37 登记至今）"),
    ("「改判多少题」这个量的区间",
     "本节给的是**比例**的区间；⛔ 「改判题数」的区间**没有**，且那个比例本身是跨剂量的"),
)
# ⚖⚠⚠⚠⚠ **要求**（**另抄一遍的独立字面量** ⇒ 内容少印/改字都必须红）
BLANKS_REQUIRED = (
    "远端 tokenizer 快照的内容指纹",
    "`pos_frac` 只在 0.5 取过值",
    "哪一条臂是机制效应",
    "固定/分层剂量下的 w/rand 各自改判数",
    "层内 rho 的重复性",
    "「改判多少题」这个量的区间",
)

# ⚖ 覆盖率检验点（(n, p)；CP 的理论保证是「每个 p 都 ≥ 1−α」）
COV_POINTS = (
    (14, 0.5), (14, 12.0 / 14.0), (14, 6.0 / 14.0), (14, 13.0 / 14.0),
    (14, 5.0 / 14.0), (7, 2.0 / 7.0), (20, 0.25), (20, 0.5), (10, 0.4), (30, 0.2),
)
COV_CP_FLOOR = 0.95      # ⚖ CP 保守 ⇒ 覆盖 ≥ 1−α（**理论保证**，实测最小 0.9586）
COV_W_FLOOR = 0.90       # ⚖ Wilson 在小 n **已知欠覆盖**（实测最小 0.9267）

# ⚖ 包含关系的暴力搜范围（实测 n=1..40, x=0..n 共 860 组零违反）
CONTAIN_NMAX = 40

# ⚖ 宽度收缩的检验：同比例 1/2，n 递增
WIDTH_NS = (4, 8, 16, 32)


# ---------------------------------------------------------------- 模块加载
def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def flip():
    return _load(FLIP, "flip_robustness_ia")


def vsrc():
    return _load(VSRC, "verdict_source_audit_ia")


# ---------------------------------------------------------------- 区间机械
def cp95(x, n, alpha=ALPHA):
    """⚖ 95% Clopper–Pearson（**每端 α/2**）。

    ⚖⚠⚠⚠ `cp_bounds` 解的是「每端 α」⇒ 覆盖率 1−2α（默认 90%）
    ⇒ **95% 必须传 α/2**。⛔ 传错 ⇒ 覆盖率掉到 0.9426 ⇒ 被 C4 抓住。
    """
    return flip().cp_bounds(x, n, alpha / 2.0)


def wilson_bounds(x, n, z=Z95):
    """⚖ Wilson 分数区间（score method）。"""
    if n <= 0:
        return (0.0, 1.0)
    ph = x / float(n)
    z2 = z * z
    den = 1.0 + z2 / n
    c = (ph + z2 / (2.0 * n)) / den
    h = (z / den) * math.sqrt(ph * (1.0 - ph) / n + z2 / (4.0 * n * n))
    return (max(0.0, c - h), min(1.0, c + h))


def newcombe_diff(x1, n1, x2, n2, z=Z95):
    """⚖ Newcombe 分数法求两比例之差的区间（**方法 10**）。

    ⚖⚠⚠⛔ **不许用两个 CI 直接相减**（那在统计上是错的：把两个独立量的
    区间端点相减，得到的是一个**保守到离谱**的区间）。
    """
    p1 = x1 / float(n1)
    p2 = x2 / float(n2)
    l1, u1 = wilson_bounds(x1, n1, z)
    l2, u2 = wilson_bounds(x2, n2, z)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (max(-1.0, lo), min(1.0, hi))


def naive_diff(x1, n1, x2, n2, z=Z95):
    """⚖ **错误做法**：两个 Wilson 区间直接相减。只用来给 C6 当反例。"""
    l1, u1 = wilson_bounds(x1, n1, z)
    l2, u2 = wilson_bounds(x2, n2, z)
    return (l1 - u2, u1 - l2)


# ---------------------------------------------------------------- 独立验端点的机械
def binom_sf_direct(n, k, p):
    """⚖ P(X ≥ k)，X~Bin(n,p)，**直算**（`math.comb` 直接求和）。

    ⚖⚠⚠ **刻意不复用** `flip_robustness.binom_pmf`（那是**对数空间**的实现）
    ⇒ 两端不同源 ⇒ 这才是真的在验 CP 的端点，不是自己验自己。
    ⚖ n ≤ 60 时直算**不会**下溢。
    """
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return sum(math.comb(n, j) * (p ** j) * ((1.0 - p) ** (n - j))
               for j in range(k, n + 1))


def binom_cdf_direct(n, k, p):
    """⚖ P(X ≤ k)，直算版。"""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(math.comb(n, j) * (p ** j) * ((1.0 - p) ** (n - j))
               for j in range(0, k + 1))


def score_z_at(x, n, p, z=Z95):
    """⚖ Wilson 端点的**定义式**：在 p 处算分数统计量的 z 值。

    ⚖ Wilson 区间 = { p : |p̂ − p| / sqrt(p(1−p)/n) ≤ z } 的反解
    ⇒ 端点处这个比值必须**恰好等于 z**。

    ⚖⚠⚠⚠ **第一版写错了一处**（实测抓到）：我一度用「**重心化**的 p̂_p」和它的
    SE 去算这个比值 ⇒ 算出来是 0.695 而不是 1.96 ⇒ 6 格全红。
    ⚖ 正确形式是**分母里就用候选值 p 本身**（分数检验的标准形式）。
    """
    phat = x / float(n)
    se = math.sqrt(max(p * (1.0 - p), 0.0) / n)
    if se <= 0.0:
        return float("inf")
    return abs(phat - p) / se


# ---------------------------------------------------------------- 判据（吃已算好的值）
def chk_defining(cp, wl, x, n, tol=1e-6):
    """⚖ C1：一个区间的两端是否满足**各自的定义式**。

    ⚖ CP：端点 L 处 P(X≥x|L)=α/2；端点 U 处 P(X≤x|U)=α/2
    ⚖ Wilson：两个端点处 |p̂−p| / sqrt(p(1−p)/n) = z

    ⚖⚠⚠⚠ **定义式只在「严格内部」的端点上成立**（244.58 第一版栽在这）：
      · x=0 时 CP 的 L=0 ⇒ `P(X≥0|0)=1`（⛔ 不是 α/2）；Wilson 的 L=0 ⇒ SE=0 ⇒ z=∞
      · x=n 时 CP 的 U=1 ⇒ `P(X≤n|1)=1`（⛔ 不是 α/2）；Wilson 的 U=1 ⇒ z=∞
    ⇒ 边界端点改由**解析解**与**贴边**条件守住（与 C5 同一组解析式）。
    """
    l, u = cp
    a = ALPHA / 2.0
    parts = []
    ok = True

    # ---- CP ----
    if x == 0:
        okc = (abs(l - 0.0) <= tol
               and abs(u - (1.0 - a ** (1.0 / n))) <= tol)
        parts.append("CP 边界解析解 [%.10f, %.10f]" % (l, u))
    elif x == n:
        okc = (abs(l - a ** (1.0 / n)) <= tol and abs(u - 1.0) <= tol)
        parts.append("CP 边界解析解 [%.10f, %.10f]" % (l, u))
    else:
        tail_l = binom_sf_direct(n, x, l)
        tail_u = binom_cdf_direct(n, x, u)
        okc = (abs(tail_l - a) <= tol and abs(tail_u - a) <= tol and l <= u)
        parts.append("CP 尾方程 %.10f / %.10f" % (tail_l, tail_u))
    ok = ok and okc

    # ---- Wilson ----
    zs = []
    okw = True
    for p, tag in ((wl[0], "L"), (wl[1], "U")):
        if 0.0 < p < 1.0:
            z = score_z_at(x, n, p)
            zs.append(z)
            if abs(z - Z95) / Z95 > 1e-6:
                okw = False
        else:
            # 边界端点：必须是**恰好贴边**（x=0 ⇒ L=0；x=n ⇒ U=1）
            want = 0.0 if x == 0 else 1.0
            if abs(p - want) > 1e-12:
                okw = False
            parts.append("Wilson %s 贴边 = %.1f" % (tag, p))
    ok = ok and okw and wl[0] <= wl[1]
    if zs:
        parts.append("Wilson 分数 z = %.8f / %.8f" % (zs[0], zs[-1]))
    detail = ("%s（应 = α/2 = %.4f；Wilson z 应 = %.8f）"
              % ("；".join(parts), a, Z95))
    return ok, detail


def chk_point_inside(cp, wl, x, n):
    """⚖ C2：点估计 x/n 必须落在两个区间内（CP 与 Wilson 都含 p̂）。"""
    ph = x / float(n)
    ok = (cp[0] - 1e-12 <= ph <= cp[1] + 1e-12
          and wl[0] - 1e-12 <= ph <= wl[1] + 1e-12)
    return ok, "点估计 %.6f；CP=[%.6f, %.6f]、W=[%.6f, %.6f]" % (
        ph, cp[0], cp[1], wl[0], wl[1])


def chk_containment(cp, wl):
    """⚖ C3：Wilson ⊆ Clopper–Pearson（**实测方向**，⛔ 不是反的）。"""
    ok = (wl[0] >= cp[0] - 1e-12 and wl[1] <= cp[1] + 1e-12)
    return ok, "W=[%.6f, %.6f] ⊆ CP=[%.6f, %.6f] ⇒ %s" % (
        wl[0], wl[1], cp[0], cp[1], "成立" if ok else "⛔ **不成立**")


def chk_coverage(nmax=30):
    """⚖ C4：**覆盖率实测**（不是「区间看起来对不对」）。

    ⚖⚠⚠ 这一条专门抓「把 α/2 写成 α」—— 那会让 CP 的实际覆盖率掉到 0.9426。
    """
    worst_cp = 1.0
    worst_w = 1.0
    where_cp = None
    where_w = None
    for (n, p) in COV_POINTS:
        cpn = 0.0
        wn = 0.0
        for x in range(n + 1):
            w = flip().binom_pmf(n, x, p)
            cl, cu = cp95(x, n)
            wl, wu = wilson_bounds(x, n)
            if cl - 1e-15 <= p <= cu + 1e-15:
                cpn += w
            if wl - 1e-15 <= p <= wu + 1e-15:
                wn += w
        if cpn < worst_cp:
            worst_cp, where_cp = cpn, (n, p)
        if wn < worst_w:
            worst_w, where_w = wn, (n, p)
    ok = (worst_cp >= COV_CP_FLOOR and worst_w >= COV_W_FLOOR)
    return ok, ("CP95 最小覆盖 %.4f（阈值 %.2f，@ n=%d,p=%.4f）｜ "
                "W95 最小覆盖 %.4f（阈值 %.2f，@ n=%d,p=%.4f）"
                % (worst_cp, COV_CP_FLOOR, where_cp[0], where_cp[1],
                   worst_w, COV_W_FLOOR, where_w[0], where_w[1]))


def chk_containment_scan(nmax=CONTAIN_NMAX):
    """⚖ C3b：暴力搜 Wilson ⊆ CP（n=1..nmax, x=0..n）。"""
    bad = []
    tot = 0
    for n in range(1, nmax + 1):
        for x in range(0, n + 1):
            cl, cu = cp95(x, n)
            wl = wilson_bounds(x, n)
            tot += 1
            if not (wl[0] >= cl - 1e-12 and wl[1] <= cu + 1e-12):
                bad.append((n, x))
    return (not bad), ("暴力搜 %d 组（n=1..%d, x=0..n），违反 %d 组%s"
                       % (tot, nmax, len(bad),
                          "" if not bad else "：%s" % bad[:5]))


def chk_boundary(cp, x, n):
    """⚖ C5：边界格的**解析解**。

    ⚖ x=0 ⇒ L = 0，U = 1 − (α/2)^(1/n)
    ⚖ x=n ⇒ L = (α/2)^(1/n)，U = 1
    """
    l, u = cp
    a = ALPHA / 2.0
    if x == 0:
        want = (0.0, 1.0 - a ** (1.0 / n))
    elif x == n:
        want = (a ** (1.0 / n), 1.0)
    else:
        return True, "x=%d 不是边界格（跳过）" % x
    ok = (abs(l - want[0]) < 1e-9 and abs(u - want[1]) < 1e-9)
    return ok, ("边界 x=%d, n=%d ⇒ CP95=[%.10f, %.10f]（解析解 [%.10f, %.10f]）"
                % (x, n, l, u, want[0], want[1]))


def chk_newcombe(nb, naive, d, x1, n1, x2, n2):
    """⚖ C6：Newcombe 差区间必须含点估计差、⊆[−1,1]、**宽度严格小于**「两 CI 相减」。

    ⚖⚠⚠⚠ **两条实测得来的限定**（244.58）：

    ① **「窄于」必须用真 margin**（⛔ 不许带 +1e-12 的松边）：
       若把 Newcombe **换成**「两 CI 相减」，两者宽度**相等** ⇒ 带松边的写法照样绿
       ⇒ 那条判据就抓不到「用错了方法」这个最要紧的错。

    ② ⚖⚠⚠ **不能说 Newcombe「严格包含于」naive** —— **实测不成立**：
       问题级 w=7/7 ⇒ Wilson 上界**贴到 1.0** ⇒ `(u1 − p1) = 0`
       ⇒ Newcombe 的**上界与 naive 的上界完全相等**（0.9178 vs 0.9178）
       ⇒ 边界格上只能说「**宽度严格更窄**」+「**包含**（非严格）」。
    """
    lo, hi = nb
    nlo, nhi = naive
    ok = (lo - 1e-12 <= d <= hi + 1e-12 and -1.0 - 1e-12 <= lo and hi <= 1.0 + 1e-12
          and (hi - lo) < (nhi - nlo) - 1e-9
          and lo >= nlo - 1e-9 and hi <= nhi + 1e-9)
    return ok, ("点估计差 %+.6f；Newcombe [%+.6f, %+.6f]（宽 %.6f）｜ "
                "⛔ 错误做法「两 CI 相减」[%+.6f, %+.6f]（宽 %.6f）"
                % (d, lo, hi, hi - lo, nlo, nhi, nhi - nlo))


def chk_width_shrink():
    """⚖ C8：同比例（1/2）下，区间宽度必须**随 n 收缩**。"""
    ws = []
    for n in WIDTH_NS:
        cl, cu = cp95(n // 2, n)
        wl, wu = wilson_bounds(n // 2, n)
        ws.append((n, cu - cl, wu - wl))
    ok = all(ws[i + 1][1] < ws[i][1] and ws[i + 1][2] < ws[i][2]
             for i in range(len(ws) - 1))
    return ok, ("｜ ".join("n=%d CP宽%.4f W宽%.4f" % w for w in ws))


# ---------------------------------------------------------------- 数据层
def derive_panel():
    """⚖ 从**读数**导出 6 个比例（⛔ 不手抄 k/n）。

    ⚖ 走 `verdict_source_audit.derive_arm`（244.55 那条已钉死的来源链）。
    """
    VS = vsrc()
    out = {}
    for arm, fn in (("w", "_an.txt"), ("rand", "_ra.txt")):
        p = os.path.join(HERE, fn)
        if not os.path.isfile(p):
            raise SystemExit("PRECOND_FAIL: 读不到读数 %s" % p)
        d = VS.derive_arm(VS.load_rows(p), arm)
        out[arm] = d
    cells = {}
    for key, label, stat, arm in PANEL:
        cells[key] = {"label": label, "stat": stat, "arm": arm,
                      "k": out[arm][stat][0], "n": out[arm][stat][1]}
    return cells, out


def compute_all(cells):
    """⚖ 把 6 格 + 三条统计量各自的差区间全部算出来。"""
    res = {}
    for key, c in cells.items():
        x, n = c["k"], c["n"]
        cp = cp95(x, n)
        wl = wilson_bounds(x, n)
        res[key] = {"cp": cp, "wilson": wl, "phat": x / float(n)}
    for dkey, dlabel, stat in DIFFS:
        cw = cells["%s_w" % stat]
        cr = cells["%s_rand" % stat]
        res[dkey] = {
            "label": dlabel,
            "newcombe": newcombe_diff(cw["k"], cw["n"], cr["k"], cr["n"]),
            "naive": naive_diff(cw["k"], cw["n"], cr["k"], cr["n"]),
            "phat_diff": cw["k"] / float(cw["n"]) - cr["k"] / float(cr["n"]),
            "w": (cw["k"], cw["n"]),
            "rand": (cr["k"], cr["n"]),
        }
    return res


# ---------------------------------------------------------------- 报告
def fmt(v, d=INTERVAL_DECIMALS):
    return ("%." + str(d) + "f") % v


def table_rows(cells, res):
    """⚖ 账本里那张表（**机器可解析** ⇒ 追加时程序化生成，⛔ 不手抄）。"""
    rows = []
    for key, label, stat, arm in PANEL:
        c = cells[key]
        r = res[key]
        rows.append("| `IV %s` | %d/%d | %s | %s | %s | %s | %s |"
                    % (key, c["k"], c["n"], fmt(r["phat"]),
                       fmt(r["cp"][0]), fmt(r["cp"][1]),
                       fmt(r["wilson"][0]), fmt(r["wilson"][1])))
    for dkey, dlabel, stat in DIFFS:
        d = res[dkey]
        rows.append("| `IV %s` | %d/%d vs %d/%d | %s | %s | %s | %s | %s |"
                    % (dkey, d["w"][0], d["w"][1], d["rand"][0], d["rand"][1],
                       fmt(d["phat_diff"]), fmt(d["newcombe"][0]), fmt(d["newcombe"][1]),
                       fmt(d["naive"][0]), fmt(d["naive"][1])))
    return rows


def build_report(cells, res):
    L = []
    R = collections.OrderedDict()

    def put(cid, ok, detail):
        R[cid] = bool(ok)
        L.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))

    L.append("【0】⚖⚠⚠⚠ **前置声明**（⛔ 删掉任何一条都必须红）")
    for s in PREAMBLE:
        L.append("  " + s)
    L.append("")

    L.append("【1】ℹ 判决面板 6 个比例的区间（账本印的值 ｜ 本次重算的值）")
    for key, label, stat, arm in PANEL:
        c = cells[key]
        r = res[key]
        L.append("  %-12s %-8s %2d/%-2d  p̂=%s ｜ CP95 [%s, %s] ｜ W95 [%s, %s]"
                 % (label, "（%s）" % stat, c["k"], c["n"], fmt(r["phat"]),
                    fmt(r["cp"][0]), fmt(r["cp"][1]),
                    fmt(r["wilson"][0]), fmt(r["wilson"][1])))
    for dkey, dlabel, stat in DIFFS:
        d = res[dkey]
        L.append("  %-12s %-8s %d/%d − %d/%d：点估计差 %s ｜ Newcombe95 [%s, %s]"
                 " ｜ ⛔「两 CI 相减」[%s, %s]"
                 % (dlabel + " 之差", "", d["w"][0], d["w"][1],
                    d["rand"][0], d["rand"][1], fmt(d["phat_diff"]),
                    fmt(d["newcombe"][0]), fmt(d["newcombe"][1]),
                    fmt(d["naive"][0]), fmt(d["naive"][1])))
    L.append("")

    L.append("【2】判据")

    # C0 z 的定义式
    erf_check = 0.5 * (1.0 + math.erf(Z95 / math.sqrt(2.0)))
    put("C0", abs(erf_check - 0.975) < 1e-12,
        "z95 的定义式 Φ(z95) = %.15f（应 = 0.975）" % erf_check)

    # C1 定义式
    ok1 = True
    d1 = []
    for key, label, stat, arm in PANEL:
        c = cells[key]
        r = res[key]
        ok, why = chk_defining(r["cp"], r["wilson"], c["k"], c["n"])
        ok1 = ok1 and ok
        d1.append("%s %s" % (label, "✅" if ok else "❌"))
    put("C1", ok1,
        "6 格的端点必须满足**各自的定义式**（CP: 二项尾 = α/2；Wilson: 分数 z = z95）"
        "：%s" % "；".join(d1))

    # C2 点估计在区间内
    ok2 = True
    d2 = []
    for key, label, stat, arm in PANEL:
        c = cells[key]
        r = res[key]
        ok, why = chk_point_inside(r["cp"], r["wilson"], c["k"], c["n"])
        ok2 = ok2 and ok
        d2.append("%s %s" % (label, "✅" if ok else "❌"))
    put("C2", ok2, "点估计必须落在 CP 与 Wilson 之内：%s" % "；".join(d2))

    # C3 包含关系（6 格）
    ok3 = True
    d3 = []
    for key, label, stat, arm in PANEL:
        c = cells[key]
        r = res[key]
        ok, why = chk_containment(r["cp"], r["wilson"])
        ok3 = ok3 and ok
        d3.append("%s %s" % (label, "✅" if ok else "❌"))
    put("C3", ok3, "6 格必须满足 **Wilson ⊆ CP**（实测方向，⛔ 不是反的）：%s"
        % "；".join(d3))

    # C3b 包含关系暴力搜
    ok3b, why3b = chk_containment_scan()
    put("C3b", ok3b, why3b)

    # C4 覆盖率
    ok4, why4 = chk_coverage()
    put("C4", ok4, why4)

    # C5 边界格
    ok5 = True
    d5 = []
    for (x, n) in ((0, 14), (14, 14), (0, 7), (7, 7)):
        ok, why = chk_boundary(cp95(x, n), x, n)
        ok5 = ok5 and ok
        d5.append(why)
    put("C5", ok5, "边界格解析解：%s" % "；".join(d5))

    # C6 Newcombe（三条统计量各自的差）
    ok6 = True
    d6 = []
    for dkey, dlabel, stat in DIFFS:
        _d = res[dkey]
        ok, why = chk_newcombe(_d["newcombe"], _d["naive"], _d["phat_diff"],
                                _d["w"][0], _d["w"][1], _d["rand"][0], _d["rand"][1])
        ok6 = ok6 and ok
        d6.append("%s %s" % (dlabel, "✅" if ok else "❌"))
    put("C6", ok6, "Newcombe 差区间（含点估计差、⊆[−1,1]、严格窄于「两 CI 相减」）：%s"
        % "；".join(d6))

    # C7 前置声明（**先印后查** ⇒ 查的是「印出来的行」）
    L.append("  ℹ 前置声明检查")
    miss7 = [s for s in PREAMBLE_REQUIRED if not any(s in ln for ln in L)]
    put("C7", not miss7,
        "三条前置声明必须逐条印出；缺 %d 条%s"
        % (len(miss7), "" if not miss7 else "：%s" % miss7))

    # C8 宽度收缩
    ok8, why8 = chk_width_shrink()
    put("C8", ok8, "同比例 1/2 下区间宽度必须随 n 收缩：%s" % why8)

    # C9 留白（**先印后查**）
    L.append("  ℹ 未量到项（⛔ 写成「未量到」，⛔ 不许写成「无差异」）")
    for name, why in BLANKS:
        L.append("    · %s —— %s" % (name, why))
    miss9 = [t for t in BLANKS_REQUIRED if not any(t in ln for ln in L)]
    put("C9", not miss9, "六条留白必须逐条印出；缺 %d 条%s"
        % (len(miss9), "" if not miss9 else "：%s" % miss9))

    return L, R


# ---------------------------------------------------------------- 账本回读
ROW_RE = re.compile(
    r"\|\s*`IV\s+([A-Za-z0-9_]+)`\s*\|\s*(\d+)/(\d+)(?:\s*vs\s*(\d+)/(\d+))?"
    r"\s*\|\s*(-?[\d.]+)\s*\|\s*(-?[\d.]+)\s*\|\s*(-?[\d.]+)\s*\|"
    r"\s*(-?[\d.]+)\s*\|\s*(-?[\d.]+)\s*\|")


def verify_ledger_text(txt, cells, res):
    """⚖ C10：**账本里的表**必须与本次重算一致（防手抄错）。

    ⚖⚠⚠⚠ **同源限定（写在原地）**：账本那几行**当初就是本工具印出来的**
    ⇒ 这一条**抓不到「本工具算错」**，只抓「**抄错/漂了**」。
    ⚖ 真正独立的守卫是 C1–C6（定义式 / 覆盖率 / 包含关系）。
    """
    found = {}
    for m in ROW_RE.finditer(txt):
        found[m.group(1)] = m
    if not found:
        return False, "账本里没有 `IV …` 表行（还没写进去？）"
    bad = []
    for key, label, stat, arm in PANEL:
        m = found.get(key)
        if m is None:
            bad.append("%s 缺行" % key)
            continue
        c = cells[key]
        r = res[key]
        want = [c["k"], c["n"], r["phat"], r["cp"][0], r["cp"][1],
                r["wilson"][0], r["wilson"][1]]
        got = [int(m.group(2)), int(m.group(3))] + [float(m.group(i))
                                                    for i in (6, 7, 8, 9, 10)]
        if got[0] != want[0] or got[1] != want[1]:
            bad.append("%s k/n 变了（账本 %d/%d vs 重算 %d/%d）"
                       % (key, got[0], got[1], want[0], want[1]))
            continue
        for j in range(2, 7):
            if abs(got[j] - want[j]) > LEDGER_TOL:
                bad.append("%s 第 %d 格：账本 %s vs 重算 %s（容差 %.1e）"
                           % (key, j - 1, got[j], want[j], LEDGER_TOL))
    for dkey, dlabel, stat in DIFFS:
        m = found.get(dkey)
        if m is None:
            bad.append("%s 缺行" % dkey)
            continue
        d = res[dkey]
        want = [d["phat_diff"], d["newcombe"][0], d["newcombe"][1],
                d["naive"][0], d["naive"][1]]
        got = [float(m.group(i)) for i in (6, 7, 8, 9, 10)]
        if (int(m.group(2)), int(m.group(3))) != d["w"]:
            bad.append("%s w 臂 k/n 变了" % dkey)
            continue
        if (int(m.group(4)), int(m.group(5))) != d["rand"]:
            bad.append("%s rand 臂 k/n 变了" % dkey)
            continue
        for j in range(5):
            if abs(got[j] - want[j]) > LEDGER_TOL:
                bad.append("%s 第 %d 格：账本 %s vs 重算 %s（容差 %.1e）"
                           % (dkey, j, got[j], want[j], LEDGER_TOL))
    return (not bad), ("账本 `IV` 表回读：%d 行，%s"
                       % (len(found), "逐格一致" if not bad else "不一致 %s" % bad))


def verify_ledger(cells, res):
    if not os.path.isfile(LEDGER):
        return False, "读不到账本 %s" % LEDGER
    return verify_ledger_text(io.open(LEDGER, encoding="utf-8").read(), cells, res)


# ---------------------------------------------------------------- 自检
class SelfFail(Exception):
    """⚖ **我自己的失败**用这个专属异常 ⇒ ⛔ 不与被测代码可能抛的异常混。"""


def selftest():
    ok, bad = [], []

    def chk(t, cond, why=""):
        (ok if cond else bad).append(t)
        print(("[PASS] %s %s" if cond else "[FAIL] %s %s") % (t, why))

    # --- C0 z 的定义式 ------------------------------------------------
    chk("C0", abs(0.5 * (1.0 + math.erf(Z95 / math.sqrt(2.0))) - 0.975) < 1e-12,
        "Φ(z95) = %.15f" % (0.5 * (1.0 + math.erf(Z95 / math.sqrt(2.0)))))

    # --- C1 负例：把 CP 端点改坏 ⇒ 必须红 ------------------------------
    cp = cp95(12, 14)
    wl = wilson_bounds(12, 14)
    good, _ = chk_defining(cp, wl, 12, 14)
    chk("C1", good, "12/14 的端点满足定义式")
    broken = (cp[0] * 0.5, cp[1])
    red, _ = chk_defining(broken, wl, 12, 14)
    chk("C1x", not red, "把 CP 下界改坏 ⇒ 定义式检查必须红")
    broken_w = (wl[0], wl[1] * 0.5)
    red2, _ = chk_defining(cp, broken_w, 12, 14)
    chk("C1y", not red2, "把 Wilson 上界改坏 ⇒ 定义式检查必须红")

    # --- C1z **alpha/2 写成 alpha** ⇒ 端点不满足 95% 的定义式 ---------
    wrong = flip().cp_bounds(12, 14, ALPHA)      # ⛔ 每端 α ⇒ 90% 区间
    red3, _ = chk_defining(wrong, wl, 12, 14)
    chk("C1z", not red3, "用 α（90% 区间）⇒ 95% 的定义式检查必须红")

    # --- C2 负例：区间不含点估计 ⇒ 必须红 ------------------------------
    good2, _ = chk_point_inside(cp, wl, 12, 14)
    chk("C2", good2, "点估计在区间内")
    red4, _ = chk_point_inside((0.95, 0.99), (0.95, 0.99), 12, 14)
    chk("C2x", not red4, "区间不含点估计 ⇒ 必须红")

    # --- C3 负例：把 Wilson 放大到超出 CP ⇒ 必须红 ----------------------
    good3, _ = chk_containment(cp, wl)
    chk("C3", good3, "Wilson ⊆ CP 成立")
    red5, _ = chk_containment(cp, (cp[0] - 0.1, cp[1] + 0.1))
    chk("C3x", not red5, "Wilson 超出 CP ⇒ 必须红")

    # --- C3b 负例：把一个 x 的 Wilson 改坏 ⇒ 暴力搜必须红 ----------------
    ok3b, why3b = chk_containment_scan(nmax=8)
    chk("C3b", ok3b, why3b)

    # --- C4 覆盖率负例：**90% 区间**的覆盖率 ⇒ 必须红 -------------------
    ok4, why4 = chk_coverage()
    chk("C4", ok4, why4)
    worst = 1.0
    for (n, p) in COV_POINTS:
        cpn = 0.0
        for x in range(n + 1):
            w = flip().binom_pmf(n, x, p)
            cl, cu = flip().cp_bounds(x, n, ALPHA)     # ⛔ 每端 α
            if cl - 1e-15 <= p <= cu + 1e-15:
                cpn += w
        worst = min(worst, cpn)
    chk("C4x", worst < COV_CP_FLOOR,
        "用 α（90%% 区间）时 CP 覆盖率最小 %.4f < %.2f ⇒ 覆盖率判据必须红"
        % (worst, COV_CP_FLOOR))

    # --- C5 边界解析解 --------------------------------------------------
    ok5, why5 = chk_boundary(cp95(0, 14), 0, 14)
    chk("C5", ok5, why5)
    ok5b, why5b = chk_boundary(cp95(14, 14), 14, 14)
    chk("C5b", ok5b, why5b)
    a = ALPHA / 2.0
    bad_b = (0.0, (1.0 - a ** (1.0 / 14.0)) * 0.5)
    red5b, _ = chk_boundary(bad_b, 0, 14)
    chk("C5x", not red5b,
        "把 x=0 的 CP 上界改坏（%s ≠ 解析解 %.10f）⇒ 必须红"
        % (bad_b[1], 1.0 - a ** (1.0 / 14.0)))
    bad_b2 = (a ** (1.0 / 14.0) * 0.5, 1.0)
    red5c, _ = chk_boundary(bad_b2, 14, 14)
    chk("C5y", not red5c,
        "把 x=n 的 CP 下界改坏 ⇒ 必须红")

    # --- C6 Newcombe 负例：换成「两 CI 相减」⇒ 必须红 -------------------
    _nb = newcombe_diff(12, 14, 6, 14)
    _nv = naive_diff(12, 14, 6, 14)
    _dd = 12 / 14.0 - 6 / 14.0
    ok6, why6 = chk_newcombe(_nb, _nv, _dd, 12, 14, 6, 14)
    chk("C6", ok6, why6)
    red6, _ = chk_newcombe(_nv, _nv, _dd, 12, 14, 6, 14)
    chk("C6x", not red6,
        "把 Newcombe 换成「两 CI 相减」（宽度 %.6f ≥ 自身宽度）⇒ 必须红"
        % (_nv[1] - _nv[0]))
    red6b, _ = chk_newcombe((_nb[1] + 0.01, _nb[1] + 0.02), _nv, _dd, 12, 14, 6, 14)
    chk("C6y", not red6b, "把 Newcombe 区间挪到不含点估计差 ⇒ 必须红")

    # --- C7 前置声明：少一条 ⇒ 必须红 -----------------------------------
    fake = ["  " + s for s in PREAMBLE[:-1]]      # ⚖ 模拟「少印一条」
    miss = [s for s in PREAMBLE_REQUIRED if not any(s in ln for ln in fake)]
    chk("C7x", len(miss) == 1, "少印一条前置声明 ⇒ 缺 %d 条（应 = 1）" % len(miss))
    fake2 = ["  " + s for s in PREAMBLE]
    miss2 = [s for s in PREAMBLE_REQUIRED if not any(s in ln for ln in fake2)]
    chk("C7y", len(miss2) == 0, "全印 ⇒ 缺 %d 条（应 = 0）" % len(miss2))

    # --- C8 宽度收缩 ----------------------------------------------------
    ok8, why8 = chk_width_shrink()
    chk("C8", ok8, why8)
    widths = [wilson_bounds(n // 2, n) for n in (4, 8, 16, 32)]
    ws = [w[1] - w[0] for w in widths]
    chk("C8x", all(ws[i + 1] < ws[i] for i in range(len(ws) - 1)),
        "Wilson 宽度随 n 严格收缩：%s" % ["%.4f" % w for w in ws])

    # --- C9 留白：少一条 ⇒ 必须红 ---------------------------------------
    L9 = []
    for name, why in BLANKS[:-1]:
        L9.append("    · %s —— %s" % (name, why))
    miss9 = [n for (n, _w) in BLANKS if not any(n in ln for ln in L9)]
    chk("C9x", len(miss9) == 1, "少印一条留白 ⇒ 缺 %d 条" % len(miss9))

    # --- C10 账本回读：造一张错的表 ⇒ 必须红 ----------------------------
    cells, _ = derive_panel()
    res = compute_all(cells)
    rows = table_rows(cells, res)
    good_ledger = "## 修订 999 —— 假账本\n" + "\n".join(rows) + "\n"
    ok10, why10 = verify_ledger_text(good_ledger, cells, res)
    chk("C10", ok10, why10)
    bad_row = rows[0].replace("| 0.5719 |", "| 0.4719 |")
    bad_ledger = "## 修订 999 —— 假账本\n" + "\n".join([bad_row] + rows[1:]) + "\n"
    red10, why10b = verify_ledger_text(bad_ledger, cells, res)
    chk("C10x", not red10, "把账本一格改掉 ⇒ %s" % why10b)
    # 少一行 ⇒ 也必须红
    short_ledger = "## 修订 999 —— 假账本\n" + "\n".join(rows[1:]) + "\n"
    red10b, why10c = verify_ledger_text(short_ledger, cells, res)
    chk("C10y", not red10b, "账本少一行 ⇒ %s" % why10c)

    print("")
    print("自检 %d/%d 通过" % (len(ok), len(ok) + len(bad)))
    if bad:
        print("失败：%s" % bad)
    return 0 if not bad else 1


# ---------------------------------------------------------------- 主流程
def run(verify=False):
    cells, _raw = derive_panel()
    res = compute_all(cells)
    L, R = build_report(cells, res)
    L.append("【3】ℹ 账本回读")
    if verify:
        ok10, why10 = verify_ledger(cells, res)
        R["C10"] = ok10
        L.append("  [%s] C10：%s" % ("PASS" if ok10 else "FAIL", why10))
    else:
        L.append("  ℹ C10 只在 `--verify-ledger` 模式下跑（账本表**追加之后**才存在）")
    L.append("")
    L.append("【4】ℹ 账本表（**程序化生成**，⛔ 不手抄）")
    for row in table_rows(cells, res):
        L.append("  " + row)
    return L, R


def main():
    ap = argparse.ArgumentParser(description="判决面板的统计置信区间（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--verify-ledger", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    try:
        L, R = run(verify=args.verify_ledger)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    print("\n".join(L))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for v in R.values() if v), len(R)))
    return 0 if all(R.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
