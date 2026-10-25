#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_cross_check_24489.py —— **跨实现互证**（244.89）。

⚖⚖⚖⚖⚖ **这一条要回答的问题**
   「被检实现算出来的 27 格作用域表与判决形态，是不是**只靠它自己那套代码**算出来的？」
   ⇒ ⇒ 本脚本是**第二条独立实现**：
     · **解析路线不同**：被检实现用「整行大正则」；本脚本用「**按表格单元格切**」
       （⛔ 切的是 `｜` 与 `|` 两种分隔符）＋**另一套定位方式**；
     · **算术路线不同**：被检实现用 `float` + 固定 z 表；
       本脚本用 **`fractions.Fraction`** 算基准 ＋ **`decimal.Decimal`**（60 位有效）算 Wilson
       ＋ **`statistics.NormalDist().inv_cdf`** 取 z（⛔ 不查那张固定表）；
     · **锚点不同**：本脚本**故意**用不同的锚点字串；
     · **Newcombe 自己实现**：被检实现用 `math.sqrt`；本脚本用 `Decimal.sqrt`。
   ⇒ ⇒ 两条路线**零共用代码**（⛔ 不 import 被检实现、不调它的任何函数）。

⚖⚖⚖⚖⚖ **互证的内容**
   ① 账本 244.81 / 244.88 段的输入**逐个**与「本脚本自己解析出来的」对账；
   ② 27 格的界**逐格**与被检实现印出来的对账（⛔ 不许只比摘要）；
   ③ **决策区成员**逐个对账（⛔ 联合置信的门槛比较必须落在整数百分点上）；
   ④ **独立重判判决形态**（用本脚本自己的判据与自己的级联）⇒ ⇒ 与被检实现的 VERDICT 必须一致。

⛔ **容差**：格内的界印到 **4 位小数** ⇒ ⇒ 容差取 **5e-5 pp**（= 打印精度的半个单位，
   ⛔ 不许拍脑袋）；c_lo 印到 **6 位小数** ⇒ ⇒ 容差取 **1e-6 pp**。
"""

import os
import re
import statistics
import subprocess
import sys
from decimal import Decimal, getcontext
from fractions import Fraction

getcontext().prec = 60

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.environ.get("R244_LEDGER", "/home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md")
DE_OUT = os.environ.get("R244_DE_OUT", "/dev/shm/_null_24489/de.out")
TARGET = "confidence_level_audit.py"
PY = os.environ.get("R244_PY", "/home/zhourui/miniconda3/envs/easysteer/bin/python")

CI_LEVELS = (0.90, 0.95, 0.99)
C_LEVELS = (0.90, 0.95, 0.99)
BASE_VARIANTS = ("main", "zero_as_half", "zero_as_zero")
JOINT_FLOOR_PCT = 90
MAIN_CI_LEVEL = 0.95

TOL_CLO = 1e-6          # c_lo 印到 6 位小数
TOL_ROW = 5e-5          # 格的界印到 4 位小数 ⇒ 半单位
TOL_BASE = 5e-7         # 基准印到 10 位小数 ⇒ 半单位
TOL_ANCHOR = 5e-3       # 账本印的两位小数 ⇒ 半单位

OK = []
MISMATCH = []


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _die(msg):
    print("CROSS_FAIL: %s" % msg)
    raise SystemExit(1)


def _cmp(name, mine, theirs, tol):
    """⚖ 一次对账 ⇒ ⇒ 差超容差 ⇒ ⇒ 记 MISMATCH。"""
    d = abs(float(mine) - float(theirs))
    if d <= tol:
        OK.append(name)
        print("[OK ] %s  独立=%+.6f ｜ 被检=%+.6f ｜ 差 %.2e" % (name, float(mine),
                                                             float(theirs), d))
    else:
        MISMATCH.append(name)
        print("[MISMATCH] %s  独立=%+.6f ｜ 被检=%+.6f ｜ 差 %.2e（容差 %.1e）"
              % (name, float(mine), float(theirs), d, tol))


def _cmp_str(name, mine, theirs):
    if str(mine) == str(theirs):
        OK.append(name)
        print("[OK ] %s  独立=%s ｜ 被检=%s" % (name, mine, theirs))
    else:
        MISMATCH.append(name)
        print("[MISMATCH] %s  独立=%s ｜ 被检=%s" % (name, mine, theirs))


# =============================================================================
# 解析层（**按单元格切**，⛔ 与被检实现不同源）
# =============================================================================

def _section(lines, rev):
    """⚖ 取「## 修订 <rev> 」那一段（⛔ 与被检实现同样的定位语义，但代码独立）。"""
    starts = [i for i, ln in enumerate(lines) if ln.startswith("## 修订 %s " % rev)]
    if len(starts) != 1:
        _die("账本里「## 修订 %s」有 %d 处" % (rev, len(starts)))
    s = starts[0]
    e = len(lines)
    for j in range(s + 1, len(lines)):
        if lines[j].startswith("## 修订 "):
            e = j
            break
    return lines[s:e]


def _cells(line):
    """⚖ 把一行按 `|` / `｜` 切开（⛔ 两种分隔符都切）⇒ ⇒ 去掉空白。"""
    return [c.strip() for c in re.split(r"[|｜]", line) if c.strip() != ""]


def _find_line(sec_lines, needle, must=1):
    """⚖ 在段内找**恰好**含某字串的行。"""
    hits = [ln for ln in sec_lines if needle in ln]
    if len(hits) != must:
        _die("段内含「%s」的行有 %d 条（期望 %d）" % (needle, len(hits), must))
    return hits[0]


def _frac_dist(text):
    """⚖ 解析 `{(2,1)×2, (3,0)×54}` ⇒ ⇒ {(2,1): 2, (3,0): 54}（**逐项回读**）。"""
    out = {}
    for a, b, c in re.findall(r"\((\d+),(\d+)\)\s*×\s*(\d+)", text):
        out[(int(a), int(b))] = out.get((int(a), int(b)), 0) + int(c)
    if not out:
        _die("分布解析不到项：%r" % text)
    return out


def parse_base_ledger():
    """⚖ 从账本 244.81 段解析输入（⛔ 全部走**单元格切**这条路线）。"""
    lines = _read(LEDGER).split("\n")
    sec = _section(lines, "244.81")

    row = _find_line(sec, "改判（主口径")
    frac = [c for c in _cells(row) if re.search(r"\*\*\d+/\d+\*\*", c)]
    if len(frac) != 2:
        _die("改判行的分数格有 %d 个（期望 2）" % len(frac))
    w_num, w_den = [int(x) for x in re.search(r"\*\*(\d+)/(\d+)\*\*", frac[0]).groups()]
    r_num, r_den = [int(x) for x in re.search(r"\*\*(\d+)/(\d+)\*\*", frac[1]).groups()]

    row = _find_line(sec, "比例区间（Wilson95）")
    spans = [c for c in _cells(row) if c.startswith("[") and c.endswith("]")]
    if len(spans) != 2:
        _die("Wilson95 行的区间格有 %d 个（期望 2）" % len(spans))
    w_wil = [float(x) for x in spans[0].strip("[]").split(",")]
    r_wil = [float(x) for x in spans[1].strip("[]").split(",")]

    row = _find_line(sec, "零假设基准（逐轨迹平均）")
    bases = [c for c in _cells(row) if re.fullmatch(r"[0-9.]+", c)]
    if len(bases) != 2:
        _die("基准行的数值格有 %d 个（期望 2）" % len(bases))
    w_base_p, r_base_p = float(bases[0]), float(bases[1])

    row = _find_line(sec, "(n_nz,n_zero) 分布")
    parts = re.findall(r"\{[^}]*\}", row)
    if len(parts) != 2:
        _die("(n_nz,n_zero) 行的分布块有 %d 个（期望 2）" % len(parts))
    w_dist = _frac_dist(parts[0].strip("{}"))
    r_dist = _frac_dist(parts[1].strip("{}"))

    row = _find_line(sec, "基准分布：{")
    parts = re.findall(r"\{[^}]*\}", row)
    if len(parts) != 2:
        _die("基准分布行的分布块有 %d 个（期望 2）" % len(parts))
    w_bms = [(float(v), int(c)) for v, c in
             re.findall(r"([0-9.]+)\s*×\s*(\d+)", parts[0].strip("{}"))]
    r_bms = [(float(v), int(c)) for v, c in
             re.findall(r"([0-9.]+)\s*×\s*(\d+)", parts[1].strip("{}"))]

    row = _find_line(sec, "**差 ")
    cells = _cells(row)
    d_traj = None
    nc_traj = None
    for c in cells:
        m = re.search(r"差\s*([+-][0-9.]+)\s*pp", c)
        if m:
            d_traj = float(m.group(1))
        m2 = re.search(r"\[([+-][0-9.]+),\s*([+-][0-9.]+)\]", c)
        if m2:
            nc_traj = (float(m2.group(1)), float(m2.group(2)))
    if d_traj is None or nc_traj is None:
        _die("轨迹级差 / Newcombe95 区间解析不到")

    row = _find_line(sec, "Fisher p = 0.000131")
    cells = _cells(row)
    bw = [c for c in cells if re.search(r"\*\*\d+/\d+\*\*", c)]
    if len(bw) != 2:
        _die("块级行的分数格有 %d 个（期望 2）" % len(bw))
    bw_num, bw_den = [int(x) for x in re.search(r"\*\*(\d+)/(\d+)\*\*", bw[0]).groups()]
    br_num, br_den = [int(x) for x in re.search(r"\*\*(\d+)/(\d+)\*\*", bw[1]).groups()]
    d_blk = None
    nc_blk = None
    for c in cells:
        m = re.search(r"差\s*([+-][0-9.]+)\s*pp", c)
        if m:
            d_blk = float(m.group(1))
        m2 = re.search(r"\[([+-][0-9.]+),\s*([+-][0-9.]+)\]", c)
        if m2:
            nc_blk = (float(m2.group(1)), float(m2.group(2)))
    if d_blk is None or nc_blk is None:
        _die("块级差 / 区间解析不到")

    return {
        "w": (w_num, w_den), "r": (r_num, r_den), "bw": (bw_num, bw_den),
        "br": (br_num, br_den), "w_wil": w_wil, "r_wil": r_wil,
        "w_base_p": w_base_p, "r_base_p": r_base_p,
        "w_dist": w_dist, "r_dist": r_dist, "w_bms": w_bms, "r_bms": r_bms,
        "d_traj": d_traj, "nc_traj": nc_traj, "d_blk": d_blk, "nc_blk": nc_blk,
    }


def parse_prev_ledger():
    """⚖ 从账本 244.88 段解析上一轮的 R5 逐格表（⛔ 单元格切）。"""
    lines = _read(LEDGER).split("\n")
    sec = _section(lines, "244.88")
    cells_map = {}
    for ln in sec:
        cs = _cells(ln)
        if len(cs) != 5:
            continue
        m = re.fullmatch(r"(0\.\d\d)", cs[0])
        if not m or cs[1] not in BASE_VARIANTS:
            continue
        mv = re.fullmatch(r"\*\*([+-][0-9.]+)\*\*", cs[2])
        mc = re.fullmatch(r"(\d+)%", cs[3])
        if not mv or not mc:
            continue
        cells_map[(float(cs[0]), cs[1])] = (float(mv.group(1)), int(mc.group(1)))
    if len(cells_map) != 9:
        _die("244.88 的 R5 逐格表解析到 %d 格（期望 9）" % len(cells_map))
    return cells_map


# =============================================================================
# 算术层（Fraction ＋ Decimal(60 位) ＋ NormalDist）
# =============================================================================

def _z(level):
    """⚖ 由置信水平得 z（⛔ 用 NormalDist，⛔ 不查被检实现那张固定表）。"""
    return Decimal(repr(statistics.NormalDist().inv_cdf(0.5 + level / 2.0)))


def _wilson(k, n, level):
    """⚖ Wilson 区间（Decimal 60 位）。"""
    z = _z(level)
    nn = Decimal(n)
    p = Decimal(k) / nn
    den = Decimal(1) + z * z / nn
    mid = (p + z * z / (Decimal(2) * nn)) / den
    half = (z / den) * (p * (Decimal(1) - p) / nn + z * z / (Decimal(4) * nn * nn)).sqrt()
    return (max(Decimal(0), mid - half) * 100, min(Decimal(1), mid + half) * 100)


def _newcombe(kw, nw, kr, nr, level):
    """⚖ Newcombe 方法 10（Decimal 60 位；⛔ 自己实现）。

    ⚠⚖⚖ **单位陷阱**：`_wilson` 返回的是 **pp**（×100）⇒ ⇒ 这里必须**换回比例**
    ⇒ ⇒ 否则 Newcombe 的公式里混了两种单位 ⇒ ⇒ 结果会离谱（实测过：量级 1e4）。
    """
    lw, uw = _wilson(kw, nw, level)
    lr, ur = _wilson(kr, nr, level)
    lw, uw = lw / 100, uw / 100
    lr, ur = lr / 100, ur / 100
    pw = Decimal(kw) / Decimal(nw)
    pr = Decimal(kr) / Decimal(nr)
    diff = pw - pr
    lo = (diff - ((pw - lw) ** 2 + (ur - pr) ** 2).sqrt()) * 100
    hi = (diff + ((uw - pw) ** 2 + (pr - lr) ** 2).sqrt()) * 100
    return (lo, hi)


def _base_frac(dist, total, variant):
    """⚖ 零假设基准（Fraction；⛔ 零格轨迹 = n_zero > 0）。"""
    if variant == "main":
        b_zero = Fraction(1, 4)
    elif variant == "zero_as_half":
        b_zero = Fraction(1, 2)
    elif variant == "zero_as_zero":
        b_zero = Fraction(0)
    else:
        _die("未知变体 %r" % variant)
    z = sum(c for (_nz, zr), c in dist.items() if zr > 0)
    rest = total - z
    return (b_zero * z + Fraction(1, 2) * rest) / total


def _base_ms(entries):
    """⚖ 由账本印的**基准分布**行现算基准（Fraction；**第二条路线**）。"""
    num = Fraction(0)
    den = 0
    for v, c in entries:
        num += Fraction(str(v)) * c
        den += c
    return num / den


def joint_pct(lv_ci, lv_c):
    """⚖ 联合置信（**整数百分点**；⛔ 不用浮点比较门槛）。"""
    return int(round(lv_ci * 100)) + int(round(lv_c * 100)) - 100


# =============================================================================
# 被检实现的收据解析
# =============================================================================

CELL_RE = re.compile(r"CI([0-9.]+) / 污染([0-9.]+) / (\S+)\s+界=([+-][0-9.]+) pp "
                      r"｜ 联合 (\d+)% ｜ (.+)$")


def parse_de_out(path):
    """⚖ 从被检实现的收据里读出 27 格与判决形态（⛔ 只读打印出来的东西）。"""
    txt = _read(path)
    if "副表：全 27 格" not in txt:
        _die("收据里找不到「副表：全 27 格」这一段 ⇒ ⇒ 收据形状变了 ⇒ ⇒ 中止")
    tail = txt.split("副表：全 27 格", 1)[1]
    block = tail.split("──── 读法—作用域表 ────", 1)[0]
    cells = {}
    order = []
    for ln in block.split("\n"):
        m = CELL_RE.search(ln)
        if not m:
            continue
        key = (float(m.group(1)), float(m.group(2)), m.group(3))
        cells[key] = {"bound": float(m.group(4)), "conf": int(m.group(5)),
                      "ok": "成立" in m.group(6) and "不成立" not in m.group(6)}
        order.append(key)
    if len(cells) != 27:
        _die("收据里解析到 %d 格（期望 27）" % len(cells))
    mv = re.search(r"^VERDICT=(\S+)$", txt, re.M)
    if not mv:
        _die("收据里没有 VERDICT= 这一行")
    m2 = re.search(r"^N_DECISION_HOLD=(\d+)$", txt, re.M)
    m3 = re.search(r"^N_ALL_HOLD=(\d+)$", txt, re.M)
    m4 = re.search(r"^N_DECISION=(\d+)$", txt, re.M)
    return cells, mv.group(1), int(m2.group(1)), int(m3.group(1)), int(m4.group(1))


# =============================================================================
# 主流程
# =============================================================================

def main():
    if not os.path.isfile(LEDGER):
        print("CROSS_FAIL: 账本不存在：%s" % LEDGER)
        return 2
    if not os.path.isfile(DE_OUT):
        print("CROSS_FAIL: 被检实现的收据不存在：%s" % DE_OUT)
        return 2

    L = parse_base_ledger()
    prev = parse_prev_ledger()
    de_cells, de_form, de_dec_hold, de_all_hold, de_dec_n = parse_de_out(DE_OUT)

    (w_num, w_den) = L["w"]
    (r_num, r_den) = L["r"]
    (bw_num, bw_den) = L["bw"]
    (br_num, br_den) = L["br"]

    # ---- ① 输入对账（本脚本自己解析的 vs 账本印的）----
    d_traj = Decimal(w_num - r_num) * 100 / Decimal(w_den)
    d_blk = Decimal(bw_num - br_num) * 100 / Decimal(bw_den)
    _cmp("DELTA_OBS_PP", d_traj, L["d_traj"], TOL_ANCHOR)
    _cmp("DELTA_OBS_BLK_PP", d_blk, L["d_blk"], TOL_ANCHOR)

    w_wil = _wilson(w_num, w_den, 0.95)
    r_wil = _wilson(r_num, r_den, 0.95)
    _cmp("WILSON95_W_LO", w_wil[0], L["w_wil"][0], TOL_ANCHOR)
    _cmp("WILSON95_W_HI", w_wil[1], L["w_wil"][1], TOL_ANCHOR)
    _cmp("WILSON95_R_LO", r_wil[0], L["r_wil"][0], TOL_ANCHOR)
    _cmp("WILSON95_R_HI", r_wil[1], L["r_wil"][1], TOL_ANCHOR)

    base_main = _base_frac(L["r_dist"], r_den, "main")
    base_main_ms = _base_ms(L["r_bms"])
    _cmp("BASE_MAIN_R", base_main, L["r_base_p"], TOL_ANCHOR)
    _cmp("BASE_MAIN_R_MS", base_main_ms, L["r_base_p"], TOL_ANCHOR)
    _cmp("BASE_MAIN_ROUTE2", base_main, base_main_ms, TOL_BASE)

    nc_traj = _newcombe(w_num, w_den, r_num, r_den, 0.95)
    nc_blk = _newcombe(bw_num, bw_den, br_num, br_den, 0.95)
    _cmp("CI_LO_TRAJ_PP", nc_traj[0], L["nc_traj"][0], TOL_ANCHOR)
    _cmp("CI_HI_TRAJ_PP", nc_traj[1], L["nc_traj"][1], TOL_ANCHOR)
    _cmp("CI_LO_BLK_PP", nc_blk[0], L["nc_blk"][0], TOL_ANCHOR)
    _cmp("CI_HI_BLK_PP", nc_blk[1], L["nc_blk"][1], TOL_ANCHOR)

    # ---- ② 27 格逐格对账 ----
    ci_lo = {}
    for lv in CI_LEVELS:
        ci_lo[lv] = _newcombe(w_num, w_den, r_num, r_den, lv)[0]
    c_lo = {}
    for var in BASE_VARIANTS:
        b = _base_frac(L["r_dist"], r_den, var)
        # ⚠⚖⚖ **Fraction → Decimal 不能直接转**（⛔ `Decimal(Fraction)` 抛 TypeError）
        #   ⇒ ⇒ 必须走「分子/分母」这条路（⛔ 也不许先转 float ⇒ ⇒ 会丢精度）
        b_dec = Decimal(b.numerator) / Decimal(b.denominator)
        for lv in C_LEVELS:
            c_lo[(var, lv)] = _wilson(r_num, r_den, lv)[0] - b_dec * 100

    my_cells = {}
    for lv_ci in CI_LEVELS:
        for lv_c in C_LEVELS:
            for var in BASE_VARIANTS:
                bound = ci_lo[lv_ci] + c_lo[(var, lv_c)]
                my_cells[(lv_ci, lv_c, var)] = {
                    "bound": bound, "conf": joint_pct(lv_ci, lv_c),
                    "ok": bound > 0, "in_decision": joint_pct(lv_ci, lv_c) >= JOINT_FLOOR_PCT,
                }
                key = (lv_ci, lv_c, var)
                theirs = de_cells.get(key)
                if theirs is None:
                    MISMATCH.append("CELL%g/%g/%s" % (lv_ci * 100, lv_c * 100, var))
                    print("[MISMATCH] 格 %s 在收据里不存在" % (key,))
                    continue
                _cmp("CELL_CI%g_C%g_%s" % (lv_ci * 100, lv_c * 100, var),
                     bound, theirs["bound"], TOL_ROW)
                _cmp_str("CELLFLAG_CI%g_C%g_%s" % (lv_ci * 100, lv_c * 100, var),
                         "成立" if bound > 0 else "不成立",
                         "成立" if theirs["ok"] else "不成立")
                _cmp_str("CELLCONF_CI%g_C%g_%s" % (lv_ci * 100, lv_c * 100, var),
                         joint_pct(lv_ci, lv_c), theirs["conf"])

    # ---- ③ 决策区成员对账 ----
    my_dec = sorted(set((k[0], k[1]) for k, v in my_cells.items() if v["in_decision"]))
    de_dec = sorted(set((k[0], k[1]) for k, v in de_cells.items()
                        if v["conf"] >= JOINT_FLOOR_PCT))
    _cmp_str("DECISION_ALLOCS", my_dec, de_dec)
    my_dec_hold = len([1 for v in my_cells.values() if v["in_decision"] and v["ok"]])
    _cmp("DECISION_HOLD", my_dec_hold, de_dec_hold, 0)
    _cmp("DECISION_N", len(my_dec) * len(BASE_VARIANTS), de_dec_n, 0)
    my_all_hold = len([1 for v in my_cells.values() if v["ok"]])
    _cmp("ALL_HOLD", my_all_hold, de_all_hold, 0)

    # ---- ④ 独立重判判决形态 ----
    # H1：解析链（本脚本自己算的 vs 账本印的）
    h1_ok = (abs(float(d_traj) - L["d_traj"]) <= TOL_ANCHOR
             and abs(float(d_blk) - L["d_blk"]) <= TOL_ANCHOR
             and abs(float(w_wil[0]) - L["w_wil"][0]) <= TOL_ANCHOR
             and abs(float(w_wil[1]) - L["w_wil"][1]) <= TOL_ANCHOR
             and abs(float(r_wil[0]) - L["r_wil"][0]) <= TOL_ANCHOR
             and abs(float(r_wil[1]) - L["r_wil"][1]) <= TOL_ANCHOR
             and abs(float(base_main) - L["r_base_p"]) <= TOL_ANCHOR
             and abs(float(nc_traj[0]) - L["nc_traj"][0]) <= TOL_ANCHOR
             and abs(float(nc_traj[1]) - L["nc_traj"][1]) <= TOL_ANCHOR
             and abs(float(nc_blk[0]) - L["nc_blk"][0]) <= TOL_ANCHOR)
    # H3：单源读法跨水平
    h3_ok = all(my_ci_lo > 0 for my_ci_lo in
                [_newcombe(w_num, w_den, r_num, r_den, lv)[0] for lv in CI_LEVELS])
    h3_ok = h3_ok and all(_newcombe(bw_num, bw_den, br_num, br_den, lv)[0] > 0
                          for lv in CI_LEVELS)
    # H4：点估计读法跨水平
    h4_ok = all((d_traj + c_lo[(var, lv)]) > 0
                for lv in C_LEVELS for var in BASE_VARIANTS)
    h4_ok = h4_ok and all((d_blk + c_lo[(var, lv)]) > 0
                          for lv in C_LEVELS for var in BASE_VARIANTS)
    # H5：决策区全成立
    h5_ok = all(v["ok"] for v in my_cells.values() if v["in_decision"])
    # H6：全 27 格成立
    h6_ok = all(v["ok"] for v in my_cells.values())
    # H9 的关键部分：与 244.88 印的那 9 格**逐格**对账（差必须被 CI 输入的偏移完全解释）
    # ⚖ 容差 = 244.88 那 9 格的打印精度（4 位小数）的半个单位 = 5e-5
    #   （⛔ 1e-6 不可能达到 ⇒ ⇒ 那条判据会恒红 ⇒ ⇒ 等于没有判据）
    old_ci_input = Decimal(str(_prev_r1(LEDGER)))
    shift = ci_lo[MAIN_CI_LEVEL] - old_ci_input
    h9_ok = True
    for (lv_c, var), (old, _conf) in sorted(prev.items()):
        mine = my_cells[(MAIN_CI_LEVEL, lv_c, var)]["bound"]
        resid = (mine - Decimal(str(old))) - shift
        if abs(float(resid)) > 5e-5:
            h9_ok = False
            print("[MISMATCH] H9 残差 CI95/%.0f/%s ⇒ %.3e" % (lv_c * 100, var, float(resid)))
        if (mine > 0) != (old > 0):
            h9_ok = False
            print("[MISMATCH] H9 标志 CI95/%.0f/%s 不一致" % (lv_c * 100, var))
    if h9_ok:
        OK.append("H9_残差与标志")
        print("[OK ] H9_残差与标志  9 格逐格：差全部被 CI 输入偏移 %+.6f 解释（残差 ≤ 5e-5）"
              % float(shift))
    else:
        MISMATCH.append("H9_残差与标志")

    # 独立级联（⛔ 自己写一遍，不调被检实现）
    if not h1_ok or not h9_ok:
        my_form = "E'"
    elif not h3_ok:
        my_form = "D'"
    elif not h4_ok:
        my_form = "C'"
    elif not h5_ok or not h6_ok:
        my_form = "B'"
    else:
        my_form = "A'"
    _cmp_str("判决形态", my_form, de_form)
    _cmp_str("判决形态(独立级联)", my_form, de_form)

    print("")
    print("CROSS_OK=%d ｜ CROSS_MISMATCH=%d" % (len(OK), len(MISMATCH)))
    print("CROSS_FORM=%s" % my_form)
    if MISMATCH:
        print("CROSS_MISMATCH_LIST=%s" % ",".join(MISMATCH))
        print("CROSS_RC=1")
        return 1
    print("CROSS_RC=0")
    return 0


def _prev_r1(ledger_path):
    """⚖ 244.88 段印的 R1 界（= 它当时用的 CI 输入）⇒ ⇒ 独立解析。"""
    lines = _read(ledger_path).split("\n")
    sec = _section(lines, "244.88")
    for ln in sec:
        if "**R1**" in ln and "轨迹级" in ln:
            m = re.search(r"\*\*([+-][0-9.]+) pp\*\*", ln)
            if m:
                return float(m.group(1))
    _die("244.88 段印的 R1 界读不到")


if __name__ == "__main__":
    sys.exit(main())
