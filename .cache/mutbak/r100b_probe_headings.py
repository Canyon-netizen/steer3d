#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摸清预登记的二级标题到底有几种格式（一次性勘察，不入库）。"""
import re
from pathlib import Path

P = Path(".cache/xcheck/R6_RERUN_PREREG.md")
lines = P.read_text(encoding="utf-8").split("\n")

revN, revD, base = {}, {}, []
for i, l in enumerate(lines):
    if not l.startswith("## "):
        continue
    body = l[3:].strip()
    m1 = re.match(r"^修订\s*(\d+)", body)
    if m1:
        n = int(m1.group(1))
        revN.setdefault(n, []).append((i + 1, body[:70]))
        continue
    m2 = re.match(r"^(\d+)\.(\d+)\s", body)          # 形如 13.0
    if m2:
        n = int(m2.group(1))
        revD.setdefault(n, []).append((i + 1, body[:70]))
        continue
    m3 = re.match(r"^(\d+)\.\s*\S", body)            # 形如 0. 标题
    base.append((i + 1, int(m3.group(1)) if m3 else None, body[:70]))

print(f"基础章节 {len(base)} 条，编号 {sorted({n for _, n, _ in base if n is not None})}")
ns, nd = sorted(revN), sorted(revD)
print(f"\n## 修订 N      {len(ns)} 条：{ns}")
print(f"## N.M 小节式  {len(nd)} 条：{nd}")
allr = sorted(set(ns) | set(nd))
print(f"\n修订合计 {len(allr)} 条 / 范围 1–{max(allr)}")
print("缺口:", [i for i in range(1, max(allr) + 1) if i not in allr] or "无")
print("两格式重叠:", sorted(set(ns) & set(nd)) or "无")

print("\n=== 同一编号在「## 修订 N」下出现多次的 ===")
for n, v in sorted(revN.items()):
    if len(v) > 1:
        print(f"  修订 {n}:")
        for ln, b in v:
            print(f"     {ln:>6}  {b}")

print("\n=== 「## N.M」里每个编号的小节数（前 8）===")
for n in nd[:8]:
    print(f"  修订 {n}: {len(revD[n])} 个小节，例 {revD[n][0][1][:52]}")
