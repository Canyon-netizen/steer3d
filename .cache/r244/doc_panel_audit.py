#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc_panel_audit.py —— 244.96：页面 §6.1 **判决面板 P1–P29** ↔ 账本 **可溯源**对账（零 GPU）。

⚖⚖⚖ **口径真相源**：`.cache/xcheck/R6_PANEL_PREREG.md`（244.96 签，**先于**实现）。
   §0 范围与不做项、§1 侦察结论、§2 判据 E1–E8、§3 实现纪律、§4 变异台、§5 互证、§6 边界。

⚖⚖⚖ **本文件做什么**
   ① 抓页面 §6.1 的 **29** 个 P 行；
   ② 每行取「账本位置」⇒ 解析成**精确的引用行集合**
      （离散项取自己；区间项取区间全部行；⛔ **不用 min..max 窗口**）；
   ③ 实测列的**强 token**（含小数点 / e 记法）必须
      「逐位出现在那些行里」**或**满足 **R6'**（各自印到 6 位小数后逐位相同）；
   ④ 「破口 N」「决策区内 N」两个计数：N 必须等于某条**破口/违例清单**的条目数，
      且**短语（数＋量词）**必须逐位出现在那些行里；
   ⑤ 派生分数 `a/b` 必须逐位出现在那些行里。

⚖⚖⚖ **本文件不做什么**
   ⛔ **不读收据**（收据不入库）⇒ ⇒ 别人 clone 下来就能跑。
   ⛔ **零 GPU**、⛔ 没跑批、⛔ 不碰 bpath、⛔ **不改任何被测文件**。
   ⛔ **不判弱 token**（纯整数在窗口里几乎必然偶然出现 ⇒ ⇒ 证据弱）⇒ ⇒ 留白。
   ⛔ **不判**「56 个 base」这类**页面补充说明** ⇒ ⇒ 留白。
   ⛔ **不许**用「|page − ledger| ≤ tol 且 tol 现算」的容差 ⇒ ⇒ 那是「为让数对上而定的容差」。

⚖ **R6' 的外部依据**（⛔ 不是本轮反推的）：账本 `:41722`「把本轮的值印到 6 位小数，
   必须与账本那个数**逐位相同**」＋「绝对差 ≤ 5e-7（由打印精度推导，不是从实测值倒推）」；
   账本 `:39004`「判决行与场景行改用 6 位小数」。
"""

import argparse
import io
import os
import re
import sys
from decimal import Context, ROUND_HALF_UP

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEFAULT_PAGE = os.path.join("docs", "BPATH_VERDICT.md")
DEFAULT_LEDGER = os.path.join(".cache", "xcheck", "R6_RERUN_PREREG.md")

CTX = Context(prec=30, rounding=ROUND_HALF_UP)

# ⚖ 预登记 §2 里写死的口径常量（⛔ 不许在实现里另定）
N_PANEL_ROWS = 29
R6_DECIMALS = 6

# ⚖ 计数短语（预登记 §2 E5/E6）：只管这两类
COUNT_PATTERNS = (("破口", r"破口\s*(\d+)\s*[处个]"),
                  ("决策区内", r"决策区内\s*(\d+)\s*[处个]"))

TOKEN_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
NUM_RE = re.compile(r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?")
FRAC_RE = re.compile(r"\d+/\d+")


# ---------------------------------------------------------------- 基础工具

def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def norm(s):
    """归一化：去反引号 / 去粗体星号 / 去所有空白（244.93/244.94 同口径）。"""
    s = s.replace("`", "").replace("**", "")
    return re.sub(r"\s+", "", s)


def cited_lines(loc):
    """从「账本位置」格子解析**精确的引用行集合**（预登记 §1.1 ②）。

    ⚠⚠⚠⛔ **不许用 min..max 的区间窗口**：P22 的引用是 `:42164`、`:42222`
      （**两个离散行**）⇒ 取区间会**夹进 57 行没被引用的行** ⇒ ⇒
      「4/12」会在区间内的 `:42388` 上**偶然命中** ⇒ ⇒ **判据虚高**。
    """
    out = set()
    loc = loc.replace("`", "")
    for item in re.split(r"[、,，]", loc):
        rng = re.search(r":(\d+)\s*[–\-—~]\s*:?(\d+)", item)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            out.update(range(min(a, b), max(a, b) + 1))
            continue
        one = re.search(r":(\d+)", item)
        if one:
            out.add(int(one.group(1)))
    return sorted(out)


def fmt6_fixed(v):
    """定点：印到 6 位小数（字符串）⇒ 账本 :41722 的「印到 6 位小数」口径。"""
    q = CTX.create_decimal(CTX.create_decimal(repr(float(v))).quantize(
        CTX.create_decimal("0.000001")))
    return str(q)


def fmt6_sci(v):
    """科学计数法：尾数印 6 位小数（字符串），指数 e±NN。"""
    fv = float(v)
    if fv == 0:
        return "0.000000"
    k = 0
    a = abs(fv)
    while a >= 10:
        a /= 10.0
        k += 1
    while a < 1:
        a *= 10.0
        k -= 1
    qm = CTX.create_decimal(CTX.create_decimal(repr(a)).quantize(
        CTX.create_decimal("0.000001")))
    return "%se%+03d" % (str(qm), k)


def r6_equal(ledger_num, page_token):
    """规则 R6'：账本数与页面数**各自**按页面记法印到 6 位小数 ⇒ ⇒ 逐位相同？

    ⚖ **字符串级**，⛔ 不是容差比较。依据：账本 `:41722`。
    """
    t = page_token.lstrip("+")
    try:
        ft = float(t)
    except ValueError:
        return False
    if "e" in t.lower():
        return fmt6_sci(ledger_num) == fmt6_sci(ft)
    return fmt6_fixed(ledger_num) == fmt6_fixed(ft)


def page_decimals(token):
    """页面值的打印精度（定点的小数位数 / 科学计数法**尾数**的小数位数）。"""
    t = token.lstrip("+")
    if "e" in t.lower():
        mant = t.lower().split("e")[0]
        return len(mant.split(".")[1]) if "." in mant else 0
    return len(t.split(".")[1]) if "." in t else 0


def is_strong(tok):
    """强 token = 含小数点或 e 记法（p 值、pp 值）⇒ ⇒ 证据强。"""
    return ("." in tok) or ("e" in tok.lower())


def list_len_in_line(line_norm):
    """一行里「破口：」/「违例：」清单的条目数；没有清单 ⇒ None。

    ⚖ 计数口径（预登记 §2 E5）：**一条** = 一个形如
      `CI<档>/污染<档>/<基准>(<值>, 联合 <x>%)` 的项；按**条目分隔符**切分。
    ⚖⚠ **分隔符**：预登记写的是 `), `（**带空格**，因为那是账本原文）；
      ⇒ ⇒ 本函数在**去空白之后**的文本上切 ⇒ ⇒ 分隔符变成 `),`
      ⇒ ⇒ **两者计数完全等价**（norm 只去空白，不动标点）⇒ ⇒ ⛔ 不是改口径。
    """
    for marker in ("破口：", "违例："):
        idx = line_norm.rfind(marker)
        if idx < 0:
            continue
        body = line_norm[idx + len(marker):]
        if not body:
            continue
        items = [x for x in body.split("),") if x.strip()]
        return len(items)
    return None


# ---------------------------------------------------------------- 面板解析

def parse_panel(page_text):
    """抓 §6.1 面板的 29 个 P 行 ⇒ ⇒ [(pid, cells, raw_line)]；解析失败 ⇒ 抛。"""
    lines = page_text.split("\n")
    start = None
    for i, l in enumerate(lines):
        if l.startswith("## 6.1 "):
            start = i
            break
    if start is None:
        raise ValueError("页面里找不到 §6.1 标题")
    rows = []
    for l in lines[start:]:
        if l.startswith("## 6.2"):
            break
        m = re.match(r"^\|\s*\*\*(P\d+)\*\*\s*\|(.*)$", l)
        if not m:
            continue
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if len(cells) < 6:
            raise ValueError("%s 的格子数 = %d（期望 ≥6）" % (m.group(1), len(cells)))
        rows.append((m.group(1), cells, l))
    return rows


# ---------------------------------------------------------------- 判据

def audit(page_text, ledger_text):
    """跑 E1–E8 ⇒ ⇒ (results, aux)。results = [(cid, ok, detail)]。"""
    res = []
    aux = {}

    def chk(cid, ok, detail):
        res.append((cid, bool(ok), detail))

    led_lines = ledger_text.split("\n")
    n_ledger = ledger_text.count("\n")

    # ---- E1 结构 ----
    try:
        rows = parse_panel(page_text)
        parse_err = ""
    except ValueError as e:
        rows = []
        parse_err = str(e)
    pids = [r[0] for r in rows]
    expect_ids = ["P%d" % i for i in range(1, N_PANEL_ROWS + 1)]
    e1_ok = (not parse_err) and len(rows) == N_PANEL_ROWS and pids == expect_ids
    chk("E1", e1_ok,
        "P 行 %d 条（期望 %d）｜ 编号连续无缺无重：%s%s"
        % (len(rows), N_PANEL_ROWS, "是" if pids == expect_ids else "否",
           ("｜ 解析错误：" + parse_err) if parse_err else ""))
    if not rows:
        return res, aux

    # ---- 逐行 ----
    n_strong = n_verb = n_r6 = n_miss = 0
    n_frac = n_frac_miss = 0
    r6_detail = []
    miss_detail = []
    frac_miss_detail = []
    cnt_detail = []
    cnt_miss_detail = []      # E5：计数口径不满足
    cnt_phrase_miss_detail = []   # E6：短语不逐位
    e2_ok = True
    e5_ok = True
    e6_ok = True
    e7_ok = True
    e8_ok = True
    row_verdicts = []
    matrix = []

    for pid, cells, raw in rows:
        meas = cells[2]
        loc = cells[4]
        cl = cited_lines(loc)
        # ---- E2 出处存在 ----
        if not cl:
            e2_ok = False
        for n in cl:
            if n < 1 or n > n_ledger:
                e2_ok = False
        # ⚠ 越界的行号**不取进窗口**（否则 IndexError）⇒ ⇒ E2 照样判红，
        #   而 E3/E5/E6/E7 只在**有效引用**上判（⛔ 不让越界把别的判据带崩）
        cited_text = "\n".join(led_lines[n - 1] for n in cl if 1 <= n <= n_ledger)
        cn = norm(cited_text)
        cn_lines = [norm(led_lines[n - 1]) for n in cl if 1 <= n <= n_ledger]
        win_nums = NUM_RE.findall(cited_text)

        # ---- E3 强 token 可溯源 ----
        s_n = v_n = r_n = mi_n = 0
        for t in TOKEN_RE.findall(meas):
            if not is_strong(t):
                continue
            s_n += 1
            cand = [t, t.lstrip("+"), t.lstrip("-"), "+" + t.lstrip("+"), "-" + t.lstrip("-")]
            if any(norm(c) in cn for c in cand):
                v_n += 1
                continue
            hit = False
            for s in win_nums:
                try:
                    fv = float(s)
                except ValueError:
                    continue
                if r6_equal(fv, t):
                    hit = True
                    break
            if hit:
                r_n += 1
                r6_detail.append((pid, t, page_decimals(t)))
            else:
                mi_n += 1
                miss_detail.append((pid, t))
        n_strong += s_n
        n_verb += v_n
        n_r6 += r_n
        n_miss += mi_n

        # ---- E4 R6' 分支的收紧 ----
        for _p, t, d in [x for x in r6_detail if x[0] == pid]:
            if d != R6_DECIMALS:
                e4_ok = False
        # E3 自身的缺口
        if mi_n:
            e3_ok = False
        else:
            e3_ok = True

        # ---- E7 派生分数逐位 ----
        fr = []
        for m in FRAC_RE.finditer(norm(meas)):
            if m.group(0) not in fr:
                fr.append(m.group(0))
        f_hit = [p_ for p_ in fr if p_ in cn]
        f_miss = [p_ for p_ in fr if p_ not in cn]
        n_frac += len(fr)
        n_frac_miss += len(f_miss)
        if f_miss:
            e7_ok = False
            frac_miss_detail.append((pid, f_miss))

        # ---- E5 / E6 计数 ----
        c_hit = 0
        c_total = 0
        for _name, pat in COUNT_PATTERNS:
            m2 = norm(meas)
            for m in re.finditer(pat, m2):
                c_total += 1
                num = int(m.group(1))
                phrase = m.group(0)
                # E6：短语（数＋量词）逐位
                if phrase not in cn:
                    e6_ok = False
                    cnt_phrase_miss_detail.append((pid, phrase, "短语不逐位"))
                # E5：N == 某条破口/违例清单的条目数
                lens = [list_len_in_line(l) for l in cn_lines]
                lens = [x for x in lens if x is not None]
                if num not in lens:
                    e5_ok = False
                    cnt_miss_detail.append((pid, phrase, "计数不可数（清单长度 %s）" % lens))
                else:
                    c_hit += 1
        cnt_detail.append((pid, c_hit, c_total))

        # ---- E8 非空 ----
        if (v_n + r_n + len(f_hit) + c_hit) == 0:
            e8_ok = False
            row_verdicts.append((pid, "EMPTY"))
        else:
            row_verdicts.append((pid, "OK" if (mi_n == 0 and not f_miss) else "MISS"))

        matrix.append((pid, len(cl), s_n, v_n, r_n, mi_n, len(f_hit), len(fr)))

    # ---- 汇总判据 ----
    chk("E2", e2_ok,
        "每行都有可解析的 `:NNNN` 且所有被引行号 ∈ [1, %d]：%s"
        % (n_ledger, "是" if e2_ok else "否"))
    chk("E3", n_miss == 0,
        "强 token %d 个 ｜ 逐位 %d ｜ R6' %d ｜ **缺口 %d**%s"
        % (n_strong, n_verb, n_r6, n_miss,
           ("（%s）" % "、".join("%s:%s" % (p_, t) for p_, t in miss_detail[:6])) if n_miss else ""))
    e4_bad = [x for x in r6_detail if x[2] != R6_DECIMALS]
    chk("E4", not e4_bad,
        "走 R6' 分支的 %d 个页面值，打印精度必须恰好 %d 位小数：%s"
        % (len(r6_detail), R6_DECIMALS,
           ("全部 %d 位 ✅" % R6_DECIMALS) if not e4_bad
           else ("⛔ %s" % "、".join("%s:%s(%d 位)" % (p_, t, d) for p_, t, d in e4_bad))))
    chk("E5", e5_ok,
        "每个「破口 N / 决策区内 N」的 N 必须等于某条破口/违例清单的条目数：%s"
        % ("是" if e5_ok else
           ("⛔ " + "、".join("%s「%s」%s" % (p_, ph, why) for p_, ph, why in cnt_miss_detail))))
    chk("E6", e6_ok,
        "每个计数短语（数＋量词）必须逐位出现在所引账本行里：%s"
        % ("是" if e6_ok else
           ("⛔ " + "、".join("%s「%s」" % (p_, ph) for p_, ph, _w in cnt_phrase_miss_detail))))
    chk("E7", n_frac_miss == 0,
        "派生分数 %d 个 ｜ 逐位 %d ｜ **缺口 %d**%s"
        % (n_frac, n_frac - n_frac_miss, n_frac_miss,
           ("（%s）" % "、".join("%s:%s" % (p_, "、".join(m)) for p_, m in frac_miss_detail[:6]))
           if n_frac_miss else ""))
    chk("E8", e8_ok,
        "每行至少有 1 个强 token 或派生短语被命中：%s"
        % ("是" if e8_ok else
           ("⛔ " + "、".join(p for p, v in row_verdicts if v == "EMPTY"))))

    aux.update({
        "rows": rows, "matrix": matrix, "row_verdicts": row_verdicts,
        "n_strong": n_strong, "n_verbatim": n_verb, "n_r6": n_r6, "n_missing": n_miss,
        "n_frac": n_frac, "n_frac_missing": n_frac_miss,
        "n_count": sum(c for _p, c, _t in cnt_detail),
        "n_count_total": sum(t for _p, _c, t in cnt_detail),
        "r6_detail": r6_detail,
        "miss_detail": miss_detail,
        "frac_miss_detail": frac_miss_detail,
        "cnt_miss_detail": cnt_miss_detail,
        "cnt_phrase_miss_detail": cnt_phrase_miss_detail,
        "n_ledger_lines": n_ledger,
    })
    return res, aux


def verdict_of(res):
    red = [cid for cid, ok, _d in res if not ok]
    if not red:
        return "A", []
    return "D", red


# ---------------------------------------------------------------- 自检

def _fixture(rows_spec, ledger_lines):
    """造一份合成页面：rows_spec = [(pid, meas, loc)]。"""
    out = ["## 6.1 📊 判决面板", "", "| # | 量 | 实测 | 口径 | 账本位置 | 复算 |",
           "|---|---|---|---|---|---|"]
    for pid, meas, loc in rows_spec:
        out.append("| **%s** | 量 | %s | 口径 | %s | RC |" % (pid, meas, loc))
    out.append("")
    out.append("## 6.2 📐 剂量轴")
    return "\n".join(out) + "\n"


def _full_fixture(ledger_lines):
    """造一份**完整**的 29 行合成面板：每行一个强 token，且都逐位可溯源。"""
    spec = []
    for i in range(1, 30):
        spec.append(("P%d" % i, "实测 **0.5%**", "`:1`"))
    return _fixture(spec, ledger_lines), spec


def selftest():
    fails = []

    def case(name, cond, detail=""):
        if not cond:
            fails.append("%s｜%s" % (name, detail))

    # ---- 合成夹具区开始（⛔ 本区的合成值**不算**「手写期望」）----
    led = "\n".join([
        "· L1 有 **0.500000** 的数",
        "· L2 有 **0.25** 的数",
        "· L3 破口：CI95/污染99/main(-0.7675, 联合 94%), CI99/污染99/main(-6.3298, 联合 98%)",
        "· L4 违例：CI95/污染99/main(-0.7675, 联合 94%)",
        "· L5 有 **3.940943378013e-01**",
        "· L6 有 **0.709842**",
    ]) + "\n"

    # ---- 夹具 1：29 行、全部逐位可溯源 ⇒ E1–E8 全绿 ----
    page, spec = _full_fixture(led.split("\n"))
    res, aux = audit(page, led)
    v, red = verdict_of(res)
    case("T1 全绿夹具", v == "A" and not red, "verdict=%s red=%s" % (v, red))
    case("T1b 强 token 全命中", aux["n_missing"] == 0 and aux["n_strong"] == 29,
         "missing=%d strong=%d" % (aux["n_missing"], aux["n_strong"]))

    # ---- E1：少一行 ⇒ 红 ----
    p2, _ = _full_fixture(led.split("\n"))
    p2 = p2.replace("| **P29** | 量 | 实测 **0.5%** | 口径 | `:1` | RC |\n", "")
    res2, _ = audit(p2, led)
    v2, red2 = verdict_of(res2)
    case("T2 E1 少一行", "E1" in red2 and v2 == "D", "red=%s" % red2)

    # ---- E2：引用越界 ⇒ 红 ----
    spec3 = [("P%d" % i, "实测 **0.5%**", "`:1`") for i in range(1, 30)]
    spec3[0] = ("P1", "实测 **0.5%**", "`:99999`")
    p3 = _fixture(spec3, led.split("\n"))
    res3, _ = audit(p3, led)
    _v3, red3 = verdict_of(res3)
    case("T3 E2 越界", "E2" in red3, "red=%s" % red3)

    # ---- E3：把 0.5% 改成 0.6% ⇒ 红 ----
    spec4 = [("P%d" % i, "实测 **0.5%**", "`:1`") for i in range(1, 30)]
    spec4[0] = ("P1", "实测 **0.6%**", "`:1`")
    p4 = _fixture(spec4, led.split("\n"))
    res4, _ = audit(p4, led)
    _v4, red4 = verdict_of(res4)
    case("T4 E3 数被改坏", "E3" in red4, "red=%s" % red4)

    # ---- R6'：0.394094 应由 3.940943378013e-01 经 6 位小数命中 ----
    spec5 = [("P%d" % i, "实测 **0.5%**", "`:1`") for i in range(1, 30)]
    spec5[0] = ("P1", "实测 p = **0.394094**", "`:5`")
    p5 = _fixture(spec5, led.split("\n"))
    res5, aux5 = audit(p5, led)
    _v5, red5 = verdict_of(res5)
    case("T5 R6' 命中", "E3" not in red5 and aux5["n_r6"] == 1,
         "red=%s r6=%d" % (red5, aux5["n_r6"]))

    # ---- E4：7 位小数 ⇒ E4 红（E3 仍绿）⇒ 这正是 E4 存在的理由 ----
    spec6 = [("P%d" % i, "实测 **0.5%**", "`:1`") for i in range(1, 30)]
    spec6[0] = ("P1", "实测 p = **0.3940944**", "`:5`")
    p6 = _fixture(spec6, led.split("\n"))
    res6, _ = audit(p6, led)
    _v6, red6 = verdict_of(res6)
    case("T6 E4 7 位小数", "E4" in red6 and "E3" not in red6, "red=%s" % red6)

    # ---- E5：破口 N 与清单长度不符 ⇒ 红 ----
    spec7 = [("P%d" % i, "实测 **0.5%**", "`:1`") for i in range(1, 30)]
    spec7[0] = ("P1", "实测 **破口 10 个**", "`:3`")     # L3 的清单是 2 条
    p7 = _fixture(spec7, led.split("\n"))
    res7, _ = audit(p7, led)
    _v7, red7 = verdict_of(res7)
    case("T7 E5 计数不符", "E5" in red7, "red=%s" % red7)

    # ---- E6：量词不同 ⇒ 红 ----
    spec8 = [("P%d" % i, "实测 **0.5%**", "`:1`") for i in range(1, 30)]
    spec8[0] = ("P1", "实测 **破口 2 处**", "`:3`")     # L3 写的是「破口：」不是「破口 2 个」
    p8 = _fixture(spec8, led.split("\n"))
    res8, _ = audit(p8, led)
    _v8, red8 = verdict_of(res8)
    case("T8 E6 量词不符", "E6" in red8, "red=%s" % red8)

    # ---- E7：派生分数不逐位 ⇒ 红 ----
    spec9 = [("P%d" % i, "实测 **0.5%**", "`:1`") for i in range(1, 30)]
    spec9[0] = ("P1", "实测 **4/12 格成立**", "`:2`")
    p9 = _fixture(spec9, led.split("\n"))
    res9, _ = audit(p9, led)
    _v9, red9 = verdict_of(res9)
    case("T9 E7 分数不逐位", "E7" in red9, "red=%s" % red9)

    # ---- E8：整行全 miss ⇒ 红 ----
    spec10 = [("P%d" % i, "实测 **0.5%**", "`:1`") for i in range(1, 30)]
    spec10[0] = ("P1", "实测 **0.6%**", "`:2`")
    p10 = _fixture(spec10, led.split("\n"))
    res10, _ = audit(p10, led)
    _v10, red10 = verdict_of(res10)
    case("T10 E8 空行", "E8" in red10, "red=%s" % red10)

    # ---- 精确引用集合：**不能**用 min..max 窗口 ⇒⇒ 离散引用外的行不算数 ----
    led2 = "\n".join([
        "L1 **0.111111**",
        "L2 **0.222222**",
        "L3 **0.333333**",
        "L4 **0.444444**",
    ]) + "\n"
    # ⚠ 其余 28 行必须引用**含有它们自己那个数**的行，否则它们自己就会漏
    spec11 = [("P%d" % i, "实测 **0.111111**", "`:1`") for i in range(1, 30)]
    spec11[0] = ("P1", "实测 **0.444444**", "`:1`、`:4`")   # 只引 L1 与 L4 ⇒ L4 在窗口里
    p11 = _fixture(spec11, led2.split("\n"))
    res11, aux11 = audit(p11, led2)
    case("T11 离散引用命中", "E3" not in verdict_of(res11)[1], "red=%s" % verdict_of(res11)[1])

    spec12 = [("P%d" % i, "实测 **0.111111**", "`:1`") for i in range(1, 30)]
    spec12[0] = ("P1", "实测 **0.333333**", "`:1`、`:4`")   # 0.333333 在 L3，**没被引用**
    p12 = _fixture(spec12, led2.split("\n"))
    res12, _ = audit(p12, led2)
    case("T12 区间窗口不得夹带", "E3" in verdict_of(res12)[1], "red=%s" % verdict_of(res12)[1])

    # ---- 弱 token 不判（⇒ E3 不因纯整数红）----
    spec13 = [("P%d" % i, "实测 **0.5%**", "`:1`") for i in range(1, 30)]
    spec13[0] = ("P1", "实测 **99/56**", "`:1`")
    p13 = _fixture(spec13, led.split("\n"))
    res13, aux13 = audit(p13, led)
    case("T13 弱 token 不判", aux13["n_missing"] == 0,
         "missing=%d" % aux13["n_missing"])

    # ---- 自检区结束 ----
    print("")
    total = 13
    print("自检 %d/%d 通过" % (total - len(fails), total))
    if fails:
        for f in fails:
            print("  [FAIL] %s" % f)
    print("SELFTEST_RED=%d" % len(fails))
    print("SELFTEST_RC=%d" % (0 if not fails else 1))
    return 0 if not fails else 1


# ---------------------------------------------------------------- 主流程

def run_data(page_path, ledger_path):
    page_text = read_text(page_path)
    ledger_text = read_text(ledger_path)
    res, aux = audit(page_text, ledger_text)
    v, red = verdict_of(res)

    print("=" * 78)
    print("页面：%s" % page_path)
    print("账本：%s（%d 行）" % (ledger_path, ledger_text.count("\n")))
    print("=" * 78)
    for cid, ok, detail in res:
        print("[%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))
    print("")
    print("⚖ **明细计数（⛔ 不是判据）**：")
    print("  · 强 token %d ｜ 逐位 %d ｜ R6' %d ｜ 缺口 %d"
          % (aux["n_strong"], aux["n_verbatim"], aux["n_r6"], aux["n_missing"]))
    print("  · 派生分数 %d ｜ 缺口 %d" % (aux["n_frac"], aux["n_frac_missing"]))
    print("  · 计数短语 %d ｜ 口径不满足 %d 处"
          % (aux["n_count_total"], len(aux["cnt_miss_detail"])))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for _c, ok, _d in res if ok), len(res)))
    print("VERDICT=%s" % v)
    print("REASON=%s" % (
        "页面 §6.1 判决面板 P1–P29 的每个强 token 都**可溯源**到它引用的账本行"
        "（逐位，或按 R6' 印到 6 位小数后逐位相同）⇒ 形态 A"
        if v == "A" else
        "有判红（%s）⇒ 形态 D（⛔ 那次不算判决）" % "、".join(red)))
    print("")
    print("===== NUM_MATRIX =====")
    for pid, ncite, s_n, v_n, r_n, mi_n, f_hit, f_tot in aux["matrix"]:
        print("ROW=%s|cites=%d|strong=%d|verbatim=%d|r6=%d|missing=%d|frac=%d/%d"
              % (pid, ncite, s_n, v_n, r_n, mi_n, f_hit, f_tot))
    print("===== END_NUM_MATRIX =====")
    print("")
    print("===== ROW_VERDICTS =====")
    for pid, st in aux["row_verdicts"]:
        print("ROWV=%s|%s" % (pid, st))
    print("===== END_ROW_VERDICTS =====")
    print("")
    print("===== AUDIT_KEYS =====")
    print("VERDICT=%s" % v)
    print("N_CHECKS=%d" % len(res))
    print("CHECKS_RED=%d" % sum(1 for _c, ok, _d in res if not ok))
    for cid, ok, _d in res:
        print("CHECK_%s=%s" % (cid, "PASS" if ok else "FAIL"))
    print("N_STRONG=%d" % aux["n_strong"])
    print("N_VERBATIM=%d" % aux["n_verbatim"])
    print("N_R6=%d" % aux["n_r6"])
    print("N_MISSING=%d" % aux["n_missing"])
    print("N_FRAC=%d" % aux["n_frac"])
    print("N_FRAC_MISSING=%d" % aux["n_frac_missing"])
    print("N_COUNT=%d" % aux["n_count_total"])
    print("===== END_AUDIT_KEYS =====")
    return 0 if v == "A" else 1


def main():
    ap = argparse.ArgumentParser(
        description="244.96：页面 §6.1 判决面板 P1–P29 ↔ 账本 可溯源对账（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--data", action="store_true")
    ap.add_argument("--page", default=None)
    ap.add_argument("--ledger", default=None)
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if args.data:
        page_path = args.page or os.path.join(REPO, DEFAULT_PAGE)
        ledger_path = args.ledger or os.path.join(REPO, DEFAULT_LEDGER)
        try:
            return run_data(page_path, ledger_path)
        except Exception as e:                       # noqa: BLE001
            print("[错误] %s" % e)
            return 2
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
