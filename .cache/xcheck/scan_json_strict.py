#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据：**页面上用的产物**必须是严格合法的 JSON。

## 为什么有这条（§8.9 第十四笔）

`.cache/completeness/completeness.json` 里有 **67 处裸 `NaN`**
（全是 `per_traj_rho_of_max_dir_median`）⇒ 它**不是合法 JSON**。
Python 的 `json` 模块接受 `NaN`（扩展），`JSON.parse` **不接受**
⇒ 同一个文件，Python 读得好好的，JS 侧直接抛 `Unexpected token 'N'`。

⇒ 我写判据时 `JSON.parse` 炸了，`comp` 变 null，E5/E8 两条**恒红**，
  而红的原因是**解析器**不是数据 —— 我第一反应是「产物坏了」，
  实际是「产物不是 JSON」。

## 判据本身的两条纪律

1. **只 gate 已发布的产物**（`frontend/public/latent/data/`）——
   它们才是页面与判据真正读的东西。中间产物（`.cache/`）里出现裸 NaN
   属于「分析过程中存了未定义值」，是另一回事，用**报告**而不是判红处理。
   ⚠ 判据如果一开始就是红的，它就会被人关掉 —— 那是「判红绿两态」最常见的死法。
2. **报告里必须写出「实际读了哪几份」**，否则「漏读」这件事本身不可见。

## 第三种状态

`completence.json` 这类中间产物读不了时，**不是**判据崩，
也不是通过 —— 单独计数并说清楚。
"""
import io
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLISHED = ROOT / "frontend/public/latent/data"
INTERMEDIATE = [
    ROOT / ".cache/completeness/completeness.json",
    ROOT / ".cache/rolesverify/probe_axes.json",
    ROOT / ".cache/rolesverify/axis_readouts.pre_specificity.json",
]

BARE = re.compile(r":\s*(NaN|-?Infinity)\b")

results = []


def check(name, ok, detail):
    results.append({"name": name, "ok": bool(ok)})
    print("[%s] %s: %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    # ---- J0 已发布产物目录必须存在（否则后面全是「0 个 ⇒ 通过」）----
    if not PUBLISHED.is_dir():
        check("J0 已发布产物目录存在", False, "缺 %s" % PUBLISHED)
        print("\nRESULT json_strict  FAIL  0/1 一条都没跑完（目录不存在）")
        return 1
    files = sorted(PUBLISHED.glob("*.json"))
    check("J0 已发布产物目录存在且非空", len(files) > 0,
          "读了 %d 份：%s" % (len(files), ", ".join(f.name for f in files)))

    # ---- J1 每一份都必须能被**严格**解析（先扫裸 NaN/Infinity，再 parse）----
    bad = []
    for f in files:
        raw = io.open(str(f), encoding="utf-8").read()
        n = len(BARE.findall(raw))
        if n:
            bad.append((f.name, n))
    check("J1 已发布产物里不得有裸 NaN / Infinity（它会让 JSON.parse 直接抛）",
          not bad,
          "读了 %d 份，全部严格合法" % len(files) if not bad
          else "不合法的：%s" % "；".join("%s（%d 处）" % b for b in bad))

    # ---- J2 逐份真正 parse 一遍 —— J1 只扫了字面量，parse 才是判据 ----
    unreadable = []
    for f in files:
        try:
            json.loads(io.open(str(f), encoding="utf-8").read(),
                       parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
        except Exception as e:
            unreadable.append((f.name, str(e)[:60]))
    check("J2 每一份都能被严格 JSON 解析器读完（连 NaN/Infinity 常量也拒）",
          not unreadable,
          "%d 份全部可解析" % len(files) if not unreadable
          else "读不了：%s" % "；".join("%s → %s" % u for u in unreadable))

    # ---- J3 中间产物：只**报告**。它们出现裸 NaN 不判红，但必须说出来。----
    #   ⚠ 这里刻意不判红：中间产物本来就不是发布物，判红会让门禁永远红，
    #     而一个永远红的判据会被直接关掉 —— 那是「判红绿两态」最常见的死法。
    notes = []
    for f in INTERMEDIATE:
        if not f.exists():
            notes.append("%s（不存在）" % f.name)
            continue
        raw = io.open(str(f), encoding="utf-8").read()
        n = len(BARE.findall(raw))
        notes.append("%s：%s（%d 处裸 NaN/Infinity）" % (
            f.name, "存在", n) if n else "%s：严格合法" % f.name)
    check("J3 中间产物的严格 JSON 状况必须被报告（不判红：它们不是发布物）",
          True, "；".join(notes)
          + " ⇒ Python 的 json 读得了、JS 的 JSON.parse 读不了的那一类，"
            + "任何跨语言消费它的判据都必须先处理")

    failed = [r for r in results if not r["ok"]]
    print("\nRESULT json_strict  %s  %d/%d 条通过"
          % ("RED" if failed else "GREEN", len(results) - len(failed), len(results)))
    for f in failed:
        print("   [FAIL] " + f["name"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
