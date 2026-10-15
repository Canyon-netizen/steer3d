#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 可分辨性闸自检（修订 198 立）—— 12 项。

按修订 8 §8.3 的同一条纪律：**新旧两个口径都要能判，且边界必须测到**。
夹具是两份真实实测值（修订 197 §197.2，`w_unembed_align.py` 可复算）：

    armB      dot_marker_mean=0.18019922077655792   class_gap=231.978
    new_p2a   dot_marker_mean=0.043172              class_gap=113.474

期望：armB ⇒ RESOLVABLE（旧批那次 P9 能过的那个 w）
      new_p2a ⇒ BELOW_FLOOR（本批重训的 w）
⚠ 若两个都判同一个，说明闸没在量它该量的东西。

退出码：0 全过 / 1 有项红 / 2 自检自身崩了
"""

import sys
from math import isclose
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from p6_resolvability import assess, bf16_ulp, FIXTURES, ATTENUATION_L20
except Exception as e:                       # noqa: BLE001
    print("[错误] 导入 p6_resolvability 失败：%r" % (e,))
    sys.exit(2)

FAILS = []


def check(name, cond, detail=""):
    print("  %-50s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def raises(f):
    """f() 抛异常就返回 True。"""
    try:
        f()
    except Exception:                            # noqa: BLE001
        return True
    return False


def main():
    LOGIT = 40.0          # 落在 [32,64) 桶 ⇒ ulp 0.25（修订 7 记的那一档）

    print("=== R1–R4：bf16 ulp 函数本身 ===")
    check("R1 ulp(40)=0.25（修订 7 那一桶）", isclose(bf16_ulp(40.0), 0.25, abs_tol=1e-12),
          "实得 %r" % bf16_ulp(40.0))
    check("R2 ulp(8)=0.0625", isclose(bf16_ulp(8.0), 0.0625, abs_tol=1e-12),
          "实得 %r" % bf16_ulp(8.0))
    check("R3 ulp(100)=0.5", isclose(bf16_ulp(100.0), 0.5, abs_tol=1e-12),
          "实得 %r" % bf16_ulp(100.0))
    check("R4 非正量级必须抛错而不是静默",
          raises(lambda: bf16_ulp(0.0)))

    print("\n=== R5–R6：两份真实夹具必须判出**不同**结果 ===")
    a_b = assess(FIXTURES["armB"]["dot_marker_mean"],
                 FIXTURES["armB"]["class_gap"], LOGIT)
    a_n = assess(FIXTURES["new_p2a"]["dot_marker_mean"],
                 FIXTURES["new_p2a"]["class_gap"], LOGIT)
    check("R5 armB ⇒ RESOLVABLE", a_b["resolvable"] is True,
          "ratio=%.3f" % a_b["ratio_to_floor"])
    check("R6 new_p2a ⇒ BELOW_FLOOR", a_n["resolvable"] is False,
          "ratio=%.3f" % a_n["ratio_to_floor"])
    check("R6b 两者判定**不同**（闸确实在量东西）",
          a_b["resolvable"] != a_n["resolvable"])

    print("\n=== R7–R8：手算核对（防止公式被改坏而夹具也跟着变） ===")
    check("R7 armB 校准点预测 ≈ +41.81",
          isclose(a_b["d_calib"], 231.978 * 0.18019922077655792, rel_tol=1e-9),
          "实得 %.4f" % a_b["d_calib"])
    check("R8 new_p2a L20 残差 ≈ +0.1225（< ulp 0.25）",
          isclose(a_n["d_l20"], (113.474 * 0.043172) / ATTENUATION_L20, rel_tol=1e-9)
          and a_n["d_l20"] < a_n["floor_ulp"],
          "实得 d_l20=%.4f floor=%.4f" % (a_n["d_l20"], a_n["floor_ulp"]))

    print("\n=== R9–R10：边界必须测到（>= 而非 >） ===")
    floor_ulp = bf16_ulp(LOGIT)                       # 0.25
    at_floor = floor_ulp * ATTENUATION_L20 / 1.0     # 反解出恰在一个 ulp 上的 dot
    r_eq = assess(at_floor, 1.0, LOGIT)              # rel=1, gap=1 ⇒ α=1
    r_lt = assess(at_floor * 0.999, 1.0, LOGIT)
    check("R9 恰在一个 ulp 上 ⇒ RESOLVABLE（>= 不是 >）",
          r_eq["resolvable"] is True, "实得 %r" % r_eq["resolvable"])
    check("R10 略低于一个 ulp ⇒ BELOW_FLOOR",
          r_lt["resolvable"] is False, "实得 %r" % r_lt["resolvable"])

    print("\n=== R11：收紧方向 —— 闸只能拒，不能放行 ===")
    # 给一个「本该拒」的组合，再看闸有没有被参数绕过去
    r_tiny = assess(1e-9, 1.0, LOGIT)
    check("R11 极小 dot ⇒ BELOW_FLOOR（绕不过去）",
          r_tiny["resolvable"] is False, "实得 %r" % r_tiny["resolvable"])

    print("\n=== R12：分桶敏感性（结论会随 logit 量级翻转，必须自报） ===")
    # new_p2a 在 [32,64) 桶不可分辨；若 logit 落在 [2,4) 桶，ulp=0.0156，则可分辨
    r_low = assess(FIXTURES["new_p2a"]["dot_marker_mean"],
                   FIXTURES["new_p2a"]["class_gap"], 3.0)
    check("R12 同一条 w 换分桶 ⇒ 结论会翻转（故 --logit-mag 必填）",
          r_low["resolvable"] != a_n["resolvable"],
          "40 桶=%r, 3 桶=%r" % (a_n["resolvable"], r_low["resolvable"]))

    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT p6_resolvability_selftest  FAIL  %d 项红：%s"
              % (len(FAILS), FAILS))
        return 1
    print("RESULT p6_resolvability_selftest  OK  12/12")
    return 0



if __name__ == "__main__":
    sys.exit(main())
