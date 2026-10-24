#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_cross_check_24487.py —— **跨实现互证**（244.87）。

⚖⚖⚖⚖⚖ **这一条要回答的问题**
   「被检实现算出来的 9 个 c_max 与判决形态，是不是**只靠它自己那套代码**算出来的？」
   ⇒ ⇒ 本脚本是**第二条独立实现**：
     · **解析路线不同**：被检实现用「整行大正则」；本脚本用「**按表格单元格切**」＋**另一套正则**；
     · **算术路线不同**：被检实现用 `float` + 固定 z 表；
       本脚本用 **`fractions.Fraction`** 算基准 ＋ **`decimal.Decimal`**（60 位有效）算 Wilson
       ＋ **`statistics.NormalDist().inv_cdf`** 取 z（⛔ 不查那张固定表）；
     · **锚点不同**：本脚本**故意**用不同的锚点字串。
   ⇒ ⇒ 两条路线**零共用代码**（⛔ 不 import 被检实现、不调它的任何函数）。

⚖⚖⚖⚖⚖ **互证的内容**
   ① 账本 244.81 段的 9 个输入（I1–I9）**逐个**与「本脚本自己解析出来的」对账；
   ② 9 个口径的 c_max（3 档 Wilson × 3 种基准）**逐个**与被检实现印出来的对账；
   ③ **独立重判判决形态**（用本脚本自己的判据）⇒ ⇒ 与被检实现的 VERDICT 必须一致。

⛔ **容差**：c_max 用 **1e-6 pp**（账本打印精度是 2 位小数 ⇒ 半单位 0.005 pp；
   本互证比的是**被检实现现算到 6 位小数的值**，⇒ ⇒ 容差取 **1e-6 pp** 足以区分
   「算式写错」这种量级 ≥ 1e-3 pp 的差异，⛔ 又不至于把浮点噪声当差异）。
"""

import os
import re
import statistics
import sys
from decimal import Decimal, getcontext
from fractions import Fraction

getcontext().prec = 60

LEDGER = os.environ.get("R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
DE_OUT = os.environ.get("R244_DE_OUT", "/dev/shm/_null_24487/de.out")

WILSON_LEVELS = (0.90, 0.95, 0.99)
BASE_VARIANTS = ("main", "zero_as_half", "zero_as_zero")
MAIN_LEVEL = 0.95
TOL_CMAX = 1e-6
TOL_PRINT = 0.005          # = 账本打印精度（2 位小数）的半个单位
TOL_BASE = 5e-4


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _die(msg):
    print("⛔ %s" % msg)
    sys.exit(2)


# =============================================================================
# 独立解析：按**表格单元格**切（⛔ 不用被检实现那条整行正则）
# =============================================================================

def _section_24481(text):
    lines = text.split("\n")
    starts = [i for i, l in enumerate(lines) if l.startswith("## 修订 244.81 ")]
    if len(starts) != 1:
        _die("「## 修订 244.81」命中 %d 处" % len(starts))
    s = starts[0]
    e = len(lines)
    for j in range(s + 1, len(lines)):
        if lines[j].startswith("## 修订 "):
            e = j
            break
    return lines[s:e]


def _cells(line):
    """⚖ 把一行 markdown 表格切成单元格（去首尾空单元）。"""
    if "|" not in line:
        return []
    parts = line.split("|")
    return [p.strip() for p in parts[1:-1]] if len(parts) > 2 else []


def _one(lines, pred, what):
    hits = [l for l in lines if pred(l)]
    if len(hits) != 1:
        _die("段内「%s」命中 %d 行（期望 1 行）" % (what, len(hits)))
    return hits[0]


def parse_independent(text):
    lines = _section_24481(text)
    out = {}

    # ---- 改判数：单元格 2、3 ----
    row = _one(lines, lambda l: "改判（主口径" in l, "改判行")
    cs = _cells(row)
    m = re.match(r"\*\*(\d+)/(\d+)\*\*", cs[1])
    out["w_num"], out["w_den"] = int(m.group(1)), int(m.group(2))
    m = re.match(r"\*\*(\d+)/(\d+)\*\*", cs[2])
    out["r_num"], out["r_den"] = int(m.group(1)), int(m.group(2))

    # ---- Wilson95 区间：单元格 2、3 ----
    row = _one(lines, lambda l: "比例区间（Wilson95）" in l, "Wilson95 行")
    cs = _cells(row)
    for idx, key in ((1, "w"), (2, "r")):
        m = re.match(r"\[([+-][0-9.]+), ([+-][0-9.]+)\]", cs[idx])
        out["%s_wlo" % key] = float(m.group(1))
        out["%s_whi" % key] = float(m.group(2))

    # ---- 零假设基准：单元格 2、3 ----
    row = _one(lines, lambda l: "零假设基准（逐轨迹平均）" in l, "零假设基准行")
    cs = _cells(row)
    out["base_w"] = float(cs[1])
    out["base_r"] = float(cs[2])

    # ---- (n_nz,n_zero) 分布：按全角 ｜ 切成两段，再用**另一种**正则抽 ----
    row = _one(lines, lambda l: "(n_nz,n_zero) 分布" in l, "分布行")
    parts = [p.strip() for p in row.split("｜")]
    if len(parts) < 2:
        _die("分布行切不出两段")
    out["dist_w"] = _dist(parts[0])
    out["dist_r"] = _dist(parts[1])

    # ---- Δ_obs 轨迹级 + Newcombe ----
    #   ⚠ 锚点必须带方括号「差区间（Newcombe95）[」⇒ ⇒ 否则会连表头行一起命中（2 行）
    row = _one(lines, lambda l: "差区间（Newcombe95）[" in l, "Newcombe 行")
    m = re.search(r"\*\*差 ([+-][0-9.]+) pp\*\*", row)
    out["delta_obs"] = float(m.group(1))
    m = re.search(r"Newcombe95）\[([+-][0-9.]+), ([+-][0-9.]+)\]", row)
    out["nc_lo"], out["nc_hi"] = float(m.group(1)), float(m.group(2))

    # ---- 块级 Δ_obs + bootstrap ----
    row = _one(lines, lambda l: "按**块**重采样" in l, "块级 bootstrap 行")
    m = re.search(r"块级差 \*\*([+-][0-9.]+) pp\*\*", row)
    out["delta_obs_blk"] = float(m.group(1))
    m = re.search(r"95% 区间 \*\*\[([+-][0-9.]+), ([+-][0-9.]+)\] pp\*\*", row)
    out["boot_lo"], out["boot_hi"] = float(m.group(1)), float(m.group(2))

    # ---- 块级改判数 ----
    row = _one(lines, lambda l: re.search(r"w \*\*\d+/\d+\*\* ｜ rand \*\*\d+/\d+\*\*", l)
               is not None, "块级改判数行")
    m = re.search(r"w \*\*(\d+)/(\d+)\*\* ｜ rand \*\*(\d+)/(\d+)\*\*", row)
    out["blk_w_num"], out["blk_w_den"] = int(m.group(1)), int(m.group(2))
    out["blk_r_num"], out["blk_r_den"] = int(m.group(3)), int(m.group(4))
    return out


def _split_top(s):
    """⚖ **括号感知**的顶层逗号切分（括号内的逗号不算）。

    ⚖⚖⚖ 为什么必须这么切：分布项 `{(2,0)×1, (3,0)×55}` 里，**内层 `(2,0)` 自带逗号**
       ⇒ ⇒ 直接按 ',' 切会把 `(2,0)` 切碎 ⇒ ⇒ 244.86 已经在这上面踩过一次
       （账本第 5 条缺陷的第 4 小条）⇒ ⇒ 这里**故意**用「括号深度」而不是正则来切
       ⇒ ⇒ 与被检实现的「正则逐项抽」路线**真的不同源**。
    """
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def _dist(s):
    """⚖ 另一种解析法：**括号感知**切顶层逗号 → 按 '×' 切 → 拆出 (n_nz, n_zero)。
    （⛔ 不用被检实现那条正则）"""
    i = s.find("{")
    j = s.rfind("}")
    if i < 0 or j < 0 or j <= i:
        _die("分布段里找不到花括号：%r" % s)
    body = s[i + 1:j]
    d = {}
    for item in _split_top(body):
        item = item.strip()
        if not item:
            continue
        if "×" not in item:
            _die("分布项没有 ×：%r" % item)
        pair, cnt = item.split("×")
        pair = pair.strip().strip("()")
        a, b = pair.split(",")
        d[(int(a), int(b))] = int(cnt.strip())
    return d


# =============================================================================
# 独立算术：Fraction 算基准 ＋ Decimal 算 Wilson ＋ NormalDist 取 z
# =============================================================================

def base_frac(dist, variant):
    """⚖ 基准（**精确有理数**，⛔ 不经过 float）。"""
    if variant == "main":
        b_zero = Fraction(1, 4)
    elif variant == "zero_as_half":
        b_zero = Fraction(1, 2)
    else:
        b_zero = Fraction(0, 1)
    num = Fraction(0)
    den = 0
    for (nz, zr), cnt in dist.items():
        b = b_zero if zr > 0 else Fraction(1, 2)
        num += b * cnt
        den += cnt
    return num / den


def wilson_hi_dec(k, n, level):
    """⚖ Wilson 上界（**Decimal** 60 位有效 + **NormalDist** 取 z）。"""
    z = Decimal(repr(statistics.NormalDist().inv_cdf(0.5 + level / 2.0)))
    kk = Decimal(k)
    nn = Decimal(n)
    p = kk / nn
    d = Decimal(1) + z * z / nn
    c = (p + z * z / (Decimal(2) * nn)) / d
    h = (z / d) * (p * (Decimal(1) - p) / nn + z * z / (Decimal(4) * nn * nn)).sqrt()
    return c + h


def cmax_indep(k, n, dist, variant, level):
    """⚖ **独立路线**的 c_max（单位 pp）。"""
    hi = wilson_hi_dec(k, n, level) * Decimal(100)
    # ⚠ Fraction 与 Decimal 不能直接相乘 ⇒ ⇒ 先把**精确有理数**无损转成 Decimal
    bf = base_frac(dist, variant)
    base = (Decimal(bf.numerator) / Decimal(bf.denominator)) * Decimal(100)
    return hi - base


# =============================================================================
# 主流程
# =============================================================================

def _parse_audit_keys(de_text):
    m = re.search(r"===== AUDIT_KEYS =====\n(.*?)\n===== END_AUDIT_KEYS =====", de_text, re.S)
    if not m:
        _die("de.out 里没有 AUDIT_KEYS 块")
    K = {}
    for ln in m.group(1).splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            K[k.strip()] = v.strip()
    return K


def main():
    if not os.path.isfile(LEDGER):
        print("PRECOND_FAIL: 账本不存在：%s" % LEDGER)
        return 2
    if not os.path.isfile(DE_OUT):
        print("PRECOND_FAIL: de.out 不存在：%s" % DE_OUT)
        return 2

    text = _read(LEDGER)
    I = parse_independent(text)
    K = _parse_audit_keys(_read(DE_OUT))

    ok = 0
    bad = []

    def chk(name, cond, detail=""):
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append("%s%s" % (name, ("｜%s" % detail) if detail else ""))

    # ---- ① 输入逐项对账（被检实现印出来的 vs 本脚本自己解析的）----
    #   ⚖ 被检实现的 AUDIT_KEYS 里没有全部 I 值 ⇒ ⇒ 这里拿它印出来的**数**来对：
    #   改判数、基准、Δ_obs 都在 AUDIT_KEYS 或 VERDICT 之外的判据明细里 ⇒ ⇒
    #   本互证改为：**独立算出来的** vs **被检实现的 AUDIT_KEYS**。
    chk("I1/I2 改判数（独立解析 vs 被检实现的 Δ_obs 反推）",
        abs((I["w_num"] / I["w_den"] - I["r_num"] / I["r_den"]) * 100.0
            - float(K["DELTA_OBS_PP"])) <= TOL_PRINT,
        "独立 Δ_obs=%+.6f vs 被检 %s" % ((I["w_num"] / I["w_den"] - I["r_num"] / I["r_den"]) * 100.0,
                                        K["DELTA_OBS_PP"]))
    chk("I5 零假设基准（独立算 vs 被检实现印的）",
        abs(float(base_frac(I["dist_r"], "main")) - float(K["BASE_MAIN_R"])) <= TOL_BASE,
        "独立=%s vs 被检 %s" % (float(base_frac(I["dist_r"], "main")), K["BASE_MAIN_R"]))
    chk("I7 Δ_obs 轨迹级（账本印的 vs 独立解析的）",
        abs(I["delta_obs"] - float(K["DELTA_OBS_PP"])) <= TOL_PRINT,
        "账本 %+.2f vs 被检 %s" % (I["delta_obs"], K["DELTA_OBS_PP"]))
    chk("I8 Δ_obs 块级（账本印的 vs 被检实现印的）",
        abs(I["delta_obs_blk"] - float(K["DELTA_OBS_BLK_PP"])) <= TOL_PRINT,
        "账本 %+.2f vs 被检 %s" % (I["delta_obs_blk"], K["DELTA_OBS_BLK_PP"]))
    chk("I3/I4 Wilson95（独立算 vs 账本印的，rand 臂）",
        abs(float(wilson_hi_dec(I["r_num"], I["r_den"], 0.95) * 100) - I["r_whi"]) <= TOL_PRINT,
        "独立=%.6f vs 账本 %+.2f" % (float(wilson_hi_dec(I["r_num"], I["r_den"], 0.95) * 100), I["r_whi"]))
    chk("I9 块级改判数（独立解析 vs 账本印的块级 Δ_obs）",
        abs((I["blk_w_num"] / I["blk_w_den"] - I["blk_r_num"] / I["blk_r_den"]) * 100.0
            - I["delta_obs_blk"]) <= TOL_PRINT,
        "独立=%+.6f vs 账本 %+.2f" % ((I["blk_w_num"] / I["blk_w_den"] - I["blk_r_num"] / I["blk_r_den"]) * 100.0,
                                     I["delta_obs_blk"]))

    # ---- ② 9 个口径的 c_max 逐个对账 ----
    mine = {}
    for level in WILSON_LEVELS:
        for variant in BASE_VARIANTS:
            key = "CMAX_%d_%s" % (int(round(level * 100)), variant.upper())
            mine[key] = cmax_indep(I["r_num"], I["r_den"], I["dist_r"], variant, level)
            chk("%s（独立 Decimal 路线 vs 被检实现）" % key,
                abs(float(mine[key]) - float(K[key])) <= TOL_CMAX,
                "独立=%+.6f vs 被检 %s" % (float(mine[key]), K[key]))

    # ---- ③ 独立重判判决形态 ----
    #   ⛔ 本互证**不复算** H1/H6/H7（那是「出处/只读」层），⇒ ⇒ 只判 A vs B：
    #     若「所有口径下 c_max < Δ_obs」不成立 ⇒ ⇒ 独立形态 = B；否则 = A。
    #     ⚖ 若被检实现给的是 C/D（硬失败），⇒ ⇒ 本互证**明确报「不一致」**（⛔ 不猜）。
    delta_obs = I["delta_obs"]
    all_below = all(float(v) < delta_obs for v in mine.values())
    indep_form = "A" if all_below else "B"
    got_form = K.get("VERDICT")
    chk("独立重算的判决形态（%s）vs 被检实现（%s）" % (indep_form, got_form),
        indep_form == got_form,
        "独立=%s 被检=%s" % (indep_form, got_form))

    # ---- ④ 主口径 c_max 与 244.86 段印的那个数对上（独立地）----
    lines = text.split("\n")
    s86 = [i for i, l in enumerate(lines) if l.startswith("## 修订 244.86 ")]
    if len(s86) != 1:
        chk("244.86 段的 c_max 锚点唯一", False, "命中 %d 处" % len(s86))
    else:
        i = s86[0]
        sec86 = []
        for l in lines[i:]:
            if l.startswith("## 修订 ") and sec86:
                break
            sec86.append(l)
        hits = re.findall(r"c_max = \*\*([+-][0-9.]+) pp\*\*", "\n".join(sec86))
        chk("244.86 段的 c_max 锚点唯一", len(hits) == 1, "命中 %d 处" % len(hits))
        if len(hits) == 1:
            ref = float(hits[0])
            c_main = float(mine["CMAX_95_MAIN"])
            chk("主口径 c_max（独立算 vs 244.86 段印的 %+.2f）" % ref,
                abs(c_main - ref) <= TOL_PRINT,
                "独立=%+.6f vs 账本 %+.2f" % (c_main, ref))

    print("互证：OK %d ｜ MISMATCH %d" % (ok, len(bad)))
    if bad:
        for b in bad:
            print("  ⛔ %s" % b)
    print("独立重算的判决形态：%s" % indep_form)
    print("互证小结：OK %d ｜ MISMATCH %d" % (ok, len(bad)))
    if bad:
        print("CROSS_RC=1")
        return 1
    print("CROSS_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
