#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_cross_check_24488.py —— **跨实现互证**（244.88）。

⚖⚖⚖⚖⚖ **这一条要回答的问题**
   「被检实现算出来的作用域表与判决形态，是不是**只靠它自己那套代码**算出来的？」
   ⇒ ⇒ 本脚本是**第二条独立实现**：
     · **解析路线不同**：被检实现用「整行大正则」；本脚本用「**按表格单元格切**」
       （⛔ 切的是 `｜` 与 `|` 两种分隔符）＋**另一套定位方式**；
     · **算术路线不同**：被检实现用 `float` + 固定 z 表；
       本脚本用 **`fractions.Fraction`** 算基准 ＋ **`decimal.Decimal`**（60 位有效）算 Wilson
       ＋ **`statistics.NormalDist().inv_cdf`** 取 z（⛔ 不查那张固定表）；
     · **锚点不同**：本脚本**故意**用不同的锚点字串。
   ⇒ ⇒ 两条路线**零共用代码**（⛔ 不 import 被检实现、不调它的任何函数）。

⚖⚖⚖⚖⚖ **互证的内容**
   ① 账本 244.81 / 244.86 段的输入**逐个**与「本脚本自己解析出来的」对账；
   ② 9 个口径的 `c_lo`（3 档 Wilson × 3 种基准）**逐个**与被检实现印出来的对账；
   ③ 作用域表的每一行（R1 / R2 / R3 / R4 / R5）**逐个**与被检实现印出来的对账；
   ④ **独立重判判决形态**（用本脚本自己的判据）⇒ ⇒ 与被检实现的 VERDICT 必须一致。

⛔ **容差**：c_lo 比 **1e-6 pp**（被检实现现算到 6 位小数）；
   作用域表的界印到 **4 位小数** ⇒ ⇒ 容差取 **5e-5 pp**（= 打印精度的半个单位，
   ⛔ 不许拍脑袋）；基准比 **5e-7**（印 12 位小数 ⇒ 半单位）。
"""

import os
import re
import statistics
import sys
from decimal import Decimal, getcontext
from fractions import Fraction

getcontext().prec = 60

LEDGER = os.environ.get("R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
DE_OUT = os.environ.get("R244_DE_OUT", "/dev/shm/_null_24488/de.out")

WILSON_LEVELS = (0.90, 0.95, 0.99)
BASE_VARIANTS = ("main", "zero_as_half", "zero_as_zero")
MAIN_LEVEL = 0.95
TOL_CLO = 1e-6          # c_lo 印到 6 位小数
TOL_ROW = 5e-5          # 作用域表的界印到 4 位小数 ⇒ 半单位
TOL_BASE = 5e-7         # 基准印到 12 位小数 ⇒ 半单位


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _die(msg):
    print("CROSS_FAIL: %s" % msg)
    raise SystemExit(1)


# =============================================================================
# 解析层（**按单元格切**，⛔ 与被检实现不同源）
# =============================================================================

def _cells(line):
    """⚖ **按单元格切**（被检实现走的是「整行大正则」⇒ ⇒ 两条路线不同源）。"""
    parts = re.split(r"[｜|]", line)
    return [p.strip() for p in parts]


def _num(s):
    """⚖ 从一个单元格里抠出第一个带符号/不带符号的数。"""
    m = re.search(r"[+-]?[0-9]+(?:\.[0-9]+)?", s.replace("**", ""))
    if not m:
        return None
    return float(m.group(0))


def _int(s):
    m = re.search(r"(\d+)\s*/\s*(\d+)", s.replace("**", ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _section(text, rev):
    lines = text.split("\n")
    starts = [i for i, l in enumerate(lines) if l.startswith("## 修订 %s " % rev)]
    if len(starts) != 1:
        _die("「## 修订 %s」有 %d 处（期望 1）" % (rev, len(starts)))
    s = starts[0]
    e = len(lines)
    for j in range(s + 1, len(lines)):
        if lines[j].startswith("## 修订 "):
            e = j
            break
    return lines[s:e]


def parse_independent(text):
    """⚖ 自己解析 244.81 / 244.86 段（⛔ 锚点字串与被检实现不同）。"""
    sec81 = _section(text, "244.81")
    sec86 = _section(text, "244.86")
    out = {}

    # ---- 改判数（w / rand）----
    hits = [l for l in sec81 if "改判（主口径" in l]
    if len(hits) != 1:
        _die("改判行命中 %d 次" % len(hits))
    cs = _cells(hits[0])
    # ⚖⚖⚖ **按「形状」取**，⛔ 不按下标取（表头行以 `|` 开头 ⇒ 首格是空串 ⇒ 下标会错位）
    pairs = [c for c in cs if re.fullmatch(r"\*\*\d+/\d+\*\*", c)]
    if len(pairs) != 2:
        _die("改判单元格解析失败：%r" % cs)
    wr = _int(pairs[0])
    rr = _int(pairs[1])
    if not wr or not rr:
        _die("改判单元格解析失败：%r" % pairs)
    out["w_num"], out["w_den"] = wr
    out["r_num"], out["r_den"] = rr

    # ---- 轨迹级：差 + Newcombe95 ----
    # ⚖⚖⚖ **必须同时**含「`**差 `」与「差区间（Newcombe95）」
    #   ⇒ ⇒ 否则会命中 `pos_frac` 那张表的**表头行**（它也有「差区间（Newcombe95）」和「Fisher p」）
    hits = [l for l in sec81 if "**差 " in l and "差区间（Newcombe95）" in l]
    if len(hits) != 1:
        _die("轨迹级差行命中 %d 次" % len(hits))
    cs = _cells(hits[0])
    d_traj = _num(cs[0])
    iv = re.search(r"\[([+-][0-9.]+), ([+-][0-9.]+)\]", cs[1])
    if d_traj is None or not iv:
        _die("轨迹级差/区间解析失败：%r" % cs[:2])
    out["delta_traj"] = d_traj
    out["nc_lo_traj"] = float(iv.group(1))
    out["nc_hi_traj"] = float(iv.group(2))

    # ---- 块级：改判数 + 差 + Newcombe95 ----
    hits = [l for l in sec81 if "Fisher p = 0.000131" in l]
    if len(hits) != 1:
        _die("块级行命中 %d 次" % len(hits))
    cs = _cells(hits[0])
    bw = _int(cs[0])
    br = _int(cs[1])
    d_blk = _num(cs[2])
    iv = re.search(r"\[([+-][0-9.]+), ([+-][0-9.]+)\]", cs[3])
    if not bw or not br or d_blk is None or not iv:
        _die("块级解析失败：%r" % cs[:4])
    out["bw_num"], out["bw_den"] = bw
    out["br_num"], out["br_den"] = br
    out["delta_blk"] = d_blk
    out["nc_lo_blk"] = float(iv.group(1))
    out["nc_hi_blk"] = float(iv.group(2))

    # ---- (n_nz,n_zero) 分布（rand 臂）----
    hits = [l for l in sec81 if "(n_nz,n_zero) 分布" in l]
    if len(hits) != 1:
        _die("分布行命中 %d 次" % len(hits))
    cs = _cells(hits[0])
    out["dist_r"] = _dist(cs[-1])

    # ---- 244.86 段：真实差（Q8 ①）的下端点 ----
    hits = [l for l in sec86 if "真实差（Q8 ①）" in l]
    if len(hits) != 1:
        _die("244.86 的真实差行命中 %d 次" % len(hits))
    cs = _cells(hits[0])
    iv = re.search(r"\[([+-][0-9.]+), ([+-][0-9.]+)\]", cs[-1])
    if not iv:
        _die("244.86 的真实差解析失败：%r" % cs)
    out["true_lo"] = float(iv.group(1))
    return out


def _dist(s):
    """⚖ 解析 `{(2,1)×2, (3,0)×54}` ⇒ ⇒ {(2,1):2, (3,0):54}（⛔ 不用逗号直接切）。"""
    items = re.findall(r"\((\d+),(\d+)\)\s*×\s*(\d+)", s)
    if not items:
        _die("分布解析失败：%r" % s)
    d = {}
    for a, b, c in items:
        k = (int(a), int(b))
        d[k] = d.get(k, 0) + int(c)
    return d


# =============================================================================
# 独立算术：Fraction 算基准 ＋ Decimal 算 Wilson（两端）＋ NormalDist 取 z
# =============================================================================

def base_frac(dist, variant):
    """⚖ 基准（**精确有理数**，⛔ 不经过 float）。"""
    if variant == "main":
        b_zero = Fraction(1, 4)
    elif variant == "zero_as_half":
        b_zero = Fraction(1, 2)
    elif variant == "zero_as_zero":
        b_zero = Fraction(0, 1)
    else:
        _die("未知基准变体 %r" % variant)
    num = Fraction(0)
    den = 0
    for (nz, zr), cnt in dist.items():
        b = b_zero if zr > 0 else Fraction(1, 2)
        num += b * cnt
        den += cnt
    return num / den


def wilson_bounds_dec(k, n, level):
    """⚖ Wilson 区间（**Decimal** 60 位有效 + **NormalDist** 取 z）⇒ ⇒ **两端**。"""
    z = Decimal(repr(statistics.NormalDist().inv_cdf(0.5 + level / 2.0)))
    kk = Decimal(k)
    nn = Decimal(n)
    p = kk / nn
    d = Decimal(1) + z * z / nn
    c = (p + z * z / (Decimal(2) * nn)) / d
    h = (z / d) * (p * (Decimal(1) - p) / nn + z * z / (Decimal(4) * nn * nn)).sqrt()
    lo = max(Decimal(0), c - h) * Decimal(100)
    hi = min(Decimal(1), c + h) * Decimal(100)
    return lo, hi


def c_bounds_indep(k, n, dist, variant, level):
    """⚖ `c` 的区间（单位 pp）＝ Wilson 两端 − 基准。"""
    lo, hi = wilson_bounds_dec(k, n, level)
    base = base_frac(dist, variant)
    # ⚠ Fraction 与 Decimal 不能直接相乘 ⇒ ⇒ 先把**精确有理数**无损转成 Decimal
    b100 = Decimal(base.numerator) / Decimal(base.denominator) * Decimal(100)
    return (lo - b100, hi - b100)


# =============================================================================
# 独立重算：作用域表 + 判决形态
# =============================================================================

def independent_table(I):
    """⚖ 独立重算 9 个口径与作用域表 R1..R5。"""
    rows = []
    for lv in WILSON_LEVELS:
        for va in BASE_VARIANTS:
            lo, hi = c_bounds_indep(I["r_num"], I["r_den"], I["dist_r"], va, lv)
            rows.append({"level": lv, "variant": va, "c_lo": float(lo), "cmax": float(hi),
                         "base": float(base_frac(I["dist_r"], va))})
    r1 = I["nc_lo_traj"]
    r2 = I["nc_lo_blk"]
    r3 = [(I["delta_traj"] + r["c_lo"]) for r in rows]
    r4 = [(I["delta_blk"] + r["c_lo"]) for r in rows]
    r5 = [(I["nc_lo_traj"] + r["c_lo"]) for r in rows]
    return rows, r1, r2, r3, r4, r5


def independent_form(I, r1, r2, r3, r4, r5):
    """⚖ 独立重判形态（⛔ 只用**界**，不用被检实现的任何函数）。

    ⚖ 硬失败（H1/H2/H8/H9）与「前提失败」不在本互证的范围内 ⇒ ⇒
       本脚本判出的是**实质形态**（A′/B′/C′/D′）⇒ ⇒ 若被检实现判 E′，
       本脚本**不**与它对账形态（而是报告「被检实现判了 E′ ⇒ 前提失败」）。
    """
    if min(r1, r2) <= 0:
        return "D'"
    if any(x <= 0 for x in r3) or any(x <= 0 for x in r4):
        return "C'"
    if any(x <= 0 for x in r5):
        return "B'"
    return "A'"


def _parse_audit_keys(de_text):
    """⚖ 解析被检实现印出来的 AUDIT_KEYS 块。"""
    out = {}
    inside = False
    for line in (de_text or "").split("\n"):
        if line.strip() == "===== AUDIT_KEYS =====":
            inside = True
            continue
        if line.strip() == "===== END_AUDIT_KEYS =====":
            break
        if inside and "=" in line:
            k, v = line.strip().split("=", 1)
            out[k] = v
    return out


def main():
    if not os.path.isfile(LEDGER):
        print("CROSS_FAIL: 账本不存在：%s" % LEDGER)
        return 2
    if not os.path.isfile(DE_OUT):
        print("CROSS_FAIL: 被检实现的输出不存在：%s" % DE_OUT)
        return 2

    text = _read(LEDGER)
    I = parse_independent(text)
    rows, r1, r2, r3, r4, r5 = independent_table(I)
    form = independent_form(I, r1, r2, r3, r4, r5)

    de_text = _read(DE_OUT)
    K = _parse_audit_keys(de_text)
    if not K:
        print("CROSS_FAIL: 被检实现的输出里没有 AUDIT_KEYS 块")
        return 2

    ok = 0
    bad = 0

    def chk(name, got, want, tol):
        nonlocal ok, bad
        d = abs(float(got) - float(want))
        if d <= tol:
            ok += 1
            print("[OK ] %s  独立=%+.6f ｜ 被检=%+.6f ｜ 差 %.2e" % (name, float(want), float(got), d))
        else:
            bad += 1
            print("[MISMATCH] %s  独立=%+.6f ｜ 被检=%+.6f ｜ 差 %.2e（容差 %.1e）"
                  % (name, float(want), float(got), d, tol))

    # ---- ① 输入对账 ----
    chk("BASE_MAIN_R", K.get("BASE_MAIN_R", "0"), float(base_frac(I["dist_r"], "main")), TOL_BASE)
    chk("DELTA_OBS_PP", K.get("DELTA_OBS_PP", "0"), I["delta_traj"], TOL_PRINT_HALF)
    chk("DELTA_OBS_BLK_PP", K.get("DELTA_OBS_BLK_PP", "0"), I["delta_blk"], TOL_PRINT_HALF)
    chk("CI_LO_TRAJ_PP", K.get("CI_LO_TRAJ_PP", "0"), I["nc_lo_traj"], TOL_PRINT_HALF)
    chk("CI_LO_BLK_PP", K.get("CI_LO_BLK_PP", "0"), I["nc_lo_blk"], TOL_PRINT_HALF)

    # ---- ② 9 个口径的 c_lo ----
    for r in rows:
        key = "CLO_%d_%s" % (int(round(r["level"] * 100)), r["variant"].upper())
        if key not in K:
            bad += 1
            print("[MISMATCH] %s  被检实现的输出里**没有**这个键" % key)
            continue
        chk(key, K[key], r["c_lo"], TOL_CLO)

    # ---- ③ 作用域表 ----
    chk("R1_BOUND_PP", K.get("R1_BOUND_PP", "0"), r1, TOL_ROW)
    chk("R2_BOUND_PP", K.get("R2_BOUND_PP", "0"), r2, TOL_ROW)
    chk("R3_MIN_PP", K.get("R3_MIN_PP", "0"), min(r3), TOL_ROW)
    chk("R3_MAX_PP", K.get("R3_MAX_PP", "0"), max(r3), TOL_ROW)
    chk("R4_MIN_PP", K.get("R4_MIN_PP", "0"), min(r4), TOL_ROW)
    chk("R5_MIN_PP", K.get("R5_MIN_PP", "0"), min(r5), TOL_ROW)
    chk("R3_NVIOL", K.get("R3_NVIOL", "0"), len([x for x in r3 if x <= 0]), 0.5)
    chk("R4_NVIOL", K.get("R4_NVIOL", "0"), len([x for x in r4 if x <= 0]), 0.5)
    chk("R5_NVIOL", K.get("R5_NVIOL", "0"), len([x for x in r5 if x <= 0]), 0.5)

    # ---- ④ 判决形态 ----
    got_form = K.get("VERDICT", "?")
    if got_form == "E'":
        print("[形态] 被检实现判 **E′**（前提层面的硬失败）⇒ ⇒ 本互证**不**与它对账形态"
              "（本脚本判出的实质形态是 %s）" % form)
        ok += 1
    elif got_form == form:
        ok += 1
        print("[OK ] 判决形态 独立=%s ｜ 被检=%s" % (form, got_form))
    else:
        bad += 1
        print("[MISMATCH] 判决形态 独立=%s ｜ 被检=%s" % (form, got_form))

    print("")
    print("CROSS_OK=%d ｜ CROSS_MISMATCH=%d" % (ok, bad))
    print("CROSS_FORM=%s" % form)
    return 0 if bad == 0 else 1


TOL_PRINT_HALF = 5e-3      # 账本印两位小数 ⇒ 半单位

if __name__ == "__main__":
    sys.exit(main())
