#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_cross_check_24495.py —— 244.95 的**第二条独立实现**（互证）。

⚖⚖⚖ **244.95 新增**：**E6**（rand 臂列 vs 账本的**可比较形式 L**，⚖ **按词切分**口径）
   与 **E7**（被引的账本行必须**互不相同**）⇒ ⇒ 两条都在本实现里**独立**判一遍。

⚖⚖⚖ **与被检实现的差异（刻意为之，预登记 §5）**：
   · **归一化**：被检实现 = **逐字符删空白**后整串比；本实现 = **按词切分**后**逐词序列**比
     ⇒ ⇒ 「删字 / 合词」类差异两边的**敏感度不同** ⇒ ⇒ 必须逐条对账。
   · **锚定**：被检实现 = 按**页面的 6 格表头**定位那张表 ＋ 按**量列**的文字匹配行；
     本实现 = 先按**账本自己的 5 格表头**定位账本那张表，
     再按**页面的「账本位置」列里的行号**反查匹配 ⇒ ⇒ 零共用锚点。
   · **行匹配**：被检实现靠「量」这一格的文字；本实现靠**行号** ⇒ ⇒ 两边各读各的。
⚖ **零共用代码**（⛔ 不 import 被检实现、⛔ 不复制它的任何函数）。
⚖ **互证自己也要能红**（`--selftest`）：把被检实现的输出**改坏** ⇒ ⇒ 本实现必须抓到。

⚖ **用法**（远端）：
   python3 _cross_check_24494.py --main <data_after.out> --page <page> --ledger <ledger>
   python3 _cross_check_24494.py --selftest --main <data_after.out> --page <page> --ledger <ledger>
"""

import argparse
import io
import os
import re
import sys

# ⚖⚖⚖ **按词切分**（⛔ 与被检实现的「删空白整串比」**故意不同**）：
#    一个 token = 「以字母/数字/下划线开头的一串」或「单个非空白非字母数字下划线字符」。
TOKEN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_+.=\-]*|[^\sA-Za-z0-9_]")
# ⚖ 账本行号引用
CITE_RE = re.compile(r":(\d{1,6})")
# ⚖ 账本那张表的表头（⚖ **账本侧**的 5 格表头 ⛔ 不是页面那张 6 格的）
LEDGER_HEADER = ["量", "w臂", "rand臂", "差/判据", "结论"]
# ⚖ 页面 → 账本 的列对应（量 / w 臂 / 差・判据）——⛔ rand 臂**不在**逐字比较的作用域内
COLS = ((0, 0), (1, 1), (3, 3))
# ⚖ 行数期望（⚖ 与预登记 E5 一致：9）
EXPECT_ROWS = 9


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def strip_deco(s):
    """⚖ 去掉 markdown 装饰（反引号 / 粗体标记）。"""
    return s.replace("`", "").replace("**", "")


def tokens(s):
    """⚖ **按词切分**（本实现的归一化口径）。"""
    return TOKEN_RE.findall(strip_deco(s))


def flat(s):
    """⚖ 「删掉所有空白」的表示（⚖ **只用于区分「表示差异」与「内容差异」**）。"""
    return re.sub(r"\s+", "", strip_deco(s))


def cells(row):
    """⚖ 表格行 ⇒ ⇒ 列（去掉首尾两个空列）。"""
    parts = row.split("|")
    return [p.strip() for p in parts[1:-1]]


def is_sep(s):
    return set(s.strip()) <= set("|-: ")


# ================================================================ 账本侧：定位那张表
def find_ledger_table(ledger_lines):
    """⚖ 在账本里定位那张 **5 格**表 ⇒ ⇒ 返回 (表头行号(1-based), [表行行号…])。"""
    for i, l in enumerate(ledger_lines):
        s = l.strip()
        if not s.startswith("|") or is_sep(s):
            continue
        if [flat(c) for c in cells(s)] != LEDGER_HEADER:
            continue
        rows = []
        j = i + 1
        while j < len(ledger_lines):
            s2 = ledger_lines[j].strip()
            if not s2.startswith("|"):
                break
            if not is_sep(s2) and len(cells(s2)) == 5 and flat(cells(s2)[0]):
                rows.append(j + 1)
            j += 1
        return i + 1, rows
    return None, []


# ================================================================ 页面侧：按**行号**反查
def find_page_rows(page_lines, ledger_rows):
    """⚖ 页面里**引用到那张表的行** ⇒ ⇒ [(页行号, 单元格, 账本行号)]。

    ⚖⚖⚖ **锚定故意不同**：不靠页面表头、不靠「量」这一格的文字
    ⇒ ⇒ 而是「**行的第 5 格里有指向账本那张表的行号**」⇒ ⇒ 零共用锚点。
    """
    sset = set(ledger_rows)
    out = []
    for i, l in enumerate(page_lines):
        s = l.strip()
        if not s.startswith("|") or is_sep(s):
            continue
        cs = cells(s)
        if len(cs) < 5:
            continue
        hits = [int(m.group(1)) for m in CITE_RE.finditer(cs[4])]
        hit = [h for h in hits if h in sset]
        if len(hit) == 1:
            out.append((i + 1, cs, hit[0]))
    return out


def derive_header_line(page_lines, first_page_row_no):
    """⚖ 由**首个匹配行往上**推导出那张表的**表头行**（跳过分隔行）⇒ ⇒ 不硬写表头文字。"""
    for i in range(first_page_row_no - 2, -1, -1):
        s = page_lines[i].strip()
        if not s.startswith("|"):
            break
        if is_sep(s):
            continue
        return i + 1
    return None


# ================================================================ 互证自己的判定
def cross_evaluate(page_text, ledger_text):
    """⚖ 一次互证判定 ⇒ ⇒ (结论字典)。"""
    page_lines = page_text.split("\n")
    ledger_lines = ledger_text.split("\n")
    n_ledger = len(ledger_lines)

    hdr_no, ledger_rows = find_ledger_table(ledger_lines)
    rows = find_page_rows(page_lines, ledger_rows) if ledger_rows else []

    bad = []
    rowv = []
    n_eq = 0
    n_ne = 0
    n_same_ok = 0
    n_same_total = 0
    rand_mismatch = 0
    cited_lines = []

    for (pl, cs, ln) in rows:
        lcs = cells(ledger_lines[ln - 1])
        cited_lines.append(ln)
        # ---- 逐字（**按词序列**）----
        eq = True
        for pi, li in COLS:
            a = tokens(cs[pi]) if pi < len(cs) else []
            b = tokens(lcs[li]) if li < len(lcs) else []
            if a != b:
                eq = False
        if eq:
            n_eq += 1
        else:
            n_ne += 1
        # ---- 「同」断言 ----
        same = "NA"
        if len(cs) >= 3 and tokens(cs[2]) == ["同"]:
            n_same_total += 1
            if len(lcs) >= 5:
                w, rnd = tokens(lcs[1]), tokens(lcs[2])
                if rnd == ["同"] or w == rnd:
                    same = "1"
                    n_same_ok += 1
                else:
                    same = "0"
            else:
                same = "0"
        # ---- rand 列：**E6**（244.95 新增）—— 页面 rand（不是「同」时）vs 账本的**可比较形式 L**
        #    ⚖ L = 账本 rand 格是「同」⇒ ⇒ 取**账本 w 格**；否则取**账本 rand 格**（预登记 §1.4）
        #    ⚖⚖⚖ 本实现用**自己的按词切分**口径 ⇒ ⇒ 与被检实现的「删空白整串」**故意不同**
        if len(cs) >= 3 and tokens(cs[2]) != ["同"] and len(lcs) >= 3:
            if tokens(lcs[2]) == ["同"]:
                L = tokens(lcs[1]) if len(lcs) >= 2 else []
            else:
                L = tokens(lcs[2])
            if tokens(cs[2]) != L:
                rand_mismatch += 1
        label = "".join(tokens(cs[0])) if cs else ""
        rowv.append((label, "1" if eq else "0", same))

    # ---- E1：逐字不一致 ⇒ 红 ----
    if n_ne:
        bad.append("E1：有 %d 行的「量/w臂/差」按词序列不等" % n_ne)
    # ---- E2：「同」断言没有出处 ⇒ 红 ----
    if n_same_total != n_same_ok:
        bad.append("E2：有 %d 行写「同」但账本证不了" % (n_same_total - n_same_ok))
    # ---- E3：每个被引的行号都必须存在、且落在那张表里 ----
    for (pl, cs, ln) in rows:
        for m in CITE_RE.finditer(cs[4]):
            n = int(m.group(1))
            if n > n_ledger:
                bad.append("E3：页行 %d 引用了不存在的账本行 :%d" % (pl, n))
            elif n not in set(ledger_rows):
                bad.append("E3：页行 %d 引的行 :%d 不在那张表里" % (pl, n))
    # ---- E4：唯一性 ----
    for (pl, cs, ln) in rows:
        full = "| " + " | ".join(cs) + " |"
        n = sum(1 for l in page_lines if l.strip() == full.strip())
        if n != 1:
            bad.append("E4：页行 %d 在整页出现 %d 次" % (pl, n))
    hdr_line = derive_header_line(page_lines, rows[0][0]) if rows else None
    if hdr_line is not None:
        htext = page_lines[hdr_line - 1].strip()
        n = sum(1 for l in page_lines if l.strip() == htext)
        if n != 1:
            bad.append("E4：表头行（%d）在整页出现 %d 次" % (hdr_line, n))
    # ---- E5：行数 ----
    if len(rows) != EXPECT_ROWS:
        bad.append("E5：匹配到 %d 行（期望 %d）" % (len(rows), EXPECT_ROWS))
    # ---- E6（244.95 新增）：rand 列与账本的**可比较形式 L** 不等 ⇒ 红 ----
    if rand_mismatch:
        bad.append("E6：有 %d 行的 rand 臂列与账本的可比较形式不等" % rand_mismatch)
    # ---- E7（244.95 新增）：被引的账本行必须**互不相同** ----
    dup = {}
    for (pl, cs, ln) in rows:
        dup.setdefault(ln, []).append(pl)
    for ln, pls in sorted(dup.items()):
        if len(pls) > 1:
            bad.append("E7：账本行 :%d 被页行 %s 同时引用" % (ln, pls))

    checks = {"E1": not any(b.startswith("E1：") for b in bad),
              "E2": not any(b.startswith("E2：") for b in bad),
              "E3": not any(b.startswith("E3：") for b in bad),
              "E4": not any(b.startswith("E4：") for b in bad),
              "E5": not any(b.startswith("E5：") for b in bad),
              "E6": not any(b.startswith("E6：") for b in bad),
              "E7": not any(b.startswith("E7：") for b in bad)}
    bij_total = len(cited_lines)
    bij_distinct = len(set(cited_lines))
    return {
        "checks": checks,
        "verdict": "A" if all(checks.values()) else "D",
        "bad": bad,
        "rowv": rowv,
        "n_anchors": len(rows),
        "n_eq": n_eq,
        "n_ne": n_ne,
        "n_same_ok": n_same_ok,
        "n_same_total": n_same_total,
        "rand_mismatch": rand_mismatch,
        "bij_total": bij_total,
        "bij_distinct": bij_distinct,
        "labels": [r[0] for r in rowv],
        "cells": [r[1] for r in rows],
    }


# ================================================================ 解析被检实现的输出
def parse_main(text):
    """⚖ 从被检实现的 --data 输出里取：AUDIT_KEYS、NUM_MATRIX、ROW_VERDICTS。"""
    keys = {}
    in_keys = False
    in_matrix = False
    in_rowv = False
    rows = []
    rowv = []
    for l in text.split("\n"):
        s = l.strip()
        if s == "===== AUDIT_KEYS =====":
            in_keys = True
            continue
        if s == "===== END_AUDIT_KEYS =====":
            in_keys = False
            continue
        if s == "===== NUM_MATRIX =====":
            in_matrix = True
            continue
        if s == "===== END_NUM_MATRIX =====":
            in_matrix = False
            continue
        if s == "===== ROW_VERDICTS =====":
            in_rowv = True
            continue
        if s == "===== END_ROW_VERDICTS =====":
            in_rowv = False
            continue
        if in_keys and "=" in l:
            k, v = l.split("=", 1)
            keys[k.strip()] = v.strip()
        elif in_matrix and l.startswith("ROW="):
            rows.append(l[4:])
        elif in_rowv and l.startswith("ROWV="):
            rowv.append(l[5:])
    return keys, rows, rowv


def parse_rowv(line):
    parts = line.split("|")
    if len(parts) < 3:
        return None
    eq = sam = "NA"
    for p in parts[1:]:
        if p.startswith("EQ="):
            eq = p[3:]
        if p.startswith("SAME="):
            sam = p[5:]
    return (parts[0], eq, sam)


# ================================================================ 对账
def compare(main_text, page_text, ledger_text):
    """⚖ 互证自己的结论 ↔ 被检实现的结论 ⇒ ⇒ 不符处逐条列出。"""
    keys, mrows, mrowv = parse_main(main_text)
    mine = cross_evaluate(page_text, ledger_text)
    diffs = []

    # ---- ① 闸门结论 ----
    for cid in ("E1", "E2", "E3", "E4", "E5", "E6", "E7"):
        got = keys.get("CHECK_" + cid)
        if got is None:
            diffs.append("%s：被检实现**没有**输出 CHECK_%s" % (cid, cid))
        elif (got == "PASS") != mine["checks"][cid]:
            diffs.append("%s：被检实现=%s ／ 互证=%s" % (cid, got, "PASS" if mine["checks"][cid] else "FAIL"))
    # ---- ② 形态 ----
    if keys.get("VERDICT") != mine["verdict"]:
        diffs.append("形态：被检实现=%s ／ 互证=%s" % (keys.get("VERDICT"), mine["verdict"]))
    # ---- ③ 逐行结论（EQ / SAME）----
    m_map = {}
    for l in mrowv:
        r = parse_rowv(l)
        if r:
            m_map[r[0]] = (r[1], r[2])
    c_map = dict((r[0], (r[1], r[2])) for r in mine["rowv"])
    for lab in sorted(set(list(m_map.keys()) + list(c_map.keys()))):
        a = m_map.get(lab)
        b = c_map.get(lab)
        if a is None:
            diffs.append("逐行：互证多出「%s」（被检实现没有这一行）" % lab)
        elif b is None:
            diffs.append("逐行：被检实现多出「%s」（互证没有这一行）" % lab)
        elif a != b:
            diffs.append("逐行「%s」：被检实现 EQ/SAME=%s/%s ／ 互证=%s/%s" % (lab, a[0], a[1], b[0], b[1]))
    # ---- ④ 页面读数（**区分「表示差异」与「内容差异」）----
    repr_diff = 0
    cell_diff = 0
    if len(mrows) != len(mine["cells"]):
        diffs.append("NUM_MATRIX 行数：被检实现=%d ／ 互证=%d" % (len(mrows), len(mine["cells"])))
    else:
        for mr, cs in zip(mrows, mine["cells"]):
            mf = mr.split("|")
            for k in range(min(len(mf), 4)):
                if tokens(mf[k]) != tokens(cs[k]):
                    if flat(mf[k]) == flat(cs[k]):
                        repr_diff += 1
                    else:
                        cell_diff += 1
                        diffs.append("第 %d 列读数不同：被检实现「%s」／ 互证「%s」"
                                     % (k, mf[k][:40], cs[k][:40]))
    # ---- ⑤ 辅助测量 ----
    if keys.get("AUX_RAND_MISMATCH") is not None:
        if int(keys["AUX_RAND_MISMATCH"]) != mine["rand_mismatch"]:
            diffs.append("AUX rand 列不符数：被检实现=%s ／ 互证=%d"
                         % (keys["AUX_RAND_MISMATCH"], mine["rand_mismatch"]))
    if keys.get("AUX_BIJ") is not None:
        if int(keys["AUX_BIJ"]) != mine["bij_distinct"]:
            diffs.append("AUX 一一对应数：被检实现=%s ／ 互证=%d"
                         % (keys["AUX_BIJ"], mine["bij_distinct"]))
    return mine, diffs, repr_diff, cell_diff


def selftest(main_text, page_text, ledger_text):
    """⚖ **互证自己也要能红**：把被检实现的输出**改坏** ⇒ ⇒ 必须被抓到。"""
    bad_out = main_text
    bad_out = bad_out.replace("CHECK_E6=PASS", "CHECK_E6=FAIL", 1)
    if bad_out == main_text:
        bad_out = bad_out.replace("CHECK_E1=PASS", "CHECK_E1=FAIL", 1)
    if bad_out == main_text:
        bad_out = bad_out.replace("CHECK_E2=PASS", "CHECK_E2=FAIL", 1)
    # 再改一个逐行结论（EQ）与一个读数
    lines = bad_out.split("\n")
    out2 = []
    done_rowv = False
    done_num = False
    for l in lines:
        if (not done_rowv) and l.startswith("ROWV=") and "|EQ=1|" in l:
            l = l.replace("|EQ=1|", "|EQ=0|", 1)
            done_rowv = True
        elif (not done_num) and l.startswith("ROW=") and l.count("|") >= 3:
            parts = l.split("|")
            parts[1] = parts[1] + "X"
            l = "|".join(parts)
            done_num = True
        out2.append(l)
    bad_out = "\n".join(out2)
    _mine, diffs, _rd, _cd = compare(bad_out, page_text, ledger_text)
    n = len(diffs)
    print("互证自证：把被检实现的输出改坏（翻一个闸门 ＋ 改一个逐行结论 ＋ 改一个读数）")
    print("  ⇒ 互证抓到 **%d** 处不符" % n)
    for d in diffs[:8]:
        print("    · %s" % d)
    if n == 0:
        print("⛔ 互证**抓不到**被改坏的输出 ⇒ ⇒ 互证自己**没有牙齿** ⇒ ⇒ 中止")
        print("===== AUDIT_KEYS =====")
        print("CROSS_SELFTEST_RC=1")
        print("===== END_AUDIT_KEYS =====")
        return 1
    print("===== AUDIT_KEYS =====")
    print("CROSS_SELFTEST_N_DIFF=%d" % n)
    print("CROSS_SELFTEST_RC=0")
    print("===== END_AUDIT_KEYS =====")
    return 0


def main():
    ap = argparse.ArgumentParser(description="244.94 互证：第二条独立实现（零共用代码）")
    ap.add_argument("--main", required=True, help="被检实现的 --data 输出")
    ap.add_argument("--page", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    main_text = read_text(a.main)
    page_text = read_text(a.page)
    ledger_text = read_text(a.ledger)

    if a.selftest:
        return selftest(main_text, page_text, ledger_text)

    mine, diffs, repr_diff, cell_diff = compare(main_text, page_text, ledger_text)

    print("=" * 70)
    print("互证：锚点 **按账本表头 + 行号反查**（⛔ 与被检实现的「页面表头 + 量列」**故意不同**）")
    print("     归一化：**按词切分逐词比**（⛔ 与被检实现的「删空白整串比」**故意不同**）")
    print("=" * 70)
    for cid in ("E1", "E2", "E3", "E4", "E5", "E6", "E7"):
        print("[%s] %s" % ("PASS" if mine["checks"][cid] else "FAIL", cid))
    print("")
    print("锚点 %d ｜ 逐字相同 %d ｜ 逐字不同 %d" % (mine["n_anchors"], mine["n_eq"], mine["n_ne"]))
    print("「同」断言：%d/%d 有出处" % (mine["n_same_ok"], mine["n_same_total"]))
    print("辅助测量：rand 列不符 %d ｜ 一一对应 %d/%d"
          % (mine["rand_mismatch"], mine["bij_distinct"], mine["bij_total"]))
    print("形态（互证自己算的）：%s" % mine["verdict"])
    print("")
    print("⚖ 与被检实现的不符：%d 处（表示差异 %d 处不算不符）" % (len(diffs), repr_diff))
    for d in diffs:
        print("  · %s" % d)
    if mine["bad"]:
        print("")
        print("⚖ 互证自己的判红明细：")
        for b in mine["bad"]:
            print("  · %s" % b)

    print("")
    print("===== AUDIT_KEYS =====")
    print("CROSS_N_ANCHORS=%d" % mine["n_anchors"])
    print("CROSS_E6_MISMATCH=%d" % mine["rand_mismatch"])
    print("CROSS_E7_DUP=%d" % max(0, mine["bij_total"] - mine["bij_distinct"]))
    print("CROSS_N_EQ=%d" % mine["n_eq"])
    print("CROSS_N_NE=%d" % mine["n_ne"])
    print("CROSS_SAME_OK=%d" % mine["n_same_ok"])
    print("CROSS_SAME_TOTAL=%d" % mine["n_same_total"])
    print("CROSS_CELL_MISMATCH=%d" % cell_diff)
    print("CROSS_REPR_DIFF=%d" % repr_diff)
    print("CROSS_RAND_MISMATCH=%d" % mine["rand_mismatch"])
    print("CROSS_BIJ=%d" % mine["bij_distinct"])
    print("CROSS_BIJ_TOTAL=%d" % mine["bij_total"])
    print("CROSS_MISMATCH=%d" % len(diffs))
    print("CROSS_VERDICT=%s" % mine["verdict"])
    print("CROSS_RC=%d" % (0 if not diffs else 1))
    print("===== END_AUDIT_KEYS =====")
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
