#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读动摇点上的逐层 logit lens：动摇信号在**哪一层**最先变得可读。

⚠ 本脚本只做**读数**，不下判决。要回答的问题：
  在模型写下 `Wait, no.` / `Let me check again.` 的那个 token 位置上，
  「要回头重看」这件事的信号，是不是在**某几层**先于其他层变得可读？

⚠ 关键纪律：不用「生成文本变了」当证据（空对照下 98% 的生成就会不同）。
  这里读的是 **teacher-forced 逐层 logprob**，无混沌、可逐比特比较。
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LENS = os.path.join(ROOT, ".cache", "mutbak", "logit_lens_hinge.json")
HINGE = os.path.join(ROOT, ".cache", "xcheck", "hinge.json")
AUDIT = os.path.join(ROOT, ".cache", "mutbak", "hinge_audit.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="列前 N 个")
    a = ap.parse_args()

    d = json.load(open(LENS, encoding="utf-8"))
    h = json.load(open(HINGE, encoding="utf-8"))
    au = {(x["traj"], x["start"]): x for x in json.load(open(AUDIT, encoding="utf-8"))}
    # tok -> 句子
    tok2sent = {}
    for r in h["rows"]:
        for x in r["hinges"]:
            tok2sent[(r["trajectory_id"], x["tok"])] = x

    print("=== 逐层聚合：121 个动摇点 ===")
    agg = d["aggregate"]
    for k, v in agg.items():
        if isinstance(v, (int, float, str)):
            print(f"  {k}: {v}")

    print("\n=== first_layer_correct 直方图（0=没读出，28=最后一层才读出）===")
    fl = agg.get("first_layer_correct_hist", {})
    counts = fl.get("counts", [])
    for i, c in enumerate(counts):
        if c:
            print(f"  L{i:2d}: {'█'*min(c,40)} {c}")
    print(f"  never_correct = {fl.get('never_correct')}（{fl.get('note','')}）")

    # 每个位置：首层、单调性、margin
    rows = []
    for tr in d["trajectories"]:
        for st in tr["steps"]:
            key = (tr["id"], st["t"])
            info = tok2sent.get(key)
            rows.append({
                "traj": tr["id"], "t": st["t"], "tok": st["tok"],
                "final_id": st["final_id"],
                "first": st["first_layer_correct"],
                "nlayers_ok": st["n_layers_correct"],
                "monotone": st["monotone"],
                "margin": st["real_margin"],
                "decidable": st["decidable"],
                "anchor_ok": st["anchor_ok"],
                "sentence": (info["sentence"] if info else ""),
                "cls": (info["cls"] if info else ""),
                "verdict": (au.get((tr["id"], info["start"]), {}).get("verdict", "")
                            if info else ""),
            })

    dec = [r for r in rows if r["decidable"]]
    print(f"\n=== decidable 步（margin>=1.0）{len(dec)} 个 ===")
    firsts = [r["first"] for r in dec if r["first"] is not None]
    if firsts:
        firsts.sort()
        n = len(firsts)
        print(f"  首个正确层：中位 {firsts[n//2]}  均值 {sum(firsts)/n:.1f}  "
              f"范围 {firsts[0]}–{firsts[-1]}")
        late = sum(1 for x in firsts if x >= 20)
        print(f"  首次读出在 L20 及以后：{late}/{n}（{late/n*100:.0f}%）")
    mono = sum(1 for r in dec if r["monotone"])
    print(f"  单调（一旦正确就一直正确）：{mono}/{len(dec)}"
          f"（{mono/len(dec)*100:.0f}%）")

    print(f"\n=== 前 {a.n} 个 decidable 动摇点明细 ===")
    dec_sorted = sorted(dec, key=lambda r: (r["first"] is None, r["first"]))
    print(f"  {'轨迹':6s} {'tok':>5s} {'首层':>4s} {'正确层数':>6s} {'单调':>4s} "
          f"{'margin':>6s}  类别 裁决")
    for r in dec_sorted[:a.n]:
        print(f"  {r['traj'][5:9]:6s} {r['tok']:>5} {str(r['first']):>4} "
              f"{r['nlayers_ok']:>6} {str(r['monotone']):>4} {r['margin']:>6.2f}  "
              f"类{r['cls']} {r['verdict']}")
        print(f"       {r['sentence'][:88]}")

    # 早 vs 晚
    print("\n=== 首层分布的两端 ===")
    early = [r for r in dec if r["first"] is not None and r["first"] <= 12]
    late = [r for r in dec if r["first"] is not None and r["first"] >= 20]
    print(f"  早（L≤12）：{len(early)} 个   晚（L≥20）：{len(late)} 个")
    for r in early[:3] + late[:3]:
        print(f"    [{r['traj'][5:9]} tok{r['tok']}] 首层 L{r['first']} "
              f"{r['sentence'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())