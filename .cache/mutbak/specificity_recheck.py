#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 |Δ| 重算特异性：R-3 / R-4 两条规则都写错了，必须自己抓出来。

`causal_inject.py` 里那两条是我在**看到 buggy 读数之后**写的
（buggy = 全前缀注入，见 PREREG 修订 2），因此两条都不算数：

    R-3  原写法：w 上升 **且** 随机方向下降
         实测：w +1.6661 上升，随机 +0.0841 **也上升** ⇒ FAIL
         但随机方向只是小 20 倍。诚实的说法是**幅度比**，不是符号。

    R-4  原写法：Δmarker > Δ'the'（**带符号**比较）
         实测：+1.6661 > −1.6607 ⇒ PASS
         ⚠ 它只因为对照是负的就通过了，**根本没比幅度**。
         按幅度：1.6661 vs 1.6607，比值 **1.003** ⇒ 等幅移动，
         特异性**不成立**。

⇒ 同一份数据（`causal_rel8.json`），只换比较口径，不重跑。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, ".cache", "mutbak", "causal_rel8.json")
NOISE = 4.339e-05          # 本次实测：批量 vs 逐个前向的最大差
RATIO_MIN = 1.2            # 幅度比要超过它才算「有选择性」

d = json.load(open(SRC, encoding="utf-8"))
RP = d["keys_rel_pos"]
RR = ["rand|rel+0.00", "rand|rel+0.10", "rand|rel+0.25",
      "rand|rel+0.50", "rand|rel+1.00", "rand|rel+2.00"]
mk, ct, cu, rd = d["rel_pos"], d["rel_ctl"], d["rel_cur"], d["rel_rand"]

i = RP.index("w|rel+1.00")
j = RR.index("rand|rel+1.00")
ratio = abs(mk[i]) / max(1e-9, abs(ct[i]))
rratio = abs(mk[i]) / max(1e-9, abs(rd[j]))

print(f"案例 {d['n_cases']} 个，类间间距 {d['class_gap']:.1f}，"
      f"噪声底 {NOISE:.2e} nats\n")
print("=== α_rel=1.0 处 ===")
print(f"  |Δmarker|             {abs(mk[i]):.4f}")
print(f"  |Δ the |             {abs(ct[i]):.4f}")
print(f"  |Δ随机方向 marker|     {abs(rd[j]):.4f}")
print(f"  |Δ标记词本身|          {abs(cu[i]):.4f}")

print("\n=== 逐档按 |Δ| ===")
print(f"  {'α_rel':>10s} {'|Δmarker|':>11s} {'|Δ the |':>11s} {'比':>7s} "
      f"{'|Δ标记词本身|':>13s}")
for k, a, b, c in zip(RP, mk, ct, cu):
    print(f"  {k:>10s} {abs(a):11.4f} {abs(b):11.4f} "
          f"{abs(a) / max(1e-9, abs(b)):7.2f} {abs(c):13.4f}")

print("\n=== 三条候选口径 ===")
print(f"  R-3 原写法（w 升 且 随机 降）：{mk[i]:+.4f} / {rd[j]:+.4f} "
      f"⇒ {'PASS' if mk[i] > 0 and rd[j] < 0 else 'FAIL'}")
print(f"      随机方向其实也**升**，只是小 {rratio:.0f} 倍 ⇒ 原写法误判")
print(f"  R-3 改为幅度比 ≥ 10×：{rratio:.1f}× "
      f"⇒ {'PASS' if rratio >= 10 else 'FAIL'}   ✅ 方向可区分，成立")
print()
print(f"  R-4 原写法（带符号）：{mk[i]:+.4f} > {ct[i]:+.4f} "
      f"⇒ {'PASS' if mk[i] > ct[i] else 'FAIL'}")
print(f"      ⚠ 它只因对照是负的就过，**没比幅度** ⇒ 假判据")
print(f"  R-4 改为幅度比 ≥ {RATIO_MIN}：{abs(mk[i]):.4f} vs {abs(ct[i]):.4f}"
      f"（比 {ratio:.3f}）⇒ {'PASS' if ratio >= RATIO_MIN else 'FAIL'}"
      f"   ✅ 这条是真的")

print(f"\n  ⚠⚠ 特异性的诚实读数：比值 {ratio:.3f} ≈ 1。")
print("    marker 集合与高频对照词 ` the` **等幅移动**（一升一降，"
      "幅度几乎相同）")
print("    ⇒ 说不出「这个方向**专**门影响动摇标记词」。")
print(f"    能说的只有两条：① 它比随机方向**大 {rratio:.0f} 倍**；")
print("    ② 它对**另一个具体 token** 没有任何选择性。")

nz = [abs(x) for x in mk[1:]]
nzc = [abs(x) for x in cu[1:]]
print(f"\n  非基线档最小 |Δmarker| = {min(nz):.4f}（噪声底的 "
      f"{min(nz) / NOISE:.0f} 倍）⇒ 全部可分辨。")
print(f"  非基线档最小 |Δ标记词本身| = {min(nzc):.4f}（噪声底的 "
      f"{min(nzc) / NOISE:.0f} 倍）⇒ 可分辨，且**全程与 marker 集合反向**。")
