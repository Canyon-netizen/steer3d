#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`r204_noise_probe.analyze()` 的自检（修订 204 立）—— 四组，纯 stdlib/合成数据。

⚠⚠⚴ 为什么探针也要自检：本项目反复栽的坑是「**仪器本身没验过**」。
⚠⚠⚴ 修订 201 用「残差 std = 0.059」当噪声底，而「残差 std 这个数怎么算出来的」
⚠⚠⚴ 从未被任何东西检查过 —— 它是那个量的**定义**，定义错了后面全错。

四组：
  A1 已知噪声   ⇒ resid_std 应复原注入的 σ
  A2 无噪声     ⇒ resid_std ≈ 0（纯线性）
  A3 量化台阶   ⇒ 取整到 0.125 网格 ⇒ min_adj_diff = 0.125 且 n_distinct 变小
  A4 斜率复原   ⇒ 注入斜率应被拟合回来

⛔ 反向项（判据必须能红）：
  A5 ⛔ 若把 resid_std 的定义换成「原始 dm 的 std」，A1 必须红
     ⇒ 证明这条断言量的是**残差**而不是总波动。

退出码：0 全过 / 1 有项红 / 2 导入失败
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE.parents[1] / ".cache/mutbak/r204_noise_probe.py"

FAILS = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    print("  %-54s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def load():
    spec = importlib.util.spec_from_file_location("p204", PROBE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    try:
        import numpy as np
    except Exception:                                 # noqa: BLE001
        print("[错误] 本机无 numpy，本自检无法运行")
        return 2
    try:
        M = load()
    except Exception as e:                            # noqa: BLE001
        print("[错误] 导入 r204_noise_probe 失败：%r" % e)
        return 2

    rng = np.random.default_rng(20261015)
    alphas = np.linspace(-60.0, 60.0, 60)

    print("=== A1：注入已知噪声 σ=0.05，残差 std 必须复原它 ===")
    true_slope = 0.0039
    for sigma in (0.02, 0.05, 0.12):
        dm = true_slope * alphas + rng.normal(0.0, sigma, alphas.size)
        st = M.analyze(alphas, dm, np.zeros_like(dm))
        # ⚠ 容差：60 点的 σ 估计自身标准误 ≈ σ/√(2n) ≈ σ/11
        tol = 3.0 * sigma / (2.0 * alphas.size) ** 0.5
        check("A1 σ=%.2f ⇒ resid_std≈%.4f（容差 ±%.4f）" % (sigma, sigma, tol),
              abs(st["resid_std"] - sigma) < tol,
              "实得 %.6f" % st["resid_std"])

    print("\n=== A2：纯线性、无噪声 ⇒ resid_std ≈ 0 ===")
    dm = true_slope * alphas + 0.7
    st = M.analyze(alphas, dm, np.zeros_like(dm))
    check("A2 resid_std < 1e-9", st["resid_std"] < 1e-9, "实得 %.3e" % st["resid_std"])
    check("A2 斜率复原 0.0039（±1%）",
          abs(st["slope"] - true_slope) / true_slope < 0.01,
          "实得 %.8f" % st["slope"])
    check("A2 60 个点全部不同 ⇒ n_distinct=60",
          st["n_distinct"] == 60, "实得 %d" % st["n_distinct"])

    print("\n=== A3：量化到 0.125 网格 ⇒ 台阶必须被看见 ===")
    raw = true_slope * alphas + 0.3
    q = 0.125
    dm_q = np.round(raw / q) * q
    st = M.analyze(alphas, dm_q, np.zeros_like(dm_q))
    check("A3 min_adj_diff == 0.125", abs(st["min_adj_diff"] - q) < 1e-9,
          "实得 %.9f" % st["min_adj_diff"])
    check("A3 n_distinct 明显少于 60（取值被压到网格上）",
          st["n_distinct"] < 60, "实得 %d" % st["n_distinct"])
    # ⚠⚠ 关键反证：与**未量化**的同一组数据比，台阶数必须不同 ——
    # ⚠⚠ 否则「min_adj_diff 是 0.125」可能只是 α 网格碰巧的步长。
    st_raw = M.analyze(alphas, raw, np.zeros_like(raw))
    check("A3 ⛔ 同 α 网格下未量化的 min_adj_diff 必须**不同**（否则是网格的巧合）",
          abs(st_raw["min_adj_diff"] - q) > 1e-6,
          "实得 %.9f" % st_raw["min_adj_diff"])
    # ⚗ α 网格本身的步长：linspace(-60,60,60) ⇒ 120/59 ≈ 2.034，×斜率 0.0039 ≈ 0.0079
    check("A3 ⛔ 且未量化的 min_adj_diff ≈ 斜率×α步长（手算 0.00793）",
          abs(st_raw["min_adj_diff"] - 0.00793) < 5e-4,
          "实得 %.9f" % st_raw["min_adj_diff"])

    print("\n=== A4：斜率复原（容差按**估计量自身的标准误**给，不是我拍的）===")
    # ⚠⚠⚴ 第一版我拍了个 ±5%，结果 s=0.0005 那条红了（实得 0.00064631）。
    # ⚠⚠⚴ 查下来是**容差错**，不是代码错：最小二乘斜率的标准误
    # ⚠⚠⚴     SE(s) = σ / (√n · std(α))，此处 std(α)=60/√3≈34.6, n=60
    # ⚠⚠⚴     SE = 0.05/(7.746×34.6) ≈ **1.86e-4**
    # ⚠⚠⚴ 而 ±5%×0.0005 = 2.5e-5 —— 比标准误还紧 7 倍，红的是**我的尺子**。
    # ⚗⇒ 判据的容差必须跟着估计量的噪声走，否则它量的是「运气」。
    # ⚗⇒ 副产物：**真实斜率 0.0039 的相对标准误 ≈ 1.86e-4/0.0039 ≈ 4.8%** ——
    # ⚗⇒ 即真实测量的斜率也有 ~±15%（3 SE）的不确定度（残差 std 不受影响）。
    sigma4 = 0.05
    se = sigma4 / ((alphas.size) ** 0.5 * float(alphas.std()))
    print("  （SE(斜率) = σ/(√n·std(α)) = %.3e，σ=%.2f）" % (se, sigma4))
    for s in (0.0005, 0.0039, 0.02):
        dm = s * alphas + rng.normal(0.0, sigma4, alphas.size)
        st = M.analyze(alphas, dm, np.zeros_like(dm))
        tol = 3.0 * se                        # 3 SE 的容差
        check("A4 斜率 %.4f 复原（±3SE=%.2e，相对 %.1f%%）" % (s, tol, 100 * tol / s),
              abs(st["slope"] - s) < tol, "实得 %.8f" % st["slope"])

    print("\n=== A5：⛔ 定义敏感性（证明 A1 量的是**残差**不是总波动）===")
    dm = true_slope * alphas + rng.normal(0.0, 0.05, alphas.size)
    st = M.analyze(alphas, dm, np.zeros_like(dm))
    raw_std = float(np.asarray(dm).std(ddof=1))
    # ⚠ 若 resid_std 误用「原始 dm 的 std」，它会 ≈ raw_std（≈0.235）而不是 0.05。
    check("A5 ⛔ 总波动的 std（%.4f）与残差 std（%.4f）必须显著不同"
          % (raw_std, st["resid_std"]),
          abs(raw_std - st["resid_std"]) > 0.05,
          "两者太接近（%.6f / %.6f）⇒ 这条 A1 断言可能量错了东西"
          % (raw_std, st["resid_std"]))
    check("A5 ⛔ 且 resid_std 必须更接近注入的 0.05",
          abs(st["resid_std"] - 0.05) < abs(raw_std - 0.05),
          "实得 resid=%.6f  raw=%.6f" % (st["resid_std"], raw_std))

    print("\n=== A6：退化输入不得崩 ===")
    for nm, aa, dd in (("全等值", [1.0] * 5, [1.0] * 5),
                       ("单点", [0.0], [1.0]),
                       ("两行", [0.0, 1.0], [0.0, 0.0])):
        try:
            st = M.analyze(aa, dd, dd)
            ok = isinstance(st["resid_std"], float)
        except Exception as e:                        # noqa: BLE001
            ok = False
            print("      %s 抛异常：%r" % (nm, e))
        check("A6 %s 不得抛异常" % nm, ok)

    print("\n=== B：P9 相关量（α=rel×gap）===")
    # ⚠⚠⚴ 第一遍扫描只到 ±60，而 gap≈113 ⇒ α=1.0·gap **落在扫域外**。
    # ⚠⚠⚴ 在外推区报出的 se 若不随外推距离变大，那个 se 就是装饰。
    GAP = 113.474
    dm = true_slope * alphas + rng.normal(0.0, 0.05, alphas.size)
    st_out = M.analyze(alphas, dm, np.zeros_like(dm), gap=GAP)
    check("B1 给了 gap 才报 P9 量（不给就没有这些键）",
          "p9_hi" in st_out and "p9_up_mono" in st_out)

    small_gap = 30.0                      # α_hi=30 落在 ±60 之内
    st_in = M.analyze(alphas, dm, np.zeros_like(dm), gap=small_gap)
    check("B2 ⛔ 外推（gap=113）时 p9_se_hi 必须**大于**域内（gap=30）",
          st_out["p9_se_hi"] > st_in["p9_se_hi"],
          "外推 %.4f vs 域内 %.4f" % (st_out["p9_se_hi"], st_in["p9_se_hi"]))
    # 手算：se(x) = rstd·sqrt(1 + 1/n + (x−x̄)²/Sxx)
    n = alphas.size
    xbar = float(alphas.mean()); sxx = float(((alphas - xbar) ** 2).sum())
    rstd_in = st_in["resid_std"]
    # ⚠⚠⚴ 第一版这里拿 `p9_se_lo`（在 α=**0.5**·gap）去比按 **1.0**·gap 算的手算
    # ⚠⚠⚴ ⇒ 差 0.4%。**是我的尺子用错了 x**，不是代码错。
    hand = rstd_in * (1.0 + 1.0 / n + (0.5 * small_gap - xbar) ** 2 / sxx) ** 0.5
    check("B3 p9_se_lo 与手算公式逐位一致（x 取 0.5·gap）",
          abs(st_in["p9_se_lo"] - hand) < 1e-12,
          "实得 %.9f 手算 %.9f" % (st_in["p9_se_lo"], hand))
    hand_hi = rstd_in * (1.0 + 1.0 / n + (1.0 * small_gap - xbar) ** 2 / sxx) ** 0.5
    check("B3b p9_se_hi 与手算一致（x 取 1.0·gap）",
          abs(st_in["p9_se_hi"] - hand_hi) < 1e-12,
          "实得 %.9f 手算 %.9f" % (st_in["p9_se_hi"], hand_hi))

    print("\n=== C：P9 单调判据的符号 ===")
    for slp, want in ((0.0039, True), (-0.0039, False)):
        d2 = slp * alphas + rng.normal(0.0, 0.05, alphas.size)
        st2 = M.analyze(alphas, d2, np.zeros_like(d2), gap=GAP)
        check("C 斜率 %+.4f ⇒ p9_up_mono=%s" % (slp, want),
              st2["p9_up_mono"] is want, "实得 %r" % st2["p9_up_mono"])
    # ⛔ 关键：p9_up_mono 只看**斜率符号**，与噪声大小无关 ——
    # ⛔ 所以它是一个**确定性**判据；噪声影响的是另一个判据（比随机方向大）。
    # ⛔ 斜率恰为 0 时「我期望 True」是**没有依据的**：拟合斜率是纯噪声，
    # ⛔ 符号随机。⇒ 真正该测的是它的**通过率**。
    nz = M.analyze(alphas, true_slope * alphas + rng.normal(0.0, 0.05, alphas.size),
                   np.zeros(alphas.size), gap=GAP)
    check("C ⛔ p9_up_mono 必须**恒等于**「拟合斜率 ≥ 0」（这是它真正在做的事）",
          nz["p9_up_mono"] == (nz["slope"] >= 0.0),
          "up_mono=%r slope=%r" % (nz["p9_up_mono"], nz["slope"]))
    hits = 0
    T = 400
    for _ in range(T):
        d0 = rng.normal(0.0, 0.05, alphas.size)      # 真斜率 0
        st0 = M.analyze(alphas, d0, np.zeros(alphas.size), gap=GAP)
        hits += 1 if st0["p9_up_mono"] else 0
    rate = hits / float(T)
    print("      （零效应下 p9_up_mono 通过率 = %.1f%%，n=%d 次）" % (100 * rate, T))
    check("C ⛔⛔ 零效应下通过率必须落在 40%%–60%%（⇒ 它是**掷硬币**，不是判据）",
          0.40 <= rate <= 0.60, "实得 %.1f%%" % (100 * rate))
    noisy = true_slope * alphas + rng.normal(0.0, 0.5, alphas.size)   # 噪声 10 倍
    st3 = M.analyze(alphas, noisy, np.zeros_like(noisy), gap=GAP)
    check("C ⛔ 噪声放大 10 倍仍照符号判（说明它**不是**一个抗噪判据）",
          st3["p9_up_mono"] is True, "实得 %r" % st3["p9_up_mono"])
    check("C ⛔ 但 margin_se 必须随噪声变大而变小（抗噪度体现在这里）",
          st3["p9_margin_se"] < st_out["p9_margin_se"],
          "噪声大 %.4f vs 原 %.4f" % (st3["p9_margin_se"], st_out["p9_margin_se"]))

    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT r204_noise_selftest  FAIL  %d/%d 项红：%s"
              % (len(FAILS), CHECKS[0], FAILS))
        return 1
    print("RESULT r204_noise_selftest  OK  %d/%d" % (CHECKS[0], CHECKS[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
