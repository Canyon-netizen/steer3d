#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.87「c_max 的口径稳健性」的实现**（口径真相源 = 244.87 预登记）。

⚖⚖⚖ **这一轮要回答什么**
   244.86 给的 **c_max = +15.22 pp**（污染最多能把 rand 臂抬高多少）是一个**数**、不是**一个区**
   ⇒ ⇒ 它由「rand 改判率的 Wilson **上界**」减「零假设基准」得到
   ⇒ ⇒ 两个输入的**口径**都会动它 ⇒ ⇒ 「**污染解释不了观测差**」这条结论**对口径敏不敏感**？

⚖⚖⚖ **三个量必须分清（244.86 第 6/7 条的教训 ⇒ 见预登记 N6/N7）**
   ① `c`        = rand 改判率 − 零假设基准（**污染量**）
   ② `c_max`    = **c 的上界**            （kind = ``c_upper``）
   ③ `Δ_obs`    = w − rand（**观测差**）   （kind = ``delta_obs``）
   ④ 真实差      = Δ_obs + c
   ⛔ **Newcombe95 / 块级 bootstrap 的下端点**是「w − rand 的差」的区间下端点
      （kind = ``delta_ci_lo``）⇒ ⇒ **不是** Δ_obs、**不是**真实差
      ⇒ ⇒ **不许**拿它去比 `c_max` ⇒ ⇒ 否则会得出「+15.22 翻越 +13.01」的**假警报**
      ⇒ ⇒ 本实现用 **H5 量纲自检**专门拦这个（见 `_check_kind`）

⚖ **代码里不写死任何一个「原始数」** ⇒ ⇒ I1–I9 全部从账本 **244.81 段**逐行解析
   ⇒ ⇒ 且必须与该段**印出来的值逐位对上**（半 A 解析 vs 半 B 账本印的）⇒ ⇒ 改账本 ⇒ 必须红
⚖ **SPEC 常量**（Wilson 置信水平、基准变体）**是口径参数、不是原始数** ⇒ ⇒ 写死在这里
   ⇒ ⇒ 并由 244.87 的「预登记 ↔ 实现」对账脚本机械比对

⚖⚖⚖ **形态的优先级级联（预登记 §3.1 ＋ §0.5 更正 ②）**
   硬失败（H1 / H2 / H6 / H7 / H8 任一红）⇒ **C**
   ⇒ ⇒ 否则 H5 红 ⇒ **D**
   ⇒ ⇒ 否则 H3 / H4 红（扫描出现违例）⇒ **B**
   ⇒ ⇒ 否则 ⇒ **A**
   ⇒ ⇒ **四个形态互斥且穷尽**（Phase-0 的 G0-1 逐条验可达性）

用法：
  python3 cmax_robustness_audit.py --print-spec
  python3 cmax_robustness_audit.py --selftest
  python3 cmax_robustness_audit.py --data --ledger <账本路径>
"""

import argparse
import hashlib
import io
import math
import os
import re
import shutil
import statistics
import sys
import tempfile

# ==== SPEC（口径参数；⛔ 不是原始数；由预登记 §2 的 Q3/Q4 决定）====
# ⚠⚠⚖ **口径参数只有「置信水平」，没有「alpha」** ⇒ ⇒ alpha 是**显著性水平**，
#   与「Wilson 区间的置信水平」是**两个不同的量** ⇒ ⇒ 混用会算错（实现期真踩过）
MAIN_LEVEL = 0.95                     # 主口径：Wilson95
WILSON_LEVELS = (0.90, 0.95, 0.99)     # Q3：扫描维度 A
BASE_VARIANTS = ("main", "zero_as_half", "zero_as_zero")   # Q4：扫描维度 B（零格 base = .25/.5/.0）

# ==== 判决形态（预登记 §3.1：互斥且穷尽）====
FORM_A = "A"   # 全部口径下 c_max < Δ_obs ⇒ 「对口径稳健」
FORM_B = "B"   # 存在某口径下 c_max ≥ Δ_obs ⇒ 「对口径稳健」被否
FORM_C = "C"   # 硬失败（H1/H2/H6/H7/H8 红）⇒ 修实现/修环境 ⇒ 形态无意义
FORM_D = "D"   # H5 红 ⇒ 实现把两个量纲混比 ⇒ 硬失败
FORMS = (FORM_A, FORM_B, FORM_C, FORM_D)

# ==== 量的 kind 标签（H5 量纲自检的唯一依据）====
KIND_C_UPPER = "c_upper"
KIND_DELTA_OBS = "delta_obs"
KIND_DELTA_CI_LO = "delta_ci_lo"      # ⛔ 永远不许拿去比 KIND_C_UPPER

# ⚖⚖⚖ **唯一允许的比较对**（预登记 Q6 的主判据就是这一对）：
#   `c_upper`（污染量 c 的上界）vs `delta_obs`（观测差 w − rand）⇒ ⇒ 两者都是 pp、同量纲
#   ⇒ ⇒ 「污染最多抬这么多，而观测差至少这么多」⇒ ⇒ 污染**解释不了**观测差
ALLOWED_KIND_PAIRS = frozenset([
    (KIND_C_UPPER, KIND_DELTA_OBS),
    (KIND_DELTA_OBS, KIND_C_UPPER),
])

# ⚖ 判据 id（真数据路径印的是这些；变异台按 id 认「哪条该红」）
CRIT_IDS = ("H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8")
# ⚠ **必须是 tuple 而不是生成器**（⛔ 生成器是一次性的 ⇒ ⇒ 第一次用掉之后就没了
#   ⇒ ⇒ 对账脚本会看到空列表 ⇒ ⇒ 明细会骗人）
GATE_IDS = tuple("G0-%d" % i for i in range(1, 8))

# ⚖ **硬失败**（⇒ ⇒ 形态 C）：预登记 §3.1 的 C 行 ＋ §0.5 更正 ② 的级联
HARD_FAIL_IDS = ("H1", "H2", "H6", "H7", "H8")


def _die(msg):
    raise SystemExit("HARD_FAIL: %s" % msg)


def _read(p):
    with io.open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _md5_bytes(b):
    return hashlib.md5(b).hexdigest()


def _md5_file(p):
    with open(p, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def qty(value, kind, name):
    """⚖ **带 kind 标签的量** ⇒ ⇒ 量纲自检（H5）才有可核对的东西。"""
    return {"value": float(value), "kind": kind, "name": name}


# =============================================================================
# 账本解析层：全部输入从 244.81 段逐行解析
# =============================================================================

def _section(lines, rev):
    """⚖ 取「## 修订 <rev> 」那一段（到下一个「## 修订 」为止）⇒ 返回 (段文本, 起行号, 止行号)。"""
    starts = [i for i, l in enumerate(lines) if l.startswith("## 修订 %s " % rev)]
    if len(starts) != 1:
        _die("账本里「## 修订 %s」有 %d 处（期望恰好 1 处）" % (rev, len(starts)))
    s = starts[0]
    e = len(lines)
    for j in range(s + 1, len(lines)):
        if lines[j].startswith("## 修订 "):
            e = j
            break
    # ⚖ 行号是 **1-based**：段首 = s+1；段尾 = e（= 下一段标题行的 1-based 号 − 1）
    return "\n".join(lines[s:e]), s + 1, e


def _one(pattern, text, what, flags=re.M):
    hits = list(re.finditer(pattern, text, flags))
    if len(hits) != 1:
        _die("段内「%s」按模式命中 %d 次（期望恰好 1 次 ⇒ ⇒ 锚点不唯一 ⇒ ⇒ 中止）"
             % (what, len(hits)))
    return hits[0]


def parse_inputs(ledger_path, rev="244.81"):
    """⚖ 从账本 <rev> 段解析 I1–I9；**每个数都要逐位回读原文**。"""
    with open(ledger_path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    lines = text.split("\n")
    sec, sec_start, sec_end = _section(lines, rev)

    out = {"section": (sec_start, sec_end)}
    locs = {}

    def loc(m):
        """⚖ 命中位置对应的**文件行号**（1-based）⇒ ⇒ H7 要核对「解析到的行全部落在段内」。"""
        return sec_start + sec[:m.start()].count("\n")

    # ---- I1 / I2：改判数（46/56、29/56）----
    m = _one(r"改判（主口径：逐轨迹\*\*严格多数\*\*，`nT·2 > m`） \| \*\*(\d+)/(\d+)\*\* \| \*\*(\d+)/(\d+)\*\*",
             sec, "改判（主口径）行")
    out["i1_w_num"], out["i1_w_den"] = int(m.group(1)), int(m.group(2))
    out["i2_r_num"], out["i2_r_den"] = int(m.group(3)), int(m.group(4))
    locs["I1/I2"] = loc(m)

    # ---- I3 / I4：Wilson95 区间 ----
    m = _one(r"比例区间（Wilson95） \| \[\+([0-9.]+), \+([0-9.]+)\] \| \[\+([0-9.]+), \+([0-9.]+)\]",
             sec, "比例区间（Wilson95）行")
    out["i3_w_lo"], out["i3_w_hi"] = float(m.group(1)), float(m.group(2))
    out["i4_r_lo"], out["i4_r_hi"] = float(m.group(3)), float(m.group(4))
    locs["I3/I4"] = loc(m)

    # ---- I5：零假设基准（印的两位小数）----
    m = _one(r"零假设基准（逐轨迹平均） \| ([0-9.]+) \| ([0-9.]+)", sec, "零假设基准行")
    out["i5_w"], out["i5_r"] = float(m.group(1)), float(m.group(2))
    locs["I5"] = loc(m)

    # ---- I6：(n_nz,n_zero) 分布（两臂各一段）----
    m = _one(r"\(n_nz,n_zero\) 分布：\{([^}]*)\} ｜ \{([^}]*)\}", sec, "(n_nz,n_zero) 分布行")
    out["i6_w"] = _parse_dist(m.group(1))
    out["i6_r"] = _parse_dist(m.group(2))
    locs["I6"] = loc(m)

    # ---- I7：Δ_obs 轨迹级（+ Newcombe95，⚠ 后者只作交叉核对）----
    m = _one(r"\*\*差 ([+-][0-9.]+) pp\*\* ｜ 差区间（Newcombe95）\[([+-][0-9.]+), ([+-][0-9.]+)\]",
             sec, "差 + Newcombe95 行")
    out["i7_delta_obs"] = float(m.group(1))
    out["i7_newcombe_lo"] = float(m.group(2))
    out["i7_newcombe_hi"] = float(m.group(3))
    locs["I7"] = loc(m)

    # ---- I8：Δ_obs 块级（+ bootstrap 区间，⚠ 同上只作交叉核对）----
    m = _one(r"块级差 \*\*([+-][0-9.]+) pp\*\*，95% 区间 \*\*\[([+-][0-9.]+), ([+-][0-9.]+)\] pp\*\*",
             sec, "块级 bootstrap 行")
    out["i8_delta_obs_blk"] = float(m.group(1))
    out["i8_boot_lo"] = float(m.group(2))
    out["i8_boot_hi"] = float(m.group(3))
    locs["I8"] = loc(m)

    # ---- I9：块级改判数（w 21/28、rand 6/28）⇒ ⇒ 用来**独立复算**块级 Δ_obs ----
    #   ⚠ 实现层加的一项：预登记 §2.1 的 I8 要求「与账本印的值逐位对上」，
    #   而块级 Δ_obs 的「算的」必须由块级改判数算 ⇒ ⇒ 必须把这两个数也读出来。
    m = _one(r"w \*\*(\d+)/(\d+)\*\* ｜ rand \*\*(\d+)/(\d+)\*\* ｜ 差 ([+-][0-9.]+) pp",
             sec, "块级改判数行")
    out["i9_w_num"], out["i9_w_den"] = int(m.group(1)), int(m.group(2))
    out["i9_r_num"], out["i9_r_den"] = int(m.group(3)), int(m.group(4))
    locs["I9"] = loc(m)

    out["_raw_md5"] = _md5_bytes(raw)
    out["_sec"] = sec          # ⚖ 留给 H6：重建串必须**逐字符**出现在段内
    out["_lines"] = locs       # ⚖ 留给 H7：解析到的行号必须**全部落在段内**
    out["_sec_range"] = (sec_start, sec_end)

    # ---- 带 kind 标签的量（⚖ H5 量纲自检的唯一依据）----
    out["delta_qty"] = qty(out["i7_delta_obs"], KIND_DELTA_OBS, "delta_obs(traj)")
    out["delta_qty_blk"] = qty(out["i8_delta_obs_blk"], KIND_DELTA_OBS, "delta_obs(block)")
    out["newcombe_lo_qty"] = qty(out["i7_newcombe_lo"], KIND_DELTA_CI_LO, "newcombe_lo")
    out["boot_lo_qty"] = qty(out["i8_boot_lo"], KIND_DELTA_CI_LO, "boot_lo")
    return out


def _parse_dist(s):
    """⚖ 解析 `{(2,0)×1, (3,0)×55}` ⇒ ⇒ {(2,0):1, (3,0):55}
    ⛔ `⛔ 不用逗号直接切` ⇒ ⇒ 内层 `(2,0)` **自带逗号** ⇒ ⇒ 用正则逐项抽。"""
    items = re.findall(r"\((\d+),(\d+)\)\s*×\s*(\d+)", s)
    if not items:
        _die("(n_nz,n_zero) 分布解析不到项：%r" % s)
    d = {}
    for a, b, c in items:
        k = (int(a), int(b))
        d[k] = d.get(k, 0) + int(c)
    # ⚖ **逐位回读**：拼回去必须与原文**逐字符相同**（含分隔风格）⇒ ⇒ 防止解析悄悄改了东西
    #   ⚠ 比较时**两边都剥掉外层花括号**（正则捕获组本来就不含花括号）⇒ ⇒ 否则永远对不上
    rebuilt = "{%s}" % ", ".join("(%d,%d)×%d" % (k[0], k[1], v) for k, v in d.items())
    norm = re.sub(r"\s+", "", s).strip("{}")
    rnorm = re.sub(r"\s+", "", rebuilt).strip("{}")
    if rnorm != norm:
        _die("(n_nz,n_zero) 分布逐位回读对不上：原文 %r ⇒ 回读 %r" % (s, rebuilt))
    return d


def _dist_text(dist):
    """⚖ 由分布**重建**成账本里印的那一串（供 H6 的逐字符回读用）。"""
    return "{%s}" % ", ".join("(%d,%d)×%d" % (k[0], k[1], v) for k, v in dist.items())


def parse_ref_cmax(ledger_path, rev="244.86"):
    """⚖ 从账本 <rev> 段读出**主口径 c_max 的参考值**（244.86 段印的那个数）。

    ⛔ 命中数 ≠ 1 ⇒ ⇒ 返回 None（**不崩**）⇒ ⇒ H1 判红 ⇒ ⇒ 形态 C
       （⛔ 不是静默兜底：H1 会明确报「锚点命中 N 次」）
    """
    try:
        with open(ledger_path, "rb") as fh:
            text = fh.read().decode("utf-8")
    except OSError:
        return None
    lines = text.split("\n")
    try:
        sec, _s, _e = _section(lines, rev)
    except SystemExit:
        return None
    hits = re.findall(r"c_max = \*\*([+-][0-9.]+) pp\*\*", sec)
    if len(hits) != 1:
        return None
    return float(hits[0])


def ref_cmax_hits(ledger_path, rev="244.86"):
    """⚖ 辅助：锚点命中几次（用来在报错里说清楚）。"""
    try:
        with open(ledger_path, "rb") as fh:
            text = fh.read().decode("utf-8")
        lines = text.split("\n")
        sec, _s, _e = _section(lines, rev)
        return len(re.findall(r"c_max = \*\*([+-][0-9.]+) pp\*\*", sec))
    except (OSError, SystemExit):
        return -1


# =============================================================================
# 口径计算层
# =============================================================================

def _wilson_z(level):
    """⚖ 由置信水平得 z（⛔ 用固定的 z 表，口径参数，不是原始数）。"""
    z = {0.90: 1.6448536269514722,
         0.95: 1.959963984540054,
         0.99: 2.5758293035489004}
    if level not in z:
        _die("Wilson 置信水平 %r 不在 SPEC 里" % (level,))
    return z[level]


def wilson_bounds(k, n, level=0.95):
    """⚖ Wilson 区间（比例 × 100 ⇒ pp 口径）。"""
    if n <= 0:
        _die("Wilson：分母 ≤ 0")
    z = _wilson_z(level)
    p = k / float(n)
    d = 1.0 + z * z / n
    c = (p + z * z / (2.0 * n)) / d
    h = (z / d) * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return (max(0.0, c - h) * 100.0, min(1.0, c + h) * 100.0)


def base_from_dist(dist, variant):
    """⚖ 由 (n_nz,n_zero) 分布**现算**零假设基准（**比例**，⛔ 不乘 100）。

    · base = main         ：**逐轨迹算再平均**（零格轨迹 base=0.25、其余 base=0.5）
                            ⇒ ⇒ 与 244.81 段「零格进分母、不进基准」的口径一致
    · base = zero_as_half ：零格轨迹 base=**0.5**
    · base = zero_as_zero ：零格轨迹 base=**0**（极端下界）

    ⚖⚖⚖ **三个变体的基准都必须落在 [0,1]** ⇒ ⇒ 越界 ⇒ ⇒ **硬失败**
       （实现期真踩过：把「格数」当成「比例」⇒ base=2.964286 ⇒ ⇒ 就是这条抓到的）
    """
    if variant == "main":
        b_zero = 0.25
    elif variant == "zero_as_half":
        b_zero = 0.5
    elif variant == "zero_as_zero":
        b_zero = 0.0
    else:
        _die("未知基准变体 %r" % (variant,))
    num, den = 0.0, 0
    for (nz, zr), cnt in dist.items():
        n_traj = nz + zr
        if n_traj <= 0:
            _die("base(%s)：有轨迹的 n_nz+n_zero = 0" % variant)
        b = b_zero if zr > 0 else 0.5
        num += b * cnt
        den += cnt
    out = num / den
    if not (0.0 <= out <= 1.0):
        _die("base(%s)=%r **越界**（必须落在 [0,1]）⇒ ⇒ 基准算法写错了 ⇒ ⇒ 中止"
             % (variant, out))
    return out


def c_bounds(rand_num, rand_den, base, level):
    """⚖ **c 的区间**：[Wilson 下界 − 基准, Wilson 上界 − 基准]（单位 pp）。"""
    lo, hi = wilson_bounds(rand_num, rand_den, level)
    return (lo - base * 100.0, hi - base * 100.0)


def c_upper(rand_num, rand_den, base, level):
    """⚖ **c_max** = rand 改判率的 Wilson **上界** − 零假设基准（单位 pp）。"""
    return c_bounds(rand_num, rand_den, base, level)[1]


# =============================================================================
# H5 量纲自检（硬门）
# =============================================================================

def _md5_unchanged(path, before_md5):
    """⚖⚖⚖ **「这个文件没被改过」的判断**（H7 与 G0-7 **共用同一个函数**）。

    ⚖ **为什么要抽成函数**：变异台把「G0-7 的比较表达式」改成恒真 ⇒ ⇒ **没有任何闸门能抓**
       （自检层的固有上限：⛔ 改「比较表达式」这件事本身没人监督）⇒ ⇒ 修法：
       ① 把比较抽成**一个函数**；② G0-7 除了正控（没碰 ⇒ 必须说「没变」）还加**负控**
       （碰一下 ⇒ 必须说「变了」）⇒ ⇒ 两个控件**共用**这个函数 ⇒ ⇒ 把它改成恒真
       ⇒ ⇒ **正控与负控同时失效** ⇒ ⇒ G0-7 自己就红 ⇒ ⇒ 抓得到。
    """
    return _md5_file(path) == before_md5


def _check_kind(kind_a, kind_b):
    """⚖⚖⚖ **量纲自检**：比较两个量之前，**必须**核对它们的 kind 标签。

    ⚖ **允许的对**只有 `c_upper ↔ delta_obs`（预登记 Q6 的主判据）。
    ⛔ **禁止**：`delta_ci_lo`（Newcombe / 块级 bootstrap 的**差值区间下端点**）
       参与任何比较 —— 它是「w − rand 的差」的区间下端点，**不是** Δ_obs、**不是**真实差
       ⇒ ⇒ 拿它比 `c_max` 会得出「+15.22 翻越 +13.01」的**假警报**
       ⇒ ⇒ 这条**专门**用来抓 244.86 差点踩的那个坑。

    ⚖⚖⚖ **两条分支必须能被区分开**（各有各的**代号**）⇒ ⇒ 否则删掉其中一条
       ⇒ ⇒ 另一条仍会挡住 ⇒ ⇒ G0-4 的自证**察觉不到** ⇒ ⇒ 护栏被削弱而没人知道
       ⇒ ⇒ 变异台 MU8 就是靠这个抓的 ⇒ ⇒ 代号 = `H5-KIND-DELTA-CI-LO` / `H5-KIND-PAIR`。
    """
    if kind_a == KIND_DELTA_CI_LO or kind_b == KIND_DELTA_CI_LO:
        _die("H5-KIND-DELTA-CI-LO: ⛔⚠⚠ **量纲自检红（H5）**：拿「w − rand 的差的区间下端点」"
             "（kind=%s）去比「污染量 c 的上界」（kind=%s）⇒ ⇒ **量纲不同** ⇒ ⇒ 这是**假警报** ⇒ ⇒ 中止"
             % (kind_a if kind_a == KIND_DELTA_CI_LO else kind_b,
                kind_b if kind_a == KIND_DELTA_CI_LO else kind_a))
    if (kind_a, kind_b) not in ALLOWED_KIND_PAIRS:
        _die("H5-KIND-PAIR: ⛔⚠ **量纲自检红（H5）**：kind %s vs %s **不是允许的比较对** %s"
             % (kind_a, kind_b, sorted(ALLOWED_KIND_PAIRS)))


def _kind_code(msg):
    """⚖ 从护栏的报错消息里**取出分支代号**（⛔ 不靠 `split(":")` ⇒ `_die` 加了前缀会错位）。"""
    m = re.search(r"H5-KIND-[A-Z\-]+", msg or "")
    return m.group(0) if m else "(无代号)"


def _guard_selftest():
    """⚖ **H5 的自证**：喂一个**错标签**的量 ⇒ ⇒ 必须被判红 **且必须由 delta_ci_lo 那条分支判红**
    ⇒ ⇒ 否则「护栏被削弱」这件事**没人知道**（⛔ 另一条分支也能挡 ⇒ ⇒ 察觉不到）。"""
    try:
        _check_kind(KIND_DELTA_CI_LO, KIND_C_UPPER)
        return False, "⛔ 拿 delta_ci_lo 比 c_upper 却**没有**判红 ⇒ ⇒ 这条护栏是恒绿的，不可用", None
    except SystemExit as e:
        msg = str(e)
        code = _kind_code(msg)
        if code == "H5-KIND-DELTA-CI-LO":
            return True, "错标签比较被判红（分支 %s）⇒ %s" % (code, msg[:100]), code
        return False, ("⛔ 错标签虽然被判红，但**不是 delta_ci_lo 那条分支**（分支 %s）"
                       "⇒ ⇒ 护栏被削弱了却**察觉不到**" % code), code


# =============================================================================
# 主流程：扫描 + 判据
# =============================================================================

def canonical_scan_seq():
    """⚖ 扫描的**固定顺序**（Q3 × Q4，层序：先水平后变体）。"""
    return [(lv, va) for lv in WILSON_LEVELS for va in BASE_VARIANTS]


def run_scan(I):
    """⚖ 扫描 3 档 Wilson × 3 种基准 ⇒ ⇒ 每个口径算 c_max ⇒ ⇒ 与 Δ_obs 比。"""
    rows = []
    for level in WILSON_LEVELS:
        for variant in BASE_VARIANTS:
            base = base_from_dist(I["i6_r"], variant)
            lo, hi = c_bounds(I["i2_r_num"], I["i2_r_den"], base, level)
            rows.append({"level": level, "variant": variant, "base": base,
                         "c_lo": lo, "cmax": hi})
    return rows


def judge(I, rows, ledger_path):
    """⚖ 逐条判 H1–H8 ⇒ ⇒ 出四态之一（预登记 §3.1 ＋ §0.5 更正 ② 的级联）。

    ⚖ 返回 (形态, 明细列表)；明细 = [(id, 名称, 是否绿, 说明), ...]
    """
    res = []
    kind_err = [None]

    def chk(cid, name, ok, detail):
        res.append((cid, name, bool(ok), detail))
        return bool(ok)

    # ---- H5 的自证部分（与数据无关）----
    guard_ok, guard_detail, _guard_code = _guard_selftest()

    # ---- Δ_obs（**带 kind 标签**的量）----
    dq = I["delta_qty"]

    def cmp_cmax(cmax):
        """⚖ 比较（**必须**先过量纲自检）⇒ ⇒ 返回 True / False / None(量纲被拒)。"""
        try:
            _check_kind(KIND_C_UPPER, dq["kind"])
        except SystemExit as e:
            kind_err[0] = str(e)
            return None
        return bool(cmax < dq["value"])

    # ---- H1 主口径复算门槛：c_max（Wilson95, main）必须与 244.86 段印的数逐位对上 ----
    main_rows = [r for r in rows if r["level"] == MAIN_LEVEL and r["variant"] == "main"]
    c_main = main_rows[0]["cmax"] if main_rows else float("nan")
    ref = parse_ref_cmax(ledger_path)
    hits = ref_cmax_hits(ledger_path)
    h1 = chk("H1", "主口径复算门槛",
             ref is not None and abs(c_main - ref) <= 5e-3,
             "现算 c_max=%+.4f pp ｜ 244.86 段印 %s ｜ 容差 0.005 pp（= 账本打印精度 2 位的半个单位）"
             % (c_main, ("%+.2f pp" % ref) if ref is not None
                else "(锚点命中 %d 次 ⇒ 读不到 ⇒ 硬失败)" % hits))

    # ---- H2 扫描完备性：3×3 = 9 个口径、顺序固定 ----
    expect_seq = canonical_scan_seq()
    got_seq = [(r["level"], r["variant"]) for r in rows]
    h2 = chk("H2", "扫描完备性（9 个口径、顺序固定）", got_seq == expect_seq,
             "%d 个口径（期望 %d）｜ 顺序%s"
             % (len(rows), len(expect_seq), "固定" if got_seq == expect_seq else "**乱**"))

    # ---- H3 主判据：每个口径下 c_max < Δ_obs（轨迹级 = 最紧的那个）----
    delta_obs = dq["value"]
    viol, cmp_none = [], []
    for r in rows:
        ok = cmp_cmax(r["cmax"])
        if ok is None:
            cmp_none.append(r)
        elif not ok:
            viol.append(r)
    h3 = chk("H3", "主判据（每口径 c_max < Δ_obs）",
             not viol and not cmp_none,
             "Δ_obs=%+.2f pp ｜ 违例 %d 个 %s%s"
             % (delta_obs, len(viol), [("%.2f/%s" % (r["cmax"], r["variant"])) for r in viol],
                ("｜ 量纲被拒 %d 个" % len(cmp_none)) if cmp_none else ""))

    # ---- H4 最紧组合单点（Wilson95, main, 轨迹级 Δ_obs）----
    h4 = chk("H4", "最紧组合单点", (cmp_cmax(c_main) is True),
             "(Wilson95, main) c_max=%+.4f pp < Δ_obs=%+.2f pp ⇒ %s"
             % (c_main, delta_obs, "成立" if (cmp_cmax(c_main) is True) else "**不成立**"))

    # ---- H5 量纲自检（硬门）：护栏能红 ＋ 本次流程里没有错标签的量进入比较 ----
    h5 = chk("H5", "量纲自检（硬门）", guard_ok and kind_err[0] is None,
             (guard_detail if guard_ok else guard_detail)
             + ("｜ 本次流程：%s" % kind_err[0][:90] if kind_err[0] else "｜ 本次流程：无错标签比较"))

    # ---- H6 输入出处：把解析出的值**按账本的印刷格式重建**，必须**逐字符出现在段内** ----
    #   ⚠⚠⚖ 这样才有牙齿：改账本任一个数 ⇒ ⇒ 重建串不再出现在段内 ⇒ ⇒ **红**
    #   （⛔ 绝不能写成「解析成功就算过」那种恒真判断）
    rebuilds = [
        ("I1", "**%d/%d**" % (I["i1_w_num"], I["i1_w_den"])),
        ("I2", "**%d/%d**" % (I["i2_r_num"], I["i2_r_den"])),
        ("I3", "[+%.2f, +%.2f]" % (I["i3_w_lo"], I["i3_w_hi"])),
        ("I4", "[+%.2f, +%.2f]" % (I["i4_r_lo"], I["i4_r_hi"])),
        ("I5w", "%.4f" % I["i5_w"]),
        ("I5r", "%.4f" % I["i5_r"]),
        ("I6w", _dist_text(I["i6_w"])),
        ("I6r", _dist_text(I["i6_r"])),
        ("I7", "**差 %+.2f pp**" % I["i7_delta_obs"]),
        ("I8", "块级差 **%+.2f pp**" % I["i8_delta_obs_blk"]),
        ("I9w", "**%d/%d**" % (I["i9_w_num"], I["i9_w_den"])),
        ("I9r", "**%d/%d**" % (I["i9_r_num"], I["i9_r_den"])),
    ]
    miss = [k for k, s in rebuilds if s not in I["_sec"]]
    h6 = chk("H6", "输入出处（重建串必须逐字符出现在段内）", not miss,
             "%d/%d 项重建串在段内命中 ｜ 缺失 %s"
             % (len(rebuilds) - len(miss), len(rebuilds), miss or "无"))

    # ---- H7 只读：账本 md5 运行前后不变 ＋ 解析到的行号全部落在 244.81 段内 ----
    md5_now = _md5_file(ledger_path)
    s0, s1 = I["_sec_range"]
    out_of_range = [(k, v) for k, v in I["_lines"].items() if not (s0 <= v <= s1)]
    h7 = chk("H7", "只读（账本 md5 不变 + 行号落在段内）",
             _md5_unchanged(ledger_path, I["_raw_md5"]) and not out_of_range,
             "运行后 md5 %s ｜ 运行前 %s ｜ 段范围 [%d, %d] ｜ 越界行 %s"
             % (md5_now, I["_raw_md5"], s0, s1, out_of_range or "无"))

    # ---- H8 跨来源交叉核对 ----
    #   ⚠⚠⚖ H8 比的是「**账本印的值** vs「现算的值」⇒ ⇒ 必须用**账本印的那个** Δ_obs
    #      （I7）⇒ ⇒ **不能**用「可能被换掉的量」（dq）⇒ ⇒ 否则「把 Newcombe 下端点接到
    #      Δ_obs 槽位」会**连带**把 H8 也带红 ⇒ ⇒ 形态被误判成 C（⛔ 量纲问题归 H5 管）
    delta_obs_printed = I["i7_delta_obs"]
    calc_delta = (I["i1_w_num"] / I["i1_w_den"] - I["i2_r_num"] / I["i2_r_den"]) * 100.0
    calc_delta_blk = (I["i9_w_num"] / I["i9_w_den"] - I["i9_r_num"] / I["i9_r_den"]) * 100.0
    base_calc = base_from_dist(I["i6_r"], "main")
    w_hi_calc = wilson_bounds(I["i2_r_num"], I["i2_r_den"], 0.95)[1]
    h8_ok = (abs(calc_delta - delta_obs_printed) <= 0.005
             and abs(calc_delta_blk - I["i8_delta_obs_blk"]) <= 0.005
             and abs(base_calc - I["i5_r"]) <= 5e-4
             and abs(w_hi_calc - I["i4_r_hi"]) <= 0.005)
    h8 = chk("H8", "跨来源交叉核对", h8_ok,
             "Δ_obs(轨迹) 算=%+.4f vs 印=%+.2f ｜ Δ_obs(块) 算=%+.4f vs 印=%+.2f ｜ "
             "基准 算=%.10f vs 印=%.4f ｜ Wilson(rand) 上界 算=%.4f vs 印=%.2f"
             % (calc_delta, delta_obs_printed, calc_delta_blk, I["i8_delta_obs_blk"],
                base_calc, I["i5_r"], w_hi_calc, I["i4_r_hi"]))

    # ---- 形态（预登记 §3.1 ＋ §0.5 更正 ② 的优先级级联）----
    flags = {cid: ok for cid, _n, ok, _d in res}
    hard = [cid for cid in HARD_FAIL_IDS if not flags.get(cid, True)]
    if hard:
        form = FORM_C
    elif not flags.get("H5", True):
        form = FORM_D
    elif not (flags.get("H3", True) and flags.get("H4", True)):
        form = FORM_B
    else:
        form = FORM_A

    reason = _reason(form, res, hard, c_main, delta_obs)
    return form, res, reason


def _reason(form, res, hard, c_main, delta_obs):
    flags = {cid: ok for cid, _n, ok, _d in res}
    if form == FORM_C:
        return ("硬失败（%s 红）⇒ ⇒ 不是结论层面的问题 ⇒ ⇒ 修实现/修环境 ⇒ ⇒ **形态无意义**"
                % "、".join(hard))
    if form == FORM_D:
        return ("量纲自检（H5）红 ⇒ ⇒ 实现把两个量纲混比 ⇒ ⇒ **硬失败**"
                "（⛔ 不许当成「结论有瑕疵」放过）")
    if form == FORM_B:
        return ("存在某个扫描口径下 c_max ≥ Δ_obs ⇒ ⇒ 「对口径不敏感」这个命题**被否** "
                "⇒ ⇒ 结论必须**收紧**成「只在 Wilson95 主口径下成立」"
                "（⛔ **不许**因此说「污染能解释观测差」）")
    return ("「污染解释不了观测差」这条结论**对扫描的所有口径都成立** ⇒ ⇒ "
            "c_max 从「一个数」升级成「一个区」（最紧组合 c_max=%+.4f pp < Δ_obs=%+.2f pp）"
            % (c_main, delta_obs))


# =============================================================================
# Phase-0（合成夹具，⛔ 零账本、⛔ 零 GPU）
# =============================================================================

def _tmp_root():
    """⚖ 临时目录（远端走 /dev/shm；⛔ 不写 NFS、⛔ 不碰真账本）。"""
    d = os.environ.get("R24487_TMPDIR")
    if d:
        if not os.path.isdir(d):
            os.makedirs(d)
        return d
    for cand in ("/dev/shm", None):
        try:
            return tempfile.mkdtemp(prefix="cma87_", dir=cand)
        except Exception:
            continue
    _die("建不了临时目录")


def fixture_text(w_num=46, w_den=56, r_num=29, r_den=56,
                 w_lo="+70.16", w_hi="+90.00", r_lo="+39.01", r_hi="+64.33",
                 base_w="0.4955", base_r="0.4911",
                 dist_w="{(2,0)×1, (3,0)×55}", dist_r="{(2,1)×2, (3,0)×54}",
                 delta_traj="+30.36", nc_lo="+13.01", nc_hi="+45.36",
                 blk_w=21, blk_den=28, blk_r=6, blk_delta="+53.57",
                 boot_lo="+32.14", boot_hi="+75.00",
                 ref_cmax="+15.22", dup_anchor=False, drop_ref=False):
    """⚖ **合成账本片段**（格式逐字照抄真账本 244.81 / 244.86 段的锚点行）。"""
    lines = []
    lines.append("# 合成夹具账本（244.87 Phase-0 用；⛔ 不是真账本、⛔ 零 GPU）")
    lines.append("")
    lines.append("## 修订 244.81 —— （合成）固定剂量下的判决数")
    lines.append("")
    lines.append("| 改判（主口径：逐轨迹**严格多数**，`nT·2 > m`） | **%d/%d** | **%d/%d** |"
                 % (w_num, w_den, r_num, r_den))
    lines.append("| 比例区间（Wilson95） | [%s, %s] | [%s, %s] |" % (w_lo, w_hi, r_lo, r_hi))
    lines.append("| 零假设基准（逐轨迹平均） | %s | %s |" % (base_w, base_r))
    lines.append("")
    lines.append("  · (n_nz,n_zero) 分布：%s ｜ %s" % (dist_w, dist_r))
    lines.append("")
    lines.append("· **差 %s pp** ｜ 差区间（Newcombe95）[%s, %s] ｜ 跨臂 Fisher p = 0.001152。"
                 % (delta_traj, nc_lo, nc_hi))
    lines.append("")
    lines.append("· w **%d/%d** ｜ rand **%d/%d** ｜ 差 %s pp ｜ 差区间 [+27.79, +70.23] ｜ "
                 "Fisher p = 0.000131。" % (blk_w, blk_den, blk_r, blk_den, blk_delta))
    lines.append("")
    lines.append("· **区间**：按**块**重采样（承认聚类）的 bootstrap ⇒ ⇒ 块级差 **%s pp**，"
                 "95%% 区间 **[%s, %s] pp**。" % (blk_delta, boot_lo, boot_hi))
    if dup_anchor:
        lines.append("| 比例区间（Wilson95） | [%s, %s] | [%s, %s] |" % (w_lo, w_hi, r_lo, r_hi))
    lines.append("")
    head = "## 修订 244.86 —— （合成）对照臂的零假设地位"
    if not drop_ref:
        head += "：c_max = **%s pp**" % ref_cmax
    lines.append(head)
    lines.append("")
    lines.append("| 幅度上界 | c_max = rand Wilson95 **上界** − 零假设基准 | **%s pp** |" % ref_cmax)
    lines.append("")
    lines.append("## 修订 244.87 —— （合成）结束")
    lines.append("")
    return "\n".join(lines)


def _run_fixture(tmpdir, text, tag, mutate=None):
    """⚖ 写合成账本 → 解析 → 扫描 → 判 ⇒ ⇒ 返回 (form, res, I, rows, path)。"""
    path = os.path.join(tmpdir, "ledger_%s.md" % tag)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    I = parse_inputs(path)
    if mutate is not None:
        mutate(I, path)
    rows = run_scan(I)
    form, res, reason = judge(I, rows, path)
    return form, res, I, rows, path


def _ids(res):
    return {cid: ok for cid, _n, ok, _d in res}


def selftest():
    """⚖⚖⚖ **Phase-0 闸门**（预登记 §5：G0-1 .. G0-7，合成夹具、⛔ 零账本、⛔ 零 GPU）。

    G0-1：四个形态（A / B / C / D）**全部可达**且**互斥**
    G0-2：H1..H8 **每条都能红**
    G0-3：扫描**完备性**（3×3 = 9 个口径、顺序固定）
    G0-4：H5 量纲自证（喂一个错标签 ⇒ 必须红）
    G0-5：主口径复算（**独立公式**现算 ⇒ 必须与实现一致）
    G0-6：输入解析（合成账本能解析出 I1–I9；锚点不唯一 ⇒ 必须硬失败）
    G0-7：只读（运行前后账本 md5 逐位不变）
    """
    fails = []
    tmp = _tmp_root()
    own_tmp = not os.environ.get("R24487_TMPDIR")
    try:
        # ---------- G0-1：四个形态全部可达且互斥 ----------
        # A：全绿（夹具用的是账本里那组数）
        formA, resA, _I, _rows, _pA = _run_fixture(tmp, fixture_text(), "A")
        # B：扫描出现违例（把 w 臂改判改成 31/56 ⇒ Δ_obs 变小到 +3.57）
        formB, resB, _I, _rB, _pB = _run_fixture(
            tmp, fixture_text(w_num=31, delta_traj="+3.57"), "B")
        # C：硬失败（244.86 段的 c_max 锚点读不到 ⇒ H1 红）
        formC, resC, _I, _rC, _pC = _run_fixture(tmp, fixture_text(drop_ref=True), "C")
        # E：**另一类**硬失败（Δ_obs 印的与算的对不上 ⇒ H8 红 ⇒ 同样落 C）
        #   ⚠ 这条夹具的作用：把「H8 红 ⇒ 形态 C」**钉住** ⇒ ⇒ 否则把 H8 移出硬失败集合
        #   这条变异（改成落 B）**没有任何闸门能抓** ⇒ ⇒ 必须有夹具。
        formE, resE, _I, _rE, _pE = _run_fixture(tmp, fixture_text(delta_traj="+40.00"), "E")
        # D：量纲混比（把 Newcombe 下端点接到 Δ_obs 的位置上 ⇒ H5 红）
        def _wrong_kind(I, path):
            I["delta_qty"] = qty(I["i7_newcombe_lo"], KIND_DELTA_CI_LO, "newcombe_lo")
        formD, resD, _I, _rD, _pD = _run_fixture(tmp, fixture_text(), "D", _wrong_kind)

        got = {"A": formA, "B": formB, "C": formC, "D": formD}
        ok1 = (got == {"A": FORM_A, "B": FORM_B, "C": FORM_C, "D": FORM_D})
        ok1 = ok1 and (len(set(got.values())) == 4)
        ok1 = ok1 and (formE == FORM_C)
        print("[%s] G0-1（四个形态全部可达且互斥） 实得 A/B/C/D = %s ｜ E(H8红)=%s ⇒ ⇒ %s"
              % ("PASS" if ok1 else "FAIL", got, formE,
                 "互斥且穷尽" if ok1 else "**不成立**"))
        if not ok1:
            fails.append("G0-1")

        # ---------- G0-2：H1..H8 每条都能红 ----------
        red_cases = []

        # H1：244.86 段印的 c_max 与现算对不上
        _f, res, _I, _r, _p = _run_fixture(tmp, fixture_text(ref_cmax="+12.34"), "H1")
        red_cases.append(("H1", _ids(res), "244.86 段印的 c_max 被改成 +12.34"))

        # H2：扫描口径数/顺序不对
        _f, _res, I, _r, path = _run_fixture(tmp, fixture_text(), "H2")
        rows_bad = run_scan(I)[:-1]
        _f2, res2, _r2 = judge(I, rows_bad, path)
        red_cases.append(("H2", _ids(res2), "扫描少算一个口径"))

        # H3 / H4：违例（同一个夹具 ⇒ H4 红蕴含 H3 红）
        red_cases.append(("H3", _ids(resB), "B 夹具：Δ_obs 变小 ⇒ 违例"))
        red_cases.append(("H4", _ids(resB), "B 夹具：最紧组合违例（H4 红 ⇒ H3 必红）"))

        # H5：错标签
        red_cases.append(("H5", _ids(resD), "把 Newcombe 下端点接到 Δ_obs 槽位"))

        # H6：基准印的位数变了 ⇒ 重建串对不上
        _f, res, _I, _r, _p = _run_fixture(tmp, fixture_text(base_r="0.49"), "H6")
        red_cases.append(("H6", _ids(res), "基准印成 0.49（两位）⇒ 重建串 0.4900 命不中"))

        # H7：解析完把账本碰一下 ⇒ md5 变
        def _touch(I, path):
            with io.open(path, "a", encoding="utf-8", newline="") as fh:
                fh.write("\n<!-- 触碰 -->\n")
        _f, res, _I, _r, _p = _run_fixture(tmp, fixture_text(), "H7", _touch)
        red_cases.append(("H7", _ids(res), "解析后触碰账本 ⇒ md5 变"))

        # H8：Δ_obs 印的与算的对不上
        _f, res, _I, _r, _p = _run_fixture(tmp, fixture_text(delta_traj="+40.00"), "H8")
        red_cases.append(("H8", _ids(res), "Δ_obs(轨迹) 印成 +40.00（与 w/rand 算出的 +30.36 不符）"))
        # H8（第二条腿）：**块级** Δ_obs 印的与算的对不上
        _f, res, _I, _r, _p = _run_fixture(tmp, fixture_text(blk_delta="+60.00"), "H8b")
        red_cases.append(("H8", _ids(res), "Δ_obs(块) 印成 +60.00（与块级改判数算出的 +53.57 不符）"))

        bad2 = []
        for cid, ids, note in red_cases:
            if ids.get(cid, True):
                bad2.append("%s（没能变红）" % cid)
        ok2 = not bad2
        print("[%s] G0-2（H1..H8 每条都能红） %s"
              % ("PASS" if ok2 else "FAIL",
                 "8 条判据各自都有能红的夹具" if ok2 else "**没能变红**：%s" % bad2))
        for cid, ids, note in red_cases:
            print("      · %s ⇒ %s ｜ 夹具：%s" % (cid, "红" if not ids.get(cid, True) else "**绿**", note))
        if not ok2:
            fails.append("G0-2")

        # ---------- G0-3：扫描完备性（9 个口径、顺序固定） ----------
        seq = [(r["level"], r["variant"]) for r in run_scan(parse_inputs(_pA))]
        ok3 = (len(seq) == 9 and seq == canonical_scan_seq())
        print("[%s] G0-3（扫描完备性：3×3=9、顺序固定） %d 个口径 ｜ 顺序%s"
              % ("PASS" if ok3 else "FAIL", len(seq), "固定" if ok3 else "**乱**"))
        if not ok3:
            fails.append("G0-3")

        # ---------- G0-4：H5 量纲自证 ----------
        ok4, detail4, code4 = _guard_selftest()
        # ⚠ **第二条腿**：不是 delta_ci_lo 的**别的不允许的对**也必须被拒
        #   （⛔ 只挡一种错法 ⇒ ⇒ 护栏形同虚设 ⇒ ⇒ 变异台会把「删掉 ALLOWED_KIND_PAIRS 检查」
        #   那条变异放过去 ⇒ ⇒ 这里必须补上）
        try:
            _check_kind(KIND_C_UPPER, "delta_ci_hi")
            ok4b, detail4b = False, "⛔ 未知 kind 的比较**没有**被拒 ⇒ ⇒ 护栏只挡了一种错法"
        except SystemExit as e:
            ok4b, detail4b = True, "未知 kind 的比较被判红（分支 %s）" % _kind_code(str(e))
        ok4 = ok4 and ok4b
        print("[%s] G0-4（H5 量纲自证：喂错标签必须红） %s ｜ %s"
              % ("PASS" if ok4 else "FAIL", detail4, detail4b))
        if not ok4:
            fails.append("G0-4")

        # ---------- G0-5：主口径复算（**独立公式**） ----------
        #   ⚠ z 用 statistics.NormalDist().inv_cdf 现算（**不是** SPEC 里那张固定表）
        #   ⚠ base 用**手写的求和**（**不调用** base_from_dist）
        #   ⚠ 两条臂都验：① 真账本那把（29/56）② **另一组数**（7/20）⇒ ⇒ 证明不是写死的
        def _indep_cmax(k, n, base_ratio):
            """⚖ **独立路线**的 c_max（⛔ 不调用实现里的 wilson_bounds / base_from_dist）。"""
            z_ind = statistics.NormalDist().inv_cdf(0.5 + MAIN_LEVEL / 2.0)
            p_ind = k / float(n)
            d_ind = 1.0 + z_ind * z_ind / n
            c_ind = (p_ind + z_ind * z_ind / (2.0 * n)) / d_ind
            h_ind = (z_ind / d_ind) * math.sqrt(p_ind * (1.0 - p_ind) / n
                                              + z_ind * z_ind / (4.0 * n * n))
            return min(1.0, c_ind + h_ind) * 100.0 - base_ratio * 100.0

        # ① 真账本那把（rand 臂 29/56；基准：2 条零格轨迹 base=0.25 + 54 条满格 base=0.5）
        base_ind = (2 * 0.25 + 54 * 0.5) / 56.0     # ⚠ 手写求和（**不调用** base_from_dist）
        cmax_ind = _indep_cmax(29, 56, base_ind)
        cmax_impl = c_upper(29, 56, base_from_dist({(2, 1): 2, (3, 0): 54}, "main"), MAIN_LEVEL)
        # ② **另一组数**（7/20、基准 0.5）⇒ ⇒ 证明实现不是对着 29/56 写死的
        cmax_ind2 = _indep_cmax(7, 20, 0.5)
        cmax_impl2 = c_upper(7, 20, 0.5, MAIN_LEVEL)
        d1 = abs(cmax_impl - cmax_ind)
        d2 = abs(cmax_impl2 - cmax_ind2)
        ok5 = (d1 <= 1e-9) and (d2 <= 1e-9)
        print("[%s] G0-5（主口径复算：独立公式 vs 实现） "
              "① 29/56：独立=%+.10f ｜ 实现=%+.10f ｜ 差 %.2e　"
              "② 7/20：独立=%+.10f ｜ 实现=%+.10f ｜ 差 %.2e"
              % ("PASS" if ok5 else "FAIL", cmax_ind, cmax_impl, d1,
                 cmax_ind2, cmax_impl2, d2))
        if not ok5:
            fails.append("G0-5")

        # ---------- G0-6：输入解析（I1–I9 全对；锚点不唯一 ⇒ 硬失败）----------
        I6 = parse_inputs(_pA)
        ok6a = (I6["i1_w_num"] == 46 and I6["i1_w_den"] == 56
                and I6["i2_r_num"] == 29 and I6["i2_r_den"] == 56
                and I6["i5_r"] == 0.4911
                and I6["i6_r"] == {(2, 1): 2, (3, 0): 54}
                and abs(I6["i7_delta_obs"] - 30.36) < 1e-12
                and abs(I6["i8_delta_obs_blk"] - 53.57) < 1e-12
                and I6["i9_w_num"] == 21 and I6["i9_r_num"] == 6)
        dup_hard = False
        try:
            _run_fixture(tmp, fixture_text(dup_anchor=True), "DUP")
            dup_hard = False
        except SystemExit:
            dup_hard = True
        miss_hard = False
        try:
            bad_text = fixture_text().replace(
                "| 比例区间（Wilson95） | [+70.16, +90.00] | [+39.01, +64.33] |", "", 1)
            _run_fixture(tmp, bad_text, "MISS")
            miss_hard = False
        except SystemExit:
            miss_hard = True
        ok6 = ok6a and dup_hard and miss_hard
        print("[%s] G0-6（输入解析：I1–I9 正确 ＋ 锚点不唯一/缺失 ⇒ 硬失败） "
              "I1–I9 %s ｜ 锚点重复⇒硬失败 %s ｜ 锚点缺失⇒硬失败 %s"
              % ("PASS" if ok6 else "FAIL",
                 "对" if ok6a else "**错**",
                 "是" if dup_hard else "**否**", "是" if miss_hard else "**否**"))
        if not ok6:
            fails.append("G0-6")

        # ---------- G0-7：只读 ----------
        #   ⚠⚠⚖ **正控 + 负控**（负控是变异台 MU15 能抓到「把比较改成恒真」的**唯一**原因）
        md5_before = _md5_file(_pA)
        _run_fixture(tmp, fixture_text(), "RO")
        md5_after = _md5_file(_pA)
        ok7_pos = _md5_unchanged(_pA, md5_before)
        # 负控：碰一下账本 ⇒ 「没被改过」必须**变成 False**
        with io.open(_pA, "a", encoding="utf-8", newline="") as fh:
            fh.write("\n<!-- 触碰 -->\n")
        ok7_neg = (not _md5_unchanged(_pA, md5_before))
        ok7 = ok7_pos and ok7_neg
        print("[%s] G0-7（只读：运行前后账本 md5 不变） 正控 %s ｜ 负控（碰一下必须被检出）%s"
              % ("PASS" if ok7 else "FAIL", "对" if ok7_pos else "**错**",
                 "对" if ok7_neg else "**错**"))
        if not ok7:
            fails.append("G0-7")

    finally:
        if own_tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    print("自检（Phase-0 G0-1..G0-7）：%d 条 ｜ FAIL %d 条%s"
          % (7, len(fails), ("：%s" % fails) if fails else ""))
    return 0 if not fails else 1


def print_spec():
    print("SPEC（口径参数；⛔ 不是原始数）：")
    print("  MAIN_LEVEL      = %r" % MAIN_LEVEL)
    print("  WILSON_LEVELS   = %r" % (WILSON_LEVELS,))
    print("  BASE_VARIANTS   = %r" % (BASE_VARIANTS,))
    print("  形态            = %r" % ([FORM_A, FORM_B, FORM_C, FORM_D],))
    print("  硬失败判据      = %r" % (HARD_FAIL_IDS,))
    print("  扫描口径数      = %d × %d = %d"
          % (len(WILSON_LEVELS), len(BASE_VARIANTS),
             len(WILSON_LEVELS) * len(BASE_VARIANTS)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-spec", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--data", action="store_true")
    ap.add_argument("--ledger", default=None)
    a = ap.parse_args()

    if a.print_spec:
        print_spec()
        return 0
    if a.selftest:
        return selftest()

    if not a.data:
        print("（没给 --data ⇒ 只打印用法）")
        print_spec()
        return 0

    ledger = a.ledger
    if not ledger:
        here = os.path.dirname(os.path.abspath(__file__))
        ledger = os.path.join(os.path.dirname(here), "xcheck", "R6_RERUN_PREREG.md")

    I = parse_inputs(ledger)
    rows = run_scan(I)
    form, res, reason = judge(I, rows, ledger)
    dq = I["delta_qty"]

    print("──── 扫描（Wilson 水平 × 基准变体）────")
    for r in rows:
        print("  %.2f / %-14s base=%.6f  c ∈ [%+.4f, %+.4f] pp  ⇒  c_max=%+.4f pp"
              % (r["level"], r["variant"], r["base"], r["c_lo"], r["cmax"], r["cmax"]))
    print("──── 每个口径的真实差区间（Q7：两条都算，⛔ 不许只印对自己有利的那条）────")
    for r in rows:
        iv_no = (dq["value"] + r["c_lo"], dq["value"] + r["cmax"])
        iv_up = (dq["value"], dq["value"] + r["cmax"])
        print("  %.2f / %-14s 不假定方向 [%+.4f, %+.4f] pp ｜ 假定污染抬高 [%+.4f, %+.4f] pp"
              % (r["level"], r["variant"], iv_no[0], iv_no[1], iv_up[0], iv_up[1]))
    print("──── 判据 ────")
    for cid, name, ok, detail in res:
        print("[%s] %s %s — %s" % ("PASS" if ok else "FAIL", cid, name, detail))
    print()
    print("VERDICT=%s" % form)
    print("理由：%s" % reason)

    cmax_main = [r["cmax"] for r in rows if r["level"] == MAIN_LEVEL and r["variant"] == "main"][0]
    # ⚠⚠⚖ **IV_* 必须取「主口径行」（Wilson95, main）** ⇒ ⇒ 与 244.86 账本印的那两条区间**同口径**
    #   （⛔ 早先取了 rows[0] = (Wilson90, main) ⇒ ⇒ 提交信息会引到**别的口径**的数 ⇒ ⇒ 已修）
    row_main = [r for r in rows if r["level"] == MAIN_LEVEL and r["variant"] == "main"][0]
    print("===== AUDIT_KEYS =====")
    print("VERDICT=%s" % form)
    print("N_SCAN=%d" % len(rows))
    print("BASE_MAIN_R=%.12f" % base_from_dist(I["i6_r"], "main"))
    print("DELTA_OBS_PP=%.4f" % dq["value"])
    print("DELTA_OBS_BLK_PP=%.4f" % I["i8_delta_obs_blk"])
    print("C_MAIN_PP=%.6f" % cmax_main)
    print("C_MIN_PP=%.6f" % min(r["cmax"] for r in rows))
    print("C_MAX_PP=%.6f" % max(r["cmax"] for r in rows))
    for r in rows:
        print("CMAX_%d_%s=%.6f" % (int(round(r["level"] * 100)), r["variant"].upper(), r["cmax"]))
    print("IV_NO_LO_PP=%.4f" % (dq["value"] + row_main["c_lo"]))
    print("IV_NO_HI_PP=%.4f" % (dq["value"] + row_main["cmax"]))
    print("IV_UP_LO_PP=%.4f" % dq["value"])
    print("IV_UP_HI_PP=%.4f" % (dq["value"] + row_main["cmax"]))
    print("===== END_AUDIT_KEYS =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
