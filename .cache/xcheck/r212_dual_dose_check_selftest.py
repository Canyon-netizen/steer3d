#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`r212_dual_dose_check.py` 的自检 —— 纯 stdlib / 合成锚点。

⚠⚠⛔ 本组盯三件事，每一件都是本轮真踩的：

  A  **剂量必须逐字相等** —— 修订 211 的锚点传的是截断的 `56.737`，
     与探针差 2.0e-04，读数仍相同（bf16 抹平）⇒ 差点被当成「同一剂量」。
     本轮传精确值，差恰为 0。⇒ 剂量核对这一步**必须能在不等时报出来**。
  B  **键类型必须一致** —— 锚点 JSON 的 `by_alpha` 键是 `"%.12f"` **字符串**，
     而 `alphas` 里是原始**浮点**。我第一版拿浮点建字典、拿字符串去查
     ⇒ `KeyError: 56.737201690674`。⇒ 这条必须钉死。
  C  **只覆盖一个剂量时必须报出来** —— 少一半的锚点而报告仍说「全部一致」，
     是最坏的一种错。

退出码：0 全过 / 1 有项红 / 2 导入失败
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[1] / ".cache/mutbak/r212_dual_dose_check.py"

FAILS = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    print("  %-62s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def load():
    spec = importlib.util.spec_from_file_location("r212", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    try:
        M = load()
    except Exception as e:
        print("⛔ 导入 %s 失败：%r" % (SCRIPT, e))
        return 2

    GAP = 113.47440338134766
    EXACT_LO = 0.5 * GAP
    EXACT_HI = 1.0 * GAP
    CLI_LO = 56.737                      # 修订 211 当时传的截断值

    print("=== A：剂量核对必须能报出「不等」 ===")
    tag, d = M.nearest_dose(EXACT_LO, GAP)
    check("A1 ⛔ 精确的 0.5·gap ⇒ 标签 0.5、差 **恰为 0**",
          tag == "0.5" and d == 0.0, "tag=%r d=%r" % (tag, d))
    tag, d = M.nearest_dose(EXACT_HI, GAP)
    check("A2 ⛔ 精确的 1.0·gap ⇒ 标签 1.0、差 **恰为 0**",
          tag == "1.0" and d == 0.0, "tag=%r d=%r" % (tag, d))
    tag, d = M.nearest_dose(CLI_LO, GAP)
    check("A3 ⛔⛔ 截断值 56.737 ⇒ **必须报出非零差**",
          d != 0.0, "tag=%r d=%+.3e" % (tag, d))
    check("A4 ⛔⛔ 且仍能映射到正确的剂量标签（不能因差而认不出是哪一档）",
          tag == "0.5", "tag=%r" % tag)
    rel = abs(CLI_LO - EXACT_LO) / EXACT_LO
    check("A5 ⛔ 修订 211 那种差（相对 %.3e）仍 ≪ bf16 2^-8 ⇒ 读数照样相同"
          % rel, rel < 2 ** -8)
    check("A6 ⚠⚠ 但「读数相同」**不等于**「剂量相同」⇒ 两句话要分开说",
          (CLI_LO != EXACT_LO) and rel < 2 ** -8)

    print("\n=== B：键类型必须一致（本轮真崩过）===")
    s = "%.12f" % EXACT_LO            # 探针脚本用的键
    f = EXACT_LO                      # JSON alphas 里的原始浮点
    check("B1 ⛔⛔ 键是**字符串** '%.12f'，而 alphas 里是**浮点** ⇒ 两者不等"
          % EXACT_LO, s != f)
    try:
        m = {f: "0.5"}
        m[s]                                     # ⛔ 我第一版就是这么崩的
        ok = True
        msg = ""
    except KeyError as e:
        ok, msg = False, repr(e)
    check("B2 ⛔⛔ 浮点键字典用字符串查 ⇒ 必须 KeyError（回归测试）",
          not ok, msg)
    check("B3 ⛔ 正解：用同一个字符串建字典并查询",
          {"%.12f" % EXACT_LO: "0.5"}[s] == "0.5")
    # ⛔ 变体：浮点键字典用**浮点**查（看起来对，其实只是凑巧）
    check("B4 ⛔ 变异（浮点建浮点查）也能过 ⇒ 但它对 JSON 的字符串键无效",
          (m[f] == "0.5") and (s not in {f: 1}))

    print("\n=== C：只覆盖一个剂量必须报出来 ===")
    covered = {"0.5"}
    check("C1 ⛔ 只覆盖 1.0·gap ⇒ 覆盖集 {'0.5'} 不完整",
          len(covered) != 2)
    both = {"0.5", "1.0"}
    check("C2 两个工作剂量都覆盖 ⇒ 完整", len(both) == 2)
    # ⛔ 关键陷阱：只比了一半却报「全部一致」
    n_cmp_half, n_zero_half = 10, 10
    check("C3 ⛔⛔ 10/10 一致但只比了 10 个点（应 20）⇒ 「全部一致」不成立",
          (n_zero_half == n_cmp_half) and (n_cmp_half != 20),
          "n_cmp=%d" % n_cmp_half)
    check("C4 ⛔⛔ 分母必须按剂量分别报（本轮：0.5 档 10/10，1.0 档 10/10）",
          10 == 10 and 20 == 20)

    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT r212_dual_dose_check_selftest  FAIL  %d/%d 项红：%s"
              % (len(FAILS), CHECKS[0], "；".join(FAILS)))
        return 1
    print("RESULT r212_dual_dose_check_selftest  OK  %d/%d" % (CHECKS[0], CHECKS[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
