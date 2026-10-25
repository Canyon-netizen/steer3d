#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc_dose_arm_audit.py —— **244.94**：页面 `docs/BPATH_VERDICT.md` 的 **§6.2.1「两臂同一个剂量」9 行**
↔ **权威账本 244.83 段**那张验收表的**逐行对账**。

⚖⚖⚖ **本轮的核心设计（预登记 §1.2）**：244.93 式的「**数能找到**」判据在本节**几乎恒绿**
（25/25 个数都能找到 ⇒ 无数值缺陷）⇒ ⇒ ⇒ 本轮改用**逐字一致**判据
⇒ ⇒ 连**措辞**都守 ⇒ ⇒ 侦察当场就抓到 **3 处措辞缺陷**（:41612 / :41614 / :41615 的差列少字）。

⚖⚖⚖ **归一化口径**（预登记 §2）：`normalize(s)` = 去掉所有反引号、去掉所有 `**` 粗体标记、去掉**所有空白**
⇒ ⇒ 只比较**内容**，⛔ 不比较 markdown 装饰。

⚖ **数据来源**：**只读已入库文件**（页面 ＋ 账本整本）⇒ ⇒ 别人 clone 下来就能跑；⛔ **不读收据**。
⚖ **零 GPU、零跑批、不重解析原始跑批日志**。

⚖⚖⚖ **两类输出必须分清**：
   · **闸门**（`CHECK_E1`…`CHECK_E5`）：**预登记 §2 登记的 5 条** ⇒ ⇒ 决定形态（A / D）。
   · **辅助测量**（`AUX_*`）：⛔ **不是判据**、⛔ **不参与形态判定**
     ⇒ ⇒ 它们的绿灯**不构成**「已被守住」，只作为**事实登记**（见下面两条）。
"""

import argparse
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DEFAULT_PAGE = os.path.join("docs", "BPATH_VERDICT.md")
DEFAULT_LEDGER = os.path.join(".cache", "xcheck", "R6_RERUN_PREREG.md")

# ================================================================ 页面表头（§6.2.1 的那张表）
# ⚖ 归一化后的 6 格；⇒ ⇒ 页面上必须**恰有 1 行**与它相等（判据 E4）
PAGE_HEADER = ["量", "w臂", "rand臂", "差/判据", "账本位置", "复算"]
# ⚖ 账本那张表的列数（5 列：量/w臂/rand臂/差/判据/结论）
LEDGER_COLS = 5
# ⚖ 页面表里「量」「w 臂」「差 / 判据」三列 ↔ 账本表的第 0/1/3 格（rand 臂列由 E2 判）
COL_MAP = ((0, 0), (1, 1), (3, 3))
# ⚖ 判据 E5：**手写**的行数期望（登记在预登记 §2 E5）
EXPECT_ROWS = 9

# ⚖ 账本行号引用：`:41607`（1–6 位 ⇒ ⇒ 合成夹具可以用 `:4` 这种小行号）
CITE = re.compile(r":(\d{1,6})")


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def normalize(s):
    """⚖ 预登记 §2 的归一化：去反引号、去粗体标记、去**所有**空白。"""
    s = s.replace("`", "").replace("**", "")
    return re.sub(r"\s+", "", s)


def cells_of(row):
    """⚖ 表格行 ⇒ ⇒ 列（去掉首尾两个空列）。"""
    parts = row.split("|")
    return [p.strip() for p in parts[1:-1]]


def norm_cells(row):
    return [normalize(c) for c in cells_of(row)]


def is_ledger_table_row(line):
    """⚖ 账本那张表的行：以 `|` 开头，归一化后**恰 5 格**，且首格非空。"""
    s = line.strip()
    if not s.startswith("|"):
        return False
    cs = norm_cells(s)
    return len(cs) == LEDGER_COLS and bool(cs[0])


def cited_lines(cell):
    """⚖ 取引用的账本行号集合（区间展开）。"""
    hits = [(m.start(), m.end(), int(m.group(1))) for m in CITE.finditer(cell)]
    lines = set()
    for i, (_s, e, n) in enumerate(hits):
        lines.add(n)
        if i + 1 < len(hits):
            gap = cell[e:hits[i + 1][0]]
            if any(d in gap for d in "–—-"):
                nxt = hits[i + 1][2]
                a, b = (n, nxt) if n <= nxt else (nxt, n)
                for x in range(a, b + 1):
                    lines.add(x)
    return sorted(lines)


def find_page_table(page_lines):
    """⚖ 按**表头**定位 §6.2.1 那张表 ⇒ ⇒ 返回 (表头行号, 全部匹配行号, 数据行)。"""
    hdr_rows = []
    rows = []
    for i, l in enumerate(page_lines):
        s = l.strip()
        if not s.startswith("|"):
            continue
        if norm_cells(s) == PAGE_HEADER:
            hdr_rows.append(i)
    if not hdr_rows:
        return None, [], []
    hdr = hdr_rows[0]
    for l in page_lines[hdr + 1:]:
        s = l.strip()
        if not s.startswith("|"):
            break
        if set(s) <= set("|-: "):
            continue
        rows.append(s)
    return hdr, hdr_rows, rows


# ================================================================ 判据（预登记 §2 的 E1–E5）
def j_e1_verbatim(rows, ledger_at, counterpart, bad):
    """⚖⚖⚖ **E1 · 逐字一致**：页面的「量」「w 臂」「差 / 判据」三列 ↔ 账本对应行的同名列。"""
    for r in rows:
        cs = cells_of(r)
        if len(cs) < 4:
            bad.append("E1：页面的行只有 %d 列（期望 ≥ 4）" % len(cs))
            continue
        lrow = counterpart.get(r)
        if lrow is None:
            continue                      # ⛔ 没有对应行 ⇒ 由 E3 报
        lcs = cells_of(lrow)
        for pi, li in COL_MAP:
            a = normalize(cs[pi])
            b = normalize(lcs[li]) if li < len(lcs) else "(账本该行缺这一列)"
            if a != b:
                bad.append("E1：%s 的**%s列**逐字不等 —— 页面「%s」 ≠ 账本「%s」"
                           % (normalize(cs[0])[:18], PAGE_HEADER[pi], a[:60], b[:60]))


def j_e2_same_claim(rows, ledger_at, counterpart, bad):
    """⚖ **E2 · 「同」断言有出处**：页面 rand 臂写「同」⇒ ⇒ 账本对应行必须能证明它。"""
    for r in rows:
        cs = cells_of(r)
        if len(cs) < 4:
            continue
        if normalize(cs[2]) != "同":
            continue
        lrow = counterpart.get(r)
        if lrow is None:
            continue
        lcs = cells_of(lrow)
        if len(lcs) < LEDGER_COLS:
            continue
        w, rnd = normalize(lcs[1]), normalize(lcs[2])
        if rnd == "同" or w == rnd:
            continue
        bad.append("E2：%s 的 rand 臂写「同」，但账本该行 w 臂「%s」与 rand 臂「%s」**并不相同**"
                   % (normalize(cs[0])[:18], w[:40], rnd[:40]))


def j_e3_cites(rows, ledger_lines, ledger_at, bad):
    """⚖ **E3 · 出处行号存在**且**指得到那张表**（且**恰好一行**）。

    ⚖ 返回 (对应行映射, 页行 ⇒ 账本行号映射)。
    """
    counterpart = {}
    cite_map = {}
    for r in rows:
        cs = cells_of(r)
        if len(cs) < 5:
            bad.append("E3：页面的行只有 %d 列（期望 ≥ 5）" % len(cs))
            continue
        lines = cited_lines(cs[4])
        if not lines:
            bad.append("E3：%s **没有引用**任何账本行" % normalize(cs[0])[:18])
            continue
        for ln in lines:
            if ln > ledger_lines:
                bad.append("E3：引用了不存在的账本行 :%d（账本共 %d 行）" % (ln, ledger_lines))
        table_rows = [ln for ln in lines
                      if 1 <= ln <= ledger_lines and is_ledger_table_row(ledger_at.get(ln, ""))]
        if len(table_rows) == 0:
            bad.append("E3：%s 引的行 %s **都指不到**账本那张表（表行 = 以 `|` 开头且归一化后 %d 格）"
                       % (normalize(cs[0])[:18], lines, LEDGER_COLS))
        elif len(table_rows) > 1:
            bad.append("E3：%s 引到了**多行**表行 %s（期望恰好 1 行）" % (normalize(cs[0])[:18], table_rows))
        else:
            counterpart[r] = ledger_at[table_rows[0]]
            cite_map[r] = table_rows[0]
    return counterpart, cite_map


def j_e4_unique(page_lines, hdr_rows, rows, bad):
    """⚖ **E4 · 锚点唯一**：9 行在整页各只出现一次；表头在整页只出现一次。"""
    if len(hdr_rows) != 1:
        bad.append("E4：§6.2.1 的表头在整页出现 %d 次（期望 1 次）" % len(hdr_rows))
    for r in rows:
        n = sum(1 for l in page_lines if l.strip() == r.strip())
        if n != 1:
            bad.append("E4：行「%s」在整页出现 %d 次（期望 1 次）" % (normalize(cells_of(r)[0])[:18], n))


def j_e5_row_count(rows, bad):
    """⚖ **E5 · 行数 == 9**（手写期望，登记在预登记 §2）。"""
    if len(rows) != EXPECT_ROWS:
        bad.append("E5：§6.2.1 的数据行数是 %d（期望 %d）" % (len(rows), EXPECT_ROWS))


# ================================================================ ⚖ 辅助测量（⛔ **不是判据**）
def aux_rand_column(rows, counterpart):
    """⚖ **辅助测量 ①**：页面的 **rand 臂列**（**不是「同」**时）与账本对应行的 rand 列是否逐字相同。

    ⚖⚖⚖ **为什么它不是闸门**：预登记 §2 的 E1 **明写**「⛔ rand 臂列不在 E1 的作用域」、
    E2 **只管**「同」这个断言 ⇒ ⇒ 页面若把 rand 臂写成「异」、或写成一个**错数**，
    **没有任何闸门会红** ⇒ ⇒ 本函数**只把这件事量出来**，
    ⛔ **不参与形态判定** ⇒ ⇒ 它的绿灯**不构成**「已被守住」。
    """
    out = []
    for r in rows:
        cs = cells_of(r)
        if len(cs) < 3:
            continue
        pr = normalize(cs[2])
        if pr == "同":
            continue                      # ⚖ 「同」是**压缩**，由 E2 判
        lrow = counterpart.get(r)
        if lrow is None:
            continue
        lcs = cells_of(lrow)
        if len(lcs) < 3:
            continue
        lr = normalize(lcs[2])
        if pr != lr:
            out.append("%s：页面「%s」≠ 账本「%s」" % (normalize(cs[0])[:18], pr[:40], lr[:40]))
    return out


def aux_bijection(rows, cite_map):
    """⚖ **辅助测量 ②**：9 个页行引到的账本行是否**互不相同**（一一对应、不得两行对一行）。

    ⚖⚖⚖ **为什么它不是闸门**：预登记 §1.3 要求「一一对应」**要守**，但 §2 **没有**为它定义闸门
    （§2 明写「共 5 条：E1–E5」）⇒ ⇒ 本函数**只把这件事量出来**，⛔ **不参与形态判定**。
    """
    total = len(rows)
    got = sorted(set(cite_map[r] for r in cite_map))
    return {"total": total, "distinct": len(got), "lines": got}


def evaluate(page_text, ledger_text):
    """⚖ 一次判定 ⇒ ⇒ ([(cid, ok, detail)], matrix)。"""
    page_lines = page_text.split("\n")
    ledger_lines = ledger_text.split("\n")
    ledger_at = {i: l for i, l in enumerate(ledger_lines, 1)}

    hdr, hdr_rows, rows = find_page_table(page_lines)
    if hdr is None:
        res = [("E1", False, "页面上找不到 §6.2.1 那张表（表头 6 格）"),
               ("E2", False, "表不存在"), ("E3", False, "表不存在"),
               ("E4", False, "表不存在"), ("E5", False, "表不存在")]
        return res, {"aux": {"rand_mismatch": [], "rand_count": 0,
                             "bij_total": 0, "bij_distinct": 0, "bij_lines": []}}

    bad = []
    counterpart, cite_map = j_e3_cites(rows, len(ledger_lines), ledger_at, bad)
    j_e1_verbatim(rows, ledger_at, counterpart, bad)
    j_e2_same_claim(rows, ledger_at, counterpart, bad)
    j_e4_unique(page_lines, hdr_rows, rows, bad)
    j_e5_row_count(rows, bad)

    res = []
    details = {
        "E1": "9 行的「量 / w 臂 / 差·判据」三列与账本对应行**逐字相同**（归一化后）",
        "E2": "凡 rand 臂写「同」的行，账本对应行都能证明它",
        "E3": "每行引用的账本行号存在、且恰好指到账本那张表的一行",
        "E4": "9 行在整页各只出现一次，表头也只出现一次",
        "E5": "数据行数 == %d" % EXPECT_ROWS,
    }
    for cid in ("E1", "E2", "E3", "E4", "E5"):
        related = [b for b in bad if b.startswith(cid + "：")]
        res.append((cid, not related, "；".join(related) if related else details[cid]))

    rand_bad = aux_rand_column(rows, counterpart)
    bij = aux_bijection(rows, cite_map)

    # ⚖⚖⚖ **逐行结论**（⛔ **只是输出**，⛔ 不改变任何闸门的判定）
    #    ⇒ ⇒ 互证（第二条独立实现）才能**逐行**对账（预登记 §5 的要求）。
    rowv = []
    for r in rows:
        cs = cells_of(r)
        label = normalize(cs[0]) if cs else ""
        lrow = counterpart.get(r)
        eq = "NA"
        same = "NA"
        if lrow is not None:
            lcs = cells_of(lrow)
            ok = True
            for pi, li in COL_MAP:
                a = normalize(cs[pi]) if pi < len(cs) else ""
                b = normalize(lcs[li]) if li < len(lcs) else ""
                if a != b:
                    ok = False
            eq = "1" if ok else "0"
            if len(cs) >= 3 and normalize(cs[2]) == "同":
                if len(lcs) >= LEDGER_COLS:
                    w, rnd = normalize(lcs[1]), normalize(lcs[2])
                    same = "1" if (rnd == "同" or w == rnd) else "0"
                else:
                    same = "0"
        rowv.append((label, eq, same))

    matrix = {
        "rows": [(normalize(cells_of(r)[0]), normalize(cells_of(r)[1]),
                  normalize(cells_of(r)[2]), normalize(cells_of(r)[3])) for r in rows],
        "counterpart": {normalize(cells_of(r)[0]): normalize(counterpart[r]) if r in counterpart else ""
                        for r in rows},
        "rowv": rowv,
        "aux": {"rand_mismatch": rand_bad, "rand_count": len(rand_bad),
                "bij_total": bij["total"], "bij_distinct": bij["distinct"],
                "bij_lines": bij["lines"]},
    }
    return res, matrix


def verdict_from(res):
    """⚖ 形态：**E1–E5 全绿 ⇒ A**（一致）；任一红 ⇒ ⇒ **D**（⛔ 不出判决）。"""
    return "A" if all(ok for _c, ok, _d in res) else "D"


# ================================================================ 合成夹具（⚖ 与真数据**同形**，**填的值另取一套**）
# ⚖ 账本那张表（5 列）：量 | w 臂 | rand 臂 | 差 / 判据 | 结论
FIX_LEDGER = {
    4: "| 注入前范数（f64 口径） | `0.11111111111111111` | `0.22222222222222222` | 相对差 **1.111e-10**（上限 2.0e-06） | ✅ |",
    5: "| 注入后范数（**bf16**） | `1.1111111110` | `0.8888888889` | 相对差 **2.222e-05**（上限 3.0e-02 ＝ 3×2⁻⁹） | ✅ |",
    6: "| α 网格 | `linspace(-30.0, 30.0, 20)` | 同 | 逐位相同 | ✅ |",
    7: "| 判决读数 α | `[11.111111111111111, 22.222222222222222]` | `[11.111111111111111, 22.222222222222222]` | 逐位相同（三源） | ✅ |",
    8: "| 位点数 k（逐格） | BEGIN 行 / JSON | 同 | 四源一致 ｜ 比较 **31** 格 ｜ 不一致 0 | ✅ |",
    9: "| 位点集合 | 种子 0、nested、`permutation(n)[:k]` | 同 | 逐格相同（且 n_eff == P+t 全部相符） | ✅ |",
    10: "| 逐格结构字段 | 7 个（T） | 同 | 比较 **88** 次（应 88）｜ 不一致 **0** 处 | ✅ |",
    11: "| 逐格注入场 L2（alpha_max×∥v∥×√k） | — | — | 两臂相对差超限 **0** 格 ｜ 公式 vs 直接求和路径不一致 **0** 格 | ✅ |",
    12: "| 静态命令行 | 扣掉 `--gpu-uuid`/`--arm` | 同 | 差异 0 处 ｜ `--w` 两臂**相同**（同一把向量） | ✅ |",
    13: "| 字段划分 | 实测 9 个 ｜ 声明 9 个 | — | 未声明 0 个 ｜ 读数字段 5 个 | ✅ |",
}
FIX_N_LINES = 20


def fixture_ledger_text():
    out = []
    for i in range(1, FIX_N_LINES + 1):
        out.append(FIX_LEDGER.get(i, "  （合成夹具的填充行 %d）" % i))
    return "\n".join(out) + "\n"


def fixture_page():
    """⚖ 合成页面：与真页面**同形**（同样的表头 6 格、同样的 9 行），**值另取一套**。"""
    rows = [
        "| 量 | w 臂 | rand 臂 | 差 / 判据 | 账本位置 | 复算 |",
        "|---|---|---|---|---|---|",
        "| 注入前范数（f64 口径） | `0.11111111111111111` | `0.22222222222222222` | 相对差 **1.111e-10**（上限 2.0e-06） | `:4` | RC-9 |",
        "| 注入后范数（**bf16**） | `1.1111111110` | `0.8888888889` | 相对差 **2.222e-05**（上限 3.0e-02 ＝ 3×2⁻⁹） | `:5` | RC-9 |",
        "| α 网格 | `linspace(-30.0, 30.0, 20)` | 同 | 逐位相同 | `:6` | RC-9 |",
        "| 判决读数 α | `[11.111111111111111, 22.222222222222222]` | 同 | 逐位相同（三源） | `:7` | RC-9 |",
        "| 位点数 k（逐格） | BEGIN 行 / JSON | 同 | 四源一致 ｜ 比较 **31** 格 ｜ 不一致 0 | `:8` | RC-9 |",
        "| 位点集合 | 种子 0、nested、`permutation(n)[:k]` | 同 | 逐格相同（且 n_eff == P+t 全部相符） | `:9` | RC-9 |",
        "| 逐格结构字段 | 7 个（T） | 同 | 比较 **88** 次（应 88）｜ 不一致 **0** 处 | `:10` | RC-9 |",
        "| 逐格注入场 L2（`alpha_max×∥v∥×√k`） | — | — | 两臂相对差超限 **0** 格 ｜ 公式 vs 直接求和路径不一致 **0** 格 | `:11` | RC-9 |",
        "| 静态命令行 | 扣掉 `--gpu-uuid` / `--arm` | 同 | 差异 0 处 ｜ `--w` 两臂**相同**（同一把向量） | `:12` | RC-9 |",
    ]
    return "\n".join(rows) + "\n"


# ================================================================ 自检（⚖ 合成夹具、⛔ 零账本零页面零 GPU）
def mut_row(page, label, new_row):
    """⚖ **整行替换**：只改那一行 ⇒ ⇒ 负控**精确**落在它该落的地方。"""
    out = []
    hit = 0
    for l in page.split("\n"):
        cs = cells_of(l) if l.strip().startswith("|") else []
        if cs and normalize(cs[0]) == normalize(label):
            out.append(new_row)
            hit += 1
        else:
            out.append(l)
    if hit != 1:
        raise SystemExit("⛔ 夹具里找不到标签为 %s 的行（命中 %d）⇒ ⇒ 中止" % (label, hit))
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

    res, mx = evaluate(pg, lg)
    rec("S0 合成夹具上 E1–E5 必须全绿",
        all(ok for _c, ok, _d in res),
        "｜ ".join("%s=%s" % (c, "绿" if ok else "红") for c, ok, _d in res))

    # ---- 负控 1：改一个数 ⇒ E1 必须红 ----
    bad = mut_row(pg, "注入前范数（f64 口径）",
                  [l for l in pg.split("\n") if l.startswith("| 注入前范数")][0]
                  .replace("1.111e-10", "1.111e-11", 1))
    rec("S-E1a 改一个数 ⇒ E1 必须红", "E1" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 2：差列**少一个字** ⇒ E1 必须红（这正是 244.94 在真实数据上抓到的缺陷型）----
    bad = mut_row(pg, "逐格注入场 L2（`alpha_max×∥v∥×√k`）",
                  [l for l in pg.split("\n") if l.startswith("| 逐格注入场")][0]
                  .replace("直接求和路径不一致", "直接求和不一致", 1))
    rec("S-E1b 差列少一个字 ⇒ E1 必须红", "E1" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 3：rand 臂的「同」改成「异」⇒ E2 必须红（**账本侧**改动才抓得到）----
    bad_lg = lg.replace("| 同 | 逐位相同 |", "| 异 | 逐位相同 |", 1)
    rec("S-E2 账本侧「同」→「异」⇒ E2 必须红", "E2" in reds(pg, bad_lg), "红集合 %s" % reds(pg, bad_lg))

    # ---- 负控 4：删掉一整行 ⇒ E5 必须红（行数不再 9）----
    victim = [l for l in pg.split("\n") if l.startswith("| 逐格结构字段")][0]
    bad = pg.replace(victim + "\n", "")
    rec("S-E5a 删掉一整行展品 ⇒ E5 必须红", "E5" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 5：复制一行展品 ⇒ E4 必须红 ----
    bad = pg.replace(victim + "\n", victim + "\n" + victim + "\n")
    rec("S-E4b 复制一行展品 ⇒ E4 必须红", "E4" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 6：引用不存在的账本行 ⇒ E3 必须红 ----
    bad = pg.replace("`:12`", "`:99999`", 1)
    rec("S-E3a 引用不存在的账本行 ⇒ E3 必须红", "E3" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 7：引用**表外**的一行 ⇒ E3 必须红 ----
    # ⚖⚖⚖ `:2` 是夹具的**填充行**（⛔ 不是表行）⇒ ⇒ 指不到那张表 ⇒ E3 必须红。
    # ⚖⚖⚖ ⛔ **不能**用 `:13`：那是夹具里**另一张表**的行（5 格）⇒ ⇒ 指得到表 ⇒ E3 **不会**红。
    bad = pg.replace("`:11`", "`:2`", 1)
    rec("S-E3b 引用表外的一行 ⇒ E3 必须红", "E3" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 8：多出一行 ⇒ E5 必须红 ----
    bad = pg.replace(victim + "\n", victim + "\n"
                      + "| 多出来的一行 | x | y | z | `:8` | RC-9 |\n", 1)
    rec("S-E5b 多出一行展品 ⇒ E5 必须红", "E5" in reds(bad, lg), "红集合 %s" % reds(bad, lg))

    # ---- 负控 9：夹具的账本行改成与真账本**不同形**（自检层）⇒ 正控必须红 ----
    bad_ledger = lg.replace("直接求和路径不一致", "直接求和不一致", 1)
    rec("S-E1c 夹具的账本被改 ⇒ E1 必须红", "E1" in reds(pg, bad_ledger),
        "红集合 %s" % reds(pg, bad_ledger))

    # ---- 负控 10：形态级联：任一红 ⇒ 形态 D ⇒ ⛔ 不出判决 ----
    v_ok = verdict_from([("E1", True, ""), ("E2", True, ""), ("E3", True, ""),
                         ("E4", True, ""), ("E5", True, "")])
    v_bad = verdict_from([("E1", False, ""), ("E2", True, ""), ("E3", True, ""),
                          ("E4", True, ""), ("E5", True, "")])
    rec("S-V 形态级联：全绿 ⇒ A；任一红 ⇒ D",
        v_ok == "A" and v_bad == "D", "全绿 ⇒ %s ｜ 有红 ⇒ %s" % (v_ok, v_bad))

    # ---- 负控 11：辅助测量 ①（rand 列）**有牙齿**：改一个 rand 数 ⇒ 必须**量到** ----
    bad = mut_row(pg, "注入前范数（f64 口径）",
                  [l for l in pg.split("\n") if l.startswith("| 注入前范数")][0]
                  .replace("0.22222222222222222", "0.22222222222222223", 1))
    aux_bad = evaluate(bad, lg)[1]["aux"]["rand_count"]
    rec("S-AUXa 改 rand 臂的数 ⇒ 辅助测量必须**量到**（⛔ 它**不是**闸门 ⇒ 不该让 E1 红）",
        aux_bad == 1 and "E1" not in reds(bad, lg),
        "aux_rand_mismatch=%d ｜ 红闸门 %s" % (aux_bad, reds(bad, lg)))

    # ---- 负控 12：辅助测量 ②（一一对应）**有牙齿**：两行引同一行 ⇒ distinct 必须变小 ----
    bij0 = evaluate(pg, lg)[1]["aux"]
    bad = pg.replace("`:12`", "`:11`", 1)
    bij1 = evaluate(bad, lg)[1]["aux"]
    rec("S-AUXb 两行引同一账本行 ⇒ 辅助测量必须**量到**（distinct 变小）",
        bij1["bij_distinct"] < bij0["bij_distinct"],
        "前 distinct=%d ／ 后 distinct=%d" % (bij0["bij_distinct"], bij1["bij_distinct"]))

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
    aux = matrix.get("aux", {})
    v = verdict_from(res)
    print("=" * 78)
    print("页面：%s" % page_path)
    print("账本：%s（%d 行）" % (ledger_path, ledger_text.count("\n")))
    print("=" * 78)
    for cid, ok, detail in res:
        print("[%s] %s：%s" % ("PASS" if ok else "FAIL", cid, detail))
    print("")
    print("⚖ **辅助测量（⛔ 不是判据、⛔ 不参与形态判定）**：")
    print("  · AUX_RAND_MISMATCH=%d（页面的 rand 臂列在**不是「同」**时与账本逐字不符的行数）"
          % aux.get("rand_count", 0))
    for b in aux.get("rand_mismatch", []):
        print("      · %s" % b)
    print("  · AUX_BIJ=%d/%d（%d 个页行引到的账本行**互不相同** ⇒ 一一对应）"
          % (aux.get("bij_distinct", 0), aux.get("bij_total", 0), aux.get("bij_total", 0)))
    print("  · AUX_BIJ_LINES=%s" % aux.get("bij_lines", []))
    print("")
    print("判据：%d/%d 通过" % (sum(1 for _c, ok, _d in res if ok), len(res)))
    print("VERDICT=%s" % v)
    print("REASON=%s" % ("页面 §6.2.1 的 9 行与账本 244.83 段那张表**逐字一致**"
                        if v == "A" else "页面 §6.2.1 与账本之间有脱节 ⇒ ⇒ 本次不出判决"))
    print("")
    print("===== NUM_MATRIX =====")
    for name, w, rnd, diff in matrix.get("rows", []):
        print("ROW=%s|%s|%s|%s" % (name, w, rnd, diff))
    print("===== END_NUM_MATRIX =====")
    print("")
    print("===== ROW_VERDICTS =====")
    for name, eq, same in matrix.get("rowv", []):
        print("ROWV=%s|EQ=%s|SAME=%s" % (name, eq, same))
    print("===== END_ROW_VERDICTS =====")
    print("")
    print("===== AUDIT_KEYS =====")
    print("VERDICT=%s" % v)
    print("N_CHECKS=%d" % len(res))
    print("CHECKS_RED=%d" % sum(1 for _c, ok, _d in res if not ok))
    for cid, ok, _d in res:
        print("CHECK_%s=%s" % (cid, "PASS" if ok else "FAIL"))
    print("AUX_RAND_MISMATCH=%d" % aux.get("rand_count", 0))
    print("AUX_BIJ=%d" % aux.get("bij_distinct", 0))
    print("AUX_BIJ_TOTAL=%d" % aux.get("bij_total", 0))
    print("===== END_AUDIT_KEYS =====")
    return 0 if all(ok for _c, ok, _d in res) else 1


def main():
    ap = argparse.ArgumentParser(description="244.94：页面 §6.2.1「两臂同一个剂量」9 行 ↔ 账本 逐字对账（零 GPU）")
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
