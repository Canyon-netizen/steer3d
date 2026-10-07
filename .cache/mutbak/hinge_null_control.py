#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""空转检验：`first_layer_correct` 的 L22/L25 双尖峰是**信号**还是**采样**？

⚠ 直觉上 121 个位置的直方图出现 L22=28、L25=34 两个高尖，
  像「模型在第 22/25 层决定」。但这有三种解释，不能默认第一种：
    (a) 真实信号：这两层是「决断层」
    (b) **采样伪影**：dict/set 迭代顺序、或 lens 只在少数层做 argmax
    (c) **量化伪影**：float16 重建误差在某些层把 argmax 推到巧合值

⚠ 尤其 (c)：anchor_logit_err 的中位数是 0.1013 —— 重建误差与
  真实的 top1-top2 margin 同量级。所以「某层 argmax == 最终 token」
  **本身就是个脆判据**：误差足够大时，任何一层都可能偶然对上。

这个脚本用**零对照**排掉 (b)(c)：
  对同一批轨迹取**随机位置**（不是动摇点），跑同样的 lens，
  看随机位置的直方图是不是**长得一样**。
  若随机位置也在 L22/L25 起峰 ⇒ 那些峰是装置的，不是模型的。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HINGE = os.path.join(ROOT, ".cache", "xcheck", "hinge.json")
MUT = os.path.join(ROOT, ".cache", "mutbak")
random.seed(20261007)


def hist_of(path):
    d = json.load(open(path, encoding="utf-8"))
    counts = d["aggregate"]["first_layer_correct_hist"]["counts"]
    return counts, d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=121, help="随机位置个数")
    a = ap.parse_args()

    # ---- 造随机位置的对照集：从每条轨迹里抽与该轨迹动摇点数相同的随机 tok ----
    h = json.load(open(HINGE, encoding="utf-8"))
    lens = json.load(open(os.path.join(MUT, "logit_lens_hinge.json"),
                          encoding="utf-8"))
    T = {tr["id"]: tr["T"] for tr in lens["trajectories"]}
    pos = {}
    for r in h["rows"]:
        if r["trajectory_id"] in T:
            pos[r["trajectory_id"]] = [x["tok"] for x in r["hinges"]
                                       if x["tok"] >= 0]
    rnd = {}
    for tid, toks in pos.items():
        n = T[tid]
        pick = random.sample(range(0, n), min(len(toks), n))
        rnd[tid] = pick
    pf = os.path.join(MUT, "_rand_positions.json")
    json.dump(rnd, open(pf, "w"), indent=1)
    out = os.path.join(MUT, "logit_lens_random.json")
    print(f"零对照：{sum(len(v) for v in rnd.values())} 个随机位置 / "
          f"{len(rnd)} 条轨迹 → {out}")
    r = subprocess.run(
        [sys.executable, "backend/examples/build_logit_lens.py",
         "--scan", "explicit", "--positions", pf, "--out", out],
        cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        return 1

    hc, dc = hist_of(os.path.join(MUT, "logit_lens_hinge.json"))
    hr, dr = hist_of(out)

    print("\n=== first_layer_correct 直方图：动摇点 vs 随机位置 ===")
    print(f"  {'层':>4s} {'动摇点':>8s} {'随机':>8s}")
    for i in range(max(len(hc), len(hr))):
        c = hc[i] if i < len(hc) else 0
        q = hr[i] if i < len(hr) else 0
        bar = "█" * min(q, 30)
        print(f"  L{i:2d} {c:>8d} {q:>8d}  {bar}")

    def stats(counts, d):
        n = sum(counts)
        l20 = sum(counts[20:])
        l24 = sum(counts[24:])
        return n, l20 / n if n else 0, l24 / n if n else 0

    nc, c20, c24 = stats(hc, dc)
    nr, r20, r24 = stats(hr, dr)
    print(f"\n  动摇点：n={nc}  L20+ 占 {c20*100:.0f}%  L24+ 占 {c24*100:.0f}%")
    print(f"  随机位：n={nr}  L20+ 占 {r20*100:.0f}%  L24+ 占 {r24*100:.0f}%")
    print(f"\n  anchor: 动摇 {dc['anchor']['all_steps']['rate']*100:.1f}%  "
          f"随机 {dr['anchor']['all_steps']['rate']*100:.1f}%")
    print("\n⚠ 读法：若两行**几乎一样** ⇒ L22/L25 的峰是**装置的**，不是模型的。")
    print("  若随机位置明显更早/更平 ⇒ 动摇点确有偏移。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())