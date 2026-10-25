#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_spec_crosscheck_24496.py —— 预登记 ↔ 实现 的**机械对账**（244.96）。

⚖⚖⚖ **口径真相源**：`.cache/xcheck/R6_PANEL_PREREG.md`。

⚖⚖⚖ 要对账的六件事：
   ① **判据集合**：预登记 §2 登记的 E1–E8 ⇒ ⇒ 被检实现里必须**恰好**是这 8 条（不多不少）。
   ② **变异集合**：预登记 §4 登记的 MU-H1..MU-H10 ⇒ ⇒ 变异台必须**都**有（⛔ 少一条即红）；
      额外的那几条必须**是**「实现期新增、非预登记」（⇒ ⇒ 会被如实登记）。
   ③ ⚖⚖⚖ **缺陷行集合**：预登记 §1.3 登记为「出处缺失 / 量词不符」的那几行
      ⇒ ⇒ 与「**改前 → 改后**页面里实际有差异的行」必须**恰好一致**（不多不少）
      ⇒ ⇒ 这证明检查器找到的**就是**预登记登记的那些缺陷。
      ⇒ ⚠ 「页面补充说明」（P11 的「56 个 base」）在预登记里登记为**留白**⇒ ⇒ 不算缺陷行。
   ④ **零手写期望**：被检实现的源码里（⛔ 注释/docstring/夹具区除外）**不许**出现
      本轮的真值 / 真行号 ⇒ ⇒ 「期望从页面派生、零手写期望」是**机械可查**的。
   ⑤ **手写期望与口径**：E1 的手写行数 == 预登记写的那个数；归一化必须包含预登记 §3 写的
      三步（去反引号 / 去粗体 / 去所有空白）；R6' 的 6 位小数必须 == 预登记写的；
      **且**实现里必须**引用** R6' 的外部依据（账本 `:41722` / `:39004`）。
   ⑥ ⚖⚖⚖ **预登记的预测必须兑现**：预登记 §1.3 写「改前预期判红 E5 / E6 / E7」
      ⇒ ⇒ 「改前」那份收据里的判红集合必须**恰好**是 {E5, E6, E7}
      ⇒ ⇒ 这证明「预登记先于结果」不是嘴上说说（⛔ 预登记写错了 ⇒ 这里立刻红）。
"""

import argparse
import ast
import io
import os
import re
import sys

# ⚖⚖⚖ **本轮的真值 / 真行号**（真页面 §6.1 里出现过的东西）⇒ ⇒ 实现里**不许**出现它们
#    ⚖ 「破口：」「违例：」**不在此列**：它们是**预登记 §2 E5 定的口径**，⛔ 不是「手写期望」。
#    ⚖ 「4/12」「17/27」**不在此列**：它们出现在**合成夹具**里 ⇒ ⇒ 由夹具区规则排除。
REAL_TOKENS = [
    # —— 页面 §6.1 引用的全部账本行号 ——
    "41396", "41404", "41408", "41535", "41536", "41537", "41539",
    "41937", "41938", "41939", "41940", "41941", "41942", "41943", "41944",
    "42042", "42055", "42161", "42162", "42163", "42164", "42165", "42166",
    "42170", "42180", "42222", "42278", "42280", "42297", "42331", "42332",
    "42341", "42342", "42388",
    # —— 页面 §6.1 实测列里的关键短语/数值 ——
    "46/56", "29/56", "21/28", "6/28", "9/9", "7/9", "4/12", "17/27",
    "0.394094", "0.709842", "0.700293", "0.650958", "4.197724e-07", "2.662746e-08",
    "决策区内 8", "破口 10",
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
    except SyntaxError as e:
        return ["⛔ 实现源码解析失败：%s" % e]
    hits = []

    # ⚖ **docstring 不算「手写期望」**（它只是说明文字）⇒ ⇒ 先把 docstring 节点挑出来
    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_nodes.add(id(body[0].value))

    def in_fixture_zone(lineno):
        return bool(fx_start and fx_end and fx_start <= lineno <= fx_end)

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str) \
                    and id(child) not in doc_nodes \
                    and not in_fixture_zone(getattr(child, "lineno", 0)):
                for t in REAL_TOKENS:
                    if t in child.value:
                        hits.append((getattr(child, "lineno", 0), t, child.value[:70]))
            visit(child)

    visit(tree)
    return hits


def parse_keys(out):
    keys = {}
    in_block = False
    for l in out.split("\n"):
        s = l.strip()
        if s == "===== AUDIT_KEYS =====":
            in_block = True
            continue
        if s == "===== END_AUDIT_KEYS =====":
            in_block = False
            continue
        if in_block and "=" in l:
            k, v = l.split("=", 1)
            keys[k.strip()] = v.strip()
    return keys


def prereg_criteria(prereg):
    """⚖ 从预登记 §2 里抽出判据编号（E1…E8）。"""
    out = []
    in_s2 = False
    for l in prereg.split("\n"):
        if l.startswith("## §2 "):
            in_s2 = True
            continue
        if in_s2 and l.startswith("## "):
            break
        if in_s2:
            m = re.match(r"^### (E\d+)\b", l.strip())
            if m and m.group(1) not in out:
                out.append(m.group(1))
    return out


def prereg_mutations(prereg):
    """⚖ 从预登记 §4 的表里抽出变异编号（MU-H1…MU-H10）。"""
    out = []
    in_s4 = False
    for l in prereg.split("\n"):
        if l.startswith("## §4 "):
            in_s4 = True
            continue
        if in_s4 and l.startswith("## "):
            break
        if in_s4:
            m = re.match(r"^\|\s*(MU-[A-Z]+\d+)\s*\|", l)
            if m and m.group(1) not in out:
                out.append(m.group(1))
    return out


def prereg_defect_rows(prereg):
    """⚖ 从预登记 §1.3 的表里抽出「登记为缺陷」的行号。

    ⚖ **性质**列里含「出处缺失」或「量词不符」⇒ ⇒ 算缺陷行；
      「页面补充说明」⇒ ⇒ 登记为**留白**⇒ ⇒ 不算。
    """
    rows = []
    in_s13 = False
    for l in prereg.split("\n"):
        if l.startswith("### §1.3 "):
            in_s13 = True
            continue
        if in_s13 and l.startswith("### "):
            break
        if in_s13 and l.startswith("|"):
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            if len(cells) < 6:
                continue
            pid = cells[1].replace("**", "").strip()
            kind = cells[5]
            if not re.match(r"^P\d+$", pid):
                continue
            if ("出处缺失" in kind) or ("量词不符" in kind):
                if pid not in rows:
                    rows.append(pid)
    return sorted(rows)


def prereg_predicted_red(prereg):
    """⚖ 从预登记 §1.3 里读「改前预期判红」的判据集合（⛔ 不手写）。

    ⚠⚠⚠ **解析不出来 ⇒ 必须判红**（⛔ 不许静默跳过这条检查！）——
      244.96 的第一版就栽在这：正则要求「**E5 红**（…）」同行，
      而预登记是**三行分别**写的 ⇒ ⇒ 解析出空集 ⇒ ⇒ 那条检查被**静默跳过**。
    ⇒ ⇒ 现在改成「扫 §1.3 段里所有 `**E<n> 红**`」，且**空集 ⇒ 判红**。
    """
    in_s13 = False
    got = []
    for l in prereg.split("\n"):
        if l.startswith("### §1.3 "):
            in_s13 = True
            continue
        if in_s13 and l.startswith("### "):
            break
        if in_s13:
            for m in re.finditer(r"\*\*(E\d) 红\*\*", l):
                if m.group(1) not in got:
                    got.append(m.group(1))
    return sorted(got)


def page_rows_by_id(page_text):
    out = {}
    for l in page_text.split("\n"):
        m = re.match(r"^\|\s*\*\*(P\d+)\*\*\s*\|(.*)$", l)
        if m:
            out[m.group(1)] = l
    return out


def main():
    ap = argparse.ArgumentParser(description="244.96 规格对账：预登记 ↔ 实现")
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--checker", required=True)
    ap.add_argument("--bench", required=True)
    ap.add_argument("--page-before", required=True)
    ap.add_argument("--page-after", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--main-before", required=True)
    ap.add_argument("--main-after", required=True)
    args = ap.parse_args()

    prereg = read_text(args.prereg)
    checker = read_text(args.checker)
    bench = read_text(args.bench)
    pb = read_text(args.page_before)
    pa = read_text(args.page_after)
    kb = parse_keys(read_text(args.main_before))
    ka = parse_keys(read_text(args.main_after))

    bad = []

    # ① 判据集合
    pc = prereg_criteria(prereg)
    impl_c = sorted([k[6:] for k in ka if k.startswith("CHECK_E")])
    if pc != impl_c:
        bad.append("① 判据集合：预登记 %s ≠ 实现 %s" % (pc, impl_c))

    # ② 变异集合
    pm = prereg_mutations(prereg)
    bench_m = sorted(set(re.findall(r'"(MU-[A-Z]+\d+)"', bench)))
    missing = [m for m in pm if m not in bench_m]
    extra = [m for m in bench_m if m not in pm]
    if missing:
        bad.append("② 变异集合：预登记里的 %s 在变异台里**没有**" % missing)

    # ③ 缺陷行集合（⛔ 从预登记 §1.3 读，⛔ 不手写）
    want_def = prereg_defect_rows(prereg)
    rb = page_rows_by_id(pb)
    ra = page_rows_by_id(pa)
    real_def = sorted([pid for pid in rb if pid in ra and rb[pid] != ra[pid]])
    if want_def != real_def:
        bad.append("③ 缺陷行集合：预登记登记 %s ≠ 实际有差异的行 %s"
                   % (want_def, real_def))

    # ④ 零手写期望
    hits = scan_real_tokens(checker)
    if hits:
        bad.append("④ 实现源码里出现本轮真值 %d 处（⛔ 「零手写期望」不成立）" % len(hits))

    # ⑤ 手写期望与口径
    m_n = re.search(r"N_PANEL_ROWS\s*=\s*(\d+)", checker)
    m_prereg_n = re.search(r"P 行\*\*恰好 (\d+)", prereg) or re.search(r"恰好 (\d+) 条", prereg)
    if not m_n or not m_prereg_n:
        bad.append("⑤ 读不到 E1 的手写行数（实现 %s / 预登记 %s）" % (bool(m_n), bool(m_prereg_n)))
    elif m_n.group(1) != m_prereg_n.group(1):
        bad.append("⑤ E1 手写行数：实现 %s ≠ 预登记 %s" % (m_n.group(1), m_prereg_n.group(1)))
    for step in ("replace(\"`\", \"\")", "replace(\"**\", \"\")", "re.sub(r\"\\s+\", \"\", s)"):
        if step not in checker:
            bad.append("⑤ 归一化缺一步：%s" % step)
    m_d = re.search(r"R6_DECIMALS\s*=\s*(\d+)", checker)
    if not m_d or m_d.group(1) != "6":
        bad.append("⑤ R6' 的小数位数不等于 6：%s" % (m_d.group(1) if m_d else "读不到"))
    for cite in (":41722", ":39004"):
        if cite not in checker:
            bad.append("⑤ 实现里**没有**引用 R6' 的外部依据 %s" % cite)

    # ⑥ 预登记的预测必须兑现
    want_red = prereg_predicted_red(prereg)
    red_b = sorted([k[6:] for k in kb if k.startswith("CHECK_E") and kb[k] == "FAIL"])
    if not want_red:
        bad.append("⑥ **读不出**预登记 §1.3 的「改前预期判红」⇒ ⇒ 这条检查没法做"
                   " ⇒ ⇒ ⛔ 不许静默跳过 ⇒ ⇒ 判红")
    elif red_b != want_red:
        bad.append("⑥ 改前的判红集合：预登记预测 %s ≠ 实测 %s" % (want_red, red_b))
    red_a = sorted([k[6:] for k in ka if k.startswith("CHECK_E") and ka[k] == "FAIL"])
    if red_a:
        bad.append("⑥ 改后竟然还有判红 %s（形态应 A）" % red_a)

    print("===== AUDIT_KEYS =====")
    print("SPEC_N_CRITERIA=%d" % len(pc))
    print("SPEC_N_MUT=%d" % len(pm))
    print("SPEC_N_DEFECT=%d" % len(want_def))
    print("SPEC_DEFECT_LINES=%s" % want_def)
    print("SPEC_REAL_DEFECT_LINES=%s" % real_def)
    print("SPEC_REAL_TOKEN_HITS=%d" % len(hits))
    print("SPEC_EXPECT_ROWS=%s" % want_def)
    print("SPEC_PREDICTED_RED=%s" % want_red)
    print("SPEC_ACTUAL_RED_BEFORE=%s" % red_b)
    print("SPEC_ACTUAL_RED_AFTER=%s" % red_a)
    print("SPEC_MUT_EXTRA=%s" % extra)
    print("SPEC_RC=%d" % (1 if bad else 0))
    print("===== END_AUDIT_KEYS =====")
    for b in bad:
        print("  ⛔ %s" % b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
