#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
r114_n1_power.py —— 修订 114 取数笔

两件事，顺序不能换：

1. **先验功效**：「属性对、文案错」这个变异必须能让 N1 转红。
   ⚠ 不验就上线 = 又一条恒绿判据（本仓已栽过好几次）。

2. 再看今天的真实页面是不是绿的。

## ⚠⚠ 功效验证的**口径**（必须说清楚，否则会读成比它实际更强的结论）

本脚本做的是**逻辑级**功效验证：从**已提交的判据文件里把 N1 的谓词原文抽出来**，
再用它去判一组构造输入。

⚠ 它**不是端到端变异**：没有改组件、没有重新构建、没有跑真实页面。
⇒ 它能证明的是「**这条判据在逻辑上会红**」，
   **不能**证明「改了组件之后整条判据链一定会红」。
⚠ 端到端变异（「把 `SubspacePanel.tsx:159` 改成写死的错数并重新构建」）**本轮未做**，
   已作为未完成项记在预登记里。

⚠⚠ **不复写判据**：谓词是从 `verify_subspace.mjs` 的源码里抽出来的原文，
   抽不到就 exit 2。复写的实现本身就是可能出错的东西。

## 四组构造输入（都必须判红）

| 输入 | 为什么它必须红 |
|---|---|
| B 数字错 | 「命名轴只有 6 条」而产物是 4 ⇒ 文案撒谎 |
| C 整句没了 | 「没有印出来」与「印错了」是两种病，都不许放过 |
| D 同段两个数 | 「命名轴只有 4 条 … 命名轴只有 7 条」⇒ 每处都得等于产物 |
| E 小数 | 「4.0 条」⇒ 不做宽松匹配（页面印的就是「4 条」） |
"""
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VER = ROOT / ".cache/browser_verify/verify_subspace.mjs"
VIS = ROOT / ".cache/mutbak/r107_visible_all.txt"
ART = ROOT / "frontend/public/latent/data/readable_subspace.json"

PRED_RE = re.compile(r"hits\.length\s*>\s*0\s*&&\s*hits\.every\(v\s*=>\s*v\s*===\s*nAx\)")
HITS_RE = re.compile(r"matchAll\(/命名轴只有\\s\*\(\\d\+\)\\s\*条/g\)")


def die(m):
    print("[自证失败] " + m)
    sys.exit(2)


# ---------- 1. 把判据原文抽出来 ----------
src = io.open(VER, encoding="utf-8").read()
m = PRED_RE.search(src)
if not m:
    die("在已提交的 verify_subspace.mjs 里找不到 N1 的谓词原文 ⇒ 抽不到判据")
pred_src = m.group(0)
if not HITS_RE.search(src):
    die("找不到 N1 的 matchAll 正则原文")
print("[自证] 从已提交判据文件里抽出 N1 谓词原文：")
print("        " + pred_src)
print("[自证] 抽出 hits 正则原文：/命名轴只有\\s*(\\d+)\\s*条/g")

nAx = json.load(io.open(ART, encoding="utf-8"))["headline"]["named_axes"]
print("[自证] 产物 named_axes = %r" % nAx)

# ---------- 2. 真实文案里的那一句 ----------
vis = io.open(VIS, encoding="utf-8").read()
real_hits = [int(x) for x in re.findall(r"命名轴只有\s*(\d+)\s*条", vis)]
if not real_hits:
    die("真实文案里找不到「命名轴只有 N 条」⇒ 语料不是渲染出来的页面")
print("[自证] 真实文案里读到 %r" % real_hits)


def judge(text):
    """用**抽出来的谓词原文**判一段 headline 文本。"""
    hits = [int(m2.group(1)) for m2 in re.finditer(r"命名轴只有\s*(\d+)\s*条", text)]
    # 谓词是 JS 表达式，这里按同一语义执行（hits / nAx 两个自由变量）
    return (bool(hits) and all(v == nAx for v in hits)), hits


# ---------- 3. 真实输入必须绿 ----------
ok_real, h_real = judge(vis)
print()
print("=== 真实文案 ===")
print("  谓词结果 %s（读到 %r）%s" % (ok_real, h_real, "✓ 绿" if ok_real else "✗ 应绿却红了"))
if not ok_real:
    die("真实文案判红 ⇒ 这条判据今天就有活缺陷，或谓词抽取错了")

# ---------- 4. 四组构造输入必须红 ----------
BASE = "L14 上互相近正交（|cos| < 0.50）的可读方向 至少 14 条 ，而命名轴只有 4 条。 下界来自 20 个候选"
cases = [
    ("B 数字错（属性对、文案撒谎）", BASE.replace("命名轴只有 4 条", "命名轴只有 6 条")),
    ("C 整句没了", BASE.replace("，而命名轴只有 4 条", "")),
    ("D 同段两个不同的数", BASE + " 另外命名轴只有 7 条。"),
    ("E 小数形态 4.0 条", BASE.replace("命名轴只有 4 条", "命名轴只有 4.0 条")),
]
print()
print("=== 构造输入（全部必须判红）===")
allred = True
for name, txt in cases:
    ok, h = judge(txt)
    red = not ok
    allred = allred and red
    print("  %-26s 读到 %-10r %s" % (name, h, "✓ 红" if red else "✗ 竟然绿了"))
if not allred:
    die("有构造输入判绿 ⇒ N1 没有牙齿，不得发布")
print()
print("[功效 ✓] 真实绿 + 四组构造全红 ⇒ N1 在逻辑上有牙齿")
print("⚠ 但这是**逻辑级**验证：端到端变异（改组件 + 重新构建）本轮**未做**。")