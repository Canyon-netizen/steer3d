"""框架文档 §8.1 的每个数字都必须能追到上游产物（修订 47，判据 S-1 / S-2）。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_framework_doc_ladder.py

## 为什么盯这张表

`docs/STEERING_INTERPRETABILITY_FRAMEWORK.md` §8.1 是全项目**最常被读**的
一张表，而它「本项目在哪」那一列的数字是**手写**的。
`build_evidence_ladder.py` 的 6 条自检只查一部分，且**不读那份 md**
⇒ 改了 md 的数字、或改了上游产物而忘了改 md，都不会被发现。

## ⚠ 这条守卫**只读**框架文档，永不写

那个文件是作者的在制品（本会话全程未提交、未改动）。它变红时的处置方式是
**由作者决定**：要么补产物，要么改文档 —— 不是 agent 去动在制品。

## ⚠ 只查「文档 ⇒ 产物」这一个方向

文档行是**摘要**：产品里有而文档没展开的细节（`23 题配对`、地板 `0.0045`）
**不是缺陷**。查反方向（要求文档复述产品里每个数）会把正确的摘要判成错误
—— 本文件第一版就是这么写错的。

## 派生量

`82×` 这类数**不是**上游产物里的字段，是生成器自己算的比值
（LOO 0.3688 / 地板 0.0045）。所以来源池里**必须包含阶梯产物本身**，
否则 L4 会被误报成「文档写了产品支撑不了的数」。

## ⚠ 本守卫只覆盖**一个方向**，另一个方向由别处负责

* **文档 ⇒ 产物**（本文件）：框架文档 §8.1 的数必须能在产物里找到出处。
* **上游 ⇒ 阶梯产物**：由 `build_evidence_ladder.py` 的 6 条跨产物自检
  与证据链 **A2** 的逐字节复算负责。

⚠ 本文件**测不了**「改上游产物」这个方向的变异，原因是结构性的：
交付的 `evidence_ladder.json` 是**冻结快照**，它的 note 里用 `%s`
把上游数字渲染成散文（L5 的 note 里就印着「1.68×」）
⇒ 改上游产物**不会**让那个数字从快照里消失，
「目标仍在来源池中」是**正确**结果，不是变异失效。
要端到端测那个方向，必须**连阶梯产物一起重建**，
那是证据链 A2 的职责，不是本守卫的。
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
DATA = os.path.join(ROOT, "frontend/public/latent/data")
DOC = os.path.join(ROOT, "docs/STEERING_INTERPRETABILITY_FRAMEWORK.md")
LADDER = os.path.join(DATA, "evidence_ladder.json")

# 每一级喂给它的上游产物（判据 S-1 的来源表）
SRC = {"L1": ["linearity_law.json"],
       "L2": ["readable_subspace.json"],
       "L3": ["heldout_readability.json"],
       "L4": ["heldout_readability.json"],
       "L5": ["heldout_readability.json"],
       "L6": ["arm_asymmetry.json", "cot_texts.json"]}
NUM = re.compile(r"\d+\.\d+|\d+")

FAILS = []


def ok(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + ("" if cond else f"  ← {detail}"))
    if not cond:
        FAILS.append(name)


def pool(raw):
    """一个文本里所有可被引用的数字：原文里的 + 每个数值的多精度呈现。

    ⚠ 为什么要多精度：文档写 `1.50×`，上游值是 1.5036664896603755；
      写 `≥ 2×`，上游值是 2.0460249333760365（截断而非四舍五入）。
    """
    out = set(NUM.findall(raw))

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            for s in (".4f", ".3f", ".2f", ".1f", ".0f"):
                out.add(format(float(o), s))
                out.add(format(abs(float(o)), s))
    try:
        walk(json.loads(raw))
    except Exception:
        pass
    return out


def section_81(text):
    i, j = text.find("### 8.1"), text.find("### 8.2")
    if i < 0 or j < 0:
        raise SystemExit("框架文档里找不到 §8.1 / §8.2")
    return text[i:j]


def doc_cell(sec, level):
    for line in sec.splitlines():
        if line.strip().startswith("| **" + level):
            return [c.strip() for c in line.strip()[1:-1].split("|")][-1]
    return None


def verify(doc, ladder, products):
    bad = []

    def need(cond, name):
        if not cond:
            bad.append(name)

    sec = section_81(doc)
    for r in ladder["ladder"]:
        lv = r["level"]
        cell = doc_cell(sec, lv)
        need(cell is not None, f"框架文档 §8.1 有 {lv} 那一行")
        if cell is None:
            continue
        nums = sorted(set(NUM.findall(cell)), key=float)
        # 阶梯产物本身也要进池子（派生量如 82× 只在它里面）
        p = pool(r["here"] + " " + r.get("note", ""))
        for f in SRC.get(lv, []):
            p |= pool(products[f])
        miss = [n for n in nums if n not in p]
        need(not miss,
             f"§8.1 {lv} 的每个数都有出处（{len(nums)} 个）"
             f"　无出处：{miss}")
    return bad


print("== 1. 读框架文档与上游产物（**只读**）==")
doc = open(DOC, encoding="utf-8").read()
ladder = json.loads(open(LADDER, encoding="utf-8").read())
products = {f: open(os.path.join(DATA, f), encoding="utf-8").read()
            for fs in SRC.values() for f in fs}
# ⚠ 那个文件**按设计就含 3 个 U+FFFD**：第 8003 行那节在讲
#   「一个多字节字符被切开的一半」长什么样，就把半个字符印出来当例子。
#   ⇒ 检查「坏字数为 0」会**误报**，并让未来的人以为文档坏了。
#   正确做法：断言坏字**恰好是那 3 个**，且它们出现在讲这个例子的那节里。
_bad = [m.start() for m in re.finditer("\ufffd", doc)]
ok("框架文档的 U+FFFD 恰好是刻意举例的 3 个",
   len(_bad) == 3 and all(
       "多字节字符被切开" in doc[max(0, p - 400):p + 400] for p in _bad),
   f"实测 {len(_bad)} 个坏字")
ok("七个上游产物都在", all(os.path.exists(os.path.join(DATA, f))
                          for f in products))
ok("阶梯产物带 8 级", len(ladder["ladder"]) == 8)

print("\n== 2. 真数据必须全过 ==")
bad = verify(doc, ladder, products)
ok(f"真数据 {len(bad)} 条判据全过", not bad, str(bad[:4]))

print("\n== 3. 变异自证（S-2）==")
# ⚠⚠ 「变异已生效」的判据必须是**目标数字真的从来源池里消失了**，
#   而不是「JSON 变了个样」。第一版只比 `prod != products` ⇒
#   改一个**副本字段**（best_margin 是 variants[1].margin 的副本）也算「生效」，
#   而 1.68 的出处还在原地 ⇒ 变异**打空**，看起来像守卫没牙齿。
MUTS = [
    ("文档 §8.1 里 L4 的 LOO 0.3688 被改掉", "doc_num", "L4", "0.3699"),
    ("文档 §8.1 里 L6 的 92 被改成 91", "doc_num2", "L6", "91"),
    ("文档 §8.1 里 L3 的 1.50× 被改掉", "doc_num3", "L3", "1.60"),
    ("文档 §8.1 里 L5 的 1.15× 被改掉", "doc_num4", "L5", "1.25"),
]


def replace_in_81(text, old, new):
    """只替换 **§8.1 那一节里**的第一次出现。

    ⚠⚠ 直接 `text.replace(old, new, 1)` 会改到文档**别处**的同一串：
    `0.3688` 首现于 §4 的表格（行 1037），`92 个真干预 run` 首现于文档
    开头的摘要（行 21）⇒ §8.1 一个字没动 ⇒ **变异是假的**，打空两次。
    """
    i, j = text.find("### 8.1"), text.find("### 8.2")
    if i < 0 or j < 0:
        return text
    sec, tail = text[i:j], text[j:]
    if old not in sec:
        return text
    return text[:i] + sec.replace(old, new, 1) + tail


def set_all(obj, pred, val):
    """把**所有**等于 pred 的数值都改掉（含副本字段）。"""
    n = 0
    def walk(o):
        nonlocal n
        if isinstance(o, dict):
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        elif isinstance(o, float) and pred(o):
            n += 1
            return None      # 占位，下面统一替换
    # 显式遍历并替换（dict/list 原地改）
    def walk2(o):
        nonlocal n
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if isinstance(v, float) and pred(v):
                    o[k] = val; n += 1
                else:
                    walk2(v)
        elif isinstance(o, list):
            for i2, v in enumerate(o):
                if isinstance(v, float) and pred(v):
                    o[i2] = val; n += 1
                else:
                    walk2(v)
    walk2(obj)
    return n


def mutate(kind):
    d, lad, prod = doc, ladder, dict(products)
    if kind == "doc_num":
        d = replace_in_81(d, "0.3688", "0.3699")
    elif kind == "doc_num2":
        d = replace_in_81(d, "92 个真干预 run", "91 个真干预 run")
    elif kind == "doc_num3":
        d = replace_in_81(d, "（1.50×）", "（1.60×）")
    elif kind == "doc_num4":
        d = replace_in_81(d, "1.15×", "1.25×")
    return d, lad, prod



def pool_has(sec, lad, prod, level, needle):
    """目标数字是否还在该级的来源池里。"""
    r = [x for x in lad["ladder"] if x["level"] == level][0]
    p = pool(r["here"] + " " + r.get("note", ""))
    for f in SRC.get(level, []):
        p |= pool(prod[f])
    return needle in p


for name, kind, level, target in MUTS:
    d, lad, prod = mutate(kind)
    ok(f"变异「{name}」已改动 §8.1", d != doc,
       "替换没有落到 §8.1 里（多半是它先在文档别处出现过）")
    ok(f"变异「{name}」的目标数字 {target} 在来源池里确实不存在",
       not pool_has(section_81(d), lad, prod, level, target),
       "目标本来就在池子里 ⇒ 这次变异测不到任何东西")
    got = verify(d, lad, prod)
    ok(f"变异「{name}」能让守卫变红", bool(got),
       "verify 仍然全绿 ⇒ 这条判据没有牙齿")

print()
if FAILS:
    print(f"**先验失败 {len(FAILS)} 项**：{FAILS}")
    sys.exit(1)
print("先验全过")
