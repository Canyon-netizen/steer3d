#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚖ **244.88「污染解释不了观测差」的保守读法与口径边界** —— 实现
（口径真相源 = `.cache/xcheck/R6_CONSERVATIVE_BOUND_PREREG.md`，**先于**本实现签发）

⚖⚖⚖ **这一轮要回答什么**
  244.87 判成形态 **A**：9 个扫描口径下 `c_max ∈ [+12.43, +19.65] pp` 全部 < `Δ_obs(轨迹级) = +30.36 pp`
  ⇒ ⇒ 「污染解释不了观测差」这条结论**对口径稳健**。
  ⇒ ⇒ 但 ① 那条主判据是**点估计**口径；② 它**只守了 c 区间的高端** ——
     面板里那列「真实差（不假定方向）」= `Δ_obs + c_lo` **只被打印、没有任何判据守它**。
  ⇒ ⇒ 本轮：① **补守紧端**（把 `Δ_obs + c_lo` 接到判据上）；② **把抽样噪声也算进去** ——
     「**把污染幅度与抽样噪声同时按最保守方向放**」，这条结论还站得住吗？
     ⇒ ⇒ 本轮的交付物是一张「**读法—口径作用域表**」，而不只是一个形态。

⚖⚖⚖ **量纲（三个量 + 四个 kind）**
  `c`      = rand 改判率 − 零假设基准（**污染量**）
  `c_hi`   = `c` 的 Wilson **上界**（kind = `c_upper`）  ← 244.87 的主判据用它
  `c_lo`   = `c` 的 Wilson **下界**（kind = `c_lower`）  ← **244.87 只打印、没判据守过**
  `Δ_obs`  = w − rand（kind = `delta_obs`）
  `CI_lo`  = 差区间**下端点**（kind = `delta_ci_lo`）

⚖⚖⚖ **允许的比较 / 加法**（预登记 §1 ＋ §0.5 更正 ①）
  ① `c_upper ↔ delta_obs`      ⇒ 244.87 的主判据（「污染最多抬这么多，而观测差至少这么多」）
  ② `delta_ci_lo + c_lower`    ⇒ **本轮新增**的保守读法
     ⚖ 合法性：population 层的分解 `Δ_true = Δ_obs + c` ⇒ ⇒ 若 `Δ_obs ≥ CI_lo`（95%）
       **且** `c ≥ c_lo`（95%）⇒ ⇒ `Δ_true ≥ CI_lo + c_lo`；两项各 95% ⇒ ⇒
       **Bonferroni ⇒ 联合 ≥ 90%**（⛔ Bonferroni **不要求**两项独立）。
  ③ `delta_obs + c_lower`      ⇒ **点估计读法**（同一分解的点估计版 ⇒ 补守 244.87 的紧端）
     ⚠ 更正 ①：初版预登记只登记了 ② ⇒ ⇒ 实现用到 ③ 时**被自己的量纲门拦死**
        ⇒ ⇒ 追加 ③（**起草层遗漏**；写实现时**尚未跑过任何东西** ⇒ ⛔ 不是结果驱动的改动）。
  ⛔ `delta_ci_lo ↔ c_upper`   ⇒ 244.87 的 H5 硬门，**继续红**（那是「假警报」）
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

# ==== SPEC（口径参数；⛔ 不是原始数；由预登记 §1/§2 决定）====
MAIN_LEVEL = 0.95                        # 主口径：Wilson95
WILSON_LEVELS = (0.90, 0.95, 0.99)       # 扫描维度 A：Wilson 置信水平
BASE_VARIANTS = ("main", "zero_as_half", "zero_as_zero")   # 扫描维度 B：零格 base = .25/.5/.0
ALPHA_CI = 0.05                          # 差区间（Newcombe95）的 alpha ⇒ 预登记 §2 的「单源 95%」

# ==== 判决形态（预登记 §3.2：互斥且穷尽的**唯一级联** E′ → D′ → C′ → B′ → A′）====
FORM_Ap = "A'"   # H3..H7 全绿 ⇒ 所有读法、所有扫描口径下都成立
FORM_Bp = "B'"   # 保守读法（R5）有破口 ⇒ 结论必须收紧（边界清单必须逐条写出）
FORM_Cp = "C'"   # 点估计口径（R3/R4）有违例 ⇒ 「对口径稳健」被否
FORM_Dp = "D'"   # 主读法（R1/R2）被否 ⇒ 连不修正污染的 CI 下端点都 ≤ 0
FORM_Ep = "E'"   # 硬失败（H1/H2/H8/H9 红）⇒ 本轮不出判决
FORMS = (FORM_Ep, FORM_Dp, FORM_Cp, FORM_Bp, FORM_Ap)

# ==== 量的 kind 标签（量纲自检的唯一依据）====
KIND_C_UPPER = "c_upper"
KIND_C_LOWER = "c_lower"
KIND_DELTA_OBS = "delta_obs"
KIND_DELTA_CI_LO = "delta_ci_lo"
KIND_SUM = "sum_bound"        # 两种加法的**结果**（一个界），⛔ 不参与任何比较

# ⚖⚖⚖ **加法 ① 允许的比较对**（预登记 §1）
ALLOWED_PAIRS = frozenset([
    (KIND_C_UPPER, KIND_DELTA_OBS),
    (KIND_DELTA_OBS, KIND_C_UPPER),
])

# ⚖⚖⚖ **加法 ②/③ 允许的加法对**（预登记 §1 ＋ §0.5 更正 ①）
#   ② `delta_ci_lo + c_lower` ⇒ **保守读法**（抽样噪声 + 污染幅度同时最保守）
#   ③ `delta_obs  + c_lower` ⇒ **点估计读法**（同一分解 `Δ_true = Δ_obs + c` 的点估计版）
#   ⚠ 更正 ①：初版预登记只登记了 ② ⇒ ⇒ 实现用到 ③ 时**被自己的量纲门拦死**
#      ⇒ ⇒ 追加 ③（**起草层遗漏**，⛔ 不是结果驱动的改动：写实现时**尚未跑过任何东西**）。
ALLOWED_SUMS = frozenset([
    (KIND_DELTA_CI_LO, KIND_C_LOWER),
    (KIND_C_LOWER, KIND_DELTA_CI_LO),
    (KIND_DELTA_OBS, KIND_C_LOWER),
    (KIND_C_LOWER, KIND_DELTA_OBS),
])

# ⚖ 判据 id（真数据路径印的是这些；变异台按 id 认「哪条该红」）
CRIT_IDS = ("H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9")
# ⚠ **必须是 tuple 而不是生成器**（⛔ 生成器是一次性的 ⇒ ⇒ 第一次用掉之后就没了
#   ⇒ ⇒ 对账脚本会看到空列表 ⇒ ⇒ 明细会骗人）
GATE_IDS = tuple("G0-%d" % i for i in range(1, 10))

# ⚖ **硬失败**（⇒ ⇒ 形态 E′）：预登记 §3.2 的 E′ 行
HARD_FAIL_IDS = ("H1", "H2", "H8", "H9")

# ⚖ 读法 id（作用域表的行）
READINGS = ("R1", "R2", "R3", "R4", "R5", "R6")


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
    """⚖ **带 kind 标签的量** ⇒ ⇒ 量纲自检才有可核对的东西。"""
    return {"value": float(value), "kind": kind, "name": name}


def _tol_from_printed(s):
    """⚖⚖⚖ **容差由账本的打印精度推导**（⛔ 不是拍脑袋的常数）。

    账本把数印成两位小数 ⇒ ⇒ 打印精度的**半个单位** = 0.005 pp ⇒ ⇒ 这是容差的**外部依据**。
    ⚠ 打印几位 ⇒ ⇒ 容差跟着变（G0-4 守着这条）。
    """
    t = (s or "").strip()
    m = re.search(r"\.([0-9]+)", t)
    dec = len(m.group(1)) if m else 0
    return 0.5 * (10.0 ** (-dec))


# =============================================================================
# 账本解析层：全部输入从账本逐行解析（⛔ 代码里不写死任何一个数）
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
    return "\n".join(lines[s:e]), s + 1, e


def _one(pattern, text, what, flags=re.M):
    hits = list(re.finditer(pattern, text, flags))
    if len(hits) != 1:
        _die("段内「%s」按模式命中 %d 次（期望恰好 1 次 ⇒ ⇒ 锚点不唯一 ⇒ ⇒ 中止）"
             % (what, len(hits)))
    return hits[0]


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
    rebuilt = "{%s}" % ", ".join("(%d,%d)×%d" % (k[0], k[1], v) for k, v in d.items())
    norm = re.sub(r"\s+", "", s).strip("{}")
    rnorm = re.sub(r"\s+", "", rebuilt).strip("{}")
    if rnorm != norm:
        _die("(n_nz,n_zero) 分布逐位回读对不上：原文 %r ⇒ 回读 %r" % (s, rebuilt))
    return d


def _dist_text(dist):
    """⚖ 由分布**重建**成账本里印的那一串（供 H9 的逐字符回读用）。"""
    return "{%s}" % ", ".join("(%d,%d)×%d" % (k[0], k[1], v) for k, v in dist.items())


def parse_inputs(ledger_path, rev="244.81"):
    """⚖ 从账本 <rev> 段解析本轮要用的**全部**输入；**每个数都要逐位回读原文**。"""
    with open(ledger_path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    lines = text.split("\n")
    sec, sec_start, sec_end = _section(lines, rev)

    out = {"section": (sec_start, sec_end)}
    locs = {}

    def loc(m):
        """⚖ 命中位置对应的**文件行号**（1-based）⇒ ⇒ H9 要核对「解析到的行全部落在段内」。"""
        return sec_start + sec[:m.start()].count("\n")

    # ---- I1 / I2：改判数（46/56、29/56）----
    m = _one(r"改判（主口径：逐轨迹\*\*严格多数\*\*，`nT·2 > m`） \| \*\*(\d+)/(\d+)\*\* \| \*\*(\d+)/(\d+)\*\*",
             sec, "改判（主口径）行")
    out["i1_w_num"], out["i1_w_den"] = int(m.group(1)), int(m.group(2))
    out["i2_r_num"], out["i2_r_den"] = int(m.group(3)), int(m.group(4))
    locs["I1/I2"] = loc(m)

    # ---- I5：零假设基准（印的两位小数）----
    m = _one(r"零假设基准（逐轨迹平均） \| ([0-9.]+) \| ([0-9.]+)", sec, "零假设基准行")
    out["i5_w"], out["i5_r"] = float(m.group(1)), float(m.group(2))
    locs["I5"] = loc(m)

    # ---- I6：(n_nz,n_zero) 分布（两臂各一段）⇒ ⇒ 用来**现算**零假设基准 ----
    m = _one(r"\(n_nz,n_zero\) 分布：\{([^}]*)\} ｜ \{([^}]*)\}", sec, "(n_nz,n_zero) 分布行")
    out["i6_w"] = _parse_dist(m.group(1))
    out["i6_r"] = _parse_dist(m.group(2))
    locs["I6"] = loc(m)

    # ---- I7：Δ_obs 轨迹级 + 其 Newcombe95 区间（本轮的 CI_lo(traj)）----
    m = _one(r"\*\*差 ([+-][0-9.]+) pp\*\* ｜ 差区间（Newcombe95）\[([+-][0-9.]+), ([+-][0-9.]+)\]",
             sec, "差 + Newcombe95 行")
    out["i7_delta_obs"] = float(m.group(1))
    out["i7_nc_lo"] = float(m.group(2))
    out["i7_nc_hi"] = float(m.group(3))
    locs["I7"] = loc(m)

    # ---- I8：块级改判数 + **块级 Newcombe95** 区间（本轮的 CI_lo(blk)）----
    #   ⚠⚠⚖ **必须是块级 Newcombe95**（与轨迹级**同口径**）⇒ ⇒ **不是**那块级 bootstrap 区间
    #   （那是「按块重采样」的另一个来源 ⇒ ⇒ 预登记 §7 的 B-8 明写它**不参与**任何比较）
    m = _one(r"w \*\*(\d+)/(\d+)\*\* ｜ rand \*\*(\d+)/(\d+)\*\* ｜ 差 ([+-][0-9.]+) pp ｜ "
             r"差区间 \[([+-][0-9.]+), ([+-][0-9.]+)\]",
             sec, "块级改判数 + Newcombe95 行")
    out["i8_w_num"], out["i8_w_den"] = int(m.group(1)), int(m.group(2))
    out["i9_r_num"], out["i9_r_den"] = int(m.group(3)), int(m.group(4))
    out["i8_delta_obs_blk"] = float(m.group(5))
    out["i8_nc_lo"] = float(m.group(6))
    out["i8_nc_hi"] = float(m.group(7))
    locs["I8"] = loc(m)

    out["_raw_md5"] = _md5_bytes(raw)
    out["_sec"] = sec          # ⚖ 留给 H9：重建串必须**逐字符**出现在段内
    out["_lines"] = locs       # ⚖ 留给 H9：解析到的行号必须**全部落在段内**
    out["_sec_range"] = (sec_start, sec_end)

    # ---- 带 kind 标签的量（⚖ 量纲自检的唯一依据）----
    out["delta_qty"] = qty(out["i7_delta_obs"], KIND_DELTA_OBS, "delta_obs(traj)")
    out["delta_qty_blk"] = qty(out["i8_delta_obs_blk"], KIND_DELTA_OBS, "delta_obs(block)")
    out["ci_lo_traj"] = qty(out["i7_nc_lo"], KIND_DELTA_CI_LO, "newcombe_lo(traj)")
    out["ci_lo_blk"] = qty(out["i8_nc_lo"], KIND_DELTA_CI_LO, "newcombe_lo(block)")
    return out


def parse_ref_true_lo(ledger_path, rev="244.86"):
    """⚖ 从账本 <rev> 段读出「真实差（**不假定方向**）」的**下端点**（H1 的复算对象）。

    ⛔ 命中数 ≠ 1 ⇒ ⇒ 返回 None（**不崩**）⇒ ⇒ H1 判红 ⇒ ⇒ 形态 E′
       （⛔ 不是静默兜底：H1 会明确报「锚点命中 N 次」）
    """
    try:
        with open(ledger_path, "rb") as fh:
            text = fh.read().decode("utf-8")
    except OSError:
        return None, None
    lines = text.split("\n")
    try:
        sec, _s, _e = _section(lines, rev)
    except SystemExit:
        return None, None
    hits = re.findall(r"真实差（Q8 ①） \| \*\*不假定方向\*\* \| \*\*\[\+([0-9.]+), \+([0-9.]+)\] pp\*\*", sec)
    if len(hits) != 1:
        return None, len(hits)
    return (hits[0][0], hits[0][1]), len(hits)


# =============================================================================
# 口径计算层
# =============================================================================

def _wilson_z(level):
    """⚖ 由置信水平得 z（⛔ 固定的 z 表，口径参数，不是原始数）。"""
    z = {0.90: 1.6448536269514722,
         0.95: 1.959963984540054,
         0.99: 2.5758293035489004}
    if level not in z:
        _die("Wilson 置信水平 %r 不在 SPEC 里" % (level,))
    return z[level]


def wilson_bounds(k, n, level=0.95):
    """⚖ Wilson 区间（比例 × 100 ⇒ pp 口径）⇒ ⇒ **两端都算**（本轮要下界 `c_lo`）。"""
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
    · base = zero_as_half ：零格轨迹 base=**0.5**
    · base = zero_as_zero ：零格轨迹 base=**0**（极端下界）

    ⚖⚖⚖ 三个变体的基准都必须落在 [0,1] ⇒ ⇒ 越界 ⇒ ⇒ **硬失败**
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


# =============================================================================
# 量纲自检（硬门，H8）
# =============================================================================

def _md5_unchanged(path, before_md5):
    """⚖⚖⚖ **「这个文件没被改过」的判断**（H9 与 G0-7 **共用同一个函数**）。

    ⚖ **为什么要抽成函数**：把「比较表达式」改成恒真 ⇒ ⇒ **没有任何闸门能抓**
       ⇒ ⇒ 修法：① 抽成**一个函数**；② 除了正控（没碰 ⇒ 必须说「没变」）还加**负控**
       （碰一下 ⇒ 必须说「变了」）⇒ ⇒ 两个控件**共用**这个函数 ⇒ ⇒ 把它改成恒真
       ⇒ ⇒ **正控与负控同时失效** ⇒ ⇒ G0-7 自己就红 ⇒ ⇒ 抓得到。
    """
    return _md5_file(path) == before_md5


def _check_pair(kind_a, kind_b):
    """⚖⚖⚖ **加法 ① 的量纲自检**：`c_upper ↔ delta_obs` 是**唯一**允许的比较对。

    ⛔ `delta_ci_lo`（差值区间下端点）参与任何比较 ⇒ ⇒ **红**（244.87 的 H5 硬门，继续有效）
       ⇒ ⇒ 那是「+15.22 翻越 +13.01」的**假警报**。
    """
    if kind_a == KIND_DELTA_CI_LO or kind_b == KIND_DELTA_CI_LO:
        _die("H8-KIND-CILO-CUPPER: ⛔⚠⚠ **量纲自检红（H8）**：拿「w − rand 的差的区间下端点」"
             "（kind=%s）去比「污染量 c 的上界」（kind=%s）⇒ ⇒ **量纲不同** ⇒ ⇒ 假警报 ⇒ ⇒ 中止"
             % (kind_a if kind_a == KIND_DELTA_CI_LO else kind_b,
                kind_b if kind_a == KIND_DELTA_CI_LO else kind_a))
    if (kind_a, kind_b) not in ALLOWED_PAIRS:
        _die("H8-KIND-PAIR: ⛔⚠ **量纲自检红（H8）**：kind %s vs %s **不是允许的比较对** %s"
             % (kind_a, kind_b, sorted(ALLOWED_PAIRS)))


def _check_sum(kind_a, kind_b):
    """⚖⚖⚖ **加法 ② 的量纲自检**：`delta_ci_lo + c_lower` 是**唯一**允许的加法对。

    ⚖⚖⚖ **三条分支必须能被区分开**（各有各的**代号**）⇒ ⇒ 否则删掉其中一条
       ⇒ ⇒ 另一条仍会挡住 ⇒ ⇒ 护栏被削弱而没人知道 ⇒ ⇒ 变异台靠这个抓。
    """
    if {kind_a, kind_b} == {KIND_DELTA_CI_LO, KIND_C_UPPER}:
        _die("H8-KIND-CILO-CUPPER: ⛔⚠⚠ **量纲自检红（H8）**：把「差值区间下端点」"
             "（kind=%s）与「污染量 c 的上界」（kind=%s）**相加** ⇒ ⇒ 量纲不同 ⇒ ⇒ 中止"
             % (kind_a, kind_b))
    if {kind_a, kind_b} == {KIND_DELTA_CI_LO, KIND_DELTA_OBS}:
        _die("H8-KIND-CILO-DELTA: ⛔⚠⚠ **量纲自检红（H8）**：把「差值区间下端点」"
             "（kind=%s）与「观测差点估计」（kind=%s）**相加** ⇒ ⇒ 量纲不同 ⇒ ⇒ 中止"
             % (kind_a, kind_b))
    if {kind_a, kind_b} == {KIND_C_UPPER, KIND_C_LOWER}:
        _die("H8-KIND-CUPPER-PLUS-CLOWER: ⛔⚠ **量纲自检红（H8）**：把「污染量 c 的上界」"
             "（kind=%s）与「c 的下界」（kind=%s）**相加** ⇒ ⇒ 同量纲但**不是**登记的加法 ⇒ ⇒ 中止"
             % (kind_a, kind_b))
    if (kind_a, kind_b) not in ALLOWED_SUMS:
        _die("H8-KIND-SUM-UNKNOWN: ⛔⚠ **量纲自检红（H8）**：kind %s + %s **不是**允许的加法对 %s"
             % (kind_a, kind_b, sorted(ALLOWED_SUMS)))


def _kind_code(msg):
    """⚖ 从护栏的报错消息里**取出分支代号**（⛔ 不靠 `split(":")` ⇒ `_die` 加了前缀会错位）。"""
    m = re.search(r"H8-KIND-[A-Z\-]+", msg or "")
    return m.group(0) if m else "(无代号)"


def _guard_selftest():
    """⚖ **H8 的自证**：喂**未登记的配对/加法** ⇒ ⇒ 必须被判红 **且必须由对应分支判红**
    ⇒ ⇒ 否则「护栏被削弱」这件事**没人知道**（⛔ 另一条分支也能挡 ⇒ ⇒ 察觉不到）。"""
    cases = [
        (lambda: _check_pair(KIND_DELTA_CI_LO, KIND_C_UPPER), "H8-KIND-CILO-CUPPER"),
        (lambda: _check_sum(KIND_DELTA_CI_LO, KIND_C_UPPER), "H8-KIND-CILO-CUPPER"),
        (lambda: _check_sum(KIND_DELTA_CI_LO, KIND_DELTA_OBS), "H8-KIND-CILO-DELTA"),
        (lambda: _check_sum(KIND_C_UPPER, KIND_C_LOWER), "H8-KIND-CUPPER-PLUS-CLOWER"),
        # ⚖⚖⚖ **兜底分支也必须被覆盖**（⛔ 只试三条特例 ⇒ ⇒ 兜底那条被删掉时没人知道）
        #   ⇒ ⇒ 变异台 MU8 正是靠这一条抓到的（变异台第一次跑时 MU8 存活 ⇒ ⇒ 补了这一条）
        (lambda: _check_sum(KIND_SUM, KIND_C_LOWER), "H8-KIND-SUM-UNKNOWN"),
    ]
    detail = []
    for fn, want in cases:
        try:
            fn()
            return False, "⛔ 未登记配对 %s **没有**判红 ⇒ ⇒ 这条护栏是恒绿的，不可用" % want, None
        except SystemExit as e:
            code = _kind_code(str(e))
            if code != want:
                return False, ("⛔ 未登记配对虽被判红，但**不是** %s 那条分支（实得 %s）"
                               "⇒ ⇒ 护栏被削弱了却**察觉不到**" % (want, code)), code
            detail.append(want)
    return True, "未登记配对各被红（%s）⇒ 护栏在位" % "、".join(detail), detail[0]


# =============================================================================
# 扫描 + 作用域表
# =============================================================================

def canonical_scan_seq():
    """⚖ 扫描的**固定顺序**（层序：先水平后变体）。"""
    return [(lv, va) for lv in WILSON_LEVELS for va in BASE_VARIANTS]


def run_scan(I):
    """⚖ 扫描 3 档 Wilson × 3 种基准 ⇒ ⇒ 每个口径算 c 的**区间**（两端都要）。"""
    rows = []
    seq = canonical_scan_seq()
    if len(seq) != len(WILSON_LEVELS) * len(BASE_VARIANTS):
        _die("扫描序列长度异常")
    for lv, va in seq:
        base = base_from_dist(I["i6_r"], va)
        lo, hi = c_bounds(I["i2_r_num"], I["i2_r_den"], base, lv)
        rows.append({"level": lv, "variant": va, "base": base, "c_lo": lo, "cmax": hi})
    return rows


def _sum_bound(a, b):
    """⚖ **加法 ②**：`delta_ci_lo + c_lower` ⇒ ⇒ 返回一个带 kind 的界。

    ⚖ 先过量纲门（⇒ ⇒ 未登记的加法会**红**）⇒ ⇒ 再相加。
    """
    _check_sum(a["kind"], b["kind"])
    return qty(a["value"] + b["value"], KIND_SUM, "%s+%s" % (a["name"], b["name"]))


def _joint_conf(level):
    """⚖ **联合置信**（Bonferroni）：`1 − α_CI − α_Wilson(level)`。

    ⚖⚖⚖ **逐口径不同**（Wilson90/95/99 的 alpha 不同）⇒ ⇒ ⛔ **不许**三行都写 90%。
    """
    return 1.0 - ALPHA_CI - (1.0 - level)


def build_scope_table(I, rows):
    """⚖ **读法—口径作用域表**（预登记 §2 的六行 R1..R6）。"""
    dt = I["delta_qty"]
    db = I["delta_qty_blk"]
    ct = I["ci_lo_traj"]
    cb = I["ci_lo_blk"]
    tbl = []

    # R1 / R2：污染**只抬高** ⇒ ⇒ 不需要 c ⇒ ⇒ 单源 95%
    tbl.append({"id": "R1", "name": "污染只抬高 rand 臂（c ≥ 0）·轨迹级",
                "bound": ct["value"], "conf": 1.0 - ALPHA_CI,
                "per_caliber": False, "note": "单源 95%（不需要 c）"})
    tbl.append({"id": "R2", "name": "污染只抬高 rand 臂（c ≥ 0）·块级",
                "bound": cb["value"], "conf": 1.0 - ALPHA_CI,
                "per_caliber": False, "note": "单源 95%（不需要 c）"})

    # R3：点估计 · 轨迹级（补守 244.87 的紧端）
    per = []
    for r in rows:
        b = _sum_bound(dt, qty(r["c_lo"], KIND_C_LOWER, "c_lo"))
        per.append({"level": r["level"], "variant": r["variant"], "bound": b["value"], "ok": b["value"] > 0})
    tbl.append({"id": "R3", "name": "不假定方向·点估计·轨迹级",
                "per_caliber": True, "items": per, "conf": None,
                "note": "补守 244.87 只印不守的紧端"})

    # R4：点估计 · 块级（⚠ 口径混合：c 是轨迹级算的）
    per = []
    for r in rows:
        b = _sum_bound(db, qty(r["c_lo"], KIND_C_LOWER, "c_lo"))
        per.append({"level": r["level"], "variant": r["variant"], "bound": b["value"], "ok": b["value"] > 0})
    tbl.append({"id": "R4", "name": "不假定方向·点估计·块级（⚠口径混合）",
                "per_caliber": True, "items": per, "conf": None,
                "note": "⚠ c 是轨迹级算的 ⇒ 跨口径相加 ⇒ 只读成「轨迹级污染下界放到块级观测差上」"})

    # R5：保守读法 · 轨迹级（抽样噪声 + 污染幅度同时最保守）
    per = []
    for r in rows:
        b = _sum_bound(ct, qty(r["c_lo"], KIND_C_LOWER, "c_lo"))
        per.append({"level": r["level"], "variant": r["variant"], "bound": b["value"],
                    "ok": b["value"] > 0, "conf": _joint_conf(r["level"])})
    tbl.append({"id": "R5", "name": "不假定方向·保守（CI+c 同时最保守）·轨迹级",
                "per_caliber": True, "items": per, "conf": None,
                "note": "联合置信逐口径不同（Bonferroni）"})

    # R6：保守读法 · 块级（⚠ 口径混合；⚠ 只作示意，不参与形态）
    per = []
    for r in rows:
        b = _sum_bound(cb, qty(r["c_lo"], KIND_C_LOWER, "c_lo"))
        per.append({"level": r["level"], "variant": r["variant"], "bound": b["value"],
                    "ok": b["value"] > 0, "conf": _joint_conf(r["level"])})
    tbl.append({"id": "R6", "name": "不假定方向·保守·块级（⚠口径混合·示意）",
                "per_caliber": True, "items": per, "conf": None,
                "note": "⚠ 不参与形态判定（跨口径相加）"})

    return tbl


# =============================================================================
# 判据 + 形态
# =============================================================================

def _chk(cid, name, ok, detail):
    return (cid, name, bool(ok), detail)


def classify(flags):
    """⚖⚖⚖ **形态的**唯一级联**（预登记 §3.2）：E′ → D′ → C′ → B′ → A′。

    ⚖ **每个输入只落一个形态** ⇒ ⇒ 互斥且穷尽（G0-2 穷举验证）。
    """
    if any(not flags.get(c, True) for c in HARD_FAIL_IDS):
        return FORM_Ep
    if not flags.get("H3", True) or not flags.get("H4", True):
        return FORM_Dp
    if not flags.get("H5", True) or not flags.get("H6", True):
        return FORM_Cp
    if not flags.get("H7", True):
        return FORM_Bp
    return FORM_Ap


def judge(I, rows, tbl, ledger_path, ref_true_lo):
    """⚖ 主判据：H1..H9 ⇒ ⇒ 形态 + 理由。"""
    res = []
    dt = I["delta_qty"]

    # ---- H1：解析链复算门槛（现算 Δ_obs(traj)+c_lo(main) 必须 == 244.86 段印的 +20.26）----
    #   ⚖⚖⚖ **三半都要**（同一条判据的加严，不是新增判据）：
    #     ① 轨迹级**改判数独立复算**的 Δ_obs 必须与账本印的 Δ_obs 对得上；
    #     ② 块级**改判数独立复算**的 Δ_obs(blk) 必须与账本印的对得上；
    #     ③ 现算 `Δ_obs(印) + c_lo(main)` 必须与 244.86 段印的「真实差（不假定方向）」下端点对得上。
    #   （⛔ 少了 ①/② ⇒ 「解析链跑偏了」根本看不出来 ⇒ ⇒ 这两半是 H1 的**本职**）
    delta_calc = (I["i1_w_num"] - I["i2_r_num"]) * 100.0 / float(I["i1_w_den"])
    delta_blk_calc = (I["i8_w_num"] - I["i9_r_num"]) * 100.0 / float(I["i8_w_den"])
    tol_d = _tol_from_printed("%+.2f" % I["i7_delta_obs"])
    tol_b = _tol_from_printed("%+.2f" % I["i8_delta_obs_blk"])
    d_ok = abs(delta_calc - I["i7_delta_obs"]) <= tol_d
    b_ok = abs(delta_blk_calc - I["i8_delta_obs_blk"]) <= tol_b
    if ref_true_lo is None:
        res.append(_chk("H1", "解析链复算门槛", False,
                         "⛔ 244.86 段的「真实差（不假定方向）」锚点读不到 ⇒ ⇒ 中止"))
        calc_main = None
    else:
        printed_lo, printed_hi = ref_true_lo
        tol = _tol_from_printed(printed_lo)
        row_main = [r for r in rows if r["level"] == MAIN_LEVEL and r["variant"] == "main"][0]
        calc_main = dt["value"] + row_main["c_lo"]
        ok = d_ok and b_ok and (abs(calc_main - float(printed_lo)) <= tol)
        res.append(_chk("H1", "解析链复算门槛", ok,
                         "轨迹级改判数复算 Δ_obs=%+.4f vs 印 %+.2f（容差 %.4f，%s）｜ "
                         "块级改判数复算 Δ_obs(blk)=%+.4f vs 印 %+.2f（容差 %.4f，%s）｜ "
                         "现算 Δ_obs(印)+c_lo(main)=%+.4f pp ｜ 244.86 段印 %s pp ｜ 容差 %.4f pp"
                         "（= 账本打印精度的半个单位）"
                         % (delta_calc, I["i7_delta_obs"], tol_d, "对得上" if d_ok else "**对不上**",
                            delta_blk_calc, I["i8_delta_obs_blk"], tol_b, "对得上" if b_ok else "**对不上**",
                            calc_main, printed_lo, tol)))

    # ---- H2：扫描完备性（9 口径 × 2 个 Δ_obs 口径，顺序固定）----
    want = canonical_scan_seq()
    got = [(r["level"], r["variant"]) for r in rows]
    n_cells = len(rows) * 2
    ok2 = (got == want) and len(rows) == 9 and n_cells == 18
    res.append(_chk("H2", "扫描完备性（9 口径 × 2 个 Δ_obs 口径）", ok2,
                     "%d 口径 × 2 = %d 单元 ｜ 顺序固定 %s" % (len(rows), n_cells, got == want)))

    # ---- H3 / H4：R1 / R2（污染只抬高 ⇒ 不需要 c）----
    r1 = [t for t in tbl if t["id"] == "R1"][0]
    r2 = [t for t in tbl if t["id"] == "R2"][0]
    res.append(_chk("H3", "读法 R1（污染只抬高·轨迹级·单源 95%）", r1["bound"] > 0,
                     "CI_lo(traj)=%+.4f pp（95%% 单源）⇒ ⇒ %s" % (r1["bound"], "成立" if r1["bound"] > 0 else "**不成立**")))
    res.append(_chk("H4", "读法 R2（污染只抬高·块级·单源 95%）", r2["bound"] > 0,
                     "CI_lo(blk)=%+.4f pp（95%% 单源）⇒ ⇒ %s" % (r2["bound"], "成立" if r2["bound"] > 0 else "**不成立**")))

    # ---- H5 / H6 / H7：逐口径 ----
    for cid, rid, label in (("H5", "R3", "读法 R3（不假定方向·点估计·轨迹级）"),
                            ("H6", "R4", "读法 R4（不假定方向·点估计·块级·⚠口径混合）"),
                            ("H7", "R5", "读法 R5（不假定方向·保守·轨迹级）")):
        t = [x for x in tbl if x["id"] == rid][0]
        viol = [it for it in t["items"] if not it["ok"]]
        det = "%d/%d 口径成立" % (len(t["items"]) - len(viol), len(t["items"]))
        if viol:
            det += " ｜ 违例：" + ", ".join("%.2f/%s(%+.4f)" % (v["level"], v["variant"], v["bound"]) for v in viol)
        res.append(_chk(cid, label, len(viol) == 0, det))

    # ---- H8：量纲硬门（自证）----
    g_ok, g_msg, _code = _guard_selftest()
    res.append(_chk("H8", "量纲硬门（未登记的配对/加法必须被红）", g_ok, g_msg))

    # ---- H9：只读 + 出处 ----
    md5_ok = _md5_unchanged(ledger_path, I["_raw_md5"])
    sec_lo, sec_hi = I["_sec_range"]
    out_of_range = sorted(k for k, v in I["_lines"].items() if not (sec_lo <= v <= sec_hi))
    rebuilds = [
        ("改判（w）", "%d/%d" % (I["i1_w_num"], I["i1_w_den"])),
        ("改判（rand）", "%d/%d" % (I["i2_r_num"], I["i2_r_den"])),
        ("Δ_obs(traj)", "%+.2f" % I["i7_delta_obs"]),
        # ⚖⚖⚖ 区间**整段**重建（⛔ 不许只重建下端点）⇒ ⇒ 「拿上端点当下端点」这类错
        #   会让重建串变成 "[+45.36, +45.36]" ⇒ ⇒ 段内命不中 ⇒ ⇒ H9 红
        ("CI_lo(traj)", "[%+.2f, %+.2f]" % (I["i7_nc_lo"], I["i7_nc_hi"])),
        ("Δ_obs(blk)", "%+.2f" % I["i8_delta_obs_blk"]),
        ("CI_lo(blk)", "[%+.2f, %+.2f]" % (I["i8_nc_lo"], I["i8_nc_hi"])),
        ("(n_nz,n_zero) 分布（rand）", _dist_text(I["i6_r"])),
    ]
    missing = [name for name, s in rebuilds if s not in I["_sec"]]
    h9_ok = md5_ok and (not out_of_range) and (not missing)
    res.append(_chk("H9", "只读（md5 不变 + 行号落在段内 + 重建串逐字符在段内）", h9_ok,
                     "md5 %s ｜ 段范围 [%d, %d] ｜ 越界行 %s ｜ 重建串缺失 %s"
                     % ("不变" if md5_ok else "**变了**", sec_lo, sec_hi,
                        out_of_range or "无", missing or "无")))

    flags = {cid: ok for cid, _n, ok, _d in res}
    form = classify(flags)
    reason = _reason(form, res, flags, tbl)
    return form, res, reason, flags


def _reason(form, res, flags, tbl):
    def f(cid):
        for c, _n, ok, _d in res:
            if c == cid:
                return ok
        return None

    if form == FORM_Ep:
        red = [c for c in HARD_FAIL_IDS if not flags.get(c, True)]
        return ("硬失败（%s 红）⇒ ⇒ **前提层面**失败 ⇒ ⇒ 本轮不出判决" % "、".join(red))
    if form == FORM_Dp:
        return ("主读法被否：CI_lo(traj)=%+.4f / CI_lo(blk)=%+.4f ⇒ ⇒ 连**不修正污染**的差区间下端点都 ≤ 0"
                % (tbl[0]["bound"], tbl[1]["bound"]))
    if form == FORM_Cp:
        bad = []
        for rid in ("R3", "R4"):
            t = [x for x in tbl if x["id"] == rid][0]
            v = [it for it in t["items"] if not it["ok"]]
            if v:
                bad.append("%s 违例 %d 个" % (rid, len(v)))
        return ("点估计口径有违例（%s）⇒ ⇒ 「对口径稳健」被否" % "；".join(bad))
    if form == FORM_Bp:
        t = [x for x in tbl if x["id"] == "R5"][0]
        v = [it for it in t["items"] if not it["ok"]]
        viol = ", ".join("%.2f/%s(%+.4f, 联合 %.0f%%)"
                         % (x["level"], x["variant"], x["bound"], 100 * x["conf"]) for x in v)
        return ("保守读法（R5）在 %d/%d 个口径有破口（%s）⇒ ⇒ **结论要收紧**："
                "「污染解释不了观测差」在**污染只抬高**的读法下成立（不依赖 c），"
                "在**点估计**口径下成立；在**抽样噪声与污染幅度同时最保守**的读法下**只在部分口径成立**"
                % (len(v), len(t["items"]), viol))
    r3 = [x for x in tbl if x["id"] == "R3"][0]
    r5 = [x for x in tbl if x["id"] == "R5"][0]
    return ("全绿：「污染解释不了观测差」在所有读法、所有扫描口径下成立"
            "（R3 最紧 %+.4f pp ｜ R5 最紧 %+.4f pp）"
            % (min(i["bound"] for i in r3["items"]), min(i["bound"] for i in r5["items"])))


# =============================================================================
# Phase-0 自检（合成夹具、⛔ 零账本、⛔ 零 GPU）
# =============================================================================

def _tmp_root():
    env = os.environ.get("R24488_TMPDIR")
    if env:
        os.makedirs(env, exist_ok=True)
        return env
    d = os.path.join(tempfile.gettempdir(), "r24488_%d" % os.getpid())
    os.makedirs(d, exist_ok=True)
    return d


def fixture_text(w_num=46, w_den=56, r_num=29, r_den=56,
                 dist_r="{(2,1)×2, (3,0)×54}",
                 delta_traj="+30.36", nc_lo="+13.01", nc_hi="+45.36",
                 blk_w=21, blk_den=28, blk_r=6, blk_delta="+53.57",
                 blk_nc_lo="+27.79", blk_nc_hi="+70.23",
                 true_lo="+20.26", true_hi="+45.58",
                 drop_ref=False, drop_i1=False, dup_anchor=False):
    """⚖ **合成账本片段**（格式逐字照抄真账本 244.81 / 244.86 段的锚点行）。"""
    lines = []
    lines.append("# 合成夹具账本（244.88 Phase-0 用；⛔ 不是真账本、⛔ 零 GPU）")
    lines.append("")
    lines.append("## 修订 244.81 —— （合成）固定剂量下的判决数")
    lines.append("")
    if not drop_i1:
        lines.append("| 改判（主口径：逐轨迹**严格多数**，`nT·2 > m`） | **%d/%d** | **%d/%d** |"
                     % (w_num, w_den, r_num, r_den))
    lines.append("| 比例区间（Wilson95） | [+70.16, +90.00] | [+39.01, +64.33] |")
    lines.append("| 零假设基准（逐轨迹平均） | 0.4955 | 0.4911 |")
    lines.append("")
    lines.append("  · (n_nz,n_zero) 分布：{(2,0)×1, (3,0)×55} ｜ %s" % dist_r)
    lines.append("")
    lines.append("· **差 %s pp** ｜ 差区间（Newcombe95）[%s, %s] ｜ 跨臂 Fisher p = 0.001152。"
                 % (delta_traj, nc_lo, nc_hi))
    lines.append("")
    lines.append("· w **%d/%d** ｜ rand **%d/%d** ｜ 差 %s pp ｜ 差区间 [%s, %s] ｜ "
                 "Fisher p = 0.000131。" % (blk_w, blk_den, blk_r, blk_den, blk_delta, blk_nc_lo, blk_nc_hi))
    lines.append("")
    lines.append("· **区间**：按**块**重采样（承认聚类）的 bootstrap ⇒ ⇒ 块级差 **%s pp**，"
                 "95%% 区间 **[+32.14, +75.00] pp**。" % blk_delta)
    if dup_anchor:
        lines.append("| 比例区间（Wilson95） | [+70.16, +90.00] | [+39.01, +64.33] |")
    lines.append("")
    lines.append("## 修订 244.86 —— （合成）对照臂的零假设地位")
    lines.append("")
    if not drop_ref:
        lines.append("| 真实差（Q8 ①） | **不假定方向** | **[%s, %s] pp** |" % (true_lo, true_hi))
    lines.append("")
    lines.append("## 修订 244.87 —— （合成）结束")
    lines.append("")
    return "\n".join(lines)


def _run_fixture(tmpdir, text, tag, mutate=None):
    """⚖ 写合成账本 → 解析 → 扫描 → 作用域表 → 判 ⇒ ⇒ 返回 (form, res, flags, I, rows, tbl, path)。"""
    path = os.path.join(tmpdir, "ledger_%s.md" % tag)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    I = parse_inputs(path)
    if mutate is not None:
        mutate(I, path)
    rows = run_scan(I)
    tbl = build_scope_table(I, rows)
    ref, _n = parse_ref_true_lo(path)
    form, res, reason, flags = judge(I, rows, tbl, path, ref)
    return form, res, flags, I, rows, tbl, path


def _judge_with(tmpdir, text, tag, rows_mut=None, inputs_mut=None, after_parse=None):
    """⚖ 在合成夹具上**带覆写**地跑一遍判定（给 G0-9 用：逐条把判据逼红）。

    ⚖ 返回值与 `_run_fixture` **完全一致**（7 元组）⇒ ⇒ 调用方不会解包错。
    """
    path = os.path.join(tmpdir, "ledger_%s.md" % tag)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    I = parse_inputs(path)
    if inputs_mut is not None:
        inputs_mut(I)
    if after_parse is not None:
        after_parse(path)
    rows = run_scan(I)
    if rows_mut is not None:
        rows = rows_mut(rows)
    tbl = build_scope_table(I, rows)
    ref, _n = parse_ref_true_lo(path)
    form, res, reason, flags = judge(I, rows, tbl, path, ref)
    return form, res, flags, I, rows, tbl, path


def _ids(res):
    return {cid: ok for cid, _n, ok, _d in res}


def selftest():
    """⚖⚖⚖ **Phase-0 闸门**（预登记 §4：G0-1 .. G0-8，合成夹具、⛔ 零账本、⛔ 零 GPU）。

    G0-1：缺锚点 ⇒ ⇒ **构建失败**（⛔ 不许静默降级）
    G0-2：形态级联**互斥且穷尽**（穷举 2^9 组合）
    G0-3：H8 量纲门**能红**且三条分支**可区分**
    G0-4：容差**由打印精度推导**
    G0-5：加法公式与**手算**一致（正控）
    G0-6：**负控**：把 c_lo 换成 c_hi ⇒ ⇒ H5/H6/H7 必须红
    G0-7：**账本负控**：改动账本 ⇒ ⇒ H1/H9 必须检出（正控与负控共用同一个函数）
    G0-8：**幂等**：同一输入跑两次 ⇒ ⇒ 输出逐字节相同
    """
    # ⚠⚠⚖ `global` 必须**在使用之前**声明（⛔ 否则 compile 期就报
    #   「name '_guard_selftest' is used prior to global declaration」⇒ ⇒ **整份文件跑不起来**）
    global _guard_selftest
    fails = []
    tmp = _tmp_root()
    own_tmp = not os.environ.get("R24488_TMPDIR")
    try:
        # ---------- G0-1：缺锚点 ⇒ 构建失败（⛔ 不许静默降级）----------
        try:
            _run_fixture(tmp, fixture_text(drop_i1=True), "G01")
            ok1 = False
            d1 = "缺 244.81 锚点却**没有**构建失败 ⇒ ⇒ 静默降级"
        except SystemExit:
            ok1 = True
            d1 = "缺 244.81 锚点 ⇒ 构建失败（⛔ 不静默降级）"
        # ⛔ 另外：缺 244.86 的参照锚点 ⇒ ⇒ **不崩**，而是 H1 红 ⇒ ⇒ 形态 E′（硬失败）
        _f1b, res1b, fl1b, _I1b, _r1b, _t1b, _p1b = _run_fixture(tmp, fixture_text(drop_ref=True), "G01b")
        ok1b = (fl1b.get("H1") is False) and (_f1b == FORM_Ep)
        print("[%s] G0-1（缺锚点必须构建失败） ⇒ ⇒ %s ｜ 缺参照锚点 ⇒ H1 红 ⇒ 形态 %s ⇒ ⇒ %s"
              % ("PASS" if (ok1 and ok1b) else "FAIL", d1, _f1b,
                 "两条都符合" if (ok1 and ok1b) else "**有一条不符合**"))
        if not (ok1 and ok1b):
            fails.append("G0-1")

        # ---------- G0-2：形态级联互斥且穷尽（穷举 2^9）----
        # ⚖⚖⚖ **期望级联里的硬失败集合必须「手写」**（⛔ **不许**从模块常量 `HARD_FAIL_IDS` 派生）
        #   ⇒ ⇒ 否则「把常量改掉」这种变异**两边一起变** ⇒ ⇒ 闸门看不见 ⇒ ⇒ 恒绿
        #   ⇒ ⇒ 变异台 MU1 正是靠这一条抓到的（变异台第一次跑时 MU1 存活 ⇒ ⇒ 补了这一条）
        hard_literal = ("H1", "H2", "H8", "H9")
        n_bad = 0
        n_total = 0
        for mask in range(512):
            flags = {("H%d" % (i + 1)): bool(mask & (1 << i)) for i in range(9)}
            n_total += 1
            got = classify(flags)
            # ⚖ 期望：按级联 E′ → D′ → C′ → B′ → A′ 逐级判定（硬失败集合用**手写**的那一份）
            if any(not flags[c] for c in hard_literal):
                want = FORM_Ep
            elif (not flags["H3"]) or (not flags["H4"]):
                want = FORM_Dp
            elif (not flags["H5"]) or (not flags["H6"]):
                want = FORM_Cp
            elif not flags["H7"]:
                want = FORM_Bp
            else:
                want = FORM_Ap
            if got != want or got not in FORMS:
                n_bad += 1
        # ⚖ 而且：模块里的硬失败集合必须与**手写**的那一份**逐条相同**
        if set(HARD_FAIL_IDS) != set(hard_literal):
            n_bad += 1
        ok2 = (n_bad == 0)
        print("[%s] G0-2（形态级联互斥且穷尽） 穷举 %d 组合 ｜ 不合规 %d ⇒ ⇒ %s"
              % ("PASS" if ok2 else "FAIL", n_total, n_bad,
                 "每个输入都落且只落一个形态" if ok2 else "**有落空或优先级错**"))
        if not ok2:
            fails.append("G0-2")

        # ---------- G0-3：H8 量纲门能红且分支可区分 ----------
        g_ok, g_msg, g_code = _guard_selftest()
        ok3 = g_ok
        print("[%s] G0-3（H8 量纲门能红且分支可区分） ⇒ ⇒ %s" % ("PASS" if ok3 else "FAIL", g_msg))
        if not ok3:
            fails.append("G0-3")

        # ---------- G0-4：容差由打印精度推导 ----------
        t2 = _tol_from_printed("+20.26")
        t3 = _tol_from_printed("+20.3")
        t4 = _tol_from_printed("+20")
        ok4 = (abs(t2 - 0.005) < 1e-12 and abs(t3 - 0.05) < 1e-12 and abs(t4 - 0.5) < 1e-12)
        print("[%s] G0-4（容差由打印精度推导） 两位⇒%.4f ｜ 一位⇒%.4f ｜ 整数⇒%.4f ⇒ ⇒ %s"
              % ("PASS" if ok4 else "FAIL", t2, t3, t4,
                 "容差跟着打印精度走" if ok4 else "**没有**"))
        if not ok4:
            fails.append("G0-4")

        # ---------- G0-5：正控 —— 加法公式与手算一致 ----------
        _f, res, _fl, I, rows, tbl, _p = _run_fixture(tmp, fixture_text(), "G05")
        ids = _ids(res)
        r3 = [t for t in tbl if t["id"] == "R3"][0]
        r5 = [t for t in tbl if t["id"] == "R5"][0]
        row_main = [r for r in rows if r["level"] == MAIN_LEVEL and r["variant"] == "main"][0]
        hand_r3 = I["i7_delta_obs"] + row_main["c_lo"]
        hand_r5 = I["i7_nc_lo"] + row_main["c_lo"]
        got_r3 = [i for i in r3["items"] if i["level"] == MAIN_LEVEL and i["variant"] == "main"][0]["bound"]
        got_r5 = [i for i in r5["items"] if i["level"] == MAIN_LEVEL and i["variant"] == "main"][0]["bound"]
        # R4 的公式必须用**块级** Δ_obs（⇒ ⇒ 跨口径串会被抓到）
        r4 = [t for t in tbl if t["id"] == "R4"][0]
        hand_r4 = I["i8_delta_obs_blk"] + row_main["c_lo"]
        got_r4 = [i for i in r4["items"] if i["level"] == MAIN_LEVEL and i["variant"] == "main"][0]["bound"]
        # 联合置信（Bonferroni）逐口径：90% / 85% / 94% ⇒ ⇒ 三行**不许**都写 90%
        conf_ok = (abs(_joint_conf(0.95) - 0.90) < 1e-12 and abs(_joint_conf(0.90) - 0.85) < 1e-12
                   and abs(_joint_conf(0.99) - 0.94) < 1e-12)
        ok5 = (abs(got_r3 - hand_r3) < 1e-9 and abs(got_r5 - hand_r5) < 1e-9
               and abs(got_r4 - hand_r4) < 1e-9 and conf_ok
               and ids.get("H1") is True and ids.get("H9") is True)
        print("[%s] G0-5（正控：加法与手算一致） R3 手算%+.6f 实现%+.6f ｜ R5 手算%+.6f 实现%+.6f "
              "｜ R4 手算%+.6f 实现%+.6f ｜ 联合置信 90/85/94%%=%s ⇒ ⇒ %s"
              % ("PASS" if ok5 else "FAIL", hand_r3, got_r3, hand_r5, got_r5,
                 hand_r4, got_r4, conf_ok,
                 "一致" if ok5 else "**对不上**"))
        if not ok5:
            fails.append("G0-5")

        # ---------- G0-6：负控 —— 两条互补（预登记 §0.5' 更正 ④）----------
        #   ① 把 c_lo 换成**很负的值** ⇒ ⇒ H5/H6/H7 必须红（证明它们在用传进来的 c_lo）
        #   ② 每一行必须 c_lo < c_hi（证明 c_lo 真的是**低端**）
        #   ⚠⛔ 原预登记写的是「把 c_lo 换成 c_hi ⇒ 必须红」⇒ ⇒ **数学上不可能红**
        #      （界只会变大）⇒ ⇒ 那是一条**恒不红**的检查 ⇒ ⇒ 已按更正 ④ 改成这两条。
        _f6, res6, _fl6, I6, rows6, _tbl6, p6 = _run_fixture(tmp, fixture_text(), "G06")
        rows6b = [dict(r, c_lo=-100.0) for r in rows6]
        tbl6b = build_scope_table(I6, rows6b)
        _f6b, res6b, _reason6b, _flags6b = judge(I6, rows6b, tbl6b, p6, ("+20.26", "+45.58"))
        ids6 = _ids(res6b)
        red_ok = (ids6.get("H5") is False and ids6.get("H6") is False and ids6.get("H7") is False)
        ends_ok = all(r["c_lo"] < r["cmax"] for r in rows6)
        ok6 = red_ok and ends_ok
        print("[%s] G0-6（负控：① c_lo 换成 −100 ⇒ H5/H6/H7 必须红 ｜ ② c_lo < c_hi）"
              " 红=%s ｜ 端点序=%s ⇒ ⇒ %s"
              % ("PASS" if ok6 else "FAIL", red_ok, ends_ok,
                 "两条都符合（⇒ 它们真的在看低端）" if ok6 else "**有一条不符合**"))
        if not ok6:
            fails.append("G0-6")

        # ---------- G0-7：账本负控 —— 改动账本 ⇒ H1/H9 必须检出 ----------
        _f7, res7, _fl7, I7, _r7, _t7, p7 = _run_fixture(tmp, fixture_text(), "G07")
        ids7 = _ids(res7)
        before = _md5_file(p7)
        with io.open(p7, "a", encoding="utf-8", newline="") as fh:
            fh.write("\n（负控：碰一下账本）\n")
        after = _md5_file(p7)
        detected = (before != after) and (not _md5_unchanged(p7, before))
        ok7 = detected and ids7.get("H9") is True
        print("[%s] G0-7（账本负控：碰一下必须被检出） md5 变了=%s 检测函数说没变=%s ⇒ ⇒ %s"
              % ("PASS" if ok7 else "FAIL", before != after, not detected,
                 "检出" if detected else "**没检出**"))
        if not ok7:
            fails.append("G0-7")

        # ---------- G0-8：幂等 —— 同一输入跑两次 ⇒ ⇒ 输出逐字节相同 ----------
        _fa, resa, fla, Ia, rowa, tbla, pa = _run_fixture(tmp, fixture_text(), "G08a")
        _fb, resb, flb, Ib, rowb, tblb, pb = _run_fixture(tmp, fixture_text(), "G08b")
        oa = _render_result(_fa, resa, fla, rowa, tbla)
        ob = _render_result(_fb, resb, flb, rowb, tblb)
        ok8 = (oa == ob) and len(oa) > 0
        print("[%s] G0-8（幂等：同一输入跑两次 ⇒ 输出逐字节相同） 长度 %d/%d ｜ 逐字节相同=%s ⇒ ⇒ %s"
              % ("PASS" if ok8 else "FAIL", len(oa), len(ob), oa == ob,
                 "幂等" if ok8 else "**两次输出不同**"))
        if not ok8:
            fails.append("G0-8")

        # ---------- G0-9：H1..H9 每条都能红（期望红的 id 是**手写**的）----------
        red_cases = []
        # H1：缺 244.86 参照锚点 ⇒ ⇒ H1 红
        _f, res, _fl, _I, _r, _t, _p = _run_fixture(tmp, fixture_text(drop_ref=True), "G09H1")
        red_cases.append(("H1", _ids(res), "缺 244.86 参照锚点"))
        # H1（另一半）：**改判数被改**而印的 Δ_obs 不变 ⇒ ⇒ 「改判数复算」那一半必须红
        _f, res, _fl, _I, _r, _t, _p = _run_fixture(
            tmp, fixture_text(w_num=31), "G09H1b")
        red_cases.append(("H1", _ids(res), "w 臂改判数被改成 31/56（印的 Δ_obs 不变）"))
        # H1（第三半）：**244.86 段印的参照值被改** ⇒ ⇒ 「现算 vs 印」那一半必须红
        _f, res, _fl, _I, _r, _t, _p = _run_fixture(
            tmp, fixture_text(true_lo="+21.00"), "G09H1c")
        red_cases.append(("H1", _ids(res), "244.86 段印的参照下端点被改成 +21.00"))
        # H1（块级那一半）：**块级改判数被改**而印的 Δ_obs(blk) 不变 ⇒ ⇒ 那一半必须红
        _f, res, _fl, _I, _r, _t, _p = _run_fixture(
            tmp, fixture_text(blk_w=20), "G09H1d")
        red_cases.append(("H1", _ids(res), "块级 w 臂改判数被改成 20/28（印的 Δ_obs(blk) 不变）"))
        # H2：少算一个口径 ⇒ ⇒ H2 红
        _f, res, _fl, _I, _r, _t, _p = _judge_with(tmp, fixture_text(), "G09H2",
                                                    rows_mut=lambda rs: rs[:-1])
        red_cases.append(("H2", _ids(res), "扫描被截短成 8 个口径"))
        # H3：CI_lo(traj) 变成负数 ⇒ ⇒ H3 红
        _f, res, _fl, _I, _r, _t, _p = _judge_with(
            tmp, fixture_text(), "G09H3",
            inputs_mut=lambda I: I["ci_lo_traj"].update({"value": -5.0}))
        red_cases.append(("H3", _ids(res), "CI_lo(traj) 被改成 −5.0 pp"))
        # H4：CI_lo(blk) 变成负数 ⇒ ⇒ H4 红
        _f, res, _fl, _I, _r, _t, _p = _judge_with(
            tmp, fixture_text(), "G09H4",
            inputs_mut=lambda I: I["ci_lo_blk"].update({"value": -5.0}))
        red_cases.append(("H4", _ids(res), "CI_lo(blk) 被改成 −5.0 pp"))
        # H5 / H6 / H7：把 c_lo 换成很负的值 ⇒ ⇒ 三条都红
        _f, res, _fl, _I, _r, _t, _p = _judge_with(
            tmp, fixture_text(), "G09H567",
            rows_mut=lambda rs: [dict(r, c_lo=-100.0) for r in rs])
        ids567 = _ids(res)
        red_cases.append(("H5", ids567, "c_lo 被换成 −100.0 pp"))
        red_cases.append(("H6", ids567, "c_lo 被换成 −100.0 pp"))
        red_cases.append(("H7", ids567, "c_lo 被换成 −100.0 pp"))
        # H8：让量纲门自证**失守** ⇒ ⇒ H8 必须红
        #   ⚠⚖⚖ **这里必须是「失守」（返回 False），⛔ 不是「恒绿」（返回 True）** ——
        #   ⇒ ⇒ 判据 H8 读的是 `g_ok` ⇒ ⇒ 护栏失守 ⇒ ⇒ H8 红
        #   ⇒ ⇒ 若有人把 H8 改成**恒绿**，这一步就抓不到 ⇒ ⇒ 变异台 MU33 靠这条抓
        _orig_guard = _guard_selftest
        try:
            _guard_selftest = lambda: (False, "假装护栏失守", None)
            _f, res, _fl, _I, _r, _t, _p = _run_fixture(tmp, fixture_text(), "G09H8")
        finally:
            _guard_selftest = _orig_guard
        red_cases.append(("H8", _ids(res), "量纲门自证被改成「失守」（H8 必须红）"))
        # H9：解析完账本后碰一下账本 ⇒ ⇒ H9 红
        def _touch(path):
            with io.open(path, "a", encoding="utf-8", newline="") as fh:
                fh.write("\n（G0-9 负控：碰一下账本）\n")
        _f, res, _fl, _I, _r, _t, _p = _judge_with(tmp, fixture_text(), "G09H9", after_parse=_touch)
        red_cases.append(("H9", _ids(res), "解析后碰一下账本"))
        # H9（另一半）：**解析到的行号落到段外** ⇒ ⇒ 「行号在段内」那一半必须红
        def _out_of_range(I):
            I["_lines"] = dict(I["_lines"])
            I["_lines"]["I7"] = 1        # 1 号行在 244.81 段**之外**
        _f, res, _fl, _I, _r, _t, _p = _judge_with(tmp, fixture_text(), "G09H9b",
                                                    inputs_mut=_out_of_range)
        red_cases.append(("H9", _ids(res), "解析到的行号被改到段外"))

        bad = [(cid, why) for cid, idsx, why in red_cases if idsx.get(cid) is not False]
        ok9 = (len(bad) == 0)
        print("[%s] G0-9（H1..H9 每条都能红） 逐条构造 %d 例 ｜ 没红的 %s ⇒ ⇒ %s"
              % ("PASS" if ok9 else "FAIL", len(red_cases), bad or "无",
                 "每条判据都能被逼红" if ok9 else "**有判据逼不红**"))
        if not ok9:
            fails.append("G0-9")

    finally:
        if own_tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    print("")
    print("SELFTEST_GATES=%d ｜ FAIL=%d ｜ %s" % (len(GATE_IDS), len(fails), fails or "全绿"))
    return 0 if not fails else 1


def _render_result(form, res, flags, rows, tbl):
    """⚖ 把一次判决渲染成**确定性文本**（给 G0-8 的幂等检查用）。

    ⚖⚖⚖ 必须**完全确定**（⛔ 不许含时间戳、路径、内存地址）⇒ ⇒ 否则幂等检查本身是假的。
    """
    out = ["FORM=%s" % form]
    for cid, name, ok, detail in res:
        out.append("%s|%s|%s|%s" % (cid, name, "PASS" if ok else "FAIL", detail))
    for r in rows:
        out.append("ROW|%.2f|%s|%.6f|%+.6f|%+.6f" % (r["level"], r["variant"], r["base"], r["c_lo"], r["cmax"]))
    for t in tbl:
        if not t["per_caliber"]:
            out.append("TBL|%s|%+.6f|%.6f" % (t["id"], t["bound"], t["conf"]))
        else:
            for it in t["items"]:
                out.append("TBL|%s|%.2f|%s|%+.6f|%s" % (t["id"], it["level"], it["variant"],
                                                         it["bound"], "1" if it["ok"] else "0"))
    return "\n".join(out) + "\n"


def print_spec():
    print("⚖ 244.88 保守读法与口径边界 —— SPEC")
    print("  形态：%s" % " / ".join(FORMS))
    print("  判据：%s" % "、".join(CRIT_IDS))
    print("  闸门：%s" % "、".join(GATE_IDS))
    print("  读法：%s" % "、".join(READINGS))
    print("  允许的比较对：%s" % sorted(ALLOWED_PAIRS))
    print("  允许的加法对：%s" % sorted(ALLOWED_SUMS))


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
    tbl = build_scope_table(I, rows)
    ref, ref_hits = parse_ref_true_lo(ledger)
    form, res, reason, flags = judge(I, rows, tbl, ledger, ref)

    print("──── 扫描（Wilson 水平 × 基准变体；⚠ 端点都要）────")
    for r in rows:
        print("  %.2f / %-14s base=%.6f  c ∈ [%+.4f, %+.4f] pp  ⇒  c_max=%+.4f pp"
              % (r["level"], r["variant"], r["base"], r["c_lo"], r["cmax"], r["cmax"]))
    print("──── 读法—口径作用域表 ────")
    for t in tbl:
        if not t["per_caliber"]:
            print("  %s  %-34s 界=%+.4f pp ｜ 置信 %.0f%% ｜ %s"
                  % (t["id"], t["name"], t["bound"], 100 * t["conf"], t["note"]))
        else:
            print("  %s  %-34s （%s）" % (t["id"], t["name"], t["note"]))
            for it in t["items"]:
                extra = (" ｜ 联合 %.0f%%" % (100 * it["conf"])) if it.get("conf") is not None else ""
                print("      %.2f / %-14s 界=%+.4f pp ⇒ %s%s"
                      % (it["level"], it["variant"], it["bound"],
                         "成立" if it["ok"] else "**不成立**", extra))
    print("──── 判据 ────")
    for cid, name, ok, detail in res:
        print("[%s] %s %s — %s" % ("PASS" if ok else "FAIL", cid, name, detail))
    print()
    print("VERDICT=%s" % form)
    print("理由：%s" % reason)

    row_main = [r for r in rows if r["level"] == MAIN_LEVEL and r["variant"] == "main"][0]
    r3 = [t for t in tbl if t["id"] == "R3"][0]
    r4 = [t for t in tbl if t["id"] == "R4"][0]
    r5 = [t for t in tbl if t["id"] == "R5"][0]
    print("===== AUDIT_KEYS =====")
    print("VERDICT=%s" % form)
    print("N_SCAN=%d" % len(rows))
    print("BASE_MAIN_R=%.12f" % base_from_dist(I["i6_r"], "main"))
    print("DELTA_OBS_PP=%.4f" % I["i7_delta_obs"])
    print("DELTA_OBS_BLK_PP=%.4f" % I["i8_delta_obs_blk"])
    print("CI_LO_TRAJ_PP=%.4f" % I["i7_nc_lo"])
    print("CI_LO_BLK_PP=%.4f" % I["i8_nc_lo"])
    print("C_MAIN_HI_PP=%.6f" % row_main["cmax"])
    print("C_MAIN_LO_PP=%.6f" % row_main["c_lo"])
    for r in rows:
        print("CLO_%d_%s=%.6f" % (int(round(r["level"] * 100)), r["variant"].upper(), r["c_lo"]))
    print("R1_BOUND_PP=%.4f" % tbl[0]["bound"])
    print("R2_BOUND_PP=%.4f" % tbl[1]["bound"])
    print("R3_MIN_PP=%.4f" % min(i["bound"] for i in r3["items"]))
    print("R3_MAX_PP=%.4f" % max(i["bound"] for i in r3["items"]))
    print("R3_NVIOL=%d" % len([i for i in r3["items"] if not i["ok"]]))
    print("R4_MIN_PP=%.4f" % min(i["bound"] for i in r4["items"]))
    print("R4_NVIOL=%d" % len([i for i in r4["items"] if not i["ok"]]))
    print("R5_MIN_PP=%.4f" % min(i["bound"] for i in r5["items"]))
    print("R5_NVIOL=%d" % len([i for i in r5["items"] if not i["ok"]]))
    for it in r5["items"]:
        if not it["ok"]:
            print("R5_VIOL_%d_%s=%.4f" % (int(round(it["level"] * 100)), it["variant"].upper(), it["bound"]))
    print("===== END_AUDIT_KEYS =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
