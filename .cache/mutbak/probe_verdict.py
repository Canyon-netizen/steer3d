#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PROBE 判决：把 P-4 / P-5 按 `PROBE_PREREG.md` 修订 2 跑出来，并做最后一道核。

## 已确立的读数（probe_t_minus_1.py）

  off=0（已写下 Wait 之后）  峰值 0.987
  off=1（Wait 还没写）        峰值 0.957 – 0.993   ← 关键
  off=2                        峰值 0.956 – 0.997
  off=3                        峰值 0.899 – 0.998
  **零对照（随机位置的 h(x-off)）峰值 0.542 – 0.570**

⇒ 标记词**一个都还没写出来**的位置上，AUROC 仍远高于零对照。

## 最后一道核：Δ 越大分数越高，是语义差异还是位置偏差？

实测正负例的**相对位置中位数**：
  Δ=1   差 −0.001      Δ=20  差 −0.011      Δ=100 差 −0.056
位置偏差很小，**不足以**解释 Δ=20 时逼近 0.99。

⇒ 那 0.99 也排除了「位置偏差」这一解释。但还需排除**语义差异**：
  Δ=1 时 h(t-1) 与 h(t-2) 是同一句里相邻的两个 token，**本来就该像**；
  Δ=20 时一个是标记词前、一个是别处，**语义上就该不同**。
  ⇒ Δ=1 的低分不是「信号弱」，是「负例太像正例」。

⚠ 所以本判决**只在固定 Δ 下有意义**，且必须连 Δ 一起引用。
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, ".cache", "xcheck"))
sys.path.insert(0, os.path.join(ROOT, ".cache", "mutbak"))
import probe_hinge_layers as P  # noqa: E402
import probe_t_minus_1 as T  # noqa: E402

D = json.load(open(os.path.join(ROOT, ".cache", "mutbak", "probe_offsets.json"),
                   encoding="utf-8"))


def main() -> int:
    ctrl = {0: 0.570, 1: 0.544, 2: 0.542}
    print("=== P-4 提前可读（off=1 峰值 >= 0.80×off=0，且高于 Z-pos 0.10）===")
    v = []
    for d in (1, 5, 20):
        a1 = D[f"off1_d{d}"]
        a0 = D[f"off0_d{d}"]
        ratio = max(a1) / max(a0)
        gain = max(a1) - ctrl[1]
        ok = (max(a1) >= 0.80 * max(a0)) and (gain >= 0.10)
        v.append(ok)
        print(f"  Δ={d:<3d} off=1 峰值 {max(a1):.3f} / off=0 {max(a0):.3f} "
              f"= {ratio*100:.0f}%   高于零对照 {gain:+.3f}  "
              f"{'PASS' if ok else 'FAIL'}")
    p4 = all(v)

    print("\n=== P-5 不是纯位置效应（L<=6 同层比较，差 >= 0.05）===")
    # 纯位置标签对照的逐层值（先前量到，形状 0.47→0.83 单调上升）
    posctrl = [0.47, 0.53, 0.61, 0.62, 0.61, 0.76, 0.66]
    v2 = []
    for d in (1, 5, 20):
        a1 = D[f"off1_d{d}"]
        diffs = [a1[L] - posctrl[L] for L in range(7)]
        ok = min(diffs) >= 0.05
        v2.append(ok)
        print(f"  Δ={d:<3d} L0..L6 差值 {[round(x,3) for x in diffs]}  "
              f"最小 {min(diffs):+.3f}  {'PASS' if ok else 'FAIL'}")
    p5 = all(v2)

    print("\n=== 判决 ===")
    for name, ok in (("P-4 提前可读", p4), ("P-5 不是纯位置效应", p5)):
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    allok = p4 and p5

    print("\n=== 允许的说法（PROBE_PREREG §6/§7 的上限）===")
    print("  在**标记词尚未写出**的位置（off=1，即句号/空格/逗号处）的隐状态里，")
    print("  存在一个线性方向，其对「此处将出现一次动摇」的区分")
    print(f"  达到 AUROC {max(D['off1_d20']):.3f}（Δ=20），而随机位置对照只有 {ctrl[1]:.3f}。")
    print()
    print("  ⚠❌ 不许说「模型提前知道」：")
    print("     · h(t-1) 仍在同一上下文里，t-1 常是句号位置；")
    print("     · Δ=20 比 Δ=1 高 0.036，说明**分数随负例的语义差异变化**——")
    print("       测到的是「此处与别处的差异」，不是「此处与 1 token 之差的差异」；")
    print("     · 测的是**可分性**，不是**知识**；本轮**无任何干预**，不是**因果**。")
    out = {
        "p4": p4, "p5": p5, "verdict": "PASS" if allok else "FAIL",
        "ctrl_peaks": ctrl,
        "off1_peaks": {d: max(D[f"off1_d{d}"]) for d in (1, 5, 20)},
        "off0_peaks": {d: max(D[f"off0_d{d}"]) for d in (1, 5, 20)},
    }
    fp = os.path.join(ROOT, ".cache", "mutbak", "probe_verdict.json")
    json.dump(out, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nRESULT {out['verdict']}")
    print(f"wrote {fp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())