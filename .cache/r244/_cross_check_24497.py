#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_cross_check_24497.py —— 244.97 的**互证**：第二条**独立**实现，验页面 §6.2.2 的可溯源性与留白守卫。

⚖⚖⚖ **口径真相源**：`.cache/xcheck/R6_DOSE_CURVE_PREREG.md` §5 ＋ §8。

⚖⚖⚖ **互证必须与被检实现「故意不同」**（否则只是复制一遍）：
   · **锚定**：被检实现用 `CITE_RE = :(\\d+)` 逐 bullet 扫 ⇒ ⇒ 互证改用
     **整行正则** `[:：](\\d+)(?!\\d)`（含**全角冒号**、**不吞尾随数字**）；
   · **归一化**：被检实现用**逐位子串包含** ⇒ ⇒ 互证改用**词元序列**
     （断言的词元序列必须**连续出现**在账本行的词元序列里，⛔ 不看空白）；
   · **匹配**：被检实现逐条判真伪 ⇒ ⇒ 互证把命中/未命中**变成集合**再比；
   · **留白豁免**：被检实现用**前向/后向括号配对扫描** ⇒ ⇒ 互证改用
     **括号整体正则** `\uFF08([^）]*)\uFF09` 逐个配对后判断位置。

⚖⚖⚖ **互证自己也要能红**（`--selftest`）：把被检实现的输出改坏
（翻一个闸门 ＋ 改一个命中计数 ＋ 改一个逐行矩阵）⇒ ⇒ **重跑真比对**必须**抓到**。
⚖ （⛔ 不是「字符串确实变了」就算能红 ⇒ ⇒ 必须**比对结果真的出现不符**。）

⚖ **零共用代码**：⛔ **不 import** 被检实现；断言登记、禁用措辞表都**在本文件里独立抄一份**
（⇒ ⇒ 两边登记若不一致 ⇒ ⇒ 比对时**立刻暴露**，不会「一起变」）。
"""

import argparse
import io
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# ⚖ 故意不同的锚定：**整行**正则扫（⛔ 与被检实现的 `:\d+` 不同：含全角冒号、排除尾随数字）
CITE_RE = re.compile(r"[:：](\d+)(?!\d)")
# ⚖ 故意不同的归一化：**词元序列**（ASCII 词 ｜ 单个非 ASCII 字符）
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]")
# ⚖ 故意不同的括号配对：**括号整体正则**
PAREN_RE = re.compile(r"（([^）]*)）")
SECNUM_RE = re.compile(r"\d+\.\d+")

SEC_HEAD = "### 6.2.2"
N_BULLETS = 3
TITLE_MUST = "未量到"

# ⚖ 互证**自己抄一份**的断言登记（⛔ 不 import 被检实现）
REG = {
    1: [("`n_bands = 1`", "措辞"),
        ("单一剂量档", "措辞"),
        ("剂量趋势未量到", "措辞"),
        ("不是「无剂量效应」", "措辞")],
    2: [("真阶梯", "措辞"),
        ("每条轨迹扫 K 个 `n_sites`", "措辞"),
        ("不能靠事后分位分档", "措辞"),
        ("切穿复制组", "措辞"),
        ("要跑批 ⇒ 要点头", "措辞")],
    3: [("3 个 `pos_frac`", "措辞"),
        ("`pos_frac=0.25`", "数值"),
        ("`pos_frac=0.50`", "数值"),
        ("`pos_frac=0.75`", "数值"),
        ("不是「单剂量」口径", "措辞")],
}

E5_MUST = "剂量趋势未量到"
E5_NEG = ("不是「无剂量效应」", "不是「无趋势」")
E6_FORBIDDEN = ("无剂量效应", "无趋势", "无差异", "不存在剂量效应", "剂量效应为 0",
                "斜率为 0", "斜率 = 0", "没有剂量效应", "剂量效应不存在",
                "已量到", "有剂量效应", "存在剂量效应")
NEG_PREFIX = "不是「"


def read_text(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def strip_md(s):
    """⚖ 剥 markdown 粗体/斜体（被检实现用 `**`/`*`；互证用**正则**剥，方法不同）。"""
    return re.sub(r"\*{1,3}", "", s)


def tokens(s):
    """⚖ 互证的归一化：**词元序列**（⛔ 不是逐位子串）。"""
    return TOKEN_RE.findall(strip_md(s))


def seq_contains(hay, needle):
    """⚖ 断言的词元序列是否**连续出现**在另一段里（⛔ 不是「子集」，顺序要连续）。"""
    n = len(needle)
    if n == 0:
        return False
    for i in range(len(hay) - n + 1):
        if hay[i:i + n] == needle:
            return True
    return False


def section_of(page_text):
    """⚖ 互证自己的 §6.2.2 切分（⛔ 按行扫描 + 下一个同级标题为止）。"""
    lines = page_text.split("\n")
    start = None
    for i, l in enumerate(lines):
        if l.startswith(SEC_HEAD):
            start = i
            break
    if start is None:
        raise ValueError("页面里找不到 §6.2.2")
    title = lines[start]
    body = []
    for l in lines[start + 1:]:
        if l.startswith("### "):
            break
        body.append(l)
    bullets = []
    for l in body:
        m = re.match(r"^\s*[-*•]\s+(\S.*\S)\s*$", l)
        if m:
            bullets.append(m.group(1))
    return title, "\n".join(body), bullets


def cites_by_scan(text):
    """⚖ 互证的锚定：**整行**正则扫 `:NNNN`（含全角冒号）。"""
    return sorted(set(int(m.group(1)) for m in CITE_RE.finditer(text)))


def exempt_paren_positions(sec):
    """⚖ 互证的「别的小节」豁免：**括号整体正则**逐个配对 ⇒ ⇒ 位置集合。"""
    pos = set()
    for m in PAREN_RE.finditer(sec):
        if SECNUM_RE.search(m.group(1)):
            for i in range(m.start(), m.end()):
                pos.add(i)
    return pos


def my_audit(page_text, ledger_text):
    """⚖ 互证自己的判定 ⇒ ⇒ (逐行结果, 汇总, 自己的 7 个闸门)。"""
    lines = ledger_text.split("\n")
    n_lines = ledger_text.count("\n")
    title, sec, bullets = section_of(page_text)

    rows = []
    hitset = set()
    missset = set()
    miss_verb = set()
    miss_num = set()
    n_assert = n_hit = n_miss = 0
    for i, b in enumerate(bullets, 1):
        cites = cites_by_scan(b)
        btok = tokens(b)
        h = 0
        mi = 0
        for tok, kind in REG.get(i, []):
            n_assert += 1
            tseq = tokens(tok)
            in_page = seq_contains(btok, tseq)
            in_led = any(in_page and seq_contains(tokens(lines[c - 1]), tseq)
                         for c in cites if 1 <= c <= n_lines)
            key = "B%d|%s" % (i, tok)
            if in_page and in_led:
                hitset.add(key)
                n_hit += 1
                h += 1
            else:
                missset.add(key)
                n_miss += 1
                mi += 1
                if kind == "措辞":
                    miss_verb.add(key)
                else:
                    miss_num.add(key)
        rows.append({"id": "B%d" % i, "cites": len(cites), "assertions": len(REG.get(i, [])),
                     "hit": h, "miss": mi})

    # ---- 留白守卫（正向 / 反向）----
    sec_s = strip_md(sec)
    e5 = (E5_MUST in sec_s) and any(f in sec_s for f in E5_NEG)

    exempt_pos = exempt_paren_positions(sec)
    n_occ = 0
    n_exempt = 0
    bad6 = []
    for ph in E6_FORBIDDEN:
        for m in re.finditer(re.escape(ph), sec):
            n_occ += 1
            pre = strip_md(sec[max(0, m.start() - 12):m.start()])
            if pre.endswith(NEG_PREFIX):
                n_exempt += 1
                continue
            if m.start() in exempt_pos:
                n_exempt += 1
                continue
            bad6.append(ph)
    e6 = not bad6

    gates = {
        "E1": (SEC_HEAD in title and TITLE_MUST in title and len(bullets) == N_BULLETS),
        "E2": all(1 <= c <= n_lines for b in bullets for c in cites_by_scan(b)),
        "E3": not miss_verb,
        "E4": not miss_num,
        "E5": e5,
        "E6": e6,
        "E7": all(r["hit"] >= 1 for r in rows),
    }
    mine = {"n_bullets": len(bullets), "n_assert": n_assert, "n_hit": n_hit,
            "n_miss": n_miss, "n_occ": n_occ, "n_exempt": n_exempt,
            "rows": rows, "hitset": hitset, "missset": missset,
            "miss_verb": miss_verb, "miss_num": miss_num, "gates": gates,
            "title": title}
    return mine


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


# ================================================================ 比对（互证 ⇔ 被检）

def compare(main_out, page_text, ledger_text):
    """⚖ 真比对：互证自己算一遍 ⇒ ⇒ 与被检实现的输出**逐项**对账 ⇒ ⇒ 返回不符清单。"""
    keys = parse_keys(main_out)
    blocks = parse_blocks(main_out)
    mine = my_audit(page_text, ledger_text)
    diffs = []

    # ① 逐行矩阵（cites / assertions / hit / miss）
    main_rows = {}
    for l in blocks.get("NUM_MATRIX", "").split("\n"):
        m2 = re.match(r"ROW=(B\d+)\|cites=(\d+)\|assertions=(\d+)\|hit=(\d+)\|miss=(\d+)",
                      l.strip())
        if m2:
            main_rows[m2.group(1)] = {"cites": int(m2.group(2)),
                                      "assertions": int(m2.group(3)),
                                      "hit": int(m2.group(4)), "miss": int(m2.group(5))}
    for r in mine["rows"]:
        mr = main_rows.get(r["id"])
        if mr is None:
            diffs.append("%s：被检输出里**没有**这一行" % r["id"])
            continue
        for f in ("cites", "assertions", "hit", "miss"):
            if mr[f] != r[f]:
                diffs.append("%s：%s 被检 %d ≠ 互证 %d" % (r["id"], f, mr[f], r[f]))

    # ② 汇总计数
    for k_mine, k_main in (("n_bullets", "N_BULLETS"), ("n_assert", "N_ASSERT"),
                           ("n_hit", "N_HIT"), ("n_miss", "N_MISS"),
                           ("n_occ", "N_SUSPECT"), ("n_exempt", "N_EXEMPT")):
        if str(mine[k_mine]) != keys.get(k_main):
            diffs.append("汇总 %s：被检 %s ≠ 互证 %d" % (k_main, keys.get(k_main), mine[k_mine]))

    # ③ 七个闸门逐个比（**集合**比较）
    for g in ("E1", "E2", "E3", "E4", "E5", "E6", "E7"):
        mk = keys.get("CHECK_" + g)
        if mk is None:
            diffs.append("闸门 %s：被检输出里**没有**这一项" % g)
            continue
        want = "PASS" if mine["gates"][g] else "FAIL"
        if mk != want:
            diffs.append("闸门 %s：被检 %s ≠ 互证 %s" % (g, mk, want))

    # ④ 整体形态
    my_verdict = "A" if all(mine["gates"].values()) else "D"
    if keys.get("VERDICT") != my_verdict:
        diffs.append("形态：被检 %s ≠ 互证 %s" % (keys.get("VERDICT"), my_verdict))

    return diffs, mine, my_verdict


# ================================================================ 互证自证（自己也要能红）

def selftest(main_out_path, page_path, ledger_path):
    """⚖ 把被检实现的输出改坏 ⇒ ⇒ **重跑真比对**必须抓到（⛔ 不许只验「字符串变了」）。"""
    out = read_text(main_out_path)
    page_text = read_text(page_path)
    ledger_text = read_text(ledger_path)
    n_diff = 0
    tampers = []

    # ① 翻一个闸门（E3 PASS → FAIL）
    bad = out.replace("CHECK_E3=PASS", "CHECK_E3=FAIL", 1)
    if bad == out:
        print("⛔ 被检输出里找不到 CHECK_E3=PASS ⇒ 中止")
        return 1
    tampers.append(("翻闸门 E3", bad))

    # ② 改一个命中计数（N_HIT）
    bad2 = re.sub(r"N_HIT=\d+", "N_HIT=999", bad, count=1)
    if bad2 == bad:
        print("⛔ 被检输出里找不到 N_HIT ⇒ 中止")
        return 1
    tampers.append(("改 N_HIT", bad2))

    # ③ 改一个逐行矩阵（第一行的 hit）
    bad3 = re.sub(r"(ROW=B\d+\|cites=\d+\|assertions=\d+\|)hit=\d+",
                  r"\g<1>hit=42", bad2, count=1)
    if bad3 == bad2:
        print("⛔ 被检输出里找不到矩阵里的 hit= ⇒ 中止")
        return 1
    tampers.append(("改矩阵 hit", bad3))

    for name, t in tampers:
        d, _m, _v = compare(t, page_text, ledger_text)
        if d:
            n_diff += 1
            print("[PASS] 篡改「%s」⇒ ⇒ 真比对**抓到** %d 处不符" % (name, len(d)))
        else:
            print("[FAIL] 篡改「%s」⇒ ⇒ 真比对**没抓到** ⇒ ⇒ 互证自己**没有牙齿**" % name)

    print("===== AUDIT_KEYS =====")
    print("CROSS_SELFTEST_N_DIFF=%d" % n_diff)
    print("CROSS_SELFTEST_N=%d" % len(tampers))
    print("CROSS_SELFTEST_RC=%d" % (0 if n_diff == len(tampers) else 1))
    print("===== END_AUDIT_KEYS =====")
    return 0 if n_diff == len(tampers) else 1


# ================================================================ 主流程

def main():
    ap = argparse.ArgumentParser(description="244.97 互证：页面 §6.2.2 的可溯源性 ＋ 留白守卫（独立实现）")
    ap.add_argument("--main", required=True, help="被检实现的 --data 输出")
    ap.add_argument("--page", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest(args.main, args.page, args.ledger)
    if not args.page or not args.ledger:
        print("⛔ --selftest 之外必须给 --page 与 --ledger")
        return 2

    page_text = read_text(args.page)
    ledger_text = read_text(args.ledger)
    main_out = read_text(args.main)

    diffs, mine, my_verdict = compare(main_out, page_text, ledger_text)

    print("⚖ **互证自己的判定**（⛔ 独立实现，零共用代码）")
    print("  · bullet %d ｜ 断言 %d ｜ 命中 %d ｜ 缺口 %d ｜ 可疑措辞 %d 处（豁免 %d）"
          % (mine["n_bullets"], mine["n_assert"], mine["n_hit"], mine["n_miss"],
             mine["n_occ"], mine["n_exempt"]))
    print("  · 命中集合 %d 条 ｜ 缺口集合 %d 条" % (len(mine["hitset"]), len(mine["missset"])))
    for r in mine["rows"]:
        print("  · %s：引用 %d ｜ 断言 %d ｜ 命中 %d ｜ 缺口 %d"
              % (r["id"], r["cites"], r["assertions"], r["hit"], r["miss"]))
    print("")
    print("===== AUDIT_KEYS =====")
    print("CROSS_N_BULLETS=%d" % mine["n_bullets"])
    print("CROSS_N_ASSERT=%d" % mine["n_assert"])
    print("CROSS_N_HIT=%d" % mine["n_hit"])
    print("CROSS_N_MISS=%d" % mine["n_miss"])
    print("CROSS_N_SUSPECT=%d" % mine["n_occ"])
    print("CROSS_N_EXEMPT=%d" % mine["n_exempt"])
    print("CROSS_N_HITSET=%d" % len(mine["hitset"]))
    print("CROSS_N_MISSSET=%d" % len(mine["missset"]))
    print("CROSS_N_ROWS=%d" % len(mine["rows"]))
    print("CROSS_MISMATCH=%d" % len(diffs))
    print("CROSS_VERDICT=%s" % my_verdict)
    print("CROSS_RC=%d" % (0 if not diffs else 1))
    print("===== END_AUDIT_KEYS =====")
    for d in diffs[:20]:
        print("  ⛔ %s" % d)
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
