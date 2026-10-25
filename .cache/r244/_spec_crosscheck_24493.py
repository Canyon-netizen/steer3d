#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_spec_crosscheck_24493.py —— 预登记 ↔ 实现 对账（244.93）。

⚖ 要对账的四件事（预登记 §2.3 / §2.4 / §4）：
   ① **判据集合**：预登记 §2.3 登记的 D1–D4 ⇒ ⇒ 被检实现里必须**恰好**是这 4 条（不多不少）。
   ② **变异集合**：预登记 §4 登记的 MU-D1..MU-D8 ⇒ ⇒ 变异台必须**都**有（⛔ 少一条即红）。
   ③ **锚点出处**：预登记 §2.4 登记的 5 行出处 ⇒ ⇒ 页面上的实际出处**必须**只与登记差在
      **显式声明的偏差**里（`--expect-deviation 4:+38198` 这样的形式）⇒ ⇒ 任何**未声明**的改动即红。
   ④ **零手写期望**（预登记 §2.2 的核心设计）：被检实现的源码里**不许**出现本轮的真值/真行号
      ⇒ ⇒ 「期望从页面行自动派生」这件事是**机械可查**的，不靠自觉。

⚖ **用法**（远端）：
   python3 _spec_crosscheck_24493.py --prereg … --checker … --bench … --page … --expect-deviation 4:+38198
"""

import argparse
import ast
import io
import os
import re
import sys

# ⚖⚖⚖ **本轮的真值/真行号**（真页面 §6.2.3 里出现过的东西）⇒ ⇒ 实现里**不许**出现它们
REAL_TOKENS = [
    "0.015", "0.250", "0.750", "0.691", "0.685", "0.0878", "0.0488",
    "27/28/30/24", "28/27/30/24", "11/16/23/24",
    "109", "244.51", "244.62",
    "36747", "36751", "37545", "37988", "38191", "38192", "38193",
    "38195", "38198", "38269", "38363", "38406", "38413", "40281", "40404",
]


REAL_NUMBERS = [109.0, 0.015, 0.25, 0.75, 0.691, 0.685, 0.0878, 0.0488, 244.51, 244.62]


def fixture_range(src_lines):
    """⚖ 被检实现里「合成夹具」那一段的行区间（⛔ 该区**必然**含真实行文 ⇒ 不计入「手写期望」）。"""
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
    """⚖ AST 级扫描：**代码**里（⛔ 注释/docstring/夹具区除外）有没有本轮的真值 ⇒ ⇒ 「零手写期望」。"""
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
        if isinstance(node, ast.Constant):
            val = node.value
            if isinstance(val, str):
                if id(node) in doc_ids:
                    continue
                for tok in REAL_TOKENS:
                    if re.search(r"(?<![\w.])%s(?![\w.])" % re.escape(tok), val):
                        hits.append("%s@L%d" % (tok, node.lineno))
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                for tok in REAL_NUMBERS:
                    if abs(float(val) - tok) < 1e-12:
                        hits.append("%s@L%d" % (tok, node.lineno))
    return hits


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def expand_cites(cell):
    """⚖ 取引用行号 ⇒ ⇒ **区间要展开**（`:38191`–`:38193` ⇒ 38191/38192/38193）。"""
    hits = [(m.start(), m.end(), int(m.group(1)))
            for m in re.finditer(r":(\d{1,6})", cell)]
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


def parse_prereg_criteria(prereg):
    """⚖ 预登记 §2.3 登记的判据 id（形如 `**D1 ·`）。"""
    return sorted(set(re.findall(r"\*\*(D\d) ·", prereg)))


def parse_prereg_mutations(prereg):
    """⚖ 预登记 §4 登记的变异 id（表格首列）。"""
    return sorted(set(re.findall(r"^\| (MU-D\d+) \|", prereg, re.M)))


def parse_prereg_anchors(prereg):
    """⚖ 预登记 §2.4 的锚点表 ⇒ ⇒ [(行号, 标签, [引用行号])]。"""
    out = []
    for m in re.finditer(r"^\| (\d+) \| (.+?) \| (.+?) \|$", prereg, re.M):
        idx, label, cites = m.group(1), m.group(2).strip(), m.group(3)
        lines = expand_cites(cites)
        out.append((int(idx), label, lines))
    return out


def parse_bench_mutations(bench_src):
    """⚖ 变异台源码里声明的变异 id。"""
    return sorted(set(re.findall(r'\("(MU-[A-Z]\d+)"', bench_src)))


def parse_page_anchor_cites(page_text):
    """⚖ 页面展品表里每行的（标签 ⇒ 引用行号集合）。"""
    lines = page_text.split("\n")
    out = {}
    for l in lines:
        s = l.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("展品",) or set(s) <= set("|-: "):
            continue
        cites = expand_cites(cells[2])
        out[cells[0]] = cites
    return out


def parse_deviation(spec):
    """⚖ `--expect-deviation 4:+38198` ⇒ ⇒ {行号: [新增行号]}。"""
    out = {}
    if not spec:
        return out
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+):\+(.+)$", part)
        if not m:
            raise SystemExit("⛔ 偏差声明格式错（应为 行号:+行号,行号）：%s" % part)
        out[int(m.group(1))] = sorted(int(x) for x in m.group(2).split("+"))
    return out


def main():
    ap = argparse.ArgumentParser(description="244.93 预登记 ↔ 实现 对账")
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--checker", required=True)
    ap.add_argument("--bench", required=True)
    ap.add_argument("--page", required=True)
    ap.add_argument("--main-out", required=True, help="被检实现的 --data 输出（AUDIT_KEYS）")
    ap.add_argument("--expect-deviation", default="",
                    help="显式声明的偏差，形如 4:+38198（⛔ 未登记的改动即红）")
    a = ap.parse_args()

    prereg = read_text(a.prereg)
    checker = read_text(a.checker)
    bench = read_text(a.bench)
    page = read_text(a.page)
    main_out = read_text(a.main_out)

    bad = []
    detail = []

    # ---- ① 判据集合 ----
    pc = parse_prereg_criteria(prereg)
    got_checks = sorted(set(re.findall(r"^CHECK_(D\d)=", main_out, re.M)))
    if pc != ["D1", "D2", "D3", "D4"]:
        bad.append("预登记 §2.3 登记的判据不是 D1–D4（实得 %s）" % pc)
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
                      % (len(pm), ("；额外 %s（实现期新增，非预登记）" % extra) if extra else ""))

    # ---- ③ 锚点出处偏差 ----
    anchors = parse_prereg_anchors(prereg)
    page_cites = parse_page_anchor_cites(page)
    expect_dev = parse_deviation(a.expect_deviation)
    seen_dev = {}
    for idx, label, plines in anchors:
        if label not in page_cites:
            bad.append("预登记 §2.4 第 %d 行（标签 %s）在页面上**定位不到**" % (idx, label))
            continue
        actual = page_cites[label]
        extra = sorted(set(actual) - set(plines))
        missing_l = sorted(set(plines) - set(actual))
        if missing_l:
            bad.append("第 %d 行（%s）：页面**少了**登记的引用 %s" % (idx, label, missing_l))
        if extra:
            seen_dev[idx] = extra
    for idx, extra in sorted(seen_dev.items()):
        want = expect_dev.get(idx, [])
        if extra != want:
            bad.append("第 %d 行：页面新增引用 %s ≠ 显式声明的 %s" % (idx, extra, want or "（无声明）"))
        else:
            detail.append("第 %d 行：新增引用 %s（已显式声明）" % (idx, extra))
    for idx in expect_dev:
        if idx not in seen_dev:
            bad.append("第 %d 行：声明了偏差 %s，但页面上**没有**该偏差" % (idx, expect_dev[idx]))

    # ---- ④ 零手写期望 ----
    hits = scan_real_tokens(checker)
    if hits:
        bad.append("被检实现的**代码**里出现了本轮的**真值/真行号** %s ⇒ ⇒ 期望不是派生的"
                   % hits[:6])
    else:
        detail.append("被检实现的**代码**里（⛔ 注释/docstring/夹具区除外）**不含**任何本轮真值"
                      "（零手写期望，机械可查）")

    print("=" * 70)
    for d in detail:
        print("  · %s" % d)
    print("")
    print("===== AUDIT_KEYS =====")
    print("SPEC_N_CRITERIA=%d" % len(pc))
    print("SPEC_N_MUT=%d" % len(pm))
    print("SPEC_N_ANCHORS=%d" % len(anchors))
    print("SPEC_N_DEVIATION=%d" % len(seen_dev))
    print("SPEC_REAL_TOKEN_HITS=%d" % len(hits))
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
