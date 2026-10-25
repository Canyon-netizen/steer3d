#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_spec_crosscheck_24494.py —— 预登记 ↔ 实现 的机械对账（244.94）。

⚖ 要对账的五件事（预登记 §2 / §3 / §4）：
   ① **判据集合**：预登记 §2 登记的 E1–E5 ⇒ ⇒ 被检实现里必须**恰好**是这 5 条（不多不少）。
   ② **变异集合**：预登记 §4 登记的 MU-E1..MU-E10 ⇒ ⇒ 变异台必须**都**有（⛔ 少一条即红）；
      额外的那几条**必须**是「实现期新增、非预登记」（⇒ ⇒ 会被如实登记）。
   ③ ⚖⚖⚖ **缺陷行集合**：预登记 §1.2 登记的**哪几行**有措辞缺陷
      ⇒ ⇒ 与「**改前**页面里实际有差异的行」必须**恰好一致**（不多不少）
      ⇒ ⇒ 这证明检查器找到的**就是**预登记登记的那些缺陷。
   ④ **零手写期望**：被检实现的源码里（⛔ 注释/docstring/夹具区除外）**不许**出现本轮的真值/真行号
      ⇒ ⇒ 「期望从页面行派生、零手写期望」是**机械可查**的，不靠自觉。
   ⑤ **手写期望与归一化口径**：E5 的手写行数必须 == 预登记写的那个数；
      归一化必须包含预登记 §2 写的三步（去反引号 / 去粗体 / 去所有空白）。

⚖ **用法**（远端）：
   python3 _spec_crosscheck_24494.py --prereg … --checker … --bench … --page-before …
       --ledger … --main-before … --main-after …
"""

import argparse
import ast
import io
import os
import re
import sys

# ⚖⚖⚖ **本轮的真值 / 真行号**（真页面 §6.2.1 里出现过的东西）⇒ ⇒ 实现里**不许**出现它们
#    ⚖ 表头列名（量 / w 臂 / rand 臂 / 差・判据 / 账本位置 / 复算）**不在此列**：
#    它们是**预登记 §1.3 登记的锚**，⛔ 不是「手写期望」。
REAL_TOKENS = [
    "6.429e-10", "5.172e-05", "1.0e-06", "1.0e-02",
    "0.99999999935713024", "0.99999999999999989", "1.0000327090", "0.9999809866",
    "linspace(-120.0, 120.0, 60)", "56.73720169067383", "113.47440338134766",
    "167", "2004",
    "41602", "41604", "41605", "41606", "41607", "41608", "41609", "41610",
    "41611", "41612", "41613", "41614", "41615", "41616",
    "直接求和路径", "同一把向量", "n_eff",
]


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def fixture_range(src_lines):
    """⚖ 被检实现里「合成夹具」那一段的行区间（⛔ 该区**必然**含合成值 ⇒ 不计入「手写期望」）。"""
    start = None
    end = None
    for i, l in enumerate(src_lines, 1):
        s = l.lstrip()
        if start is None and s.startswith("#") and "合成夹具" in l:
            start = i
        elif start is not None and s.startswith("#") and "自检" in l:
            end = i
            break
    return start, end


def scan_real_tokens(checker):
    """⚖ AST 级扫描：**代码**里（⛔ 注释/docstring/夹具区除外）有没有本轮的真值。"""
    src_lines = checker.split("\n")
    fx_start, fx_end = fixture_range(src_lines)
    try:
        tree = ast.parse(checker)
    except SyntaxError:
        return ["<语法错>"]
    doc_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                doc_ids.add(id(body[0].value))
    hits = []
    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue
        if fx_start and fx_start <= node.lineno <= (fx_end if fx_end else 10 ** 9):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in doc_ids:
                continue
            for tok in REAL_TOKENS:
                if re.search(r"(?<![\w.])%s(?![\w.])" % re.escape(tok), node.value):
                    hits.append("%s@L%d" % (tok, node.lineno))
    return hits


def parse_prereg_criteria(prereg):
    """⚖ 预登记 §2 登记的判据 id（形如 `**E1 ·`）。"""
    return sorted(set(re.findall(r"\*\*([ED]\d+) ·", prereg)))


def parse_prereg_mutations(prereg):
    """⚖ 预登记 §4 登记的变异 id（表格首列）。"""
    return sorted(set(re.findall(r"^\| (MU-E\d+) \|", prereg, re.M)))


def parse_bench_mutations(bench_src):
    """⚖ 变异台源码里声明的变异 id。"""
    return sorted(set(re.findall(r'\("(MU-E\d+)"', bench_src)))


def parse_prereg_defect_lines(prereg):
    """⚖ 预登记 §1.2 登记的**缺陷行**（账本行号）。

    ⚖⚖⚖ **只认 §1.2 那张表**（**5 格**）：⛔ §1.1 那张「抽到的数」表是 **3 格** ⇒ 必须排除
    ⇒ ⇒ 否则会把 9 行全吃进来。
    ⚖ 「合法压缩」那行（`:41610`）**不是**缺陷 ⇒ ⇒ 排除。
    """
    out = []
    for line in prereg.split("\n"):
        if not line.startswith("| `:41"):
            continue
        if len(cells(line)) != 5:
            continue
        m = re.match(r"^\| `:(\d+)` \|", line)
        if not m:
            continue
        if "合法压缩" in line:
            continue
        out.append(int(m.group(1)))
    return sorted(set(out))


def flat(s):
    """⚖ 本对账自己的归一化（去装饰 ＋ 去空白）⇒ ⇒ ⛔ 与被检实现**分开写**（不共用代码）。"""
    s = s.replace("`", "").replace("**", "")
    return re.sub(r"\s+", "", s)


def cells(row):
    parts = row.split("|")
    return [p.strip() for p in parts[1:-1]]


def is_sep(s):
    return set(s.strip()) <= set("|-: ")


def find_ledger_table_lines(ledger_lines):
    """⚖ 账本里那张 **5 格**表（表头 = 量 / w 臂 / rand 臂 / 差・判据 / 结论）的**表行行号集合**。

    ⚖⚖⚖ **为什么要这一步**：页面**别的小节**（§6.1 判决面板等）也有 6 格表、也在第 5 格放账本行号
    ⇒ ⇒ 若不把范围限死在这张表里 ⇒ ⇒ 它们的「差」列差异会被**算进**本轮的缺陷集合
    ⇒ ⇒ ⇒ 范围必须**锚到账本那张表**。
    """
    want = ["量", "w臂", "rand臂", "差/判据", "结论"]
    for i, l in enumerate(ledger_lines):
        s = l.strip()
        if not s.startswith("|") or is_sep(s):
            continue
        if [flat(c) for c in cells(s)] != want:
            continue
        out = set()
        j = i + 1
        while j < len(ledger_lines):
            s2 = ledger_lines[j].strip()
            if not s2.startswith("|"):
                break
            if not is_sep(s2) and len(cells(s2)) == 5 and flat(cells(s2)[0]):
                out.add(j + 1)
            j += 1
        return out
    return set()


def compute_diff_lines(page_text, ledger_text):
    """⚖ **独立**算出「页面里引用账本那张表的行」中**哪些账本行**的「差/判据」列与页面不一致。"""
    plines = page_text.split("\n")
    llines = ledger_text.split("\n")
    table = find_ledger_table_lines(llines)
    out = []
    for l in plines:
        s = l.strip()
        if not s.startswith("|") or is_sep(s):
            continue
        cs = cells(s)
        if len(cs) < 5:
            continue
        m = re.search(r":(\d{1,6})", cs[4])
        if not m:
            continue
        ln = int(m.group(1))
        if ln not in table:
            continue
        lcs = cells(llines[ln - 1])
        if len(lcs) < 4:
            continue
        # ⚖ E1 的**三列**（量 / w 臂 / 差・判据）⇒ ⇒ 哪一列不一致都算缺陷
        diff = False
        for pi, li in ((0, 0), (1, 1), (3, 3)):
            if pi >= len(cs) or li >= len(lcs):
                diff = True
                break
            if flat(cs[pi]) != flat(lcs[li]):
                diff = True
                break
        if diff:
            out.append(ln)
    return sorted(set(out))


def parse_expect_rows(prereg):
    """⚖ 预登记 E5 里写的**手写**行数期望。"""
    m = re.search(r"数据行数必须恰为 (\d+)", prereg)
    return int(m.group(1)) if m else None


def checker_expect_rows(checker):
    """⚖ 被检实现里 `EXPECT_ROWS = <数>` 的值（AST 级，不靠正则瞎扫注释）。"""
    try:
        tree = ast.parse(checker)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "EXPECT_ROWS":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                        return node.value.value
    return None


def check_normalization(checker):
    """⚖ 归一化必须包含预登记 §2 写的三步：去反引号 / 去粗体 / 去所有空白。"""
    marks = {
        "去反引号": 'replace("`", "")' in checker,
        "去粗体": 'replace("**", "")' in checker,
        "去所有空白": bool(re.search(r're\.sub\(\s*r"\\s\+"\s*,\s*""', checker)),
    }
    return marks


def main():
    ap = argparse.ArgumentParser(description="244.94 预登记 ↔ 实现 对账")
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--checker", required=True)
    ap.add_argument("--bench", required=True)
    ap.add_argument("--page-before", required=True)
    ap.add_argument("--page-after", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--main-before", required=True)
    ap.add_argument("--main-after", required=True)
    a = ap.parse_args()

    prereg = read_text(a.prereg)
    checker = read_text(a.checker)
    bench = read_text(a.bench)
    page_before = read_text(a.page_before)
    page_after = read_text(a.page_after)
    ledger = read_text(a.ledger)
    main_before = read_text(a.main_before)
    main_after = read_text(a.main_after)

    bad = []
    detail = []

    # ---- ① 判据集合 ----
    pc = parse_prereg_criteria(prereg)
    got_checks = sorted(set(re.findall(r"^CHECK_(E\d)=", main_after, re.M)))
    if pc != ["E1", "E2", "E3", "E4", "E5"]:
        bad.append("预登记 §2 登记的判据不是 E1–E5（实得 %s）" % pc)
    if got_checks != pc:
        bad.append("被检实现的判据集合 %s ≠ 预登记 %s" % (got_checks, pc))
    else:
        detail.append("判据集合一致：%s" % "、".join(pc))

    # ---- ② 变异集合 ----
    pm = parse_prereg_mutations(prereg)
    bm = parse_bench_mutations(bench)
    missing = [x for x in pm if x not in bm]
    if missing:
        bad.append("预登记 §4 登记的变异 %s 在变异台里**缺**" % missing)
    else:
        extra = [x for x in bm if x not in pm]
        detail.append("变异集合覆盖预登记 %d 条%s"
                      % (len(pm), ("；额外 %s（实现期新增、非预登记）" % extra) if extra else ""))

    # ---- ③ 缺陷行集合：预登记登记的 == 实际有差异的 ----
    want_def = parse_prereg_defect_lines(prereg)
    got_def = compute_diff_lines(page_before, ledger)
    if want_def != got_def:
        bad.append("缺陷行集合：预登记登记 %s ／ 实际有差异 %s ⇒ ⇒ **不一致**"
                   % (want_def, got_def))
    else:
        detail.append("缺陷行集合一致：%s（预登记登记的 == 实际有差异的）" % want_def)
    # ⚖ **改后**必须**没有**差异行（这是改动的实际效果，独立算一遍）
    after_diff = compute_diff_lines(page_after, ledger)
    if after_diff:
        bad.append("**改后**页面仍有差异行 %s ⇒ ⇒ 改后不绿" % after_diff)
    else:
        detail.append("**改后**页面：差异行 0（独立算得）")
    # ⚖ 被检实现的「改后」输出必须全绿
    after_red = re.findall(r"^CHECK_(E\d)=FAIL", main_after, re.M)
    if after_red:
        bad.append("被检实现的「改后」输出有红闸门 %s ⇒ ⇒ 改后仍不绿" % after_red)
    else:
        detail.append("被检实现的「改后」输出：E1–E5 **全绿**")

    # ---- ④ 零手写期望 ----
    hits = scan_real_tokens(checker)
    if hits:
        bad.append("被检实现的**代码**里出现了本轮的**真值/真行号** %s ⇒ ⇒ 期望不是派生的"
                   % hits[:8])
    else:
        detail.append("被检实现的**代码**里（⛔ 注释/docstring/夹具区除外）**不含**任何本轮真值"
                      "（零手写期望，机械可查）")

    # ---- ⑤ 手写期望（E5 的 9）＋ 归一化口径 ----
    want_rows = parse_expect_rows(prereg)
    got_rows = checker_expect_rows(checker)
    if want_rows is None or got_rows != want_rows:
        bad.append("E5 的手写行数期望：预登记=%s ／ 实现 EXPECT_ROWS=%s" % (want_rows, got_rows))
    else:
        detail.append("E5 的手写行数期望：预登记与实现都是 %d" % want_rows)
    marks = check_normalization(checker)
    miss_marks = [k for k, v in marks.items() if not v]
    if miss_marks:
        bad.append("归一化口径缺这几步（预登记 §2）：%s" % miss_marks)
    else:
        detail.append("归一化口径三步齐全（去反引号 / 去粗体 / 去所有空白）")

    print("=" * 70)
    for d in detail:
        print("  · %s" % d)
    print("")
    print("===== AUDIT_KEYS =====")
    print("SPEC_N_CRITERIA=%d" % len(pc))
    print("SPEC_N_MUT=%d" % len(pm))
    print("SPEC_N_DEFECT=%d" % len(want_def))
    print("SPEC_DEFECT_LINES=%s" % want_def)
    print("SPEC_REAL_TOKEN_HITS=%d" % len(hits))
    print("SPEC_EXPECT_ROWS=%s" % want_rows)
    print("SPEC_RC=%d" % (1 if bad else 0))
    print("===== END_AUDIT_KEYS =====")
    if bad:
        print("")
        for b in bad:
            print("⛔ %s" % b)
        return 1
    print("")
    print("SPEC_RC=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
