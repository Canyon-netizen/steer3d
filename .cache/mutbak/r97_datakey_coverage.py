#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 97：`categorize()` 的 DATA_KEY 覆盖面 —— 有多少「按设计该迭代的键」被当成了欠账。

诊断探针，不判红绿。

⚠ 背景：母判据 :96 的 DATA_KEY = `^(\\d{4}_[A-Z]\\d+|\\d+)$`，
  注释写「这些是**数据键**，宿主是遍历它们而不是按名字引用它们，按『字段名』判没有意义」。
⚠ 但实测里出现了 `aime__1984__1984_I_1__think` 这种**前缀形式** ⇒ 规则匹配不上
  ⇒ 它被判成 `unclassified` ⇒ 进台账 ⇒ 混进「513 条欠账」。

⚠⚠ 本脚本**不重新分类、不改判据**，只量一件事：
  有多少 unclassified 字段名**符合「按设计该被遍历」的机械形态**。

⚠ 判据边界（写死，取数前）：
  只认**能被机械指认**的形态，不做任何语义判断：
    P1 · 整体是裸题号（现行 DATA_KEY 已覆盖）
    P2 · 整体是负号整数（`-1`）
    P3 · 整体含 `YYYY_X_N` 子串（题号被包在更长的标识里）
    P4 · 整体是 `P3` 的 `__` 前缀形式（如 aime__1984__1984_I_1__think）
  ⚠ 其余一律算「不是数据键」——**不猜**。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEBT = ROOT / ".cache/xcheck/check_render_coverage_sitewide.debt.json"

P3 = re.compile(r"\d{4}_[A-Z]_\d+")
BARE = re.compile(r"^(\d{4}_[A-Z]_\d+|\d+)$")
NEGINT = re.compile(r"^-\d+$")
P4 = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*__\d{4}__\d{4}_[A-Z]_\d+__(no_think|think)$")
PIPE = re.compile(r"\|")


def kind(n):
    if BARE.match(n):
        return "P1 裸题号（现行规则已覆盖）"
    if NEGINT.match(n):
        return "P2 负号整数（现行规则未覆盖）"
    if P4.match(n):
        return "P4 __ 前缀题号（现行规则未覆盖）"
    if P3.search(n):
        return "P3 含题号子串（现行规则未覆盖）"
    return "其它"


def main():
    d = json.loads(DEBT.read_text(encoding="utf-8"))
    ents = d["debt"]
    unc = [e for e in ents if e.get("category") == "unclassified"]
    names = sorted({e["field"] for e in unc})

    print("=" * 78)
    print("修订 97 · DATA_KEY 的覆盖面（诊断探针，不重新分类、不改判据）")
    print("=" * 78)
    print(f"\n[台账] 总 {len(ents)} 条；unclassified {len(unc)} 条 / "
          f"distinct 字段名 {len(names)} 个")

    from collections import Counter
    buckets = {}
    for n in names:
        buckets.setdefault(kind(n), []).append(n)

    # 条目数（不是名字数）—— 两个口径都要印
    ent_by_kind = Counter()
    for e in unc:
        ent_by_kind[kind(e["field"])] += 1

    print(f"\n{'类别':<34}{'名字':>6}{'条目':>7}")
    for k in sorted(buckets, key=lambda x: -len(buckets[x])):
        print(f"  {k:<32}{len(buckets[k]):>6}{ent_by_kind[k]:>7}")

    n_p2 = len(buckets.get("P2 负号整数（现行规则未覆盖）", []))
    n_p3 = len(buckets.get("P3 含题号子串（现行规则未覆盖）", []))
    n_p4 = len(buckets.get("P4 __ 前缀题号（现行规则未覆盖）", []))
    gap_names = n_p2 + n_p3 + n_p4
    gap_ents = (ent_by_kind.get("P2 负号整数（现行规则未覆盖）", 0)
                + ent_by_kind.get("P3 含题号子串（现行规则未覆盖）", 0)
                + ent_by_kind.get("P4 __ 前缀题号（现行规则未覆盖）", 0))

    print(f"\n[口径·名字] 现行 DATA_KEY 覆盖不到的「疑似数据键」名字 {gap_names} 个 "
          f"/ 共 {len(names)} ⇒ {gap_names/len(names)*100:.1f}%")
    print(f"[口径·条目] 同类条目 {gap_ents} 条 / unclassified {len(unc)} 条 "
          f"⇒ 占 {gap_ents/len(unc)*100:.1f}%")

    for k in ("P2 负号整数（现行规则未覆盖）",
              "P4 __ 前缀题号（现行规则未覆盖）",
              "P3 含题号子串（现行规则未覆盖）"):
        v = buckets.get(k, [])
        if v:
            print(f"\n  {k} —— 样例：")
            for n in v[:10]:
                print(f"     {n}")

    pipes = [n for n in names if PIPE.search(n)]
    if pipes:
        print(f"\n[另一个形态] 含竖线的复合键 {len(pipes)} 个，样例：{pipes[:6]}")
        print(f"  ⚠ `field_name()`（母判据 :77-82）**完全不处理 `|`**")
        print(f"  ⚠ 这不是规则漏洞，是产物里就有的键形状 —— 但它值得记一笔：")
        print(f"    页面上要渲染它，只能整个键原样输出或按 `|` 再切一刀。")

    print(f"\n[结论·能说什么]")
    print(f"  unclassified 里**机械可指认**为「按设计该被遍历的键」的有")
    print(f"  {gap_names} 个名字 / {gap_ents} 条条目。")
    print(f"  ⚠ 这**不等于**「它们应该被移出 unclassified」——")
    print(f"    现行规则的意图是对的（数据键不该按字段名判），只是**形态没覆盖全**。")
    print(f"  ⚠ 也不等于「它们是假欠账」：一个键是不是被遍历，")
    print(f"    要看宿主怎么用那个对象 —— 那要实点页面，而通道不可用。")


if __name__ == "__main__":
    main()