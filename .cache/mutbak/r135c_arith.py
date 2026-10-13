#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r135c_arith.py —— 当场复核 r135b 里那条 ⚠⚠⚴⚠⚴ 断言

r135b 印了这一行：
    ⚠⚠⚴⚠⚠ **6 ≠ 11**：判据 C3 核的是「6 行」，而文案若自称「±5 步」，
       读者按文案推算应当看到 11 行。⇒ **两个不是同一个量。**

⚠⚠⚴⚠⚴⚠⚴ 这行是**我自己在探针脚本里手写的断言**，不是从页面量出来的。
      而且它**算错了** —— 只算了 ±5 的上界，漏了**下界截断**。

本文件只做一件事：把「±5 模式有几行」按定义算出来，与判据 C3 的
min(6, k+1) 逐 k 对账。纯算术，不开浏览器。
"""

K = 27                      # 实测：产物 problems['1983_I_1'].k
TOTAL = K + 1               # 实测：屏上文案印「共 28 行」

def rows_pm5(k, total):
    """「只看分叉前后 ±5 步」按定义的行数：t ∈ [max(0,k-5), min(total-1, k+5)]"""
    lo = max(0, k - 5)
    hi = min(total - 1, k + 5)
    return max(0, hi - lo + 1)

print("=== 逐 k 对账：±5 模式的行数 vs 判据 C3 的 min(6, k+1) ===")
print(f"{'k':>4} {'total':>6} {'±5 行数':>9} {'min(6,k+1)':>12} {'一致':>6}")
print("-" * 44)

bad = []
for k in range(0, 40):
    total = k + 1
    a = rows_pm5(k, total)
    b = min(6, k + 1)
    ok = (a == b)
    if not ok:
        bad.append((k, a, b))
    mark = "✓" if ok else "✗ 不一致"
    if k <= 8 or k in (13, 20, 26, 27, 28) or not ok:
        print(f"{k:>4} {total:>6} {a:>9} {b:>12} {mark:>6}")

print("-" * 44)
print(f"0 ≤ k ≤ 39 中不一致的个数：**{len(bad)}**")

print()
print("=== 实测那一题 ===")
print(f"  k = {K}，total = {TOTAL}")
print(f"  屏上文案「只看分叉前后 ±5 步」按定义 ⇒ t ∈ [{max(0,K-5)}, {min(TOTAL-1,K+5)}]")
print(f"  ⇒ 行数 = {rows_pm5(K, TOTAL)}")
print(f"  判据 C3 要求 nRows === min(6, k+1) = {min(6, K+1)}")
print(f"  实测屏上 nRows = 6")
print(f"  ⇒ 三者一致 ⇒ **C3 判得对**")

print()
print("=== 为什么会算错 ===")
print("  我在 r135b 里只写了「±5 ⇒ 至多 11 行」，**漏了下界** max(0, k-5)。")
print("  k=27 时下界 = 22，上界被 total-1=27 截断 ⇒ 区间 [22,27] 只有 6 个。")
print("  ⇒ 「至多 11」是对的，但**不是**「恒等于 11」。")
print("  ⇒ 用「至多 11」去否定恒等于 6，是把上界当成了取值。")

print()
print("=== 纪律记录（本轮第 N 次「自己发绿/发红」）===")
print("  形态：⚠⚠⚴ 探针脚本里**手写死**一句结论，它看起来像实测发现，")
print("        实际是错的，而且**没有一行代码算它**。")
print("  与 r131 的同族差别：r131 是解析器把 needle 搞错；")
print("        这次是**结论直接写死在脚本里**，连解析都没有。")
print("  ⇒ 固化：**探针里不得出现未经计算的断言句**。")
print("        凡是要下结论的地方，必须由上面的代码算出数字，")
print("        或者明确标成「待验」并在本轮内去验。")