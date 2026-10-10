"""收尾报告第 5 行那三个数（342 / 40 / 72）必须等于 explorer 产物上的算式
（修订 45，判据 §45.2 的 D-1 / D-2）。

跑法：PYTHONPATH=.cache/pylibs python3 .cache/bpath/test_completion_counts.py

## 为什么盯这三个数

`docs/BPATH_COMPLETION_REPORT.md` 是六项交付的收尾核对，第 5 行是
「干预结果与向量作用」。那三个数此前**只有结论没有算式**，产物里也没有
任何一个直接给出它们 ⇒ 读者要核对就得反推整个 `bpath_explorer.json`。

## 这些用例在钉什么

1. **三个数 == 写死的算式**
   （342 = 19 位点 × 18 变体；40 = Σ len(site.layers)；
   72 = 4 首位置 × 18 变体）；
2. **D-1「非零」措辞成立** —— `rel` 集合里不得出现 0。
   出现 0 的话，342 只是「档位总数」，报告的「非零干预」就是**错的**；
3. **D-2 报告写出了算式**，而不只是结果。

⚠ 第 2 条最容易被当成小题大做：它是**唯一**能把「非零干预」这个词
和实际数据绑在一起的一条。加安慰剂臂（rel=0）的那天，它会先红。
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
DOC = os.path.join(ROOT, "docs/BPATH_COMPLETION_REPORT.md")
EXPL = os.path.join(ROOT, "frontend/public/latent/data/bpath_explorer.json")

FAILS = []


def ok(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + ("" if cond else f"  ← {detail}"))
    if not cond:
        FAILS.append(name)


def counts(expl):
    """从 explorer 产物上算那三个数。

    ⚠ 这里**不硬编码** 19 / 18 / 10 —— 全部从产物数出来，
      硬编码的话产物一变就假通过。
    """
    sites = [s for t in expl["trajectories"] for s in t["sites"]]
    n_var = len(sites[0]["variants"]) if sites else 0
    return {
        "n_site": len(sites),
        "n_var": n_var,
        "inj": sum(len(s["variants"]) for s in sites),
        "layers": sum(len(s["layers"]) for s in sites),
        "norm": len(expl["trajectories"]) * n_var,
        "rels": sorted({v["rel"] for s in sites for v in s["variants"]}),
        "dirs": sorted({v["direction"] for s in sites for v in s["variants"]}),
    }


def verify(doc, c):
    bad = []

    def need(cond, name):
        if not cond:
            bad.append(name)

    # ---- 三个数与算式 ----
    need("**342**" in doc, f"报告含 342（实算 {c['inj']}）")
    need(c["inj"] == 342, f"注入总数实算 = 342（实际 {c['inj']}）")
    need("**40**" in doc, f"报告含 40（实算 {c['layers']}）")
    need(c["layers"] == 40, f"层注入实算 = 40（实际 {c['layers']}）")
    need("**72**" in doc, f"报告含 72（实算 {c['norm']}）")
    need(c["norm"] == 72, f"norm 分解实算 = 72（实际 {c['norm']}）")

    # ---- D-1「非零」措辞成立 ----
    need(0 not in c["rels"] and 0.0 not in c["rels"],
         f"剂量档里没有 rel=0（实际档位 {c['rels']}）")
    need("没有 0" in doc or "没有 0" in doc.replace(" ", ""),
         "报告说明了「非零」成立的依据（剂量档没有 0）")

    # ---- D-2 算式写出来了 ----
    need(f"{c['n_site']} 个位点 × {c['n_var']} 个变体" in doc,
         f"报告写出 342 的算式（{c['n_site']} × {c['n_var']}）")
    need(f"{len(c['rels'])} 档剂量" in doc,
         f"报告写出 18 = 档位 × 臂（实际 {len(c['rels'])} 档）")
    need(f"{len(c['dirs'])} 个臂" in doc,
         f"报告写出臂数（实际 {len(c['dirs'])}）")
    for d in c["dirs"]:
        need(f"`{d}`" in doc, f"报告写出臂 {d}")
    return bad


print("== 1. 读产物与报告 ==")
doc = open(DOC, encoding="utf-8").read()
expl = json.loads(open(EXPL, encoding="utf-8").read())
ok("报告与 explorer 产物 0 坏字", doc.count("\ufffd") == 0)
c = counts(expl)
print(f"  实算：位点 {c['n_site']} × 变体 {c['n_var']} ⇒ 注入 {c['inj']}、"
      f"层 {c['layers']}、norm {c['norm']}")
print(f"  档位 {c['rels']}；臂 {c['dirs']}")

print("\n== 2. 真数据必须全过 ==")
bad = verify(doc, c)
ok(f"真数据 {len(bad)} 条判据全过", not bad, str(bad[:6]))

print("\n== 3. 变异自证 ==")
MUTS = [
    ("少一个位点（342→324）", "drop_site"),
    ("变体少一档（18→17）", "drop_dose"),
    ("层剖面少一层（40→36）", "drop_layer"),
    ("轨迹少一条（72→54）", "drop_traj"),
    ("加一档 rel=0 ⇒「非零」不成立", "zero_dose"),
    ("报告里的 342 被改掉", "doc_num"),
    ("报告删掉算式（只留结果）", "doc_no_formula"),
]


def mutate(kind):
    e = copy.deepcopy(expl)
    d = doc
    if kind == "drop_site":
        e["trajectories"][0]["sites"] = e["trajectories"][0]["sites"][:-1]
    elif kind == "drop_dose":
        for t in e["trajectories"]:
            for s in t["sites"]:
                s["variants"] = s["variants"][:-3]
    elif kind == "drop_layer":
        e["trajectories"][0]["sites"][0]["layers"] = \
            e["trajectories"][0]["sites"][0]["layers"][:-1]
    elif kind == "drop_traj":
        e["trajectories"] = e["trajectories"][:-1]
    elif kind == "zero_dose":
        for t in e["trajectories"]:
            for s in t["sites"]:
                v = copy.deepcopy(s["variants"][0])
                v["rel"] = 0.0
                s["variants"].append(v)
    elif kind == "doc_num":
        d = d.replace("**342**", "**341**", 1)
    elif kind == "doc_no_formula":
        d = d.replace(f"{c['n_site']} 个位点 × {c['n_var']} 个变体", "若干")
    return d, counts(e)


for name, kind in MUTS:
    d, cc = mutate(kind)
    ok(f"变异「{name}」已生效", d != doc or cc != c, "变异没生效 ⇒ 测不到东西")
    got = verify(d, cc)
    ok(f"变异「{name}」能让守卫变红", bool(got),
       "verify 仍然全绿 ⇒ 这条判据没有牙齿")

print()
if FAILS:
    print(f"**先验失败 {len(FAILS)} 项**：{FAILS}")
    sys.exit(1)
print("先验全过")