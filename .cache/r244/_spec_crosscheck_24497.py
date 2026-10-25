#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_spec_crosscheck_24497.py —— 预登记 ↔ 实现 的**机械对账**（244.97）。

⚖⚖⚖ **口径真相源**：`.cache/xcheck/R6_DOSE_CURVE_PREREG.md`（含 §8 追加更正）。

⚖⚖⚖ 要对账的**七**件事：
   ① **判据集合**：预登记 §2 登记的 E1–E7 ⇒ ⇒ 被检实现里必须**恰好**是这 7 条（不多不少）。
   ② **变异集合**：预登记 §4 的 MU-C1..MU-C10 **＋** §8.3 的 MU-C11..MU-C14
      ⇒ ⇒ 变异台必须**都**有（⛔ 少一条即红）；多的必须**如实报出来**。
   ③ ⚖⚖⚖ **缺陷集合**：预登记 §1.3 登记为「真缺陷」的那几条（D1/D2）
      ⇒ ⇒ 与「**改前 → 改后**页面 §6.2.2 里实际有差异的 bullet」必须**恰好一致**（不多不少）
      ⇒ ⇒ ⚠ D3 登记为「⛔ **不是缺陷**·留白」⇒ ⇒ **必须被排除**。
   ④ **零手写期望**：被检实现 **和** 互证里（⛔ 注释/docstring/夹具区除外）
      **不许**出现本轮的**真行号**（41327/41418/41426/41431/41513/41648/41656）
      与**压缩式记号**（`pos_frac = 0.25 / 0.50 / 0.75`）⇒ ⇒ 「零手写期望」**机械可查**。
   ⑤ **手写期望与口径**：E1 的手写 bullet 数 == 预登记写的那个数；行数口径必须是
      `count("\\n")`（⛔ 不许 `len(split)`）；E4 的三个 token 必须是**账本逐字形式**；
      §8.1 的「别的小节作用域」豁免必须在实现里**真的存在**。
   ⑥ ⚖⚖⚖ **预登记的预测必须兑现**：预登记末尾写「改前预期判红 `['E3','E4']`」
      ⇒ ⇒ 「改前」那份收据里的判红集合必须**恰好**是 {E3, E4}
      ⇒ ⇒ 「改后」必须**一条不红**（形态 A）。
      ⇒ ⚠ **解析不出来 ⇒ 必须判红**（⛔ 不许静默跳过这条检查！）。
   ⑦ ⚖ **「如实登记」这条路径本身要被守住**：§8.2 登记的 MU-C6「预登记期望 ≠ 实测」
      ⇒ ⇒ 变异台收据里的 `MUT_PREREG_MISMATCH` 必须**恰好 1**（且就是 MU-C6）
      ⇒ ⇒ 否则「不符被如实登记」这件事**没被守住**（要么被藏了，要么多出了别的）。
"""

import argparse
import ast
import io
import os
import re
import sys

# ⚖⚖⚖ **本轮的真值 / 真行号**（真页面 §6.2.2 引用到的账本行）⇒ ⇒ 实现里**不许**出现它们
REAL_TOKENS = [
    "41327", "41418", "41426", "41431", "41513", "41648", "41656",
    "pos_frac = 0.25 / 0.50 / 0.75",
]


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def fixture_ranges(src):
    """⚖ 被检实现里「合成夹具」那一段的**代码区间**（⛔ 不靠注释里的巧合）。

    ⚖ 口径：**按 AST 取函数区间** —— 名字是 `selftest` 或以 `_fixture` 开头的函数
    ⇒ ⇒ 合成值只可能出现在这些函数里（⛔ 模块级常量里没有合成值）。
    ⚖ ⚠ 这比「找注释里的『合成夹具』再取到下一个 `def `」更严：
      244.97 的第一版用后者 ⇒ ⇒ 区间只剩 2 行 ⇒ ⇒ 夹具里的压缩式记号被误判成「真值」。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name == "selftest" or node.name.startswith("_fixture"):
                ranges.append((node.lineno, node.end_lineno))
    return ranges


def scan_real_tokens(src):
    """⚖ AST 级扫描：**代码**里（⛔ 注释/docstring/夹具区除外）有没有本轮的真值。"""
    fx = fixture_ranges(src)
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return ["⛔ 源码解析失败：%s" % e]
    hits = []

    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_nodes.add(id(body[0].value))

    def in_fixture_zone(lineno):
        return any(a <= lineno <= b for (a, b) in fx)

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str) \
                    and id(child.value) not in doc_nodes \
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
    """⚖ 从预登记 §2 里抽出判据编号（E1…E7）（⛔ 不手写）。"""
    out = []
    in_s2 = False
    for l in prereg.split("\n"):
        if l.startswith("## §2 "):
            in_s2 = True
            continue
        if in_s2 and l.startswith("## "):
            break
        if in_s2:
            m = re.match(r"^-\s*\[PASS\]\s*\*\*(E\d+)\b", l.strip())
            if m and m.group(1) not in out:
                out.append(m.group(1))
    return out


def prereg_mutations(prereg):
    """⚖ 从预登记 §4 **与** §8.3 的表里抽出变异编号（MU-C1…MU-C14）。"""
    out = []
    in_tab = False
    for l in prereg.split("\n"):
        if l.startswith("## §4 ") or l.startswith("### §8.3 "):
            in_tab = True
            continue
        if in_tab and (l.startswith("## ") or l.startswith("### ")):
            in_tab = False
            continue
        if in_tab and l.startswith("|"):
            cells = [c.strip().replace("**", "") for c in l.strip().strip("|").split("|")]
            m = re.match(r"^(MU-[A-Z]+\d+)$", cells[0])
            if m and m.group(1) not in out:
                out.append(m.group(1))
    return out


def prereg_defect_bullets(prereg):
    """⚖ 从预登记 §1.3 里抽出「登记为**真缺陷**」的 bullet（⛔ 不手写）。

    ⚖ **D3（⛔ 不是缺陷 · 明确留白）必须被排除** ⇒ ⇒ 只认形如 `**D<n>（B<n> ...）**`
    的标题行（⛔ 「不是缺陷」的那条的标题里**没有** `B<n>`）。
    """
    out = []
    in_s13 = False
    for l in prereg.split("\n"):
        if l.startswith("### §1.3 "):
            in_s13 = True
            continue
        if in_s13 and l.startswith("### "):
            break
        if in_s13:
            m = re.match(r"^\*\*(D\d+)（(B\d+)\s*[·・]", l.strip())
            if m and m.group(2) not in out:
                out.append(m.group(2))
    return sorted(out)


def prereg_predicted_red(prereg):
    """⚖ 从预登记**末尾**读「改前预期判红」的判据集合（⛔ 不手写）。

    ⚠⚠⚠ **解析不出来 ⇒ 必须判红**（⛔ 不许静默跳过这条检查！）。
    """
    for l in prereg.split("\n"):
        if l.startswith("⚖ 改前**预期判红**："):
            m = re.search(r"\[([^\]]*)\]", l)
            if not m:
                return []
            got = []
            for e in re.findall(r"E\d+", m.group(1)):
                if e not in got:
                    got.append(e)
            return sorted(got)
    return []


def page_bullets(page_text):
    """⚖ 取 §6.2.2 的 bullet 列表（按顺序）。"""
    lines = page_text.split("\n")
    start = None
    for i, l in enumerate(lines):
        if l.startswith("### 6.2.2"):
            start = i
            break
    if start is None:
        return []
    out = []
    for l in lines[start + 1:]:
        if l.startswith("### "):
            break
        m = re.match(r"^\s*[-*•]\s+(\S.*\S)\s*$", l)
        if m:
            out.append(m.group(1))
    return out


def main():
    ap = argparse.ArgumentParser(description="244.97 规格对账：预登记 ↔ 实现")
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--checker", required=True)
    ap.add_argument("--bench", required=True)
    ap.add_argument("--cross", required=True)
    ap.add_argument("--mut-out", required=True, help="变异台的输出收据")
    ap.add_argument("--page-before", required=True)
    ap.add_argument("--page-after", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--main-before", required=True)
    ap.add_argument("--main-after", required=True)
    args = ap.parse_args()

    prereg = read_text(args.prereg)
    checker = read_text(args.checker)
    bench = read_text(args.bench)
    cross = read_text(args.cross)
    pb = read_text(args.page_before)
    pa = read_text(args.page_after)
    kb = parse_keys(read_text(args.main_before))
    ka = parse_keys(read_text(args.main_after))
    km = parse_keys(read_text(args.mut_out))

    bad = []

    # ① 判据集合
    pc = prereg_criteria(prereg)
    impl_c = sorted([k[6:] for k in ka if k.startswith("CHECK_E")])
    if pc != impl_c:
        bad.append("① 判据集合：预登记 %s ≠ 实现 %s" % (pc, impl_c))
    if len(pc) != 7:
        bad.append("① 预登记 §2 的判据条数应为 7，实为 %d" % len(pc))

    # ② 变异集合（§4 ＋ §8.3）
    pm = prereg_mutations(prereg)
    bench_m = sorted(set(re.findall(r'"(MU-[A-Z]+\d+)"', bench)))
    missing = [m for m in pm if m not in bench_m]
    extra = [m for m in bench_m if m not in pm]
    if missing:
        bad.append("② 变异集合：预登记里的 %s 在变异台里**没有**" % missing)
    if extra:
        bad.append("② 变异集合：变异台多出 %s（⛔ 预登记没登记）" % extra)
    if len(pm) != 14:
        bad.append("② 预登记登记的变异条数应为 14（§4 的 10 ＋ §8.3 的 4），实为 %d" % len(pm))

    # ③ 缺陷集合（⛔ 从预登记 §1.3 读，⛔ 不手写）
    want_def = prereg_defect_bullets(prereg)
    bb = page_bullets(pb)
    ba = page_bullets(pa)
    real_def = []
    for i in range(min(len(bb), len(ba))):
        if bb[i] != ba[i]:
            real_def.append("B%d" % (i + 1))
    if len(bb) != len(ba):
        bad.append("③ 改前 bullet 数 %d ≠ 改后 %d（⇒ ⇒ 缺陷集合没法比）" % (len(bb), len(ba)))
    if want_def != sorted(real_def):
        bad.append("③ 缺陷集合：预登记登记 %s ≠ 实际有差异的 bullet %s"
                   % (want_def, sorted(real_def)))
    if "B3" in want_def and "D3" in prereg and "不是缺陷" in prereg:
        pass                                   # D3 是**留白**，⛔ 不算缺陷 ⇒ 上面已排除

    # ④ 零手写期望（实现 **和** 互证）
    hits = scan_real_tokens(checker)
    if hits:
        bad.append("④ 实现源码里出现本轮真值 %d 处（⛔ 「零手写期望」不成立）" % len(hits))
    hits_x = scan_real_tokens(cross)
    if hits_x:
        bad.append("④ 互证源码里出现本轮真值 %d 处（⛔ 「零手写期望」不成立）" % len(hits_x))

    # ⑤ 手写期望与口径
    m_n = re.search(r"N_BULLETS\s*=\s*(\d+)", checker)
    m_prereg_n = re.search(r"恰好\s*(\d+)\s*个\s*bullet", prereg)
    if not m_n or not m_prereg_n:
        bad.append("⑤ 读不到 E1 的手写 bullet 数（实现 %s / 预登记 %s）"
                   % (bool(m_n), bool(m_prereg_n)))
    elif m_n.group(1) != m_prereg_n.group(1):
        bad.append("⑤ E1 手写 bullet 数：实现 %s ≠ 预登记 %s" % (m_n.group(1), m_prereg_n.group(1)))
    if 'count("\\n")' not in checker:
        bad.append("⑤ 实现里找不到行数口径 count(\"\\n\")")
    if "len(lines)" in checker and "count(\"\\n\")" not in checker:
        bad.append("⑤ 行数口径用了 len(split) ⇒ ⇒ 会多 1")
    for tok in ("`pos_frac=0.25`", "`pos_frac=0.50`", "`pos_frac=0.75`"):
        if tok not in checker:
            bad.append("⑤ 实现里没有账本逐字形式的断言 token %s" % tok)
    if "in_other_section_paren" not in checker:
        bad.append("⑤ 实现里找不到 §8.1 的「别的小节作用域」豁免函数")
    if "SECNUM_RE" not in checker:
        bad.append("⑤ 实现里找不到小节号的识别（SECNUM_RE）")

    # ⑥ 预登记的预测必须兑现
    want_red = prereg_predicted_red(prereg)
    red_b = sorted([k[6:] for k in kb if k.startswith("CHECK_E") and kb[k] == "FAIL"])
    if not want_red:
        bad.append("⑥ **读不出**预登记末尾的「改前预期判红」⇒ ⇒ 这条检查没法做"
                   " ⇒ ⇒ ⛔ 不许静默跳过 ⇒ ⇒ 判红")
    elif red_b != want_red:
        bad.append("⑥ 改前的判红集合：预登记预测 %s ≠ 实测 %s" % (want_red, red_b))
    red_a = sorted([k[6:] for k in ka if k.startswith("CHECK_E") and ka[k] == "FAIL"])
    if red_a:
        bad.append("⑥ 改后竟然还有判红 %s（形态应 A）" % red_a)

    # ⑦ 「如实登记」这条路径本身要被守住
    n_mis = int(km.get("MUT_PREREG_MISMATCH", "-1"))
    if n_mis != 1:
        bad.append("⑦ 变异台的 MUT_PREREG_MISMATCH 应恰好 1（§8.2 登记的 MU-C6），实为 %s" % n_mis)
    mut_txt = read_text(args.mut_out)
    if "MU-C6" not in mut_txt or "预登记期望红闸门" not in mut_txt:
        bad.append("⑦ 变异台的收据里**看不到** MU-C6 的「预登记期望 ≠ 实测」登记")
    if int(km.get("MUT_SURVIVORS", "-1")) != 0:
        bad.append("⑦ 变异台有存活（%s）⇒ ⇒ 每条判据都得能红" % km.get("MUT_SURVIVORS"))
    if int(km.get("MUT_CRASHED", "-1")) != 0:
        bad.append("⑦ 变异台有崩（%s）" % km.get("MUT_CRASHED"))
    if int(km.get("MUT_N", "-1")) != len(pm):
        bad.append("⑦ 变异台的条数 %s ≠ 预登记登记的 %d" % (km.get("MUT_N"), len(pm)))

    print("===== AUDIT_KEYS =====")
    print("SPEC_N_CRITERIA=%d" % len(pc))
    print("SPEC_N_MUT=%d" % len(pm))
    print("SPEC_N_DEFECT=%d" % len(want_def))
    print("SPEC_DEFECT_BULLETS=%s" % want_def)
    print("SPEC_REAL_DEFECT_BULLETS=%s" % sorted(real_def))
    print("SPEC_REAL_TOKEN_HITS=%d" % len(hits))
    print("SPEC_REAL_TOKEN_HITS_CROSS=%d" % len(hits_x))
    print("SPEC_EXPECT_BULLETS=%s" % (m_prereg_n.group(1) if m_prereg_n else "?"))
    print("SPEC_PREDICTED_RED=%s" % want_red)
    print("SPEC_ACTUAL_RED_BEFORE=%s" % red_b)
    print("SPEC_ACTUAL_RED_AFTER=%s" % red_a)
    print("SPEC_MUT_EXTRA=%s" % extra)
    print("SPEC_MUT_MISMATCH=%d" % n_mis)
    print("SPEC_RC=%d" % (1 if bad else 0))
    print("===== END_AUDIT_KEYS =====")
    for b in bad:
        print("  ⛔ %s" % b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
