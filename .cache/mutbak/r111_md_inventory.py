#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r111_md_inventory.py —— 修订 111-A

目的：修订 110 量到「页面在印 markdown 源码」（148 反引号 / 16 个 `**` / 1 个 `#`），
并在待办里挂了一个前置问题：**「先定一套统一的 markdown 子集与渲染规则」**。
⚠ 但那个决定缺一个前提 —— 我至今**没有量过产物里到底有哪些记号**。
在不知道数据里有什么之前谈「支持哪种子集」是无根据的。

本脚本只做一件事：把 **34 个产物 JSON 的全部字符串叶子**按固定记号表分类，
产出「哪些字段带哪种记号」的清单。这是**取数**，不是判据，不设任何门槛。

⚠⚠ 口径（否则会得出反向结论）：
   记号统计的是**产物里存着的字符串**，不是页面上印出来的。
   产物带记号 ⇒ 页面**可能**原样印出（真会出现）；产物不带 ⇒ 页面一定印不出。
   ⇒ 这份清单是**「可能印出」的候选集**，不是「已经印出」的名单。

两个对照（缺一不可）：
   阳性：`**` 与反引号各自的受影响字段数必须 > 0
         （修订 110 已在页面上实测到 148 反引号 / 16 `**` ⇒ 产物侧必须存在源头）
   阴性：CLEAN 字段数必须 > 0 且够多
         （若「每个字符串都带记号」，说明分类器把所有东西都判成脏 ⇒ 仪器坏了）
"""
import io
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend/public/latent/data"

# ---- 固定记号表（取数前写死；不在本轮增删，改表要单独立修订）----
TOKENS = OrderedDict([
    ("BT",     "`"),        # 反引号（行内代码）
    ("BOLD",   "**"),       # 粗体
    ("HASH",   "#"),        # 井号（标题/引用）
    ("LINK",   None),       # [text](url)
    ("FENCE",  "```"),      # 围栏代码块
    ("TABLE",  "|"),        # 表格竖线
    ("HTML",   None),       # <tag>
    ("ESC",    "\\"),       # 反斜杠转义
    ("STAR",   "*"),        # 裸星号（已扣掉 BOLD）
    ("LIST",   None),       # 行首 - / * / 1.
])
RE_LINK = re.compile(r"\[[^\]\n]*\]\([^)\n]*\)")
RE_FENCE = re.compile(r"```")
RE_TABLE = re.compile(r"\n[^\n]*\|[^\n]*\n")
RE_HTML = re.compile(r"<[A-Za-z][A-Za-z0-9]*(\s[^<>]*)?/?>")
RE_LIST = re.compile(r"(?m)^\s*([-*]\s|\d+\.\s)")


def die(m):
    print("[自证失败] " + m)
    sys.exit(2)


def leaves(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from leaves(v, (p + "." + str(k)) if p else str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from leaves(v, "%s[%d]" % (p, i))
    elif isinstance(o, str) and o != "":
        yield p, o


def tokens_of(s):
    """这个字符串带哪些记号。返回 token 名列表。"""
    got = []
    if "`" in s:
        got.append("BT")
    if "**" in s:
        got.append("BOLD")
    if RE_FENCE.search(s):
        got.append("FENCE")
    if s.count("#"):
        got.append("HASH")
    if RE_LINK.search(s):
        got.append("LINK")
    if RE_HTML.search(s):
        got.append("HTML")
    if "\\" in s:
        got.append("ESC")
    if RE_TABLE.search(s):
        got.append("TABLE")
    if RE_LIST.search(s):
        got.append("LIST")
    if "*" in s.replace("**", ""):
        got.append("STAR")
    return got


files = sorted(DATA.glob("*.json"))
if len(files) != 34:
    die("产物文件数 %d ≠ 34 ⇒ 扫描根变了" % len(files))
print("[自证] 扫描 %d 个产物 JSON" % len(files))

per_token = {k: [] for k in TOKENS}      # token -> [(file, path, snippet)]
clean = []
total_str = 0
total_tok = {k: 0 for k in TOKENS}        # 记号**出现次数**（不是字段数）

for f in files:
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        die("%s 解析失败：%s" % (f.name, e))
    for path, s in leaves(d):
        total_str += 1
        tk = tokens_of(s)
        for k in TOKENS:
            if k in tk:
                per_token[k].append((f.name, path, s))
        if tk:
            # 记号出现次数另数一遍
            n = s.count("`")
            if n:
                total_tok["BT"] += n
            n = s.count("**")
            if n:
                total_tok["BOLD"] += n
            n = s.count("#")
            if n:
                total_tok["HASH"] += n
            n = s.count("\\")
            if n:
                total_tok["ESC"] += n
            n = s.count("*") - 2 * s.count("**")
            if n > 0:
                total_tok["STAR"] += n
        else:
            clean.append((f.name, path))

print("[自证] 字符串叶子共 %d 个，其中带记号 %d 个、CLEAN %d 个"
      % (total_str, total_str - len(clean), len(clean)))

# ---------- 阳性对照 ----------
bad = []
if len(per_token["BT"]) == 0:
    bad.append("BT 受影响字段 = 0")
if len(per_token["BOLD"]) == 0:
    bad.append("BOLD 受影响字段 = 0")
if bad:
    die("阳性对照失败：" + "；".join(bad) + " ⇒ 本仪器判不出记号")
print("[阳性对照 ✓] BT 受影响 %d 个字段、BOLD %d 个字段 ⇒ 仪器能认出记号"
      % (len(per_token["BT"]), len(per_token["BOLD"])))

# ---------- 阴性对照 ----------
if len(clean) < 20:
    die("阴性对照失败：CLEAN 只有 %d 个（<20）⇒ 分类器把几乎所有字符串都判成脏"
        % len(clean))
print("[阴性对照 ✓] CLEAN %d 个字段（≥20）⇒ 分类器没有把所有字符串判成脏"
      % len(clean))

# ---------- 报告 ----------
print()
print("=== 记号 → 受影响字段数 / 记号出现次数 / 覆盖产物数 ===")
for k in TOKENS:
    n = len(per_token[k])
    arts = len({x[0] for x in per_token[k]})
    if n == 0:
        print("  %-6s 字段 0 个  次数 0  产物 0 个")
    else:
        print("  %-6s 字段 %4d 个  次数 %4d  产物 %2d 个"
              % (k, n, total_tok[k], arts))

print()
print("=== 逐产物：带记号的字段数 ===")
byfile = {}
for f in files:
    n = 0
    for k in TOKENS:
        n += sum(1 for x in per_token[k] if x[0] == f.name)
    if n:
        byfile[f.name] = n
for name, n in sorted(byfile.items(), key=lambda kv: -kv[1]):
    print("  %-46s %d" % (name, n))

print()
print("=== BOLD / HASH / LINK / FENCE / TABLE / HTML 的字段全清单（低频，可逐条判读）===")
for k in ("FENCE", "TABLE", "HTML", "LINK", "HASH", "BOLD"):
    if not per_token[k]:
        continue
    print()
    print("-- %s：%d 个字段 --" % (k, len(per_token[k])))
    for fn, path, s in per_token[k][:60]:
        snip = re.sub(r"\s+", " ", s)[:110]
        print("   %-40s %-42s %s" % (fn, path, snip))
    if len(per_token[k]) > 60:
        print("   ...（余 %d 个未印）" % (len(per_token[k]) - 60))

print()
print("=== BT（反引号）按产物聚合：字段数 + 次数 ===")
bt_by = {}
for fn, path, s in per_token["BT"]:
    bt_by.setdefault(fn, [0, 0])
    bt_by[fn][0] += 1
    bt_by[fn][1] += s.count("`")
for fn, (nf, nt) in sorted(bt_by.items(), key=lambda kv: -kv[1][1]):
    print("  %-46s 字段 %3d  反引号 %4d" % (fn, nf, nt))
print()
print("合计：BT 字段 %d 个 / 反引号 %d 个；字符串叶子 %d 个"
      % (len(per_token["BT"]), total_tok["BT"], total_str))
