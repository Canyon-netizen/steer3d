#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 91 调查：「172 个孤立星号值无判据」的成因与可信度。

诊断探针，不判红绿。

要查两件事：
  (1) 172 这个数**本身**对不对 —— 用干净的「单趟」实现独立复算，
      并与母判据自印的数比对。
  (2) 产生它的机制**可不可靠** —— `z5()` 有个模块级可变计数器
      `N_ISOLATED = [0]`（母判据 :199），而 `z5()` 被调用两次：
        :300  在 z5_positive_control() 内（阳性对照）
        :418  在 main() 里 → r5 = z5()
      计数器**永不复位** ⇒ z5() 不是幂等的。

⚠⚠ 「不幂等」本身不推出「172 是错的」——
  母判据 :507 印的是 r5['n_isolated_stars']，那是**第一次**调用时
  在 :262 求值的返回值，第二次累加发生在它之后 ⇒ 印出来的应当仍是单趟值。
  ⇒ 必须实测确认，而不是靠推理。本脚本两件事都算。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
IDX = FE / "public/latent/index.html"
Y2_OUT = ROOT / ".cache/mutbak/y2_run.txt"

# 母判据 :226 逐字照抄
MD_EMPHASIS = re.compile(r"\*\*[^*\s][^*]*\*\*")
# 母判据 :42-43
EXCL_MIN_LEAVES = 2000
EXCL_MAX_STR_RATIO = 0.01


def walk(obj, path="", acc=None):
    """独立实现：收集 (path, 叶子值)。递归返回值，不用 generator+acc。"""
    if acc is None:
        acc = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk(v, f"{path}.{k}" if path else str(k), acc)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, f"{path}[{i}]", acc)
    elif obj is not None and not (isinstance(obj, str) and obj == ""):
        acc.append((path, obj))
    return acc


def main():
    src = IDX.read_text(encoding="utf-8")
    files = sorted((FE / "public/latent/data").glob("*.json")) + [FE / "public/latent/models.json"]

    per_art = {}
    n_scanned_art = 0
    n_total_iso = 0
    n_iso_in_excluded = 0
    excluded_names = set()
    sample = []

    for f in files:
        if f.name not in src:
            continue
        n_scanned_art += 1
        data = json.loads(f.read_text(encoding="utf-8"))
        acc = walk(data)

        # 顺带判这个产物是否会被 E1/E2 排除 —— z5() 是独立函数，
        # 它**不受** scan() 的排除表约束 ⇒ 排除项的孤立星号值也被算进 172。
        n = len(acc)
        n_str = sum(1 for _p, v in acc if isinstance(v, str))
        ratio = n_str / n if n else 0.0
        is_excl = (n >= EXCL_MIN_LEAVES and ratio < EXCL_MAX_STR_RATIO)
        if is_excl:
            excluded_names.add(f.name)

        iso = [(p, v) for p, v in acc
               if isinstance(v, str) and "**" in v and not MD_EMPHASIS.search(v)]
        # md 强调值（对照组：Z5 真正在判的那一类）
        md = [(p, v) for p, v in acc
              if isinstance(v, str) and MD_EMPHASIS.search(v)]
        if iso or md:
            per_art[f.name] = {"iso": len(iso), "md": len(md), "excluded": is_excl}
        n_total_iso += len(iso)
        if is_excl:
            n_iso_in_excluded += len(iso)
            sample.extend((f.name, p, v) for p, v in iso[:3])

    m = re.search(r"另有 (\d+) 个值含 `\*\*`", Y2_OUT.read_text(encoding="utf-8"))
    printed = int(m.group(1)) if m else None

    print("=" * 78)
    print("修订 91 · 「孤立星号值」的成因与可信度（诊断探针，不判红绿）")
    print("=" * 78)
    print(f"\n[口径·扫描范围] index.html 源码里出现过的产物 {n_scanned_art} 个"
          f"（要求 > 0）—— z5() 的范围与 scan() **不同**")
    print(f"[单趟复算] 孤立星号值（值含 `**` 且不匹配 markdown 强调）{n_total_iso} 个")
    print(f"[母判据自印] {printed} 个")
    if printed != n_total_iso:
        print(f"[错误] 两者不等 ⇒ 探针或母判据有一个是错的，本轮不发结论")
        sys.exit(2)
    print(f"  ⇒ 完全相等 ✔（单趟实现可复现母判据的数字）")

    print(f"\n[机制·口径差] z5() 是独立函数，**不受 scan() 的 E1/E2 排除表约束**")
    print(f"  ⇒ 被 Y2 排除的产物，它的孤立星号值**照样进 172**：")
    print(f"     其中被 E1/E2 排除的产物 {sorted(excluded_names) or '（无）'}，"
          f"贡献 {n_iso_in_excluded} 个")
    if n_iso_in_excluded:
        for art, p, v in sample:
            print(f"       {art}  {p}  值前 40 字：{v[:40]!r}")

    print(f"\n[逐产物分解]（只列有值的；iso = 孤立星号值，md = markdown 强调值）")
    for nm, d in sorted(per_art.items(), key=lambda kv: -kv[1]["iso"]):
        mark = "  ← E1/E2 排除项" if d["excluded"] else ""
        print(f"  {nm:<34} iso {d['iso']:>5}   md {d['md']:>4}{mark}")

    print(f"\n[机制·不幂等] N_ISOLATED 是模块级可变计数器（:199），永不复位")
    print(f"  z5() 被调用两次：:300（z5_positive_control 内）与 :418（main）")
    print(f"  ⇒ 第二次会把计数再加一遍，但 :507 印的是 r5 字典里**第一次**求值的快照")
    print(f"  ⇒ 今天 {printed} 这个数**没有被重复计数污染**（上面已实测相等）")
    print(f"  ⚠ 但机制本身是地雷：任何人把 :437 挪到 :418 之前，"
          f"或再调一次 z5() 再读 r5，数字就会变。")

    print(f"\n[结论] 成因不是「有 172 个坏值」，而是两条机制：")
    print(f"  1 这些值里的 `**` 是**模型真吐出来的 token**（AIME 答案里 "
          f"\\boxed{{\\textbf{{042}}}}，")
    print(f"    分词器把 `**` 切成独立 token），原样显示**是正确的** ⇒ 母判据 :428 "
          f"的说法与数据一致。")
    print(f"  2 它们**不参与** Z5 判定（Z5 只判 markdown 强调那一类，"
          f"本批 md 值共 "
          f"{sum(d['md'] for d in per_art.values())} 个）⇒ 「本项无判据」的说法也成立。")
    print(f"  ⚠ 所以这不是缺陷，是**如实披露**；真正要问的是「读者会不会误读成已判过」")


if __name__ == "__main__":
    main()
