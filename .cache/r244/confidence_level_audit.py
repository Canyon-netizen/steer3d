#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.89「保守读法」换置信水平的完整作用域** —— 实现

（口径真相源 = `.cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md`，**先于**本实现签发）

⚖⚖⚖ **这一轮要回答什么**
  244.88 判成形态 **B'**：保守读法（`CI_lo + c_lo`）在 9 个扫描口径里 **7/9** 成立，
  破口 `0.99/main`、`0.99/zero_as_half` ⇒ ⇒ 「污染解释不了观测差」**必须收紧**。
  ⇒ ⇒ 但 244.88 的 CI 下端点**只有 95% 一档**（它读账本印好的 Newcombe95 区间，
     **自己没有算 Newcombe**）⇒ ⇒ **「更宽置信水平下的保守读法」完全没量到**。

⚖⚖⚖ **本轮做两件事**
  ① **把 Newcombe 自己实现出来**（方法 10），在 **90 / 95 / 99** 三个水平各算一遍；
  ② 把保守读法放到完整的 **(CI 水平 × 污染水平 × 基准变体) = 27 格**上，
     并抽出**决策区**（联合置信 ≥ 90% ⇒ 4 种分配 × 3 个基准 = 12 格）作主表。

⚖⚖⚖ **量纲（kind 标签）**
  `delta_obs`    = w − rand 的**点估计**
  `delta_ci_lo`  = w − rand 的**差区间下端点**（本轮**自己算** Newcombe）
  `c_lower`      = 污染量 c 的 Wilson **下界**
  `c_upper`      = 污染量 c 的 Wilson **上界**（本轮**不参与**任何判据）
  `sum_bound`    = 两个下界相加得到的**界**（⛔ 不参与任何比较）

⚖⚖⚖ **只允许三种运算**（预登记 §1；其余一律红 ⇒ H7）
  ① 单源读法：`delta_ci_lo > 0`             （污染只抬高 rand 臂 ⇒ 不需要 c）
  ② 点估计读法：`delta_obs + c_lower > 0`
  ③ 保守读法：`delta_ci_lo + c_lower > 0`    （抽样噪声与污染幅度同时最保守）
  ⛔ `delta_ci_lo ↔ c_upper`（假警报）／`delta_ci_lo + delta_obs`／
     `c_upper + c_lower`／`sum_bound` 参与任何运算 ⇒ ⇒ **红**。
"""

import argparse
import hashlib
import io
import math
import os
import re
import sys
import tempfile

# =============================================================================
# SPEC（口径参数；⛔ 不是原始数；由预登记 §1/§2 决定）
# =============================================================================

#: Newcombe 差区间的置信水平（本轮**新算**）
CI_LEVELS = (0.90, 0.95, 0.99)
#: 污染量 c 的 Wilson 区间置信水平
C_LEVELS = (0.90, 0.95, 0.99)
#: 零假设基准的三个扫描变体（零格轨迹的 base 取 0.25 / 0.5 / 0；其余轨迹 base = 0.5）
BASE_VARIANTS = ("main", "zero_as_half", "zero_as_zero")
#: 零格轨迹在 `main` 变体下的 base（其余轨迹恒为 0.5）
BASE_ZERO_MAIN = 0.25
BASE_OTHER = 0.5
#: 决策区的门槛：**联合置信 ≥ 90%**（= 244.88 主口径的联合置信 ⇒ 两轮主表可直接对照）
JOINT_FLOOR = 0.90
#: ⚖⚖⚖ **决策区成员是「手写」的**（⛔ 不许从被检实现派生）⇒ ⇒ 「把联合置信改成浮点比较」
#:   这种变异会把 (95,95) 那 **3** 格（3 个基准变体）**静默踢出**决策区
#:   ⇒ ⇒ 主表会悄悄从 12 格变成 9 格 ⇒ ⇒ 这张手写表就是它的牙齿。
EXPECTED_DECISION_ALLOCATIONS = (
    (0.95, 0.95),   # 联合 90%
    (0.95, 0.99),   # 联合 94%
    (0.99, 0.95),   # 联合 94%
    (0.99, 0.99),   # 联合 98%
)
#: 主口径（跨轮对账用）
MAIN_CI_LEVEL = 0.95
MAIN_C_LEVEL = 0.95
#: ⚖⚖⚖ **H9 残差判据的容差**（由**外部依据**推导：244.88 那 9 格印到 **4 位小数**
#: ⇒ ⇒ 残差的下界就是它的**半个单位** 5e-5 pp ⇒ ⇒ 容差必须取 5e-5
#: ⇒ ⇒ ⛔ 1e-6 是**不可能达到**的（⇒ ⇒ 那条判据会恒红 ⇒ ⇒ 等于没有判据）。
#: ⚖ 这条容差**只**允许真实公式差异（量级 ≥ 1e-3）被抓到；它**抓不到** 1e-5 量级的差异。
RESID_TOL = 5e-5

#: 固定的 z 表（口径参数，⛔ 不是原始数）
Z_TABLE = {
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
    0.99: 2.5758293035489004,
}

# =============================================================================
# 判决形态（预登记 §3.2：互斥且穷尽的**唯一级联** E″ → D″ → C″ → B″ → A″）
# =============================================================================

FORM_E = "E'"   # 硬失败 ⇒ 本轮不出判决
FORM_D = "D'"   # 单源读法被否
FORM_C = "C'"   # 点估计口径被否
FORM_B = "B'"   # 保守读法有破口 ⇒ 结论必须收紧
FORM_A = "A'"   # 全绿
FORMS = (FORM_E, FORM_D, FORM_C, FORM_B, FORM_A)

#: 判据 id
CRIT_IDS = ("H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9")
#: ⚠ **必须是 tuple 而不是生成器**（⛔ 生成器是一次性的 ⇒ ⇒ 第一次用掉之后就没了
#:   ⇒ ⇒ 对账脚本第二次用时看到空列表 ⇒ ⇒ 明细会骗人）
#: ⚠ 写成**字面量**（⛔ 不用推导式）⇒ ⇒ 对账脚本能从源码文本里抠出来逐条核对
GATE_IDS = ("G0-1", "G0-2", "G0-3", "G0-4", "G0-5", "G0-6", "G0-7", "G0-8", "G0-9")
#: 硬失败集合（⇒ ⇒ 形态 E′）
HARD_FAIL_IDS = ("H1", "H2", "H7", "H8", "H9")
#: 读法 id（作用域表的行；S6 只作示意，⛔ 不参与形态判定）
READINGS = ("S1", "S2", "S3", "S4", "S5", "S6")

# =============================================================================
# kind 标签
# =============================================================================

K_C_UPPER = "c_upper"
K_C_LOWER = "c_lower"
K_DELTA_OBS = "delta_obs"
K_DELTA_CI_LO = "delta_ci_lo"
K_SUM = "sum_bound"

#: 允许的**加法对**（kind 顺序无关 ⇒ ⇒ 两种写法都登记）
ALLOWED_SUMS = frozenset([
    (K_DELTA_CI_LO, K_C_LOWER),
    (K_C_LOWER, K_DELTA_CI_LO),
    (K_DELTA_OBS, K_C_LOWER),
    (K_C_LOWER, K_DELTA_OBS),
])
#: 允许的**与 0 比较**的 kind（单源读法）
ALLOWED_ZERO_CMP = frozenset([K_DELTA_CI_LO])


# =============================================================================
# 基础工具
# =============================================================================

def die(msg):
    """⚖ **硬失败**（⛔ 不许静默降级）。"""
    raise SystemExit("HARD_FAIL: %s" % msg)


def read_text(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def md5_bytes(raw):
    return hashlib.md5(raw).hexdigest()


def md5_file(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def tol_from_printed(text):
    """⚖⚖⚖ **容差由账本的打印精度推导**（⛔ 不是拍脑袋的常数）。

    账本把数印成几位小数 ⇒ ⇒ 打印精度的**半个单位**就是容差
    （两位小数 ⇒ 0.005；四位小数 ⇒ 0.00005）。
    ⚠ 打印几位 ⇒ ⇒ 容差跟着变（G0-4 守着这条）。
    """
    t = (text or "").strip()
    m = re.search(r"\.([0-9]+)", t)
    dec = len(m.group(1)) if m else 0
    return 0.5 * (10.0 ** (-dec))


def make_qty(value, kind, name):
    """⚖ **带 kind 标签的量** ⇒ ⇒ 量纲自检才有可核对的东西。"""
    return {"value": float(value), "kind": kind, "name": name}


# =============================================================================
# 账本解析层（全部输入从账本逐行解析；⛔ 代码里不写死任何一个数）
# =============================================================================

def section_of(lines, rev):
    """⚖ 取「## 修订 <rev> 」那一段（到下一个「## 修订 」为止）⇒ (段文本, 起行号, 止行号)。"""
    starts = [i for i, ln in enumerate(lines) if ln.startswith("## 修订 %s " % rev)]
    if len(starts) != 1:
        die("账本里「## 修订 %s」有 %d 处（期望恰好 1 处 ⇒ ⇒ 锚点不唯一 ⇒ ⇒ 中止）" % (rev, len(starts)))
    s = starts[0]
    e = len(lines)
    for j in range(s + 1, len(lines)):
        if lines[j].startswith("## 修订 "):
            e = j
            break
    return "\n".join(lines[s:e]), s + 1, e


def unique_hit(pattern, text, what, flags=re.M):
    """⚖ 段内**恰好一次**的命中（⛔ 命中 0 次或多次 ⇒ ⇒ 中止）。"""
    hits = list(re.finditer(pattern, text, flags))
    if len(hits) != 1:
        die("段内「%s」按模式命中 %d 次（期望恰好 1 次 ⇒ ⇒ 锚点不唯一 ⇒ ⇒ 中止）" % (what, len(hits)))
    return hits[0]


def parse_multiset(text, what):
    """⚖ 解析 `{0.25×1, 0.5×55}` ⇒ ⇒ [(0.25, 1), (0.5, 55)]（**逐项回读**）。"""
    items = re.findall(r"([0-9.]+)\s*×\s*(\d+)", text)
    if not items:
        die("%s 解析不到项：%r" % (what, text))
    out = []
    for val, cnt in items:
        out.append((float(val), int(cnt)))
    rebuilt = "{%s}" % ", ".join("%g×%d" % (v, c) for v, c in out)
    if re.sub(r"\s+", "", rebuilt).strip("{}") != re.sub(r"\s+", "", text).strip("{}"):
        die("%s 逐位回读对不上：原文 %r ⇒ 回读 %r" % (what, text, rebuilt))
    return out


def parse_nz_dist(text, what):
    """⚖ 解析 `{(2,1)×2, (3,0)×54}` ⇒ ⇒ {(2,1): 2, (3,0): 54}（⛔ 内层自带逗号 ⇒ ⇒ 用正则逐项抽）。"""
    items = re.findall(r"\((\d+),(\d+)\)\s*×\s*(\d+)", text)
    if not items:
        die("%s 解析不到项：%r" % (what, text))
    out = {}
    for a, b, c in items:
        out[(int(a), int(b))] = out.get((int(a), int(b)), 0) + int(c)
    return out


def dist_text(dist):
    """⚖ 由分布**重建**成账本里印的那一串（供 H8 的逐字符回读用）。"""
    return "{%s}" % ", ".join("(%d,%d)×%d" % (k[0], k[1], v) for k, v in dist.items())


def parse_inputs(ledger_path, rev_base="244.81"):
    """⚖ 从账本 <rev_base> 段解析本轮的**全部**输入。

    ⛔ 每个数都要逐位回读原文；⛔ 代码里不写死任何一个数。
    """
    with open(ledger_path, "rb") as fh:
        raw = fh.read()
    lines = raw.decode("utf-8").split("\n")
    sec, sec_lo, sec_hi = section_of(lines, rev_base)

    out = {"section_range": (sec_lo, sec_hi), "anchor_lines": {}}

    def at(key, match):
        """⚖ 命中位置对应的**文件行号**（1-based）⇒ ⇒ H8 要核对「解析到的行全部落在段内」。"""
        out["anchor_lines"][key] = sec_lo + sec[:match.start()].count("\n")

    # ---- I1：轨迹级改判数（w / rand）----
    m = unique_hit(r"改判（主口径：逐轨迹\*\*严格多数\*\*，`nT·2 > m`） \| "
                   r"\*\*(\d+)/(\d+)\*\* \| \*\*(\d+)/(\d+)\*\*", sec, "改判（主口径）行")
    out["w_num"], out["w_den"] = int(m.group(1)), int(m.group(2))
    out["r_num"], out["r_den"] = int(m.group(3)), int(m.group(4))
    at("I1", m)

    # ---- I2：两臂的 Wilson95 区间（账本印好的）----
    m = unique_hit(r"比例区间（Wilson95） \| \[([+-][0-9.]+), ([+-][0-9.]+)\] \| "
                   r"\[([+-][0-9.]+), ([+-][0-9.]+)\]", sec, "Wilson95 行")
    out["w_wil_lo"], out["w_wil_hi"] = float(m.group(1)), float(m.group(2))
    out["r_wil_lo"], out["r_wil_hi"] = float(m.group(3)), float(m.group(4))
    at("I2", m)

    # ---- I3：两臂的零假设基准（印的两位小数）----
    m = unique_hit(r"零假设基准（逐轨迹平均） \| ([0-9.]+) \| ([0-9.]+)", sec, "零假设基准行")
    out["w_base_printed"] = float(m.group(1))
    out["r_base_printed"] = float(m.group(2))
    at("I3", m)

    # ---- I4：两臂的 (n_nz,n_zero) 分布 ⇒ ⇒ 用来**现算**零假设基准 ----
    m = unique_hit(r"\(n_nz,n_zero\) 分布：\{([^}]*)\} ｜ \{([^}]*)\}", sec, "(n_nz,n_zero) 分布行")
    out["w_dist"] = parse_nz_dist(m.group(1), "w 臂 (n_nz,n_zero) 分布")
    out["r_dist"] = parse_nz_dist(m.group(2), "rand 臂 (n_nz,n_zero) 分布")
    at("I4", m)

    # ---- I5：两臂的**基准分布**（账本印的逐轨迹 base 多重集）⇒ ⇒ 独立于 I4 的第二条路线 ----
    m = unique_hit(r"基准分布：\{([^}]*)\} ｜ \{([^}]*)\}", sec, "基准分布行")
    out["w_base_dist"] = parse_multiset(m.group(1), "w 臂基准分布")
    out["r_base_dist"] = parse_multiset(m.group(2), "rand 臂基准分布")
    at("I5", m)

    # ---- I6：轨迹级 Δ_obs 与 Newcombe95 区间（账本印好的）----
    m = unique_hit(r"\*\*差 ([+-][0-9.]+) pp\*\* ｜ 差区间（Newcombe95）\[([+-][0-9.]+), ([+-][0-9.]+)\]",
                   sec, "差 + Newcombe95 行")
    out["d_traj_printed"] = float(m.group(1))
    out["nc_traj_lo_printed"] = float(m.group(2))
    out["nc_traj_hi_printed"] = float(m.group(3))
    at("I6", m)

    # ---- I7：块级改判数与 Newcombe95 区间 ----
    m = unique_hit(r"w \*\*(\d+)/(\d+)\*\* ｜ rand \*\*(\d+)/(\d+)\*\* ｜ 差 ([+-][0-9.]+) pp ｜ "
                   r"差区间 \[([+-][0-9.]+), ([+-][0-9.]+)\]", sec, "块级改判数 + Newcombe95 行")
    out["bw_num"], out["bw_den"] = int(m.group(1)), int(m.group(2))
    out["br_num"], out["br_den"] = int(m.group(3)), int(m.group(4))
    out["d_blk_printed"] = float(m.group(5))
    out["nc_blk_lo_printed"] = float(m.group(6))
    out["nc_blk_hi_printed"] = float(m.group(7))
    at("I7", m)

    out["raw_md5"] = md5_bytes(raw)
    out["sec_text"] = sec
    return out


def parse_prev_round(ledger_path, rev_prev="244.88"):
    """⚖ 从账本 <rev_prev> 段解析**上一轮**（244.88）的跨轮锚。

    ⛔ 锚点不唯一 ⇒ ⇒ 命中数 ≠ 1 ⇒ ⇒ 返回 None（**不崩**）⇒ ⇒ H9 判红 ⇒ ⇒ 形态 E″
       （⛔ 不是静默兜底：H9 会明确报「锚点读不到」）
    """
    try:
        with open(ledger_path, "rb") as fh:
            text = fh.read().decode("utf-8")
    except OSError:
        return None, "账本读不到"
    lines = text.split("\n")
    try:
        sec, sec_lo, sec_hi = section_of(lines, rev_prev)
    except SystemExit as exc:
        return None, "244.88 段读不到：%s" % exc

    # ---- 244.88 的 R5 逐格表（9 行）：| 0.95 | main | **+2.9132** | 90% | ... ----
    rows = re.findall(r"^\| (0\.90|0\.95|0\.99) \| (main|zero_as_half|zero_as_zero) \| "
                      r"\*\*([+-][0-9.]+)\*\* \| (\d+)% \|", sec, re.M)
    if len(rows) != 9:
        return None, "244.88 的 R5 逐格表命中 %d 行（期望 9）" % len(rows)
    prev_cells = {}
    for lvl, var, val, conf in rows:
        prev_cells[(float(lvl), var)] = {
            "value": float(val),
            "conf": int(conf),
            "text": "%+.4f" % float(val),
        }

    def one(pattern, what):
        hits = re.findall(pattern, sec)
        if len(hits) != 1:
            return None
        return hits[0]

    r1 = one(r"\*\*R1\*\*[^\n]*?轨迹级 \| \*\*([+-][0-9.]+) pp\*\*", "R1 界")
    r2 = one(r"\*\*R2\*\*[^\n]*?块级 \| \*\*([+-][0-9.]+) pp\*\*", "R2 界")
    r3 = one(r"\*\*R3\*\*[^\n]*?最紧 \*\*([+-][0-9.]+) pp\*\*", "R3 最紧值")
    r6 = one(r"\*\*R6\*\*[^\n]*?最小 \*\*([+-][0-9.]+) pp\*\*", "R6 最小值")
    if r1 is None or r2 is None or r3 is None or r6 is None:
        return None, "244.88 的 R1/R2/R3/R6 锚点读不到"
    return {
        "cells": prev_cells,
        "r1": float(r1),
        "r2": float(r2),
        "r3_tight": float(r3),
        "r6_min": float(r6),
        "section_range": (sec_lo, sec_hi),
    }, None


# =============================================================================
# 口径计算层
# =============================================================================

def z_of(level):
    """⚖ 由置信水平得 z（⛔ 固定的 z 表，口径参数，不是原始数）。"""
    if level not in Z_TABLE:
        die("置信水平 %r 不在 SPEC 里" % (level,))
    return Z_TABLE[level]


def wilson_span(k, n, level):
    """⚖ Wilson 区间的**比例**（⛔ 不乘 100；两端都算）。"""
    if n <= 0:
        die("Wilson：分母 ≤ 0")
    z = z_of(level)
    p = k / float(n)
    den = 1.0 + z * z / n
    mid = (p + z * z / (2.0 * n)) / den
    half = (z / den) * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return (max(0.0, mid - half), min(1.0, mid + half))


def wilson_pp(k, n, level):
    """⚖ Wilson 区间（比例 × 100 ⇒ pp 口径）。"""
    lo, hi = wilson_span(k, n, level)
    return (lo * 100.0, hi * 100.0)


def newcombe_m10(kw, nw, kr, nr, level):
    """⚖⚖⚖ **Newcombe 方法 10**（square-and-add）⇒ ⇒ 两条比例之差的区间。

    lower = diff − √((p_w − l_w)² + (u_r − p_r)²)
    upper = diff + √((u_w − p_w)² + (p_r − l_r)²)

    ⚠ 这是**本轮新实现**的方法（244.88 **没有**算过 Newcombe，它读的是账本印好的 95% 区间）。
    ⚖ 合法性：这是 score 型区间，**不承认聚类**（⇒ 预登记 §7 的 B-5）。
    """
    z = z_of(level)
    pw, pr = kw / float(nw), kr / float(nr)
    lw, uw = wilson_span(kw, nw, level)
    lr, ur = wilson_span(kr, nr, level)
    diff = pw - pr
    lo = diff - math.sqrt((pw - lw) ** 2 + (ur - pr) ** 2)
    hi = diff + math.sqrt((uw - pw) ** 2 + (pr - lr) ** 2)
    return (lo * 100.0, hi * 100.0)


def zero_grid_count(dist):
    """⚖ 分布里**含零格**的轨迹数（⛔ 变体扫描的作用对象）。"""
    return sum(cnt for (_nz, zr), cnt in dist.items() if zr > 0)


def base_for_variant(dist, total, variant):
    """⚖ 由 (n_nz,n_zero) 分布**现算**零假设基准（**比例**，⛔ 不乘 100）。

    · 变体 main         ：零格轨迹 base = 0.25、其余 base = 0.5
    · 变体 zero_as_half ：零格轨迹 base = 0.5（把零格当作可动 ⇒ 多数更容易翻）
    · 变体 zero_as_zero ：零格轨迹 base = 0（极端下界）

    ⚖⚖⚖ 与 244.87 / 244.88 **同一套**变体定义（预登记 §2.1）。
    ⚠ 三个变体的基准都必须落在 [0,1] ⇒ ⇒ 越界 ⇒ ⇒ **硬失败**。
    """
    if variant == "main":
        b_zero = BASE_ZERO_MAIN
    elif variant == "zero_as_half":
        b_zero = 0.5
    elif variant == "zero_as_zero":
        b_zero = 0.0
    else:
        die("未知基准变体 %r" % (variant,))
    z = zero_grid_count(dist)
    rest = total - z
    if rest < 0:
        die("base(%s)：零格轨迹数 %d > 总数 %d" % (variant, z, total))
    out = (b_zero * z + BASE_OTHER * rest) / float(total)
    if not (0.0 <= out <= 1.0):
        die("base(%s)=%r **越界**（必须落在 [0,1]）⇒ ⇒ 基准算法写错了 ⇒ ⇒ 中止" % (variant, out))
    return out


def base_from_printed_multiset(entries):
    """⚖ 由账本印的**基准分布**行现算基准（**第二条独立路线**）。"""
    num = 0.0
    den = 0
    for val, cnt in entries:
        num += val * cnt
        den += cnt
    if den <= 0:
        die("基准分布的总数 ≤ 0")
    return num / den, den


def c_span(k, n, base, level):
    """⚖ **c 的区间**（pp）：[Wilson 下界 − 基准, Wilson 上界 − 基准]。"""
    lo, hi = wilson_pp(k, n, level)
    return (lo - base * 100.0, hi - base * 100.0)


# =============================================================================
# 量纲自检（硬门，H7）
# =============================================================================

def guard_add(kind_a, kind_b):
    """⚖⚖⚖ **加法的量纲自检**（H7）：只允许两种登记在案的加法对。

    ⚖⚖⚖ **每条分支必须可区分**（各有各的**代号**）⇒ ⇒ 否则删掉其中一条
       ⇒ ⇒ 另一条仍会挡住 ⇒ ⇒ 护栏被削弱而没人知道 ⇒ ⇒ 变异台靠这个抓。
    """
    pair = {kind_a, kind_b}
    if pair == {K_DELTA_CI_LO, K_C_UPPER}:
        die("H7-KIND-CILO-CUPPER: ⛔⚠⚠ **量纲自检红（H7）**：把「差值区间下端点」"
            "（kind=%s）与「污染量 c 的上界」（kind=%s）**相加** ⇒ ⇒ 量纲不同 ⇒ ⇒ 中止"
            % (kind_a, kind_b))
    if pair == {K_DELTA_CI_LO, K_DELTA_OBS}:
        die("H7-KIND-CILO-DELTA: ⛔⚠⚠ **量纲自检红（H7）**：把「差值区间下端点」"
            "（kind=%s）与「观测差点估计」（kind=%s）**相加** ⇒ ⇒ 量纲不同 ⇒ ⇒ 中止"
            % (kind_a, kind_b))
    if pair == {K_C_UPPER, K_C_LOWER}:
        die("H7-KIND-CUPPER-PLUS-CLOWER: ⛔⚠ **量纲自检红（H7）**：把「污染量 c 的上界」"
            "（kind=%s）与「c 的下界」（kind=%s）**相加** ⇒ ⇒ 同量纲但**不是**登记的加法 ⇒ ⇒ 中止"
            % (kind_a, kind_b))
    if K_SUM in pair:
        die("H7-KIND-SUM-SUM: ⛔⚠ **量纲自检红（H7）**：把「界本身」（kind=%s）再参与运算 ⇒ ⇒ 中止"
            % (kind_a if kind_a == K_SUM else kind_b))
    if (kind_a, kind_b) not in ALLOWED_SUMS:
        die("H7-KIND-SUM-UNKNOWN: ⛔⚠ **量纲自检红（H7）**：kind %s + %s **不是**允许的加法对 %s"
            % (kind_a, kind_b, sorted(ALLOWED_SUMS)))


def guard_cmp_zero(kind_a):
    """⚖⚖⚖ **与 0 比较的量纲自检**（H7）：只允许「差区间下端点」与 0 比。

    ⛔ `delta_ci_lo ↔ c_upper` 是 244.87 的 H5 / 244.88 的 H8 硬门 ⇒ ⇒ **继续红**
       （那是「拿差的下界去比污染的上界」的假警报）。
    """
    if kind_a not in ALLOWED_ZERO_CMP:
        if kind_a == K_C_UPPER:
            die("H7-KIND-CMP-CILO-CUPPER: ⛔⚠⚠ **量纲自检红（H7）**：拿「污染量 c 的上界」"
                "（kind=c_upper）去比 0 ⇒ ⇒ 那是「差的下界 ↔ 污染的上界」的**假警报** ⇒ ⇒ 中止")
        die("H7-KIND-CMP-UNKNOWN: ⛔⚠ **量纲自检红（H7）**：kind %s **不是**允许与 0 比较的量 %s"
            % (kind_a, sorted(ALLOWED_ZERO_CMP)))


def guard_code(msg):
    """⚖ 从护栏的报错消息里**取出分支代号**（⛔ 不靠 split(":") ⇒ die 加了前缀会错位）。"""
    m = re.search(r"H7-KIND-[A-Z\-]+", msg or "")
    return m.group(0) if m else "(无代号)"


def guard_selftest():
    """⚖ **H7 的自证**：喂**未登记的 kind 配对** ⇒ ⇒ 必须被判红 **且必须由对应分支判红**。

    ⇒ ⇒ 否则「护栏被削弱」这件事**没人知道**（⛔ 另一条分支也能挡 ⇒ ⇒ 察觉不到）。
    """
    cases = [
        (lambda: guard_add(K_DELTA_CI_LO, K_C_UPPER), "H7-KIND-CILO-CUPPER"),
        (lambda: guard_add(K_DELTA_CI_LO, K_DELTA_OBS), "H7-KIND-CILO-DELTA"),
        (lambda: guard_add(K_C_UPPER, K_C_LOWER), "H7-KIND-CUPPER-PLUS-CLOWER"),
        (lambda: guard_add(K_SUM, K_C_LOWER), "H7-KIND-SUM-SUM"),
        (lambda: guard_add(K_C_LOWER, K_C_UPPER), "H7-KIND-CUPPER-PLUS-CLOWER"),
        # ⚖⚖⚖ **兜底分支也必须被覆盖**（⛔ 只试特例 ⇒ ⇒ 兜底那条被删掉时没人知道）
        (lambda: guard_add(K_SUM, K_SUM), "H7-KIND-SUM-SUM"),
        (lambda: guard_cmp_zero(K_C_UPPER), "H7-KIND-CMP-CILO-CUPPER"),
        (lambda: guard_cmp_zero(K_C_LOWER), "H7-KIND-CMP-UNKNOWN"),
        (lambda: guard_cmp_zero(K_DELTA_OBS), "H7-KIND-CMP-UNKNOWN"),
        # ⚖⚖⚖ **兜底那条（只允许登记的加法对）必须被覆盖**
        #   ⚠ `delta_obs + delta_obs` 不命中任何一条**专属分支** ⇒ ⇒ 它**只**由兜底那条拦
        #   ⇒ ⇒ 若兜底那条被删掉 ⇒ ⇒ 这一条就红不了 ⇒ ⇒ 护栏被削弱而**没人知道**
        #   （244.88 的第 ③ 条缺陷：**兜底分支没被覆盖** ⇒ ⇒ 本轮从一开始就把它写进用例）
        (lambda: guard_add(K_DELTA_OBS, K_DELTA_OBS), "H7-KIND-SUM-UNKNOWN"),
        # ⚖⚖⚖ **调用点也必须守住**：只测护栏函数**本身**不够 ⇒ ⇒ 「`add_bounds` 不再调用护栏」
        #   这种变异**没人知道** ⇒ ⇒ 必须从**真正的加法路径**喂一次未登记配对。
        (lambda: add_bounds(make_qty(1.0, K_DELTA_CI_LO, "x"),
                            make_qty(1.0, K_C_UPPER, "y")), "H7-KIND-CILO-CUPPER"),
    ]
    detail = []
    for fn, want in cases:
        try:
            fn()
            return False, "⛔ 未登记配对 %s **没有**判红 ⇒ ⇒ 这条护栏是恒绿的，不可用" % want, None
        except SystemExit as exc:
            code = guard_code(str(exc))
            if code != want:
                return False, ("⛔ 未登记配对虽被判红，但**不是** %s 那条分支（实得 %s）"
                               "⇒ ⇒ 护栏被削弱了却**察觉不到**" % (want, code)), code
            detail.append(want)
    return True, "未登记配对各被红（%s）⇒ 护栏在位" % "、".join(detail), detail[0]


# =============================================================================
# 网格与作用域表
# =============================================================================

def grid_spec():
    """⚖ 网格的**固定顺序**：先 L_CI，再 L_c，最后基准变体。"""
    seq = []
    for lv_ci in CI_LEVELS:
        for lv_c in C_LEVELS:
            for var in BASE_VARIANTS:
                seq.append((lv_ci, lv_c, var))
    return seq


def joint_pct(lv_ci, lv_c):
    """⚖ **联合置信**（Bonferroni）：`1 − α_CI − α_c = L_CI + L_c − 1`（**整数百分点**）。

    ⚖⚖⚖ **为什么用整数百分点**（⚠ 一个真陷阱）：
       二进制浮点里 `0.95 + 0.95 − 1.0` = **0.8999999999999999 < 0.9**
       ⇒ ⇒ 若直接拿它跟门槛 0.90 比，**(95,95) 那 3 格会被静默踢出决策区**
       ⇒ ⇒ （每种分配只覆盖 3 个基准变体 ⇒ ⇒ 主表会从 12 格变成 9 格）
       ⇒ ⇒ 门槛的比较必须落在**整数百分点**上 ⇒ ⇒ 边界不含糊。
    ⚖⚖⚖ **逐格不同** ⇒ ⇒ ⛔ **不许**把整张表写成同一个数。
    ⚠ 联合置信**不是**单调带：联合更高的格**可以**破口，联合更低的格**也可以**成立
      （联合置信说的是「界 > 0 ⇒ 真差 > 0 的把握」，与界本身是否 > 0 无关）。
    """
    return int(round(lv_ci * 100)) + int(round(lv_c * 100)) - 100


def joint_conf(lv_ci, lv_c):
    """⚖ 联合置信（比例口径，供显示）。⚖ 判定一律用 `joint_pct`（整数百分点）。"""
    return joint_pct(lv_ci, lv_c) / 100.0


def build_quantities(inp):
    """⚖ 把账本输入变成**带 kind 标签的量**（本轮的一切计算入口）。"""
    q = {}
    q["d_traj"] = make_qty((inp["w_num"] - inp["r_num"]) * 100.0 / float(inp["w_den"]),
                           K_DELTA_OBS, "delta_obs(traj)")
    q["d_blk"] = make_qty((inp["bw_num"] - inp["br_num"]) * 100.0 / float(inp["bw_den"]),
                          K_DELTA_OBS, "delta_obs(block)")
    q["ci_traj"] = {}
    q["ci_blk"] = {}
    for lv in CI_LEVELS:
        lo, hi = newcombe_m10(inp["w_num"], inp["w_den"], inp["r_num"], inp["r_den"], lv)
        q["ci_traj"][lv] = {"lo": make_qty(lo, K_DELTA_CI_LO, "newcombe_lo(traj,%.2f)" % lv),
                            "hi": make_qty(hi, K_DELTA_CI_LO, "newcombe_hi(traj,%.2f)" % lv)}
        lo_b, hi_b = newcombe_m10(inp["bw_num"], inp["bw_den"], inp["br_num"], inp["br_den"], lv)
        q["ci_blk"][lv] = {"lo": make_qty(lo_b, K_DELTA_CI_LO, "newcombe_lo(block,%.2f)" % lv),
                           "hi": make_qty(hi_b, K_DELTA_CI_LO, "newcombe_hi(block,%.2f)" % lv)}
    q["base"] = {}
    q["c_span"] = {}
    for var in BASE_VARIANTS:
        base = base_for_variant(inp["r_dist"], inp["r_den"], var)
        q["base"][var] = base
        q["c_span"][var] = {}
        for lv in C_LEVELS:
            q["c_span"][var][lv] = c_span(inp["r_num"], inp["r_den"], base, lv)
    return q


def add_bounds(a, b):
    """⚖ **加法 ②/③**：过量纲门（⇒ ⇒ 未登记的加法会**红**）⇒ ⇒ 再相加。"""
    guard_add(a["kind"], b["kind"])
    return make_qty(a["value"] + b["value"], K_SUM, "%s+%s" % (a["name"], b["name"]))


def build_cells(inp, q):
    """⚖ 扫描网格 ⇒ ⇒ 27 格（轨迹级，判决口径）＋ 27 格（块级，⚠ 跨口径·示意）。"""
    cells = []
    for lv_ci, lv_c, var in grid_spec():
        base = q["base"][var]
        c_lo, c_hi = q["c_span"][var][lv_c]
        ci_lo = q["ci_traj"][lv_ci]["lo"]
        traj = add_bounds(ci_lo, make_qty(c_lo, K_C_LOWER, "c_lo(%.2f,%s)" % (lv_c, var)))
        blk_ci_lo = q["ci_blk"][lv_ci]["lo"]
        blk = add_bounds(blk_ci_lo, make_qty(c_lo, K_C_LOWER, "c_lo(%.2f,%s)" % (lv_c, var)))
        conf = joint_conf(lv_ci, lv_c)
        cells.append({
            "level_ci": lv_ci, "level_c": lv_c, "variant": var, "base": base,
            "c_lo": c_lo, "c_hi": c_hi,
            "ci_lo_traj": ci_lo["value"], "ci_lo_blk": blk_ci_lo["value"],
            "traj": traj["value"], "blk": blk["value"],
            "traj_ok": traj["value"] > 0, "blk_ok": blk["value"] > 0,
            "conf": conf, "joint_pct": joint_pct(lv_ci, lv_c),
            "in_decision": joint_pct(lv_ci, lv_c) >= int(round(JOINT_FLOOR * 100)),
        })
    return cells


def build_readings(inp, q, cells):
    """⚖ 作用域表（预登记 §2 的五行读法 S1..S5）。"""
    rows = []

    # S1：单源读法 · 轨迹级 · 跨水平（运算 ①）
    s1 = []
    for lv in CI_LEVELS:
        qty = q["ci_traj"][lv]["lo"]
        guard_cmp_zero(qty["kind"])
        s1.append({"level": lv, "bound": qty["value"], "ok": qty["value"] > 0,
                   "conf": lv})
    rows.append({"id": "S1", "name": "污染只抬高 rand 臂（c ≥ 0）·轨迹级·跨水平",
                 "items": s1, "per_caliber": True,
                 "note": "单源（不需要 c）"})

    # S2：单源读法 · 块级 · 跨水平（运算 ①）
    s2 = []
    for lv in CI_LEVELS:
        qty = q["ci_blk"][lv]["lo"]
        guard_cmp_zero(qty["kind"])
        s2.append({"level": lv, "bound": qty["value"], "ok": qty["value"] > 0,
                   "conf": lv})
    rows.append({"id": "S2", "name": "污染只抬高 rand 臂（c ≥ 0）·块级·跨水平",
                 "items": s2, "per_caliber": True, "note": "单源（不需要 c）"})

    # S3：点估计读法 · 轨迹级（运算 ②；与 CI 水平无关）
    s3 = []
    for lv_c in C_LEVELS:
        for var in BASE_VARIANTS:
            c_lo = q["c_span"][var][lv_c][0]
            bound = add_bounds(q["d_traj"], make_qty(c_lo, K_C_LOWER, "c_lo"))
            s3.append({"level_c": lv_c, "variant": var, "bound": bound["value"],
                       "ok": bound["value"] > 0})
    rows.append({"id": "S3", "name": "不假定方向·点估计·轨迹级", "items": s3,
                 "per_caliber": True, "note": "点估计（无区间）"})

    # S4：点估计读法 · 块级（运算 ②；⚠ 跨口径）
    s4 = []
    for lv_c in C_LEVELS:
        for var in BASE_VARIANTS:
            c_lo = q["c_span"][var][lv_c][0]
            bound = add_bounds(q["d_blk"], make_qty(c_lo, K_C_LOWER, "c_lo"))
            s4.append({"level_c": lv_c, "variant": var, "bound": bound["value"],
                       "ok": bound["value"] > 0})
    rows.append({"id": "S4", "name": "不假定方向·点估计·块级（⚠口径混合）", "items": s4,
                 "per_caliber": True, "note": "⚠ c 是轨迹级算的 ⇒ 跨口径相加"})

    # S5：保守读法 · 轨迹级（运算 ③）—— 本轮的核心表
    s5 = []
    for cell in cells:
        s5.append({"level_ci": cell["level_ci"], "level_c": cell["level_c"],
                   "variant": cell["variant"], "bound": cell["traj"],
                   "ok": cell["traj_ok"], "conf": cell["conf"],
                   "in_decision": cell["in_decision"]})
    rows.append({"id": "S5", "name": "不假定方向·保守（CI+c 同时最保守）·轨迹级",
                 "items": s5, "per_caliber": True,
                 "note": "联合置信 = L_CI + L_c − 1（Bonferroni）"})

    # S6：保守读法 · 块级（运算 ③；⚠ 跨口径 ⇒ ⇒ **只作示意，不参与形态判定**）
    s6 = []
    for cell in cells:
        s6.append({"level_ci": cell["level_ci"], "level_c": cell["level_c"],
                   "variant": cell["variant"], "bound": cell["blk"],
                   "ok": cell["blk_ok"], "conf": cell["conf"],
                   "in_decision": cell["in_decision"]})
    rows.append({"id": "S6", "name": "不假定方向·保守·块级（⚠口径混合·示意）",
                 "items": s6, "per_caliber": True,
                 "note": "⚠ 不参与形态判定（跨口径相加）"})

    return rows


# =============================================================================
# 判据 + 形态
# =============================================================================

def md5_unchanged(path, before_md5):
    """⚖⚖⚖ **「这个文件没被改过」的判断**（H8 与 G0-7 **共用同一个函数**）。

    ⚖ **为什么要抽成函数**：把「比较表达式」改成恒真 ⇒ ⇒ **没有任何闸门能抓**
       ⇒ ⇒ 修法：① 抽成**一个函数**；② 除了正控（没碰 ⇒ 必须说「没变」）还加**负控**
       （碰一下 ⇒ 必须说「变了」）⇒ ⇒ 两个控件**共用**这个函数 ⇒ ⇒ 把它改成恒真
       ⇒ ⇒ **正控与负控同时失效** ⇒ ⇒ G0-7 自己就红 ⇒ ⇒ 抓得到。
    """
    return md5_file(path) == before_md5


def make_check(cid, name, ok, detail):
    return {"id": cid, "name": name, "ok": bool(ok), "detail": detail}


def classify(flags):
    """⚖⚖⚖ **形态的**唯一级联**（预登记 §3.2）：E″ → D″ → C″ → B″ → A″。

    ⚖ **每个输入只落一个形态** ⇒ ⇒ 互斥且穷尽（G0-2 穷举验证）。
    """
    if any(not flags.get(cid, True) for cid in HARD_FAIL_IDS):
        return FORM_E
    if not flags.get("H3", True):
        return FORM_D
    if not flags.get("H4", True):
        return FORM_C
    if not flags.get("H5", True) or not flags.get("H6", True):
        return FORM_B
    return FORM_A


def judge(inp, q, cells, rows, ledger_path, prev, prev_err):
    """⚖ 主判据：H1..H9 ⇒ ⇒ 形态 + 理由。"""
    checks = []

    # ---- H1：解析链复算门槛（八项）----
    h1_items = []

    d_traj_calc = (inp["w_num"] - inp["r_num"]) * 100.0 / float(inp["w_den"])
    h1_items.append(("轨迹级 Δ_obs", d_traj_calc, inp["d_traj_printed"],
                     tol_from_printed("%+.2f" % inp["d_traj_printed"])))
    d_blk_calc = (inp["bw_num"] - inp["br_num"]) * 100.0 / float(inp["bw_den"])
    h1_items.append(("块级 Δ_obs", d_blk_calc, inp["d_blk_printed"],
                     tol_from_printed("%+.2f" % inp["d_blk_printed"])))

    w_lo, w_hi = wilson_pp(inp["w_num"], inp["w_den"], MAIN_CI_LEVEL)
    h1_items.append(("Wilson95(w) 下端", w_lo, inp["w_wil_lo"],
                     tol_from_printed("%+.2f" % inp["w_wil_lo"])))
    h1_items.append(("Wilson95(w) 上端", w_hi, inp["w_wil_hi"],
                     tol_from_printed("%+.2f" % inp["w_wil_hi"])))
    r_lo, r_hi = wilson_pp(inp["r_num"], inp["r_den"], MAIN_CI_LEVEL)
    h1_items.append(("Wilson95(rand) 下端", r_lo, inp["r_wil_lo"],
                     tol_from_printed("%+.2f" % inp["r_wil_lo"])))
    h1_items.append(("Wilson95(rand) 上端", r_hi, inp["r_wil_hi"],
                     tol_from_printed("%+.2f" % inp["r_wil_hi"])))

    base_calc = q["base"]["main"]
    h1_items.append(("rand 臂基准", base_calc, inp["r_base_printed"],
                     tol_from_printed("%.4f" % inp["r_base_printed"])))
    base_from_ms, ms_total = base_from_printed_multiset(inp["r_base_dist"])
    h1_items.append(("rand 臂基准（基准分布行现算）", base_from_ms, base_calc,
                     tol_from_printed("%.4f" % inp["r_base_printed"])))

    ci_traj = q["ci_traj"][MAIN_CI_LEVEL]
    h1_items.append(("Newcombe95(traj) 下端", ci_traj["lo"]["value"],
                     inp["nc_traj_lo_printed"],
                     tol_from_printed("%+.2f" % inp["nc_traj_lo_printed"])))
    h1_items.append(("Newcombe95(traj) 上端", ci_traj["hi"]["value"],
                     inp["nc_traj_hi_printed"],
                     tol_from_printed("%+.2f" % inp["nc_traj_hi_printed"])))
    ci_blk = q["ci_blk"][MAIN_CI_LEVEL]
    h1_items.append(("Newcombe95(block) 下端", ci_blk["lo"]["value"],
                     inp["nc_blk_lo_printed"],
                     tol_from_printed("%+.2f" % inp["nc_blk_lo_printed"])))
    h1_items.append(("Newcombe95(block) 上端", ci_blk["hi"]["value"],
                     inp["nc_blk_hi_printed"],
                     tol_from_printed("%+.2f" % inp["nc_blk_hi_printed"])))

    h1_bad = []
    h1_detail = []
    for label, calc, printed, tol in h1_items:
        ok = abs(calc - printed) <= tol
        if not ok:
            h1_bad.append(label)
        h1_detail.append("%s 算=%+.4f vs 印=%+.4f（容差 %.5f，%s）"
                         % (label, calc, printed, tol, "对得上" if ok else "**对不上**"))
    checks.append(make_check("H1", "解析链复算门槛（十项）", not h1_bad,
                              " ｜ ".join(h1_detail)))

    # ---- H2：扫描完备性（27 格 × 2 口径，顺序固定，集合与 SPEC 逐条相同）----
    want = grid_spec()
    got = [(c["level_ci"], c["level_c"], c["variant"]) for c in cells]
    same_set = (set(got) == set(want))
    # ⚖⚖⚖ **决策区的成员必须与「手写的那张表」逐条相同**（⛔ 不许从实现自己派生）
    got_alloc = sorted(set((c["level_ci"], c["level_c"]) for c in cells if c["in_decision"]))
    want_alloc = sorted(EXPECTED_DECISION_ALLOCATIONS)
    dec_ok = (got_alloc == want_alloc)
    ok2 = (got == want) and len(cells) == 27 and same_set and dec_ok \
        and tuple(sorted(set(c["level_ci"] for c in cells))) == tuple(sorted(CI_LEVELS)) \
        and tuple(sorted(set(c["level_c"] for c in cells))) == tuple(sorted(C_LEVELS)) \
        and tuple(sorted(set(c["variant"] for c in cells))) == tuple(sorted(BASE_VARIANTS))
    checks.append(make_check("H2", "扫描完备性（27 格 × 2 口径，顺序固定，决策区手写表）", ok2,
                              "%d 格（期望 27）× 2 口径 ｜ 顺序固定 %s ｜ 集合与 SPEC 相同 %s ｜ "
                              "决策区分配 %s（期望 %s，%s）"
                              % (len(cells), got == want, same_set,
                                 got_alloc, want_alloc, dec_ok)))

    # ---- H3：单源读法跨水平（运算 ①）----
    s1 = [r for r in rows if r["id"] == "S1"][0]
    s2 = [r for r in rows if r["id"] == "S2"][0]
    h3_bad = [it for it in s1["items"] + s2["items"] if not it["ok"]]
    h3_detail = "轨迹级 " + ", ".join("%.2f(%+.4f)" % (it["level"], it["bound"])
                                      for it in s1["items"])
    h3_detail += " ｜ 块级 " + ", ".join("%.2f(%+.4f)" % (it["level"], it["bound"])
                                        for it in s2["items"])
    if h3_bad:
        h3_detail += " ｜ **违例**：" + ", ".join("%.2f(%+.4f)" % (it["level"], it["bound"])
                                                 for it in h3_bad)
    checks.append(make_check("H3", "单源读法跨水平（污染只抬高·运算①）", not h3_bad,
                              h3_detail))

    # ---- H4：点估计读法跨水平（运算 ②）----
    s3 = [r for r in rows if r["id"] == "S3"][0]
    s4 = [r for r in rows if r["id"] == "S4"][0]
    h4_bad = [it for it in s3["items"] + s4["items"] if not it["ok"]]
    h4_detail = "轨迹级 %d/%d 成立 ｜ 块级 %d/%d 成立" % (
        len(s3["items"]) - len([it for it in s3["items"] if not it["ok"]]), len(s3["items"]),
        len(s4["items"]) - len([it for it in s4["items"] if not it["ok"]]), len(s4["items"]))
    if h4_bad:
        h4_detail += " ｜ **违例**：" + ", ".join(
            "%s/%.2f/%s(%+.4f)" % ("blk" if it in s4["items"] else "traj",
                                   it["level_c"], it["variant"], it["bound"])
            for it in h4_bad)
    checks.append(make_check("H4", "点估计读法跨水平（运算②）", not h4_bad, h4_detail))

    # ---- H5：保守读法 · 决策区（联合 ≥ 90%）----
    dec = [c for c in cells if c["in_decision"]]
    dec_bad = [c for c in dec if not c["traj_ok"]]
    h5_detail = "决策区 %d 格（联合 ≥ %.0f%%）｜ %d 成立" % (
        len(dec), 100 * JOINT_FLOOR, len(dec) - len(dec_bad))
    if dec_bad:
        h5_detail += " ｜ **违例**：" + ", ".join(
            "CI%.0f/污染%.0f/%s(%+.4f, 联合 %.0f%%)"
            % (c["level_ci"] * 100, c["level_c"] * 100, c["variant"], c["traj"],
               100 * c["conf"]) for c in dec_bad)
    checks.append(make_check("H5", "保守读法·决策区（联合 ≥ 90%·运算③）", not dec_bad,
                              h5_detail))

    # ---- H6：保守读法 · 全 27 格 ----
    all_bad = [c for c in cells if not c["traj_ok"]]
    h6_detail = "%d/%d 格成立" % (len(cells) - len(all_bad), len(cells))
    if all_bad:
        h6_detail += " ｜ **违例**：" + ", ".join(
            "CI%.0f/污染%.0f/%s(%+.4f, 联合 %.0f%%)"
            % (c["level_ci"] * 100, c["level_c"] * 100, c["variant"], c["traj"],
               100 * c["conf"]) for c in all_bad)
    checks.append(make_check("H6", "保守读法·全 27 格（运算③）", not all_bad, h6_detail))

    # ---- H7：量纲硬门（自证）----
    g_ok, g_msg, _code = guard_selftest()
    checks.append(make_check("H7", "量纲硬门（未登记的 kind 配对必须被红）", g_ok, g_msg))

    # ---- H8：只读 + 出处 ----
    md5_ok = md5_unchanged(ledger_path, inp["raw_md5"])
    sec_lo, sec_hi = inp["section_range"]
    out_of_range = sorted(k for k, v in inp["anchor_lines"].items()
                           if not (sec_lo <= v <= sec_hi))
    rebuilds = [
        ("改判（w）", "%d/%d" % (inp["w_num"], inp["w_den"])),
        ("改判（rand）", "%d/%d" % (inp["r_num"], inp["r_den"])),
        ("Δ_obs(traj)", "%+.2f" % inp["d_traj_printed"]),
        ("Wilson95(w)", "[%+.2f, %+.2f]" % (inp["w_wil_lo"], inp["w_wil_hi"])),
        ("Wilson95(rand)", "[%+.2f, %+.2f]" % (inp["r_wil_lo"], inp["r_wil_hi"])),
        ("基准(rand)", "%.4f" % inp["r_base_printed"]),
        ("(n_nz,n_zero)（rand）", dist_text(inp["r_dist"])),
        ("基准分布（rand）", "{%s}" % ", ".join("%g×%d" % (v, c)
                                                for v, c in inp["r_base_dist"])),
        ("CI_lo(traj)", "[%+.2f, %+.2f]" % (inp["nc_traj_lo_printed"], inp["nc_traj_hi_printed"])),
        ("Δ_obs(blk)", "%+.2f" % inp["d_blk_printed"]),
        ("CI_lo(blk)", "[%+.2f, %+.2f]" % (inp["nc_blk_lo_printed"], inp["nc_blk_hi_printed"])),
    ]
    missing = [name for name, s in rebuilds if s not in inp["sec_text"]]
    h8_ok = md5_ok and (not out_of_range) and (not missing)
    checks.append(make_check("H8", "只读（md5 不变 + 行号落在段内 + 重建串逐字符在段内）",
                              h8_ok,
                              "md5 %s ｜ 段范围 [%d, %d] ｜ 越界行 %s ｜ 重建串缺失 %s"
                              % ("不变" if md5_ok else "**变了**", sec_lo, sec_hi,
                                 out_of_range or "无", missing or "无")))

    # ---- H9：跨轮锚一致性（对 244.88）----
    if prev is None:
        checks.append(make_check("H9", "跨轮锚一致性（对 244.88）", False,
                                  "⛔ 244.88 的锚点读不到（%s）⇒ ⇒ 中止" % prev_err))
    else:
        old_ci_input = prev["r1"]
        new_ci_lo = q["ci_traj"][MAIN_CI_LEVEL]["lo"]["value"]
        shift = new_ci_lo - old_ci_input
        h9_detail = []
        h9_bad = []
        for (lv_c, var), ref in sorted(prev["cells"].items(), key=lambda kv: (kv[0][0], kv[0][1])):
            mine = [c for c in cells if c["level_ci"] == MAIN_CI_LEVEL
                    and c["level_c"] == lv_c and c["variant"] == var]
            if len(mine) != 1:
                h9_bad.append("CI95/%.0f/%s：本格缺失" % (lv_c * 100, var))
                continue
            mine = mine[0]
            old = ref["value"]
            resid = (mine["traj"] - old) - shift
            same_flag = (mine["traj_ok"] == (old > 0))
            if abs(resid) > RESID_TOL or not same_flag:
                h9_bad.append("CI95/%.0f/%s：残差 %.6f / 标志 %s"
                              % (lv_c * 100, var, resid, "同" if same_flag else "**不同**"))
            h9_detail.append("%.0f/%s：新 %+.4f vs 旧 %+.4f（差 %+.4f；CI 输入偏移 %+.4f；残差 %+.6f）"
                             % (lv_c * 100, var, mine["traj"], old, mine["traj"] - old,
                                shift, resid))
        # 244.88 的 R3 最紧值 / R6 最小值 / R1 / R2
        s3 = [r for r in rows if r["id"] == "S3"][0]
        s3_tight = min(it["bound"] for it in s3["items"])
        s4 = [r for r in rows if r["id"] == "S4"][0]
        blk_dec = [c for c in cells if c["level_ci"] == MAIN_CI_LEVEL]
        blk_min_slice = min(c["blk"] for c in blk_dec)
        r1_new = q["ci_traj"][MAIN_CI_LEVEL]["lo"]["value"]
        r2_new = q["ci_blk"][MAIN_CI_LEVEL]["lo"]["value"]
        for label, new, old in (("R3 最紧", s3_tight, prev["r3_tight"]),
                                ("R6 最小(L_CI=95 切片)", blk_min_slice, prev["r6_min"]),
                                ("R1", r1_new, prev["r1"]),
                                ("R2", r2_new, prev["r2"])):
            tol = tol_from_printed("%+.2f" % old)
            ok = abs(new - old) <= tol
            if not ok:
                h9_bad.append("%s：新 %+.4f vs 旧 %+.2f（容差 %.4f）" % (label, new, old, tol))
            h9_detail.append("%s：新 %+.4f vs 旧 %+.2f（容差 %.4f，%s）"
                             % (label, new, old, tol, "对得上" if ok else "**对不上**"))
        checks.append(make_check("H9", "跨轮锚一致性（对 244.88）", not h9_bad,
                                  " ｜ ".join(h9_detail) + (" ｜ **违例**：" + "，".join(h9_bad)
                                                            if h9_bad else "")))

    flags = dict((c["id"], c["ok"]) for c in checks)
    form = classify(flags)
    reason = build_reason(form, checks, flags, cells, rows)
    return form, checks, reason, flags


def build_reason(form, checks, flags, cells, rows):
    """⚖ 形态的**理由句**（⛔ 不许只在形式上给个字母）。"""
    def flag(cid):
        return flags.get(cid, True)

    dec = [c for c in cells if c["in_decision"]]
    dec_hold = len([c for c in dec if c["traj_ok"]])
    all_hold = len([c for c in cells if c["traj_ok"]])
    s1 = [r for r in rows if r["id"] == "S1"][0]
    s3 = [r for r in rows if r["id"] == "S3"][0]

    if form == FORM_E:
        red = [cid for cid in HARD_FAIL_IDS if not flag(cid)]
        return "硬失败（%s 红）⇒ ⇒ **前提层面**失败 ⇒ ⇒ 本轮不出判决" % "、".join(red)
    if form == FORM_D:
        return "单源读法（污染只抬高）被否 ⇒ ⇒ 连**不依赖 c**的差区间下端点在某个水平上都 ≤ 0"
    if form == FORM_C:
        return "点估计口径被否 ⇒ ⇒ 「对口径稳健」不成立"
    if form == FORM_B:
        bad = [c for c in cells if not c["traj_ok"]]
        bad_dec = [c for c in bad if c["in_decision"]]
        viol = ", ".join("CI%.0f/污染%.0f/%s(%+.4f, 联合 %.0f%%)"
                         % (c["level_ci"] * 100, c["level_c"] * 100, c["variant"], c["traj"],
                            100 * c["conf"]) for c in bad)
        return ("保守读法在 %d/%d 格有破口（**决策区内 %d 个**）⇒ ⇒ **结论要收紧**："
                "「污染解释不了观测差」在**污染只抬高**的读法下成立（跨水平 %d/3，"
                "最紧 %+.4f pp），在**点估计**口径下成立（%d/%d，最紧 %+.4f pp）；"
                "在**抽样噪声与污染幅度同时最保守**的读法下**只在部分水平/基准组合成立**"
                "（决策区 %d/%d 格成立）。破口：%s"
                % (len(bad), len(cells), len(bad_dec),
                   len([it for it in s1["items"] if it["ok"]]),
                   min(it["bound"] for it in s1["items"]),
                   len([it for it in s3["items"] if it["ok"]]), len(s3["items"]),
                   min(it["bound"] for it in s3["items"]),
                   dec_hold, len(dec), viol))
    return ("全绿：保守读法在全部 %d 格（%d 个水平组合 × %d 个基准）下成立"
            "（决策区 %d/%d 格成立，最紧 %+.4f pp）"
            % (len(cells), len(CI_LEVELS) * len(C_LEVELS), len(BASE_VARIANTS),
               dec_hold, len(dec), min(c["traj"] for c in cells)))


# =============================================================================
# Phase-0 自检（合成夹具、⛔ 零账本、⛔ 零 GPU）
# =============================================================================

def tmp_root():
    env = os.environ.get("R24489_TMPDIR")
    if env:
        os.makedirs(env, exist_ok=True)
        return env
    d = os.path.join(tempfile.gettempdir(), "r24489_%d" % os.getpid())
    os.makedirs(d, exist_ok=True)
    return d


def fixture_text(w_num=46, w_den=56, r_num=29, r_den=56,
                 w_dist="{(2,0)×1, (3,0)×55}", r_dist="{(2,1)×2, (3,0)×54}",
                 w_base_ms="{0.25×1, 0.5×55}", r_base_ms="{0.25×2, 0.5×54}",
                 w_wil="[+70.16, +90.00]", r_wil="[+39.01, +64.33]",
                 w_base="0.4955", r_base="0.4911",
                 d_traj="+30.36", nc_lo="+13.01", nc_hi="+45.36",
                 blk_w=21, blk_den=28, blk_r=6, blk_d="+53.57",
                 blk_lo="+27.79", blk_hi="+70.23",
                 drop_row=None, drop_prev=False):
    """⚖ **合成账本片段**（格式逐字照抄真账本 244.81 / 244.88 段的锚点行）。"""
    L = []
    L.append("# 合成夹具账本（244.89 Phase-0 用；⛔ 不是真账本、⛔ 零 GPU）")
    L.append("")
    L.append("## 修订 244.81 —— （合成）固定剂量下的判决数")
    L.append("")
    if drop_row != "i1":
        L.append("| 改判（主口径：逐轨迹**严格多数**，`nT·2 > m`） | **%d/%d** | **%d/%d** |"
                 % (w_num, w_den, r_num, r_den))
    if drop_row != "i2":
        L.append("| 比例区间（Wilson95） | %s | %s |" % (w_wil, r_wil))
    if drop_row != "i3":
        L.append("| 零假设基准（逐轨迹平均） | %s | %s |" % (w_base, r_base))
    L.append("")
    if drop_row != "i4":
        L.append("· (n_nz,n_zero) 分布：%s ｜ %s" % (w_dist, r_dist))
    if drop_row != "i5":
        L.append("· 基准分布：%s ｜ %s ｜ 零格合计：0 / 2" % (w_base_ms, r_base_ms))
    if drop_row != "i6":
        L.append("· **差 %s pp** ｜ 差区间（Newcombe95）[%s, %s] ｜ 跨臂 Fisher p = 0.001152。"
                 % (d_traj, nc_lo, nc_hi))
    if drop_row != "i7":
        L.append("· w **%d/%d** ｜ rand **%d/%d** ｜ 差 %s pp ｜ 差区间 [%s, %s] ｜ "
                 "Fisher p = 0.000131。" % (blk_w, blk_den, blk_r, blk_den, blk_d,
                                            blk_lo, blk_hi))
    L.append("")
    L.append("## 修订 244.88 —— （合成）保守读法与口径边界")
    L.append("")
    if not drop_prev:
        L.append("| 读法 | 口径 | 界 | 置信 | 结论 |")
        L.append("|---|---|---|---|---|")
        L.append("| **R1** 污染**只抬高** rand 臂（c ≥ 0） | 轨迹级 | **%s pp** | 95%% 单源 | ✅ 成立 |"
                 % nc_lo)
        L.append("| **R2** 同上 | 块级 | **%s pp** | 95%% 单源 | ✅ 成立 |" % blk_lo)
        L.append("| **R3** 不假定方向·**点估计** | 轨迹级 | 9/9 口径成立，最紧 **+15.69 pp** | 点估计 | ✅ 成立 |")
        L.append("| **R4** 不假定方向·点估计（⚠跨口径） | 块级 | 9/9 成立，最紧 **+38.90 pp** | 点估计 | ✅ 成立 |")
        L.append("| **R5** 不假定方向·**保守** | 轨迹级 | **7/9 成立** | 85/90/94% | ⛔ **有破口** |")
        L.append("| **R6** 同上（⚠跨口径·**示意**） | 块级 | 9/9 成立，最小 **+13.12 pp** | 85/90/94% | ⚠ 不参与形态判定 |")
        L.append("")
        L.append("| Wilson | 基准 | 界（pp） | 联合置信 | 结论 |")
        L.append("|---|---|---|---|---|")
        L.append("| 0.90 | main | **+4.8789** | 85% | ✅ 成立 |")
        L.append("| 0.90 | zero_as_half | **+3.9860** | 85% | ✅ 成立 |")
        L.append("| 0.90 | zero_as_zero | **+5.7718** | 85% | ✅ 成立 |")
        L.append("| 0.95 | main | **+2.9132** | 90% | ✅ 成立 |")
        L.append("| 0.95 | zero_as_half | **+2.0204** | 90% | ✅ 成立 |")
        L.append("| 0.95 | zero_as_zero | **+3.8061** | 90% | ✅ 成立 |")
        L.append("| 0.99 | main | **-0.7647** | 94% | ⛔ **不成立** |")
        L.append("| 0.99 | zero_as_half | **-1.6576** | 94% | ⛔ **不成立** |")
        L.append("| 0.99 | zero_as_zero | **+0.1281** | 94% | ✅ 成立 |")
    L.append("")
    L.append("## 修订 244.89 —— （合成）结束")
    L.append("")
    return "\n".join(L)


def run_fixture(path):
    """⚖ 在合成夹具上跑一遍：解析 → 扫描 → 作用域表 → 判。"""
    inp = parse_inputs(path)
    q = build_quantities(inp)
    cells = build_cells(inp, q)
    rows = build_readings(inp, q, cells)
    prev, prev_err = parse_prev_round(path)
    form, checks, reason, flags = judge(inp, q, cells, rows, path, prev, prev_err)
    return {"inp": inp, "q": q, "cells": cells, "rows": rows, "form": form,
            "checks": checks, "reason": reason, "flags": flags}


def check_by_id(result, cid):
    for c in result["checks"]:
        if c["id"] == cid:
            return c
    return None


def selftest():
    """⚖ Phase-0 自检闸门 G0-1..G0-9（合成夹具、⛔ 零账本、⛔ 零 GPU）。"""
    tmp = tmp_root()
    gates = []

    def record(gid, ok, detail):
        gates.append({"id": gid, "ok": bool(ok), "detail": detail})

    # ---- G0-1：缺锚点必须构建失败（⛔ 不许静默降级）----
    bad_rows = ["i1", "i2", "i3", "i4", "i5", "i6", "i7"]
    g1_detail = []
    g1_ok = True
    for row in bad_rows:
        p = os.path.join(tmp, "miss_%s.md" % row)
        with io.open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(fixture_text(drop_row=row))
        try:
            run_fixture(p)
            g1_ok = False
            g1_detail.append("缺 %s ⇒ **没有**构建失败" % row)
        except SystemExit:
            g1_detail.append("缺 %s ⇒ 构建失败 ✅" % row)
    record("G0-1", g1_ok, "缺锚点必须构建失败：" + "，".join(g1_detail))

    # ---- G0-2：形态级联互斥且穷尽 ----
    # ⚖⚖⚖⚖⚖ **期望的硬失败集合必须「手写」**（⛔ 不许用模块常量 HARD_FAIL_IDS 派生）
    #   ⇒ ⇒ 否则「把 HARD_FAIL_IDS 改掉」这种变异**两边一起变** ⇒ ⇒ 恒绿 ⇒ ⇒ 抓不到
    #   （244.88 的第 ② 条缺陷：**期望从模块常量派生** ⇒ ⇒ 本轮从一开始就手写）
    HARD_FAIL_EXPECTED = ("H1", "H2", "H7", "H8", "H9")
    g2_ok = tuple(HARD_FAIL_IDS) == HARD_FAIL_EXPECTED
    g2_detail = []
    if not g2_ok:
        g2_detail.append("硬失败集合：模块常量 %s ≠ 手写的 %s"
                         % (sorted(HARD_FAIL_IDS), sorted(HARD_FAIL_EXPECTED)))
    seen = {}
    n_combo = 0
    for mask in range(1 << len(CRIT_IDS)):
        flags = dict((cid, bool(mask & (1 << i))) for i, cid in enumerate(CRIT_IDS))
        got = classify(flags)
        n_combo += 1
        if got not in FORMS:
            g2_ok = False
            g2_detail.append("组合 %d 落空" % mask)
        # 独立的级联实现（手写）⇒ ⇒ 用来核对被检实现
        want = None
        if any(not flags[c] for c in HARD_FAIL_EXPECTED):
            want = FORM_E
        elif not flags["H3"]:
            want = FORM_D
        elif not flags["H4"]:
            want = FORM_C
        elif (not flags["H5"]) or (not flags["H6"]):
            want = FORM_B
        else:
            want = FORM_A
        if got != want:
            g2_ok = False
            g2_detail.append("组合 %d ⇒ %s（手写级联说 %s）" % (mask, got, want))
        seen[got] = seen.get(got, 0) + 1
    if len(seen) != len(FORMS):
        g2_ok = False
        g2_detail.append("形态覆盖不全：%s" % sorted(seen.keys()))
    record("G0-2", g2_ok,
           "穷举 %d 个布尔组合 ⇒ 每个只落一个形态 ｜ 各形态命中数 %s ｜ 硬失败集合（手写）%s%s"
           % (n_combo, sorted(seen.items()), sorted(HARD_FAIL_EXPECTED),
              "" if g2_ok else " ｜ " + "；".join(g2_detail)))

    # ---- G0-3：H7 的每条分支都能红（且必须由对应分支判红）----
    g3_ok, g3_msg, _code = guard_selftest()
    record("G0-3", g3_ok, g3_msg)

    # ---- G0-4：容差由打印精度推导 ----
    g4_cases = [("+30.36", 0.005), ("+15.69", 0.005), ("+2.9132", 0.00005),
                ("+13.0072", 0.00005), ("0.4911", 0.00005)]
    g4_ok = all(abs(tol_from_printed(t) - v) < 1e-12 for t, v in g4_cases)
    record("G0-4", g4_ok, " ｜ ".join("%s ⇒ %.5f" % (t, tol_from_printed(t))
                                      for t, _v in g4_cases))

    # ---- G0-5：三种运算的公式与手算一致（正控）----
    p = os.path.join(tmp, "ok.md")
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(fixture_text())
    res = run_fixture(p)
    q = res["q"]
    s1 = [r for r in res["rows"] if r["id"] == "S1"][0]
    s3 = [r for r in res["rows"] if r["id"] == "S3"][0]
    cell_main = [c for c in res["cells"]
                 if c["level_ci"] == MAIN_CI_LEVEL and c["level_c"] == MAIN_C_LEVEL
                 and c["variant"] == "main"][0]
    ci_lo = q["ci_traj"][MAIN_CI_LEVEL]["lo"]["value"]
    c_lo = q["c_span"]["main"][MAIN_C_LEVEL][0]
    d_traj = q["d_traj"]["value"]
    # ① 保守格 = CI_lo + c_lo（逐位）；② 点估计格 = Δ_obs + c_lo（逐位）；③ 单源格 = CI_lo（逐位）
    g5_a = abs(cell_main["traj"] - (ci_lo + c_lo)) < 1e-12
    g5_b = abs(s3["items"][0]["bound"] - (d_traj + q["c_span"]["main"][C_LEVELS[0]][0])) < 1e-12
    # ⚠ 单源格必须与**它自己那一档**的 CI_lo 比（⛔ 拿 0.90 的格去比 0.95 的 CI ⇒ ⇒ 假红）
    lv_s1 = s1["items"][0]["level"]
    g5_c = abs(s1["items"][0]["bound"] - q["ci_traj"][lv_s1]["lo"]["value"]) < 1e-12
    # ④ 方法复现账本印的 Newcombe95（容差 = 打印精度的半个单位）
    g5_d = abs(ci_lo - res["inp"]["nc_traj_lo_printed"]) <= tol_from_printed(
        "%+.2f" % res["inp"]["nc_traj_lo_printed"])
    # ⑤ **结构单调性**：水平越宽 ⇒ 下端点越低（Wilson 与 Newcombe 都该如此）
    #    ⚠ 一律用 SPEC 里的档位（⛔ 不写死 0.90/0.95/0.99 ⇒ ⇒ 改档位时自检不该崩）
    g5_e = (q["ci_traj"][CI_LEVELS[0]]["lo"]["value"]
            >= q["ci_traj"][MAIN_CI_LEVEL]["lo"]["value"]
            >= q["ci_traj"][CI_LEVELS[-1]]["lo"]["value"])
    g5_f = (q["c_span"]["main"][C_LEVELS[0]][0] >= q["c_span"]["main"][MAIN_C_LEVEL][0]
            >= q["c_span"]["main"][C_LEVELS[-1]][0])
    g5_ok = all([g5_a, g5_b, g5_c, g5_d, g5_e, g5_f])
    record("G0-5", g5_ok,
           "① 保守格 = CI_lo(%+.4f) + c_lo(%+.4f) = %+.4f（逐位 %s）｜ ② 点估计格 = Δ_obs + c_lo（逐位 %s）｜ "
           "③ 单源格 = CI_lo（逐位 %s）｜ ④ 现算 Newcombe95 下端 %+.4f vs 账本印 +13.01（%s）｜ "
           "⑤ 水平越宽下端点越低：CI %s / c %s"
           % (ci_lo, c_lo, ci_lo + c_lo, g5_a, g5_b, g5_c, ci_lo, g5_d, g5_e, g5_f))

    # ---- G0-6：负控 ①（c_lo 换成很负的值 ⇒ H4/H5/H6 必须红）＋ 负控 ②（c_lo < c_hi）----
    q2 = build_quantities(res["inp"])
    for var in BASE_VARIANTS:
        for lv in C_LEVELS:
            q2["c_span"][var][lv] = (-100.0, -99.0)
    cells2 = build_cells(res["inp"], q2)
    rows2 = build_readings(res["inp"], q2, cells2)
    prev2, _e = parse_prev_round(p)
    _f, checks2, _r, _fl = judge(res["inp"], q2, cells2, rows2, p, prev2, _e)
    g6 = dict((c["id"], c["ok"]) for c in checks2)
    g6_ok = (not g6["H4"]) and (not g6["H5"]) and (not g6["H6"])
    order_ok = all(c["c_lo"] < c["c_hi"] for c in res["cells"])
    record("G0-6", g6_ok and order_ok,
           "把 c_lo 换成 −100 pp ⇒ H4=%s H5=%s H6=%s（必须都是 False）｜ 每行 c_lo < c_hi：%s"
           % (g6["H4"], g6["H5"], g6["H6"], order_ok))

    # ---- G0-7：账本负控（正控与负控共用同一个函数）----
    #   ⚠⚖⚖ **为什么负控必须「在判定的间隙」改账本**：H8 的 md5 判断是「**运行前** vs **运行后**」
    #   ⇒ ⇒ 若在**运行之前**就改掉账本 ⇒ ⇒ 两次 md5 读到的都是改过之后的那份 ⇒ ⇒ **看不见**
    #   ⇒ ⇒ 负控必须**先解析、再改、再判定** ⇒ ⇒ 那才是「只读」这条闸门真正的失效模式。
    #   ① **H8 的 md5 负控**：解析后改**行文里的一个字节**（⛔ 不动任何被解析的锚点）
    #      ⇒ ⇒ H8 只可能靠 **md5** 变红 ⇒ ⇒ 这一条**真正在测「只读」这条闸门**；
    #   ② **md5 判断函数本身**的正控/负控（**同一个函数** ⇒ ⇒ 改成恒真 ⇒ ⇒ 两个控件同时失效）；
    #   ③ **解析链负控**：改账本印的一个数 ⇒ ⇒ H1 必须红。
    p7 = os.path.join(tmp, "tamper.md")
    base_text = fixture_text()
    with io.open(p7, "w", encoding="utf-8", newline="") as fh:
        fh.write(base_text)
    ok7 = run_fixture(p7)
    c1_before = check_by_id(ok7, "H1")["ok"]
    c8_before = check_by_id(ok7, "H8")["ok"]
    tampered = base_text.replace("（244.89 Phase-0 用；⛔ 不是真账本、⛔ 零 GPU）",
                                 "（244.89 Phase-0 用；⛔ 不是真账本、⛔ 零 GPU ）")
    if tampered == base_text:
        record("G0-7", False, "⛔ md5 负控的落点没找到 ⇒ ⇒ 负控形同虚设")
    else:
        # ① H8 的 md5 负控：先解析（记下 md5）⇒ ⇒ 再改一个字节 ⇒ ⇒ 再判定
        inp8 = parse_inputs(p7)
        q8 = build_quantities(inp8)
        cells8 = build_cells(inp8, q8)
        rows8 = build_readings(inp8, q8, cells8)
        prev8, err8 = parse_prev_round(p7)
        with io.open(p7, "w", encoding="utf-8", newline="") as fh:
            fh.write(tampered)
        try:
            _f, checks8, _r, _fl = judge(inp8, q8, cells8, rows8, p7, prev8, err8)
            h8_after = [c["ok"] for c in checks8 if c["id"] == "H8"][0]
        except SystemExit:
            h8_after = False
        # ② md5 判断函数本身的正控/负控（**同一个函数** ⇒ ⇒ 改成恒真 ⇒ ⇒ 两个控件同时失效）
        md5_before = md5_file(p7)
        pos_ok = md5_unchanged(p7, md5_before)
        with io.open(p7, "w", encoding="utf-8", newline="") as fh:
            fh.write(base_text)
        neg_ok = md5_unchanged(p7, md5_before)
        # ③ 解析链负控：改账本印的一个数 ⇒ ⇒ H1 必须红
        with io.open(p7, "w", encoding="utf-8", newline="") as fh:
            fh.write(fixture_text(r_base="0.4999"))
        try:
            bad7b = run_fixture(p7)
            c1_after = check_by_id(bad7b, "H1")["ok"]
        except SystemExit:
            c1_after = False
        g7_ok = (c1_before and c8_before and (not h8_after)
                 and pos_ok and (not neg_ok) and (not c1_after))
        record("G0-7", g7_ok,
               "改动账本前：H1=%s H8=%s ｜ ① 间隙负控（解析后改行文一个字节）后：H8=%s"
               "（必须被检出）｜ ② md5 判断函数：正控=%s 负控=%s（必须 True/False）｜ "
               "③ 解析链负控（改账本印的基准）后：H1=%s（必须被检出）"
               % (c1_before, c8_before, h8_after, pos_ok, neg_ok, c1_after))

    # ---- G0-8：幂等 ----
    p8 = os.path.join(tmp, "idem.md")
    with io.open(p8, "w", encoding="utf-8", newline="") as fh:
        fh.write(fixture_text())
    r8a = run_fixture(p8)
    r8b = run_fixture(p8)
    sig_a = (r8a["form"], tuple((c["id"], c["ok"], c["detail"]) for c in r8a["checks"]))
    sig_b = (r8b["form"], tuple((c["id"], c["ok"], c["detail"]) for c in r8b["checks"]))
    record("G0-8", sig_a == sig_b, "同一输入跑两次 ⇒ 输出逐条相同：%s" % (sig_a == sig_b))

    # ---- G0-9：H1..H9 每条都能红（期望红的 id 是**手写**的）----
    g9_ok = True
    g9_detail = []
    # 逐条注入（只动**被检对象**，不动闸门自己的比较表达式）
    plan = [
        ("H1", "把账本印的 Δ_obs 改掉"),
        ("H2", "删掉一格"),
        ("H3", "把单源下端点改成负数"),
        ("H4", "把 c_lo 改成很负的值"),
        ("H5", "把决策区里的一格改成负数"),
        ("H6", "把决策区外的一格改成负数"),
        ("H7", "放宽 H7 的允许加法表"),
        ("H8", "把重建串改成不存在的样子"),
        ("H9", "把 244.88 的锚点改成对不上"),
    ]
    for cid, how in plan:
        reds = forced_red_ids(cid, tmp)
        if cid not in reds:
            g9_ok = False
            g9_detail.append("%s（%s）**逼不红** ⇒ ⇒ 实际红的是 %s" % (cid, how, reds))
        else:
            g9_detail.append("%s ✅" % cid)
    record("G0-9", g9_ok,
           "H1..H9 每条都能红（逐条注入）：" + ("，" .join(g9_detail) if g9_ok
                                              else "；".join(g9_detail)))

    print("──── Phase-0 自检（合成夹具；⛔ 零账本、⛔ 零 GPU）────")
    n_fail = 0
    for g in gates:
        if not g["ok"]:
            n_fail += 1
        print("[%s] %s — %s" % ("PASS" if g["ok"] else "FAIL", g["id"], g["detail"]))
    # ⚖ 闸门清单必须与模块常量**逐条相同**（⛔ 不许实现里多写/少写一条闸门）
    if [g["id"] for g in gates] != list(GATE_IDS):
        print("[FAIL] 闸门清单 与 GATE_IDS 不一致：实际 %s ｜ 常量 %s"
              % ([g["id"] for g in gates], list(GATE_IDS)))
        n_fail += 1
    print("自检：%d 道 ｜ FAIL %d 道" % (len(gates), n_fail))
    print("SELFTEST_RC=%d" % (0 if n_fail == 0 else 1))
    return 0 if n_fail == 0 else 1


def forced_red_ids(target, tmp):
    """⚖ **G0-9 的注入器**：逐条把某条判据逼红 ⇒ ⇒ 返回实际红的 id 集合。

    ⚖ 只注入**被检对象**（输入 / 网格 / 前一轮锚点 / 护栏的自证结果），
       ⛔ 不动闸门自己的比较表达式（那是自检层的固有上限，预登记 §7 的 B-7）。
    """
    p = os.path.join(tmp, "g9.md")
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(fixture_text())
    res = run_fixture(p)
    inp, q, cells, rows = res["inp"], res["q"], res["cells"], res["rows"]
    prev, prev_err = parse_prev_round(p)
    inp2 = inp
    cells2 = cells
    rows2 = rows

    if target == "H1":
        inp2 = dict(inp)
        inp2["d_traj_printed"] = inp["d_traj_printed"] + 1.0
    elif target == "H2":
        cells2 = cells[:-1]
    elif target == "H3":
        for lv in CI_LEVELS:
            q["ci_traj"][lv]["lo"]["value"] = -1.0
            q["ci_blk"][lv]["lo"]["value"] = -1.0
        cells2 = build_cells(inp, q)
        rows2 = build_readings(inp, q, cells2)
    elif target == "H4":
        for var in BASE_VARIANTS:
            for lv in C_LEVELS:
                q["c_span"][var][lv] = (-100.0, -99.0)
        cells2 = build_cells(inp, q)
        rows2 = build_readings(inp, q, cells2)
    elif target == "H5":
        cells2 = [dict(c) for c in cells]
        for c in cells2:
            if c["in_decision"]:
                c["traj"] = -1.0
                c["traj_ok"] = False
                break
    elif target == "H6":
        cells2 = [dict(c) for c in cells]
        for c in cells2:
            if not c["in_decision"]:
                c["traj"] = -1.0
                c["traj_ok"] = False
                break
    elif target == "H7":
        # ⚖ 注入「护栏的分支代号取不到」⇒ ⇒ 护栏自证必须发现「分支对不上」
        saved = globals()["guard_code"]
        try:
            globals()["guard_code"] = lambda msg: "(无代号)"
            _f, checks, _r, _fl = judge(inp, q, cells, rows, p, prev, prev_err)
        finally:
            globals()["guard_code"] = saved
        return set(c["id"] for c in checks if not c["ok"])
    elif target == "H8":
        inp2 = dict(inp)
        inp2["sec_text"] = inp["sec_text"].replace("%d/%d" % (inp["w_num"], inp["w_den"]),
                                                  "%d/%d" % (inp["w_num"], inp["w_den"] + 1))
        cells2 = cells
    elif target == "H9":
        prev2 = {"cells": dict((k, dict(v)) for k, v in prev["cells"].items()),
                 "r1": prev["r1"], "r2": prev["r2"], "r3_tight": prev["r3_tight"],
                 "r6_min": prev["r6_min"], "section_range": prev["section_range"]}
        for k in prev2["cells"]:
            prev2["cells"][k]["value"] = prev2["cells"][k]["value"] + 1.0
        prev = prev2
    else:
        return []

    _f, checks, _r, _fl = judge(inp2, q, cells2, rows2, p, prev, prev_err)
    return set(c["id"] for c in checks if not c["ok"])


# =============================================================================
# 真数据运行
# =============================================================================

def default_ledger():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))
    return os.path.join(root, ".cache", "xcheck", "R6_RERUN_PREREG.md")


def render(inp, q, cells, rows, checks, form, reason):
    """⚖ 把结果渲染成**给人看**的面板（收据里逐字可核）。"""
    out = []
    out.append("──── 口径与基准 ────")
    out.append("  轨迹级 Δ_obs = %+.4f pp ｜ 块级 Δ_obs = %+.4f pp"
               % (q["d_traj"]["value"], q["d_blk"]["value"]))
    for var in BASE_VARIANTS:
        out.append("  基准 %-13s = %.10f" % (var, q["base"][var]))
    out.append("")
    out.append("──── Newcombe 方法 10（本轮新算）────")
    for lv in CI_LEVELS:
        out.append("  CI %.2f  轨迹级 [%+.4f, %+.4f] pp ｜ 块级 [%+.4f, %+.4f] pp"
                   % (lv, q["ci_traj"][lv]["lo"]["value"], q["ci_traj"][lv]["hi"]["value"],
                      q["ci_blk"][lv]["lo"]["value"], q["ci_blk"][lv]["hi"]["value"]))
    out.append("")
    out.append("──── 污染量 c 的区间（Wilson；随水平变宽）────")
    for lv in C_LEVELS:
        for var in BASE_VARIANTS:
            lo, hi = q["c_span"][var][lv]
            out.append("  %.2f / %-13s c ∈ [%+.4f, %+.4f] pp" % (lv, var, lo, hi))
    out.append("")
    out.append("──── 主表：决策区（联合置信 ≥ %.0f%%）────" % (100 * JOINT_FLOOR))
    dec = [c for c in cells if c["in_decision"]]
    for c in dec:
        out.append("  CI%.2f / 污染%.2f / %-13s 界=%+.4f pp ｜ 联合 %.0f%% ｜ %s"
                   % (c["level_ci"], c["level_c"], c["variant"], c["traj"],
                      100 * c["conf"], "成立" if c["traj_ok"] else "**不成立**"))
    out.append("  ⇒ 决策区 %d/%d 格成立" % (len([c for c in dec if c["traj_ok"]]), len(dec)))
    out.append("")
    out.append("──── 副表：全 27 格（完整作用域）────")
    for c in cells:
        out.append("  CI%.2f / 污染%.2f / %-13s 界=%+.4f pp ｜ 联合 %.0f%% ｜ %s%s"
                   % (c["level_ci"], c["level_c"], c["variant"], c["traj"],
                      100 * c["conf"], "成立" if c["traj_ok"] else "**不成立**",
                      " ｜ 决策区" if c["in_decision"] else ""))
    out.append("  ⇒ 全表 %d/%d 格成立" % (len([c for c in cells if c["traj_ok"]]), len(cells)))
    out.append("")
    out.append("──── 读法—作用域表 ────")
    for r in rows:
        out.append("  %s  %s" % (r["id"], r["name"]))
        for it in r["items"]:
            if "level" in it and "variant" not in it:
                out.append("      %.2f  界=%+.4f pp ⇒ %s"
                           % (it["level"], it["bound"], "成立" if it["ok"] else "**不成立**"))
            elif "level_c" in it:
                out.append("      污染%.2f / %-13s 界=%+.4f pp ⇒ %s"
                           % (it["level_c"], it["variant"], it["bound"],
                              "成立" if it["ok"] else "**不成立**"))
            else:
                out.append("      CI%.2f / 污染%.2f / %-13s 界=%+.4f pp ｜ 联合 %.0f%% ⇒ %s"
                           % (it["level_ci"], it["level_c"], it["variant"], it["bound"],
                              100 * it["conf"], "成立" if it["ok"] else "**不成立**"))
    out.append("")
    out.append("──── 判据 ────")
    for c in checks:
        out.append("[%s] %s %s — %s" % ("PASS" if c["ok"] else "FAIL", c["id"],
                                        c["name"], c["detail"]))
    out.append("")
    out.append("VERDICT=%s" % form)
    out.append("理由：%s" % reason)
    return "\n".join(out)


def run_real(ledger_path):
    """⚖ 真数据运行（只读账本；⛔ 零 GPU、⛔ 不写账本）。"""
    inp = parse_inputs(ledger_path)
    q = build_quantities(inp)
    cells = build_cells(inp, q)
    rows = build_readings(inp, q, cells)
    prev, prev_err = parse_prev_round(ledger_path)
    form, checks, reason, flags = judge(inp, q, cells, rows, ledger_path, prev, prev_err)
    print(render(inp, q, cells, rows, checks, form, reason))
    print("")
    print("===== AUDIT_KEYS =====")
    print("VERDICT=%s" % form)
    print("N_CELLS=%d" % len(cells))
    print("N_DECISION=%d" % len([c for c in cells if c["in_decision"]]))
    print("N_DECISION_HOLD=%d" % len([c for c in cells if c["in_decision"] and c["traj_ok"]]))
    print("N_ALL_HOLD=%d" % len([c for c in cells if c["traj_ok"]]))
    for lv in CI_LEVELS:
        print("CI_LO_TRAJ_%d=%+.6f" % (int(round(lv * 100)),
                                        q["ci_traj"][lv]["lo"]["value"]))
    for lv in CI_LEVELS:
        print("CI_LO_BLK_%d=%+.6f" % (int(round(lv * 100)),
                                      q["ci_blk"][lv]["lo"]["value"]))
    print("BASE_MAIN_R=%.10f" % q["base"]["main"])
    for lv in C_LEVELS:
        print("CLO_%d_MAIN=%+.6f" % (int(round(lv * 100)),
                                     q["c_span"]["main"][lv][0]))
    print("DECISION_HOLDS=%s"
          % ",".join("CI%.0f/c%.0f/%s" % (c["level_ci"] * 100, c["level_c"] * 100,
                                          c["variant"])
                     for c in cells if c["in_decision"] and c["traj_ok"]))
    print("ALL_BREAKS=%s"
          % ",".join("CI%.0f/c%.0f/%s" % (c["level_ci"] * 100, c["level_c"] * 100,
                                          c["variant"])
                     for c in cells if not c["traj_ok"]))
    n_fail = len([c for c in checks if not c["ok"] and c["id"] in HARD_FAIL_IDS])
    return 0 if n_fail == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="244.89 保守读法换置信水平（审计实现）")
    ap.add_argument("--selftest", action="store_true", help="只跑 Phase-0 自检")
    ap.add_argument("--data", action="store_true",
                    help="跑真数据路径（默认行为；保留此开关是为了与台架的调用形状一致）")
    ap.add_argument("--ledger", default=None, help="权威账本路径")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    ledger = args.ledger or default_ledger()
    return run_real(ledger)


if __name__ == "__main__":
    sys.exit(main())
