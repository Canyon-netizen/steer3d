#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc_dose_axis_audit.py —— **244.93**：页面 `docs/BPATH_VERDICT.md` 的 **§6.2.3「剂量轴展品块」**
↔ **权威账本**的逐条对账。

⚖⚖⚖ **本轮的核心设计（预登记 §2.2）**：**期望值从页面那一行自己派生**，⛔ **一个数都不手写**。
   · 判据要验的是「**页面这一行的每个数，能不能在它引用的账本行里逐位找到**」；
   · ⇒ ⇒ **数写错 ⇒ 找不到 ⇒ 红**；**出处引错 ⇒ 找不到 ⇒ 红**；
   · ⇒ ⇒ 零手写期望 ⇒ ⇒ 既不会「恒绿」，也不会像 MU21 那样「期望本身写错」。

⚖⚖⚖ **代价与边界（预登记 §6）**：本判据守的是「**数与出处脱节**」，
   ⛔ **不是**「出处引得最准」⇒ ⇒ 那是**留白**，不是缺陷。

⚖ **数据来源**：**只读已入库文件**（页面 ＋ 账本整本）⇒ ⇒ 别人 clone 下来就能跑；⛔ **不读收据**。
⚖ **零 GPU、零跑批、不重解析原始跑批日志**。
"""

import argparse
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEFAULT_PAGE = os.path.join("docs", "BPATH_VERDICT.md")
DEFAULT_LEDGER = os.path.join(".cache", "xcheck", "R6_RERUN_PREREG.md")

# ================================================================ 锚点（预登记 §2.4）
# ⚖⚖⚖ **标签是「归一化后的整格」**（数字 ⇒ `#`）：第一列里**含数据**（例：`**四档**分档（**88 格**）`）
#    ⇒ ⇒ 用**原样整格**去比**永远比不上** ⇒ ⇒ 归一化后比**整格** ⇒ ⇒ 既不是裸串、也不是子串，
#    而且对**数据变化**鲁棒（页面把 109 改成 110 时，锚点照样命中 ⇒ ⇒ 不会误报「定位不到」）。
ANCHORS = [
    ("分位点", "注入比例轴的**分位点**"),
    ("四档", "**四档**分档（**# 格**）"),
    ("rho", "rho（剂量—响应相关）"),
    ("格集合", "**格集合的三条过滤条件**"),
    ("脆性", "**脆性**：**±# token** 扰动族"),
]

# ⚖ 展品表的**表头**（用来定位这张表 ⇒ ⇒ 不依赖「第几行」这种会漂的东西）
TABLE_HEADER = "| 展品 | 实测 | 账本位置 | 复算 |"

# ⚖ 口径切换注的标记（正文行）＋ 出处行的行首（下一行）
NOTE_MARK = "**口径切换（⛔ 不许偷偷改）**"
NOTE_SRC_PREFIX = "　出处："

# ⚖ **独立成词**的数：形如 `+0.501` / `0.111` / `21`（⚖ **举例**，⛔ 不是任何期望值）
NUM_TOKEN = re.compile(r"[+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?")
# ⚖ 四档组（口径切换注专用）：`21/22/23/24`（⚖ **举例**，⛔ 不是任何期望值）
BAND_GROUP = re.compile(r"\d+/\d+/\d+/\d+")
# ⚖ 账本行号引用：`:37545`（**1–6 位** ⇒ ⇒ 合成夹具可以用 `:4` 这种小行号）
CITE = re.compile(r":(\d{1,6})")
# ⚖ 区间引用：`:38191`–`:38193`
CITE_RANGE = re.compile(r":(\d{1,6})`[–—\-]+`?:(\d{1,6})")


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def is_standalone(tok, before, after):
    """⚖ 「独立成词」：紧邻字母/下划线/点的数字**不算数**（⇒ 文件名、标签里的数字不参与）。"""
    if before and (before.isalnum() or before in "_."):
        return False
    if after and (after.isalnum() or after in "_."):
        return False
    return True


def numbers_in(text):
    """⚖ 取文本里「独立成词」的数（**带正负号**的完整 token）。"""
    out = []
    for m in NUM_TOKEN.finditer(text):
        tok = m.group(0)
        s, e = m.start(), m.end()
        before = text[s - 1] if s > 0 else ""
        after = text[e] if e < len(text) else ""
        if not is_standalone(tok, before, after):
            continue
        out.append(tok)
    return out


def cells_of(row):
    """⚖ 表格行 ⇒ ⇒ 列（去掉首尾两个空列）⇒ ⇒ [展品, 实测, 账本位置, 复算]。"""
    parts = row.split("|")
    # 形如 "| a | b | c | d |" ⇒ split ⇒ ['', ' a ', ' b ', ' c ', ' d ', '']
    return [p.strip() for p in parts[1:-1]]


def cited_lines(cell):
    """⚖ 从「账本位置」那一格取出**引用到的账本行号集合**（区间会展开）。

    ⚖⚖⚖ **区间展开是必须的**：`:38191`–`:38193` 表示**三条**行 ⇒ ⇒ 只取两端会漏掉中间那条
       ⇒ ⇒ 漏掉的那条如果正好不含页面上的某个数 ⇒ ⇒ D1 会**误判红**。
    """
    lines = set()
    for m in CITE.finditer(cell):
        lines.add(int(m.group(1)))
    for m in CITE_RANGE.finditer(cell):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b:
            for x in range(a, b + 1):
                lines.add(x)
    return sorted(lines)


def find_table_rows(page_lines):
    """⚖ 定位「展品 | 实测 | 账本位置 | 复算」这张表 ⇒ ⇒ 返回它的数据行（**整行**）。"""
    hdr = None
    for i, l in enumerate(page_lines):
        if l.strip() == TABLE_HEADER:
            hdr = i
            break
    if hdr is None:
        return None, []
    rows = []
    for l in page_lines[hdr + 1:]:
        s = l.strip()
        if not s.startswith("|"):
            break
        if set(s) <= set("|-: "):
            continue
        rows.append(l)
    return hdr, rows


def normalize_nums(text):
    """⚖ 把文本里的**数**换成 `#`（⇒ 「形状相等」用）——⚠ **只用于定位**，不用于判据本身。"""
    return NUM_TOKEN.sub("#", text)


def locate_row(rows, label):
    """⚖ 按**归一化后的整格相等**定位那一行 ⇒ ⇒ 找不到 ⇒ 返回 []（⇒ 判据红）。"""
    want = normalize_nums(label)
    hits = []
    for l in rows:
        cs = cells_of(l)
        if not cs:
            continue
        if normalize_nums(cs[0]) == want:
            hits.append(l)
    return hits


# ================================================================ 判据
def tokens_of_line(line):
    """⚖ 一行里的「独立成词」的数（**集合**）——⚖⚖⚖ **这是 token 级，不是子串级**。

    ⚖⚖⚖⚖⚖ **为什么必须是 token 级**：244.93 实施时当场踩到——页面上的「0」（缺读数 0 条）
    若按**子串**找，账本里「**88 格**」的 88 里就**含 8** ⇒ ⇒ 判绿 ⇒ ⇒ **假绿**。
    ⇒ ⇒ 「109」**不是**「0」⇒ ⇒ 必须是**独立成词**的 token 才算数。
    """
    return set(numbers_in(line))


def j_d1_numbers_have_source(rows, ledger_at, detail):
    """⚖⚖⚖ **D1 · 每个数都有出处**（作用域 = **展品列 ＋ 实测列**）。

    ⇒ ⇒ 期望从**页面那一行**现取（⛔ 不手写）⇒ ⇒ 数写错 / 出处引错 ⇒ ⇒ **都红**。
    ⚖⚖⚖ **包含判定是 token 级**（⛔ 不是子串）—— 见 `tokens_of_line` 的注释。
    ⚖ **额外返回机器可对账的逐数矩阵**（⇒ 互证要**逐个数**比，⛔ 不只比计数）。
    """
    bad = []
    checked = 0
    matrix = []
    cites = {}
    for name, label in ANCHORS:
        hits = locate_row(rows, label)
        if not hits:
            bad.append("%s：锚点行**定位不到**（标签 %s）" % (name, label))
            continue
        if len(hits) > 1:
            bad.append("%s：锚点行**定位到 %d 行**" % (name, len(hits)))
            continue
        cs = cells_of(hits[0])
        if len(cs) < 3:
            bad.append("%s：列数 %d（期望 ≥ 3）" % (name, len(cs)))
            continue
        scope = cs[0] + " ｜ " + cs[1]          # ⚖ 展品列 ＋ 实测列（⛔ 不含出处列/复算列）
        nums = numbers_in(scope)
        lines = cited_lines(cs[2])
        cites[name] = lines
        if not nums:
            continue
        if not lines:
            bad.append("%s：没有引用任何账本行 ⇒ ⇒ **%d 个数都没有出处**" % (name, len(nums)))
            for n in nums:
                matrix.append((name, n, 0))
            continue
        for n in nums:
            checked += 1
            found = [ln for ln in lines
                     if ln in ledger_at and n in tokens_of_line(ledger_at[ln])]
            matrix.append((name, n, 1 if found else 0))
            if not found:
                bad.append("%s：数 **%s** 在引用的行 %s 里**都找不到**（token 级）" % (name, n, lines))
    if bad:
        return False, "；".join(bad), {"nums": matrix, "cites": cites}
    return True, "5 行展品表的 %d 个数都能在它引用的账本行里**逐位**找到（token 级）" % checked, \
        {"nums": matrix, "cites": cites}


def j_d2_rows_unique(page_lines, rows):
    """⚖ **D2 · 锚点行全页唯一**（⛔ 按**整行相等**计数 ⇒ ⇒ 防止「负控连坐」）。"""
    bad = []
    for name, label in ANCHORS:
        hits = locate_row(rows, label)
        if len(hits) != 1:
            bad.append("%s：表内定位到 %d 行" % (name, len(hits)))
            continue
        line = hits[0]
        n_page = sum(1 for l in page_lines if l == line)
        n_table = sum(1 for l in rows if l == line)
        if n_page != 1 or n_table != 1:
            bad.append("%s：整行在全页出现 **%d** 次（表内 %d 次）" % (name, n_page, n_table))
    if bad:
        return False, "；".join(bad), {}
    return True, "5 行展品表在整页各只出现一次（整行相等计数）", {}


def j_d3_cites_exist(rows, n_lines):
    """⚖ **D3 · 出处行号存在**（≤ 账本总行数）。"""
    bad = []
    for name, label in ANCHORS:
        hits = locate_row(rows, label)
        if not hits:
            continue
        cs = cells_of(hits[0])
        if len(cs) < 3:
            continue
        for ln in cited_lines(cs[2]):
            if ln > n_lines:
                bad.append("%s：引用了不存在的账本行 **:%d**（账本共 %d 行）" % (name, ln, n_lines))
    if bad:
        return False, "；".join(bad), {}
    return True, "所有引用的账本行号都存在", {}


def find_note(page_lines):
    """⚖ 找「口径切换」注的**正文行**与**出处行**。"""
    for i, l in enumerate(page_lines):
        if NOTE_MARK in l:
            src = None
            for j in range(i + 1, min(i + 4, len(page_lines))):
                if page_lines[j].startswith(NOTE_SRC_PREFIX):
                    src = page_lines[j]
                    break
            return l, src
    return None, None


def j_d4_band_groups(page_lines, ledger_at):
    """⚖⚖⚖ **D4 · 口径切换注的每个四档组都必须有出处**（⇒ 专治「出处引到相反结论的行」）。

    ⚖⚖⚖ **只取「账本」之后的引用**：出处行前半段引的是 `HANDOFF_24478.md:7`、`:61`
    ⇒ ⇒ 那是**另一个文件**的行号，⛔ **不是账本行号** ⇒ ⇒ 混进来会污染判据。
    """
    note, src = find_note(page_lines)
    if note is None:
        return False, "页面上找不到「口径切换」注", {}
    if src is None:
        return False, "「口径切换」注**没有出处行**", {}
    groups = BAND_GROUP.findall(note)
    if not groups:
        return False, "「口径切换」注里没有四档组（形如 N/N/N/N）", {}
    tail = src
    k = src.rfind("账本")
    if k >= 0:
        tail = src[k + 2:]
    lines = cited_lines(tail)
    if not lines:
        return False, "「口径切换」注的出处行**没有引用账本行**", \
            {"note_groups": groups, "note_cites": []}
    bad = []
    for g in groups:
        found = [ln for ln in lines if ln in ledger_at and g in ledger_at[ln]]
        if not found:
            bad.append("四档组 **%s** 在引用的行 %s 里**都找不到**" % (g, lines))
    extra = {"note_groups": groups, "note_cites": lines}
    if bad:
        return False, "；".join(bad), extra
    return True, "「口径切换」注的 %d 个四档组都有出处" % len(groups), extra


def evaluate(page_text, ledger_text):
    """⚖ 一次判定：跑 D1–D4 ⇒ ⇒ 返回 ([(cid, ok, detail)], matrix)。

    ⚖ **matrix** = 机器可对账的逐数矩阵（⇒ 互证要**逐个数**比，⛔ 不只比计数）。
    """
    page_lines = page_text.split("\n")
    ledger_lines = ledger_text.split("\n")
    ledger_at = {}
    for i, l in enumerate(ledger_lines, 1):
        ledger_at[i] = l
    _hdr, rows = find_table_rows(page_lines)
    if rows is None:
        return ([("D1", False, "页面上找不到「展品 | 实测 | 账本位置 | 复算」这张表"),
                 ("D2", False, "表不存在"), ("D3", False, "表不存在"),
                 ("D4", False, "表不存在")], {})
    res = []
    matrix = {}
    for cid, fn in (("D1", lambda: j_d1_numbers_have_source(rows, ledger_at, None)),
                    ("D2", lambda: j_d2_rows_unique(page_lines, rows)),
                    ("D3", lambda: j_d3_cites_exist(rows, len(ledger_lines))),
                    ("D4", lambda: j_d4_band_groups(page_lines, ledger_at))):
        ok, detail, extra = fn()
        res.append((cid, bool(ok), detail))
        if extra:
            for k, v in extra.items():
                matrix[k] = v
    return res, matrix


def verdict_from(res):
    """⚖ 形态：**D1–D4 全绿 ⇒ A**（一致）；任一红 ⇒ ⇒ **D**（⛔ 不出判决）。"""
    if all(ok for _c, ok, _d in res):
        return "A"
    return "D"


# ================================================================ 合成夹具（⚖ 与真数据**同形**，**填的值另取一套**）
# ⚖⚖⚖ **行号是**显式控制**的：第 i 行（1 起）放什么，**必须**与夹具页面引用的行号对上
#    ⇒ ⇒ 否则正控会因为「引用了不存在的行」而红 ⇒ ⇒ 夹具就**测不到**真东西了。
FIX_LEDGER = {
    4: "  ⚖ 合成：分位点 **0.111 / 0.222 / 0.333** ｜ 四档 **21/22/23/24** ｜ rho **+0.501**",
    5: "  ⚖ 合成：分位点 **0.111 / 0.222 / 0.333** ｜ 四档 **21/22/23/24**",
    7: "  ⚖ 合成：w 臂各档为正 **41/42/43/44**",
    8: "  ⚖ 合成：**变了的**：rho（+0.502 → +0.501）",
    11: "  ⚖ 合成：244.51 的 ±4 token 扰动族里 **5 个场景翻了 1 个**（rand 臂趋势 p 从 0.1111 掉到 0.2222）",
    12: "  ⚖ 合成：244.62：rand 臂的趋势 p 从 0.1111 掉到 0.2222 ⇒ **结论翻转**",
    13: "  ⚖ 合成：真实数据实测：分位点两种口径**相同**，但**档大小**不同 ⇒ ⇒ 登记的生产剂量轴（21/22/23/24）是 exclusive 口径的值（inclusive 会是 **24/23/22/21**）",
    18: "  · 〔格集合条件 1〕inject_scope == 'k'",
    19: "  · 〔格集合条件 2〕p9_lo_meas is not None（有实测读数）",
    20: "  · 〔格集合条件 3〕inject_n_sites 为真（有位点数）",
    21: "  ⚖ 合成：实测：剂量轴 **99 格**；独立规则也给 **99** 格 ⇒ **逐条相同**；k 格共 **99** 条、缺读数 **0** 条、缺位点数 **0** 条 ⇒ **成立**",
    24: "- 剂量轴（分位点 0.111/0.222/0.333、四档 **21/22/23/24**、rho **+0.501**、±4 token 扰动下 rho 稳而分档表变 2 种）",
}
FIX_N_LINES = 30


def fixture_ledger_text():
    """⚖ 把 FIX_LEDGER 铺成一份**整本**账本（第 i 行 = FIX_LEDGER[i]）。"""
    out = []
    for i in range(1, FIX_N_LINES + 1):
        out.append(FIX_LEDGER.get(i, "  （合成夹具的填充行 %d）" % i))
    return "\n".join(out) + "\n"


def fixture_page(note_src=":13"):
    """⚖ 合成页面：与真页面**同形**（同样的表头、同样的标签、同样的列数与引用结构），**值另取一套**。"""
    rows = [
        "| 展品 | 实测 | 账本位置 | 复算 |",
        "|---|---|---|---|",
        "| 注入比例轴的**分位点** | **0.111 / 0.222 / 0.333** | `:4`、`:5`、`:24` | RC-7 |",
        "| **四档**分档（**99 格**） | **21/22/23/24** | `:4`、`:5`、`:21`、`:24` | RC-7 |",
        "| rho（剂量—响应相关） | **+0.501**（校正前 +0.502）｜ w 臂各档为正 **41/42/43/44** | `:7`、`:8`、`:4`、`:24` | RC-7 |",
        "| **格集合的三条过滤条件** | `inject_scope == 'k'` ∧ `p9_lo_meas is not None`（有实测读数）∧ `inject_n_sites` 为真（有位点数）⇒ ⇒ **99 格**（实测 k 格 99 条、缺读数 0、缺位点数 0） | `:18`–`:20`、`:21` | RC-7 |",
        "| **脆性**：**±4 token** 扰动族 | 244.51 的 **±4 token** 扰动族（4 个变体 ＋ 基准 ＝ 5 个场景）下 **rho 稳而分档表变 2 种** ⇒ ⇒ 244.62 把这条脆性对**结论**的影响量了出来 ⇒ ⇒ **结论翻了 1 个**（rand 臂趋势 p 从 0.1111 掉到 0.2222） | `:11`、`:12`、`:24` | ⛔ 远端只读 |",
        "",
        "⚖⚖⚖ **口径切换（⛔ 不许偷偷改）**：244.74 实测 —— `quantile=\"inclusive\"` 那支**没传 `method`** ⇒ ⇒ 实际算的是 **exclusive** ⇒ ⇒ **账本登记的生产剂量轴是 exclusive 口径**：真数据 99 格，默认 **21/22/23/24** vs 真 inclusive **24/23/22/21** ⇒ ⇒ 上表按**账本登记口径（exclusive）**写 ⇒ ⇒ ⛔ **改它 ＝ 改生产剂量轴 ⇒ 要点头**。",
        "　出处：`.cache/xcheck/HANDOFF_24478.md:7`、`:61`；账本 " + note_src,
        "",
    ]
    return "\n".join(rows)


# ================================================================ 自检（⚖ 合成夹具、⛔ 零账本零页面零 GPU）
def mut_row(page, label, new_row):
    """⚖ **整行替换**：只改那一行 ⇒ ⇒ 负控**精确**落在它该落的地方（⛔ 不做全局字符串替换）。

    ⚖⚖⚖ **为什么必须整行替换**：全局 `replace` 会**同时**改掉别的行 ⇒ ⇒ 负控就不再精确
       ⇒ ⇒ 红了也说不清是「哪个变异抓到的」⇒ ⇒ 变异台就废了。
    """
    out = []
    hit = False
    for l in page.split("\n"):
        cs = cells_of(l) if l.strip().startswith("|") else []
        if cs and normalize_nums(cs[0]) == normalize_nums(label):
            out.append(new_row)
            hit = True
        else:
            out.append(l)
    if not hit:
        raise SystemExit("⛔ 夹具里找不到标签为 %s 的行 ⇒ ⇒ 中止" % label)
    return "\n".join(out)


def selftest():
    ok_count = 0
    total = 0
    fails = []

    def rec(name, cond, detail):
        nonlocal ok_count, total
        total += 1
        if cond:
            ok_count += 1
            print("[PASS] %s  %s" % (name, detail))
        else:
            fails.append(name)
            print("[FAIL] %s  %s" % (name, detail))

    def reds(page, ledger):
        return sorted(cid for cid, ok, _d in evaluate(page, ledger)[0] if not ok)

    pg = fixture_page()
    lg = fixture_ledger_text()

    # ---- 正控：合成夹具必须**全绿** ----
    res, _mx = evaluate(pg, lg)
    rec("S0 合成夹具上 D1–D4 必须全绿",
        all(ok for _c, ok, _d in res),
        "｜ ".join("%s=%s" % (c, "绿" if ok else "红") for c, ok, _d in res))

    # ---- 负控 1：改一个数 ⇒ D1 必须红 ----
    r1 = [l for l in pg.split("\n") if l.startswith("| 注入比例轴的**分位点**")][0]
    bad = mut_row(pg, "注入比例轴的**分位点**", r1.replace("0.333", "0.999"))
    rec("S-D1a 改一个数 ⇒ D1 必须红", "D1" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 2：把出处换成**不含该数**的行 ⇒ D1 必须红 ----
    bad = mut_row(pg, "注入比例轴的**分位点**",
                  "| 注入比例轴的**分位点** | **0.111 / 0.222 / 0.333** | `:7`、`:8` | RC-7 |")
    rec("S-D1b 出处换成不含该数的行 ⇒ D1 必须红", "D1" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 3：删掉一行展品 ⇒ D2 必须红 ----
    lines = pg.split("\n")
    victim = [l for l in lines if l.startswith("| **脆性**")][0]
    bad = pg.replace(victim + "\n", "")
    rec("S-D2a 删掉一行展品 ⇒ D2 必须红", "D2" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 4：复制一行展品 ⇒ D2 必须红 ----
    bad = pg.replace(victim + "\n", victim + "\n" + victim + "\n")
    rec("S-D2b 复制一行展品 ⇒ D2 必须红", "D2" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 5：改口径切换注的出处 ⇒ D4 必须红 ----
    bad = fixture_page(note_src=":4")
    rec("S-D4a 口径切换注出处换成不含四档组的行 ⇒ D4 必须红",
        "D4" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 6：改口径切换注里的四档组 ⇒ D4 必须红 ----
    bad = pg.replace("**24/23/22/21**", "**29/23/22/21**")
    rec("S-D4b 改口径切换注里的四档组 ⇒ D4 必须红",
        "D4" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 7：引用不存在的账本行 ⇒ D3 必须红 ----
    bad = pg.replace("`:24`", "`:99999`")
    rec("S-D3 引用不存在的账本行 ⇒ D3 必须红", "D3" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 8：夹具的账本**被改** ⇒ D1 必须红（自检层能抓）----
    # ⚖⚖⚖ **必须改所有出现处**：只改一处的话，被引的**另一行**仍含那个数 ⇒ ⇒ D1 仍绿
    #    ⇒ ⇒ 这个负控就是**弱**的（244.93 自检当场抓到 ⇒ ⇒ 负控自己也必须被审）
    bad_ledger = lg.replace("0.333", "0.444")
    rec("S-D1c 夹具的账本被改 ⇒ D1 必须红", "D1" in reds(pg, bad_ledger), "红集合 %s" % reds(pg, bad_ledger))

    # ---- 负控 9（**关键**）：把账本里那两个**独立成词的 0** 换成 **70**
    #    ⇒ ⇒ 「0」不再是独立 token，但 **70 里含 0**
    #    ⇒ ⇒ **子串**判定下这一条仍然**绿** ⇒ ⇒ 这条负控**只在 token 级判定下才有牙齿**
    #    ⇒ ⇒ 它就是把「子串 ⇒ 假绿」那个缺陷**钉死**的用例（244.93 实施时当场踩到过）
    # ⚖⚖⚖ **必须把两个 0 一起换**：只换「缺读数 0」的话，「缺位点数 0」仍在同一行里
    #    ⇒ ⇒ D1 照样能**逐位**找到「0」⇒ ⇒ 负控**无牙齿**（244.93 自检当场抓到 ⇒ ⇒ 负控自己也必须被审）
    bad_ledger = lg.replace("缺读数 **0** 条、缺位点数 **0** 条",
                            "缺读数 **70** 条、缺位点数 **70** 条")
    rec("S-D1d 独立成词的 0 → 70（子串会假绿）⇒ D1 必须红",
        "D1" in reds(pg, bad_ledger), "红集合 %s" % reds(pg, bad_ledger))

    # ---- 负控 10：形态级联：任一红 ⇒ 形态 D ⇒ ⛔ 不出判决 ----
    v_ok = verdict_from([("D1", True, ""), ("D2", True, ""), ("D3", True, ""), ("D4", True, "")])
    v_bad = verdict_from([("D1", False, ""), ("D2", True, ""), ("D3", True, ""), ("D4", True, "")])
    rec("S-V 形态级联：全绿 ⇒ A；任一红 ⇒ D",
        v_ok == "A" and v_bad == "D", "全绿 ⇒ %s ｜ 有红 ⇒ %s" % (v_ok, v_bad))

    print("")
    print("自检 %d/%d 通过" % (ok_count, total))
    print("SELFTEST_RED=%d" % len(fails))
    print("SELFTEST_RC=%d" % (0 if not fails else 1))
    return 0 if not fails else 1


# ================================================================ 真数据
def data(page_path, ledger_path):
    page_text = read_text(page_path)
    ledger_text = read_text(ledger_path)
    res, matrix = evaluate(page_text, ledger_text)
    v = verdict_from(res)
    print("=" * 78)
    print("页面：%s" % page_path)
    print("账本：%s（%d 行）" % (ledger_path, ledger_text.count("\n")))
    print("=" * 78)
    allok = True
    for cid, ok, detail in res:
        allok = allok and ok
        print("[%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for _c, ok, _d in res if ok), len(res)))
    print("VERDICT=%s" % v)
    print("REASON=%s" % ("页面 §6.2.3 的每个数都能在它引用的账本行里逐位找到"
                        if v == "A" else "页面 §6.2.3 与账本之间有脱节 ⇒ ⇒ 本次不出判决"))
    print("")
    print("===== NUM_MATRIX =====")
    for name, num, found in matrix.get("nums", []):
        print("ROW=%s|%s|%d" % (name, num, found))
    for name in sorted(matrix.get("cites", {}).keys()):
        print("CITE=%s|%s" % (name, ",".join(str(x) for x in matrix["cites"][name])))
    for g in matrix.get("note_groups", []):
        print("NOTE_GROUP=%s" % g)
    print("NOTE_CITE=%s" % ",".join(str(x) for x in matrix.get("note_cites", [])))
    print("===== END_NUM_MATRIX =====")
    print("")
    print("===== AUDIT_KEYS =====")
    print("VERDICT=%s" % v)
    print("N_CHECKS=%d" % len(res))
    print("CHECKS_RED=%d" % sum(1 for _c, ok, _d in res if not ok))
    for cid, ok, _d in res:
        print("CHECK_%s=%s" % (cid, "PASS" if ok else "FAIL"))
    print("===== END_AUDIT_KEYS =====")
    return 0 if allok else 1


def main():
    ap = argparse.ArgumentParser(description="244.93：页面 §6.2.3 剂量轴展品块 ↔ 账本 对账（零 GPU）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--data", action="store_true")
    ap.add_argument("--page", default=None)
    ap.add_argument("--ledger", default=None)
    a = ap.parse_args()
    page = a.page or DEFAULT_PAGE
    ledger = a.ledger or DEFAULT_LEDGER
    if not os.path.isabs(page):
        page = os.path.join(REPO, page)
    if not os.path.isabs(ledger):
        ledger = os.path.join(REPO, ledger)
    try:
        if a.selftest:
            return selftest()
        return data(page, ledger)
    except SystemExit as e:
        print("%s" % e)
        return 2
    except Exception as e:  # noqa: BLE001
        print("PRECOND_FAIL: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
