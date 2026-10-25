#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_cross_check_24493.py —— 互证（244.93）：**第二条独立实现**核对 `doc_dose_axis_audit.py`。

⚖⚖⚖ **零共用代码**：⛔ 不 import 被检实现、⛔ 不复用它的任何函数。
⚖⚖⚖ **锚定口径故意不同**（预登记 §5）：
   · 被检实现：**按标签列**（「展品」列整格归一化相等）定位锚点行；
   · 本实现：**按第 1＋2 列的数集合**定位锚点行 ⇒ ⇒ 两边定位到的**必须**是同一行。
⚖⚖⚖ **取数口径故意不同**：
   · 被检实现：**token 级**（独立成词的数字**字符串**相等）；
   · 本实现：**lookaround 正则**取数 ＋ **数值 + 正负号**比较。
⚖⚖⚖ **引用解析故意不同**：
   · 被检实现：出处格里「最后一个『账本』之后」的行号 ＋ 严格区间正则；
   · 本实现：出处格里**全部**行号，⛔ 但剔掉紧跟在「.md」文件名后的那些（那是别的文件的行号）。
⚖ 要对账的量：每个锚点行引用的行号集合、每个数的「有无出处」、D1–D4 的判定、最终形态。

⚖ **用法**（远端）：
   python3 _cross_check_24493.py --main <被检实现的 data 输出> --page <页面> --ledger <账本>
   python3 _cross_check_24493.py --selftest --main <被检实现的 data 输出> --page … --ledger …
"""

import argparse
import io
import re
import sys

CHECKS = ("D1", "D2", "D3", "D4")

# ⚖⚖⚖ **本实现自己的解析口径**（⛔ 与被检实现不同）
NUM_RE = re.compile(r"(?<![\w.])[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w.])")
CITE_RE = re.compile(r":(\d{1,7})")
DASHES = "–—-"
BAND_RE = re.compile(r"(\d{1,4})\s*/\s*(\d{1,4})\s*/\s*(\d{1,4})\s*/\s*(\d{1,4})")


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def num_key(tok):
    """⚖ 页面上的数 ⇒ (正负号, 数值) 键。"""
    sign = tok[0] if tok[0] in "+-" else ""
    return (sign, float(tok))


def nums_of(text):
    """⚖ 本实现取数：lookaround 正则 ⇒ ⇒ 返回数字**字符串**列表。"""
    return [m.group(0) for m in NUM_RE.finditer(text)]


def parse_cites(cell, skip_after_md=False):
    """⚖ 本实现取引用行号：位置扫描 ＋ 「两个引用之间夹着破折号 ⇒ 是区间」。

    ⚖ `skip_after_md=True` ⇒ ⇒ 剔掉**紧跟在 `.md` 文件名后**的行号（那是**别的文件**的行号）。
    """
    hits = []
    for m in CITE_RE.finditer(cell):
        if skip_after_md:
            pre = cell[max(0, m.start() - 12):m.start()]
            if pre.rstrip().endswith(".md"):
                continue
        hits.append((m.start(), m.end(), int(m.group(1))))
    lines = set()
    for i, (_s, e, n) in enumerate(hits):
        lines.add(n)
        if i + 1 < len(hits):
            gap = cell[e:hits[i + 1][0]]
            if any(d in gap for d in DASHES):
                nxt = hits[i + 1][2]
                a, b = (n, nxt) if n <= nxt else (nxt, n)
                for x in range(a, b + 1):
                    lines.add(x)
    return sorted(lines)


def table_rows(page_lines):
    """⚖ 本实现定位表：找「首格 == 展品」的那行 ⇒ ⇒ 之后连续的表行。"""
    hdr = None
    for i, l in enumerate(page_lines):
        s = l.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and cells[0] == "展品":
            hdr = i
            break
    if hdr is None:
        return []
    rows = []
    for l in page_lines[hdr + 1:]:
        s = l.strip()
        if not s.startswith("|"):
            break
        if set(s) <= set("|-: "):
            continue
        rows.append(s)
    return rows


def row_cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def note_cites(src):
    """⚖ 本实现：口径切换注**出处行**里的引用 ⇒ ⇒ 按「**这段引用属于哪个文件**」归属。

    ⚖ `.md` 文件名**之后**的行号属于**那个文件**（⛔ 不是账本）⇒ ⇒ 见到「账本」二字才切回账本。
    ⚖ （被检实现用的是「最后一个『账本』之后的全部行号」⇒ ⇒ 口径**故意不同**。）
    """
    hits = []
    cur_file = None
    for m in re.finditer(r"([\w./-]*\.md)|(账本)|:(\d{1,7})", src):
        if m.group(1):
            cur_file = m.group(1)
        elif m.group(2):
            cur_file = None
        else:
            if cur_file is None:
                hits.append((m.start(), m.end(), int(m.group(3))))
    lines = set()
    for i, (_s, e, n) in enumerate(hits):
        lines.add(n)
        if i + 1 < len(hits):
            gap = src[e:hits[i + 1][0]]
            if any(d in gap for d in DASHES):
                nxt = hits[i + 1][2]
                a, b = (n, nxt) if n <= nxt else (nxt, n)
                for x in range(a, b + 1):
                    lines.add(x)
    return sorted(lines)


def parse_main_output(text):
    """⚖ 解析被检实现的输出 ⇒ ⇒ (AUDIT_KEYS, ROW 矩阵, CITE 映射, 注的四档组, 注的引用行)。"""
    keys = {}
    rows = []
    cites = {}
    note_groups = []
    note_cites = []
    mode = None
    for l in text.split("\n"):
        s = l.strip()
        if s == "===== AUDIT_KEYS =====":
            mode = "keys"
            continue
        if s == "===== END_AUDIT_KEYS =====":
            mode = None
            continue
        if s == "===== NUM_MATRIX =====":
            mode = "matrix"
            continue
        if s == "===== END_NUM_MATRIX =====":
            mode = None
            continue
        if mode == "keys" and "=" in l:
            k, v = l.split("=", 1)
            keys[k.strip()] = v.strip()
        elif mode == "matrix" and "=" in l:
            k, v = l.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k == "ROW":
                parts = v.split("|")
                if len(parts) >= 3:
                    rows.append((parts[0], parts[1], int(parts[2])))
            elif k == "CITE":
                parts = v.split("|")
                cites[parts[0]] = [int(x) for x in parts[1].split(",") if x]
            elif k == "NOTE_GROUP":
                note_groups.append(v)
            elif k == "NOTE_CITE":
                note_cites = [int(x) for x in v.split(",") if x]
    return keys, rows, cites, note_groups, note_cites


def find_note(page_lines):
    """⚖ 本实现找口径切换注：正文行含「口径切换」；出处行 = 其后 3 行内含「出处：」的行。"""
    note = None
    for i, l in enumerate(page_lines):
        if "口径切换" in l:
            note = (i, l)
            break
    if note is None:
        return None, None
    for j in range(note[0] + 1, min(note[0] + 4, len(page_lines))):
        if "出处：" in page_lines[j]:
            return note[1], page_lines[j]
    return note[1], None


def compare(main_text, page_text, ledger_text):
    """⚖ 对账 ⇒ ⇒ 返回一张 mismatch 计数字典。"""
    keys, mrows, mcites, mnote_groups, mnote_cites = parse_main_output(main_text)
    page_lines = page_text.split("\n")
    rows = table_rows(page_lines)
    ledger_lines = ledger_text.split("\n")
    n_lines = len(ledger_lines)
    lnum = {}
    for i, l in enumerate(ledger_lines, 1):
        lnum[i] = set(num_key(t) for t in nums_of(l))

    rep = {"n_anchors": 0, "n_numbers": 0,
           "cite_mismatch": 0, "num_mismatch": 0, "check_mismatch": 0,
           "verdict_mismatch": 0, "note_mismatch": 0, "detail": []}

    by_anchor = {}
    for name, num, found in mrows:
        by_anchor.setdefault(name, []).append((num, found))

    # ⚖ 本实现的锚定：**第 1＋2 列的数集合**相等 ⇒ ⇒ 与被检实现的「标签列」定位对账
    anchor_row = {}
    for name in sorted(by_anchor.keys()):
        rep["n_anchors"] += 1
        want_set = sorted(t for t, _f in by_anchor[name])
        hit = None
        for r in rows:
            cs = row_cells(r)
            if len(cs) < 3:
                continue
            got = sorted(nums_of(cs[0] + " ｜ " + cs[1]))
            if got == want_set:
                hit = r
                break
        if hit is None:
            rep["cite_mismatch"] += 1
            rep["detail"].append("锚点 %s：按**数集合**在本实现里**定位不到**（期望数 %s）"
                                 % (name, want_set))
            continue
        anchor_row[name] = hit

    for name in sorted(by_anchor.keys()):
        if name not in anchor_row:
            continue
        cs = row_cells(anchor_row[name])
        lines = parse_cites(cs[2])
        if list(mcites.get(name, [])) != lines:
            rep["cite_mismatch"] += 1
            rep["detail"].append("锚点 %s：引用行号集合不一致（被检 %s ｜ 本实现 %s）"
                                 % (name, mcites.get(name), lines))
        for tok, mfound in by_anchor[name]:
            rep["n_numbers"] += 1
            key = num_key(tok)
            mine = 0
            for ln in lines:
                if ln in lnum and key in lnum[ln]:
                    mine = 1
                    break
            if mine != mfound:
                rep["num_mismatch"] += 1
                rep["detail"].append("锚点 %s：数 %s 的「有无出处」不一致（被检 %d ｜ 本实现 %d）"
                                     % (name, tok, mfound, mine))

    # ⚖ 本实现自己算 D1–D4（**不**照抄被检实现）
    d1 = 1
    for name in sorted(by_anchor.keys()):
        if name not in anchor_row:
            d1 = 0
            continue
        cs = row_cells(anchor_row[name])
        lines = parse_cites(cs[2])
        for tok, _f in by_anchor[name]:
            key = num_key(tok)
            if not any(ln in lnum and key in lnum[ln] for ln in lines):
                d1 = 0

    d2 = 1
    for r in rows:
        if sum(1 for l in page_lines if l.strip() == r) != 1:
            d2 = 0

    d3 = 1
    for r in rows:
        cs = row_cells(r)
        if len(cs) < 3:
            continue
        for ln in parse_cites(cs[2]):
            if ln > n_lines:
                d3 = 0

    d4 = 1
    note, src = find_note(page_lines)
    note_lines = []
    if note is None or src is None:
        d4 = 0
    else:
        groups = ["/".join(g) for g in BAND_RE.findall(note)]
        note_lines = note_cites(src)
        for g in groups:
            gnorm = g.replace(" ", "")
            if not any(ln <= n_lines and gnorm in ledger_lines[ln - 1] for ln in note_lines):
                d4 = 0
        if sorted(groups) != sorted(mnote_groups):
            rep["note_mismatch"] += 1
            rep["detail"].append("口径切换注的四档组集合不一致（被检 %s ｜ 本实现 %s）"
                                 % (mnote_groups, groups))
        if list(mnote_cites) != note_lines:
            rep["note_mismatch"] += 1
            rep["detail"].append("口径切换注的引用行号不一致（被检 %s ｜ 本实现 %s）"
                                 % (mnote_cites, note_lines))

    mine_all = {"D1": d1, "D2": d2, "D3": d3, "D4": d4}
    for c in CHECKS:
        their = keys.get("CHECK_" + c)
        if their is None:
            rep["check_mismatch"] += 1
            rep["detail"].append("被检实现的输出里**没有** CHECK_%s" % c)
            continue
        their_ok = 1 if their == "PASS" else 0
        if their_ok != mine_all[c]:
            rep["check_mismatch"] += 1
            rep["detail"].append("%s：判定不一致（被检 %s ｜ 本实现 %s）"
                                 % (c, their, "PASS" if mine_all[c] else "FAIL"))
    my_verdict = "A" if all(mine_all.values()) else "D"
    if keys.get("VERDICT") != my_verdict:
        rep["verdict_mismatch"] += 1
        rep["detail"].append("最终形态不一致（被证 %s ｜ 本实现 %s）"
                             % (keys.get("VERDICT"), my_verdict))
    return rep


def main():
    ap = argparse.ArgumentParser(description="244.93 互证：独立实现 ↔ 被检实现")
    ap.add_argument("--main", required=True, help="被检实现的 --data 输出文件")
    ap.add_argument("--page", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--selftest", action="store_true",
                    help="⚖ 自证会红：故意改坏被检实现的输出 ⇒ ⇒ 必须被抓到")
    a = ap.parse_args()

    main_text = read_text(a.main)
    page_text = read_text(a.page)
    ledger_text = read_text(a.ledger)

    if a.selftest:
        # ⚖⚖⚖ **自证会红**：改坏被检实现的输出（翻一个「有无出处」标志 ＋ 翻一个判定）⇒ ⇒ 必须被抓到
        lines = main_text.split("\n")
        flipped_num = 0
        flipped_chk = 0
        out = []
        for l in lines:
            if l.startswith("ROW=") and not flipped_num and l.endswith("|1"):
                l = l[:-1] + "0"
                flipped_num += 1
            elif l.startswith("CHECK_D2=") and not flipped_chk:
                l = "CHECK_D2=FAIL"
                flipped_chk += 1
            out.append(l)
        if not flipped_num or not flipped_chk:
            print("⛔ 自证构造失败（翻不动）⇒ 中止")
            return 2
        rep = compare("\n".join(out), page_text, ledger_text)
        ok = (rep["num_mismatch"] > 0) and (rep["check_mismatch"] > 0)
        print("[%s] 自证会红：改坏被检输出后互证必须抓到（抓到 num=%d chk=%d）"
              % ("PASS" if ok else "FAIL", rep["num_mismatch"], rep["check_mismatch"]))
        print("===== AUDIT_KEYS =====")
        print("CROSS_SELFTEST_RED=%d" % (0 if ok else 1))
        print("CROSS_SELFTEST_RC=%d" % (0 if ok else 1))
        print("===== END_AUDIT_KEYS =====")
        return 0 if ok else 1

    rep = compare(main_text, page_text, ledger_text)
    print("=" * 70)
    print("互证：锚点 %d ｜ 逐数比对 %d ｜ 引用行号不符 %d ｜ 逐数不符 %d ｜ 判定不符 %d"
          % (rep["n_anchors"], rep["n_numbers"], rep["cite_mismatch"],
             rep["num_mismatch"], rep["check_mismatch"]))
    print("形态不符 %d ｜ 口径注不符 %d" % (rep["verdict_mismatch"], rep["note_mismatch"]))
    for d in rep["detail"]:
        print("  · %s" % d)
    print("")
    print("===== AUDIT_KEYS =====")
    print("CROSS_N_ANCHORS=%d" % rep["n_anchors"])
    print("CROSS_N_NUMBERS=%d" % rep["n_numbers"])
    print("CROSS_CITE_MISMATCH=%d" % rep["cite_mismatch"])
    print("CROSS_NUM_MISMATCH=%d" % rep["num_mismatch"])
    print("CROSS_CHECK_MISMATCH=%d" % rep["check_mismatch"])
    print("CROSS_VERDICT_MISMATCH=%d" % rep["verdict_mismatch"])
    print("CROSS_NOTE_MISMATCH=%d" % rep["note_mismatch"])
    bad = (rep["cite_mismatch"] or rep["num_mismatch"] or rep["check_mismatch"]
           or rep["verdict_mismatch"] or rep["note_mismatch"])
    print("CROSS_RC=%d" % (1 if bad else 0))
    print("===== END_AUDIT_KEYS =====")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
