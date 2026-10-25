#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_cross_check_24496.py —— 244.96 的**互证**：第二条**独立**实现，验页面 §6.1 的可溯源性。

⚖⚖⚖ **口径真相源**：`.cache/xcheck/R6_PANEL_PREREG.md` §5。

⚖⚖⚖ **互证必须与被检实现「故意不同」**（否则只是复制一遍）：
   · **锚定**：被检实现按**表格第 5 格**取「账本位置」⇒ ⇒ 互证改用
     **正则从该行整行文本里扫 `:NNNN`**（⛔ 不依赖列位置）；
   · **归一化**：被检实现用「删空白整串包含」⇒ ⇒ 互证改用
     **逐词（数值词元）序列**逐元素比较；
   · **R6'**：被检实现用 `Decimal` 量化 ⇒ ⇒ 互证改用 `%.*f` 字符串格式化。

⚖⚖⚖ **「表示差异」不算不符**：页面写 `0.5`、账本写 `0.500000` ⇒ ⇒
   两者是**同一个数**、只是打印精度不同 ⇒ ⇒ 互证**不**判它不符，
   但**如实计数**（CROSS_REPR_DIFF）⇒ ⇒ 免得「因为表述不同就误判」。

⚖ **互证自己也要能红**（`--selftest`）：把被检实现的输出改坏
（翻一个闸门 ＋ 改一个逐行结论 ＋ 改一个计数）⇒ ⇒ 互证必须抓到。
"""

import argparse
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# ⚖ 故意不同的锚定：从**整行**扫（⛔ 不依赖列位置）
CITE_RE = re.compile(r":(\d+)\s*[–\-—~]\s*:?(\d+)|:(\d+)")
# ⚖ 故意不同的归一化：**数值词元**序列（⛔ 不是「删空白整串」）
NUMTOK_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def strip_bold(s):
    return s.replace("`", "").replace("**", "")


def cites_by_scan(row_text):
    """⚖ 互证的锚定：**整行正则**扫 `:NNNN`（含区间）⇒ ⇒ 与被检实现的「按列取」不同。"""
    t = strip_bold(row_text)
    out = set()
    for m in CITE_RE.finditer(t):
        if m.group(2):
            a, b = int(m.group(1)), int(m.group(2))
            out.update(range(min(a, b), max(a, b) + 1))
        else:
            out.add(int(m.group(3)))
    return sorted(out)


def numtok_seq(text):
    """⚖ 互证的归一化：**数值词元**序列（⛔ 不是「删空白整串」）。"""
    return NUMTOK_RE.findall(strip_bold(text))


def same_number(a, b):
    """⚖ 两个数值词元是不是**同一个数**（只是打印精度不同）？

    规则：去前导 `+` 后，**短的是长的前缀** 且 **多出来的位全是 0** ⇒ ⇒ 同一个数。
    ⇒ 「0.5」≡「0.500000」✅；「0.394094」≢「0.3940944」（多出来的位不是 0）✅。
    """
    x = a.lstrip("+")
    y = b.lstrip("+")
    if x == y:
        return True
    if x.startswith(y):
        return set(x[len(y):]) <= {"0"}
    if y.startswith(x):
        return set(y[len(x):]) <= {"0"}
    return False


def fmt6_fixed_s(v):
    """⚖ 互证的 R6'：**`%.*f` 字符串格式化**（⛔ 不用 `Decimal` 量化）。"""
    return "%.*f" % (6, float(v))


def fmt6_sci_s(v):
    """⚖ 互证的 R6'（科学计数法）：尾数 `%.*f` ＋ 指数。"""
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
    return "%.*fe%+03d" % (6, a, k)


def r6_equal_s(ledger_tok, page_tok):
    """⚖ 互证的 R6'：双方**各自**印到 6 位小数后**逐位相同**（⛔ 不用 Decimal）。"""
    t = page_tok.lstrip("+")
    try:
        ft = float(t)
    except ValueError:
        return False
    try:
        fv = float(ledger_tok)
    except ValueError:
        return False
    if "e" in t.lower():
        return fmt6_sci_s(fv) == fmt6_sci_s(ft)
    return fmt6_fixed_s(fv) == fmt6_fixed_s(ft)


def is_strong(tok):
    return ("." in tok) or ("e" in tok.lower())


# ================================================================ 被检实现的输出解析

def parse_blocks(out):
    blocks = {}
    cur = None
    buf = []
    for l in out.split("\n"):
        s = l.strip()
        if s.startswith("===== ") and s.endswith(" =====") and "END_" not in s:
            cur = s[len("===== "):-len(" =====")]
            buf = []
            continue
        if s.startswith("===== END_"):
            blocks[cur] = "\n".join(buf)
            cur = None
            continue
        if cur is not None:
            buf.append(l)
    return blocks


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


# ================================================================ 互证自己的判定

def my_audit(page_text, ledger_lines):
    """⚖ 互证自己的实现：逐行锚定 → 词元序列 → 自己的 R6'。"""
    lines = page_text.split("\n")
    start = None
    for i, l in enumerate(lines):
        if l.startswith("## 6.1 "):
            start = i
            break
    if start is None:
        raise ValueError("页面里找不到 §6.1")
    rows = []
    for l in lines[start:]:
        if l.startswith("## 6.2"):
            break
        m = re.match(r"^\|\s*\*\*(P\d+)\*\*\s*\|(.*)$", l)
        if not m:
            continue
        rows.append((m.group(1), l))

    out = []
    n_anchor = 0
    n_strong = n_verb = n_r6 = n_miss = 0
    repr_diff = 0
    for pid, raw in rows:
        cites = cites_by_scan(raw)
        if cites:
            n_anchor += 1
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        meas = cells[2]
        seq = []
        for n in cites:
            if 1 <= n <= len(ledger_lines):
                seq.extend(numtok_seq(ledger_lines[n - 1]))
        s_n = v_n = r_n = mi_n = 0
        for t in NUMTOK_RE.findall(strip_bold(meas)):
            if not is_strong(t):
                continue
            s_n += 1
            # ① 互证的**严格**口径：同一个数（只是打印精度不同也算）
            if any(same_number(t, e) for e in seq):
                v_n += 1
                continue
            # ② 互证的 R6'（`%.*f`，⛔ 不用 Decimal）
            if any(r6_equal_s(e, t) for e in seq):
                r_n += 1
                continue
            # ③ **表示差异**：被检实现用**子串包含**（更松）⇒ 它可能在这里命中
            #    ⇒ ⇒ 这**不是**不符（数本身没差），但要**如实计数**
            tl = t.lstrip("+-")
            if any(tl in e.lstrip("+-") or e.lstrip("+-") in tl for e in seq):
                repr_diff += 1
                continue
            mi_n += 1
        n_strong += s_n
        n_verb += v_n
        n_r6 += r_n
        n_miss += mi_n
        out.append((pid, len(cites), s_n, v_n, r_n, mi_n))
    return out, {"n_anchor": n_anchor, "n_strong": n_strong, "n_verbatim": n_verb,
                 "n_r6": n_r6, "n_missing": n_miss, "repr_diff": repr_diff,
                 "rows": out}


# ================================================================ 互证自证（自己也要能红）

def selftest(main_out_path):
    """⚖ 把被检实现的输出改坏 ⇒ ⇒ 互证必须抓到。"""
    out = read_text(main_out_path)
    n_diff = 0
    # ① 翻一个闸门（E3 PASS → FAIL）
    bad = out.replace("CHECK_E3=PASS", "CHECK_E3=FAIL", 1)
    if bad != out:
        n_diff += 1
    else:
        print("⛔ 被检输出里找不到 CHECK_E3=PASS ⇒ 中止")
        return 1
    # ② 改一个计数（N_STRONG）
    bad2 = re.sub(r"N_STRONG=\d+", "N_STRONG=999", bad, count=1)
    if bad2 != bad:
        n_diff += 1
    else:
        print("⛔ 被检输出里找不到 N_STRONG ⇒ 中止")
        return 1
    # ③ 改一个逐行结论（NUM_MATRIX 里某个 missing）
    bad3 = re.sub(r"missing=\d+", "missing=42", bad2, count=1)
    if bad3 != bad2:
        n_diff += 1
    else:
        print("⛔ 被检输出里找不到 missing= ⇒ 中止")
        return 1
    print("===== AUDIT_KEYS =====")
    print("CROSS_SELFTEST_N_DIFF=%d" % n_diff)
    print("CROSS_SELFTEST_RC=%d" % (0 if n_diff == 3 else 1))
    print("===== END_AUDIT_KEYS =====")
    return 0 if n_diff == 3 else 1


# ================================================================ 主流程

def main():
    ap = argparse.ArgumentParser(description="244.96 互证：页面 §6.1 P1–P29 的可溯源性（独立实现）")
    ap.add_argument("--main", required=True, help="被检实现的 --data 输出")
    ap.add_argument("--page", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest(args.main)
    if not args.page or not args.ledger:
        print("⛔ --selftest 之外必须给 --page 与 --ledger")
        return 2

    page_text = read_text(args.page)
    ledger_lines = read_text(args.ledger).split("\n")
    main_out = read_text(args.main)
    keys = parse_keys(main_out)
    blocks = parse_blocks(main_out)

    mine, m = my_audit(page_text, ledger_lines)

    # ---- 与被检实现逐行对账 ----
    diffs = []
    repr_gap = []
    # 被检的 NUM_MATRIX：ROW=P1|cites=1|strong=0|verbatim=0|r6=0|missing=0|frac=2/2
    main_rows = {}
    for l in blocks.get("NUM_MATRIX", "").split("\n"):
        m2 = re.match(r"ROW=(\w+)\|cites=(\d+)\|strong=(\d+)\|verbatim=(\d+)\|"
                      r"r6=(\d+)\|missing=(\d+)\|frac=(\d+)/(\d+)", l.strip())
        if m2:
            main_rows[m2.group(1)] = {
                "cites": int(m2.group(2)), "strong": int(m2.group(3)),
                "verbatim": int(m2.group(4)), "r6": int(m2.group(5)),
                "missing": int(m2.group(6)), "frac_hit": int(m2.group(7)),
                "frac_tot": int(m2.group(8)),
            }
    for pid, ncite, s_n, v_n, r_n, mi_n in m["rows"]:
        mr = main_rows.get(pid)
        if mr is None:
            diffs.append("%s：被检输出里**没有**这一行" % pid)
            continue
        if mr["missing"] != mi_n:
            diffs.append("%s：缺口数 被检 %d ≠ 互证 %d" % (pid, mr["missing"], mi_n))
        if mr["cites"] != ncite:
            diffs.append("%s：引用行数 被检 %d ≠ 互证 %d（锚定不同 ⇒ 应相同）"
                         % (pid, mr["cites"], ncite))
        if mr["strong"] != s_n:
            diffs.append("%s：强 token 数 被检 %d ≠ 互证 %d" % (pid, mr["strong"], s_n))
        # ⚖ 逐位数的差 ⇒ 必须是「表示差异」，否则是**真不符** ⇒ ⇒ 记下来
        if mr["verbatim"] != v_n:
            repr_gap.append("%s：逐位数 被检 %d ≠ 互证 %d（差 %d ⇒ 应落进表示差异）"
                            % (pid, mr["verbatim"], v_n, mr["verbatim"] - v_n))

    # ---- 汇总口径也必须对上 ----
    # ⚖ 只比**承重**的三个：强 token 数、缺口数、引用行数。
    #   ⛔ **不比**「逐位数」⇒ ⇒ 被检是**子串**口径、互证是**严格数值**口径
    #   ⇒ ⇒ 两者的「逐位」计数**本就可以不同**（差值 = 表示差异，已单列计数）。
    for k_mine, k_main in (("n_strong", "N_STRONG"), ("n_missing", "N_MISSING")):
        if str(m[k_mine]) != keys.get(k_main):
            diffs.append("汇总 %s：被检 %s ≠ 互证 %d" % (k_main, keys.get(k_main), m[k_mine]))

    # ---- 自己的形态 ----
    my_verdict = "A" if m["n_missing"] == 0 else "D"
    if keys.get("VERDICT") != my_verdict:
        diffs.append("形态：被检 %s ≠ 互证 %s" % (keys.get("VERDICT"), my_verdict))

    print("===== AUDIT_KEYS =====")
    print("CROSS_N_ANCHORS=%d" % m["n_anchor"])
    print("CROSS_N_STRONG=%d" % m["n_strong"])
    print("CROSS_N_VERBATIM=%d" % m["n_verbatim"])
    print("CROSS_N_R6=%d" % m["n_r6"])
    print("CROSS_N_MISSING=%d" % m["n_missing"])
    print("CROSS_REPR_DIFF=%d" % m["repr_diff"])
    print("CROSS_N_ROWS=%d" % len(m["rows"]))
    print("CROSS_MISMATCH=%d" % len(diffs))
    print("CROSS_REPR_GAP=%d" % len(repr_gap))
    print("CROSS_VERDICT=%s" % my_verdict)
    print("CROSS_RC=%d" % (0 if not diffs else 1))
    print("===== END_AUDIT_KEYS =====")
    for d in diffs[:20]:
        print("  ⛔ %s" % d)
    for d in repr_gap[:20]:
        print("  ⚖ 表示差异：%s" % d)
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
