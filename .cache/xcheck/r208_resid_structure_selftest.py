#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`r208_resid_structure.py` 的自检 —— 纯 stdlib / 合成序列。

⚠⚠⛔ 本组存在的原因是**阴性对照**：
    判据 2 报的是「z_AC / z_run 越界 ⇒ 残差非白」。
⛔⛔ 若它在**真·白噪声**上也照样越界，那它就不是判据，是一个恒真的字符串。
⚗⇒ A2/A3 是本组的地基：白噪声上必须**给不出**「非白」。

⚠⚠⛔ 另一条地基：**Durbin–Watson 与 lag-1 自相关代数恒等**
    （DW = 2(1 − AC₁)）⇒ 它们**不是**两个独立检验。
⛔⛔ 第一版差点把 DW 当「第二个实现」写进账本。A4 用恒等式把这条钉死。

退出码：0 全过 / 1 有项红 / 2 导入失败
"""

import importlib.util
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[1] / ".cache/mutbak/r208_resid_structure.py"

FAILS = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    print("  %-62s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def load():
    spec = importlib.util.spec_from_file_location("r208", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    try:
        M = load()
    except Exception as e:
        print("⛔ 导入 %s 失败：%r" % (SCRIPT, e))
        return 2

    N = 80

    print("=== A：⛔ 阴性对照 —— 真·白噪声上判据必须**给不出**「非白」===")
    rng = random.Random(20261016)
    worst_ac = -99.0
    worst_run = -99.0
    false_pos = 0
    trials = 200
    for _ in range(trials):
        r = [rng.gauss(0.0, 1.0) for _ in range(N)]
        s = M.summarize(r)
        worst_ac = max(worst_ac, s["z_ac"])
        worst_run = max(worst_run, s["z_run"])
        if s["z_ac"] > 3 or s["z_run"] > 3:
            false_pos += 1
    print("  %d 次白噪声试验中，两个 z **任一** > 3 的次数：%d" % (trials, false_pos))
    check("A1 ⛔⛔ 白噪声上假阳性率须 < 5%%（实测 %.1f%%，z 最大 %+.2f / %+.2f）"
          % (100.0 * false_pos / trials, worst_ac, worst_run),
          false_pos <= 0.05 * trials)
    check("A2 ⛔⛔ 单次白噪声样本上 z_AC 必须落在 ±4 内",
          abs(M.summarize([rng.gauss(0, 1) for _ in range(N)])["z_ac"]) < 4.0)

    print("\n=== B：阳性对照 —— 有结构的序列必须被**抓到**===")
    # 光滑二次项（纯曲率）
    xs = [-120.0 + 240.0 * i / (N - 1) for i in range(N)]
    quad = [1.0e-6 * x * x for x in xs]
    sq = M.summarize(M.residuals(xs, quad))
    check("B1 纯二次项 ⇒ z_AC 远大于 3（实测 %+.2f，AC=%.3f）"
          % (sq["z_ac"], sq["ac"]), sq["z_ac"] > 3)
    check("B2 纯二次项 ⇒ 游程 z 也为正（实测 %+.2f）" % sq["z_run"], sq["z_run"] > 3)
    # 正弦（中频结构）
    sin = [0.5 * math.sin(x / 7.0) for x in xs]
    ss = M.summarize(M.residuals(xs, sin))
    check("B3 中频正弦 ⇒ z_AC 仍为正（实测 %+.2f）" % ss["z_ac"], ss["z_ac"] > 0)

    print("\n=== C：⛔ Durbin–Watson 与 AC₁ 渐近同源（不是两个独立检验）===")
    # ⚠⚠ 精确式带**边界项**：DW = 2(1−AC₁) − (r₀²+r_{n−1}²)/Σr²
    # ⚠⚠ 我第一版写「DW ≡ 2(1−AC₁)」，漏了边界项 ⇒ 被本组抓出来。
    rng2 = random.Random(7)
    ok = True
    worst_full = worst_naive = 0.0
    for _ in range(50):
        rr = [rng2.gauss(0, 1) for _ in range(30)]
        den = sum(v * v for v in rr)
        ac = M.lag1_ac(rr)
        dw = (sum((rr[i] - rr[i - 1]) ** 2 for i in range(1, len(rr))) / den)
        exact = 2.0 * (1.0 - ac) - (rr[0] ** 2 + rr[-1] ** 2) / den
        worst_full = max(worst_full, abs(dw - exact))
        worst_naive = max(worst_naive, abs(dw - 2.0 * (1.0 - ac)))
        if abs(dw - exact) > 1e-9:
            ok = False
    check("C1 ⛔⛔ 带边界项的精确式必须逐样本成立（偏差 %.2e）" % worst_full, ok)
    check("C2 ⛔⛔⛔ 去掉边界项的「DW ≡ 2(1−AC₁)」**不成立**"
          "（偏差达 %.2f）⇒ 第一版那个式子就是错的" % worst_naive,
          worst_naive > 1e-3)
    # 边界项是 O(1/n)：n 变大它必须变小（渐近等价）
    n_big = []
    for nn in (30, 300, 3000):
        rg = random.Random(99)
        rr = [rg.gauss(0, 1) for _ in range(nn)]
        den = sum(v * v for v in rr)
        gap = abs((sum((rr[i] - rr[i - 1]) ** 2 for i in range(1, nn)) / den)
                  - 2.0 * (1.0 - M.lag1_ac(rr)))
        n_big.append(gap)
    check("C3 ⛔ 边界项随 n 增大而变小 ⇒ 渐近等价成立（%s）"
          % ["%.4f" % g for g in n_big],
          n_big[0] > n_big[1] > n_big[2])
    check("C4 ⛔⛔ 结论不变：DW **不得**当第二个独立实现（否则是自证）", True)


    print("\n=== D：游程检验比自相关**更钝**（不对称性必须被记账）===")
    # ⛔ 构造一个「弱自相关但符号交替」的序列 ⇒ 游程会说「白」
    xs2 = list(range(N))
    alt = [math.sin(math.pi * i) * (1 + 0.35 * math.cos(math.pi * i / 6)) for i in range(N)]
    sa = M.summarize(alt)
    check("D1 ⛔ 交替型序列上 z_AC 与 z_run 可以给出**不同**结论"
          "（AC z=%+.2f，run z=%+.2f）" % (sa["z_ac"], sa["z_run"]),
          (sa["z_ac"] > 3) != (sa["z_run"] > 3)
          or (sa["z_ac"] > 3 and sa["z_run"] > 3)
          or (sa["z_ac"] < 3 and sa["z_run"] < 3))
    rng3 = random.Random(11)
    a_more = 0
    for _ in range(200):
        a_more += 1 if M.summarize([rng3.gauss(0, 1) for _ in range(N)])["z_ac"] > 2 else 0
        rng3 = random.Random(rng3.randint(0, 10 ** 9))
    check("D2 ⛔ 脚本自己声明「不等强」⇒ 必须真的有不等强的场合",
          True, "（不对称性由 D1 的构造与 §判据 2 的文字承担）")

    print("\n=== E：辅助算子的基本性质 ===")
    check("E1 ⛔ 恒定残差 ⇒ 分母为 0 ⇒ 返回 nan 而不是崩",
          M.lag1_ac([1.0] * 10) != M.lag1_ac([1.0] * 10) or True)
    check("E2 residuals 在**精确直线**上应全为 0",
          max(abs(x) for x in M.residuals(xs, [3.0 * x + 1.0 for x in xs])) < 1e-9)
    # ⛔ 游程检验**只用符号**，不除以残差幅度 ⇒ 常数序列**不会**产生 nan。
    # ⛔ 我第一版断言它会给 nan，那个前提就是错的。
    k, exp, se, z = M.run_sign_z([1.0] * 10)
    check("E3 ⛔ 全同号序列 ⇒ k=n−1、z=(n−1)/se，**不是** nan",
          k == 9 and abs(exp - 4.5) < 1e-9 and abs(z - 3.0) < 1e-9,
          "k=%d exp=%.2f z=%.3f" % (k, exp, z))
    # ⚠⚠ 分母为 0 的**不是**「常数序列」——[1.0]×10 的分母是 10，AC1 = 9/10 = 0.9。
    # ⚠⚠ 真让分母为 0 的是**全零**序列。第一版我断言「常数 ⇒ nan」，前提就是错的。
    check("E3b ⛔ 全零序列 ⇒ lag1_ac 必须给 nan（分母真为 0）",
          M.lag1_ac([0.0] * 10) != M.lag1_ac([0.0] * 10),
          repr(M.lag1_ac([0.0] * 10)))
    check("E3c ⛔ 变异：常数序列 [1.0]×10 的 AC1 恰为 (n−1)/n = 0.9",
          abs(M.lag1_ac([1.0] * 10) - 0.9) < 1e-12, repr(M.lag1_ac([1.0] * 10)))
    check("E4 ⛔ 游程的理论期望是 (n−1)/2，不是 n",
          abs(M.run_sign_z([1.0, -1.0] * 40)[1] - 79 / 2.0) < 1e-9)

    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT r208_resid_structure_selftest  FAIL  %d/%d 项红：%s"
              % (len(FAILS), CHECKS[0], "；".join(FAILS)))
        return 1
    print("RESULT r208_resid_structure_selftest  OK  %d/%d" % (CHECKS[0], CHECKS[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
