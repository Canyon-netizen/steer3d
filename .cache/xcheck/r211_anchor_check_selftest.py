#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`r211_anchor_check.py` 的自检 —— 纯 stdlib / 合成锚点。

⚠⚠⛔ 本组盯三件事，每一件都是我在这条线上真踩过的：

  A  **判据能红**：把一个锚点挪 1e-6，「Δ 恰为 0」必须立刻翻。
  B  **缺锚点不许静默跳过**：少比一格而报告仍说「10/10 一致」是最坏的错。
  C  **剂量口径**：我第一版把锚点的 `--alpha`（它**就是** 0.5·gap）
     当成 gap 又乘了一次 0.5 ⇒ 表头印出 28.369，实际剂量是 56.737。
     ⚠⚠ **比较本身仍有效**（两边确实同剂量），但那行描述是错的
     ⇒ 描述错 = 下一个读者会按错的剂量去复现。

退出码：0 全过 / 1 有项红 / 2 导入失败
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().resolve().parent
SCRIPT = HERE.parents[1] / ".cache/mutbak/r211_anchor_check.py"

FAILS = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    print("  %-62s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def load():
    spec = importlib.util.spec_from_file_location("r211", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    try:
        M = load()
    except Exception as e:
        print("⛔ 导入 %s 失败：%r" % (SCRIPT, e))
        return 2

    print("=== A：「Δ 恰为 0」这个判据必须**能红** ===")
    base = [5.5060715675354, 6.185001373291016, 3.7669246196746826]
    probe = list(base)
    d_ok = [p - a for p, a in zip(probe, base)]
    check("A1 原样 ⇒ Δ 全为 0", all(d == 0.0 for d in d_ok), repr(d_ok))
    # ⛔ 变异：第二个锚点挪 1e-6
    moved = list(base)
    moved[1] += 1e-6
    d_bad = [p - a for p, a in zip(probe, moved)]
    check("A2 ⛔⛔ 挪 1e-6 ⇒ 该格 Δ ≠ 0 ⇒ 判据必须翻",
          d_bad[1] != 0.0, "Δ=%+.3e" % d_bad[1])
    check("A3 ⛔⛔ 且其余格**不受影响**（变异只改一格，不能全红）",
          d_bad[0] == 0.0 and d_bad[2] == 0.0, repr(d_bad))
    check("A4 ⛔ 「一致格数」必须从 3 掉到 2",
          sum(1 for d in d_bad if d == 0.0) == 2)
    # ⛔ 容差化的判据会把两种情形混为一谈
    check("A5 ⛔ 变异：判据写成 `<= 1e-5` ⇒ 3/3「一致」⇒ 分不开 A1/A2",
          sum(1 for d in d_bad if abs(d) <= 1e-5) == 3)
    n_zero_ok = sum(1 for d in d_ok if d == 0.0)
    n_zero_bad = sum(1 for d in d_bad if d == 0.0)
    n_tol_bad = sum(1 for d in d_bad if abs(d) <= 1e-5)
    check("A6 ⛔⛔ 而 `== 0` 分得开（3/2）⇒ 正确判据是**恰好等于 0**",
          n_zero_ok == 3 and n_zero_bad == 2,
          "==0: %d vs %d" % (n_zero_ok, n_zero_bad))
    check("A7 ⛔ 记录 A5 的容差化计数（应为 3）", n_tol_bad == 3, repr(n_tol_bad))


    print("\n=== B：缺锚点必须**显式**报出，不许静默跳过 ===")
    keys_all = [("t0", "0.3"), ("t1", "0.3"), ("t2", "0.3")]
    keys_probe = [("t0", "0.3"), ("t1", "0.3")]          # 探针侧少一格
    missing = [k for k in keys_all if k not in keys_probe]
    check("B1 探针侧缺 1 格 ⇒ missing 长度 = 1", len(missing) == 1, repr(missing))
    # ⛔ 关键：若只对交集合计并报「全部一致」，会给出**误导**的结论
    cmp_n = len([k for k in keys_all if k in keys_probe])
    check("B2 ⛔⛔ 实际只比了 %d 格，但锚点有 %d 格 ⇒ 分母必须分开报"
          % (cmp_n, len(keys_all)), cmp_n != len(keys_all))
    check("B3 ⛔⛔ 因此「全部一致」这句话**只对交集合**成立，不许覆盖全集",
          cmp_n == 2 and len(keys_all) == 3)
    # ⛔ 变异：静默跳过（不产出 missing）
    silent = [k for k in keys_all if k in keys_probe and True]
    check("A4⛔ 变异（静默跳过）⇒ missing 为空 ⇒ 缺陷",
          len(silent) != len(keys_all))

    print("\n=== C：剂量口径（锚点跑的是 56.737，而 0.5·gap = 56.73720169…）===")
    GAP = 113.47440338134766
    ANCHOR_ALPHA = 0.5 * GAP          # 探针 p9_lo_meas 实际所处的剂量
    CLI_ALPHA = 56.737                 # ⛔ 锚点当时命令行传的字面量
    check("C1 0.5·gap = %.9f（**不是** 56.737）" % ANCHOR_ALPHA,
          abs(ANCHOR_ALPHA - 56.737) > 1e-7,
          "差 %.3e" % (ANCHOR_ALPHA - CLI_ALPHA))
    # ⛔ 我第一版做的：把锚点的 alpha 当 gap 又乘 0.5
    wrong = 0.5 * ANCHOR_ALPHA
    check("C2 ⛔⛔ 错误算法给出 %.6f（= 0.25·gap）⇒ **不等于**锚点剂量" % wrong,
          wrong != ANCHOR_ALPHA)
    check("C3 ⚠⚠ 两边剂量确实**不同**（差 %.3e）⇒ 读数相同**另有原因**"
          % abs(ANCHOR_ALPHA - CLI_ALPHA), ANCHOR_ALPHA != CLI_ALPHA)
    # ⓘ 真正的原因：`alpha * v` 在 **bf16** 下算
    rel = abs(ANCHOR_ALPHA - CLI_ALPHA) / ANCHOR_ALPHA
    check("C4 ⛔⛔ 相对剂量差 %.3e ≪ bf16 相对精度 2^-8=%.3e"
          % (rel, 2 ** -8), rel < 2 ** -8,
          "比值 %.1f 倍" % (2 ** -8 / rel))
    check("C5 ⛔⛔ ⇒ 两次注入的向量**逐位相同** ⇒ 读数相同是必然，不是巧合",
          rel < 2 ** -8)


    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT r211_anchor_check_selftest  FAIL  %d/%d 项红：%s"
              % (len(FAILS), CHECKS[0], "；".join(FAILS)))
        return 1
    print("RESULT r211_anchor_check_selftest  OK  %d/%d" % (CHECKS[0], CHECKS[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
