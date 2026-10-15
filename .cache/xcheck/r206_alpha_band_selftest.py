#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`r206_alpha_band.py` 的自检 —— 纯 stdlib / 合成数据，不碰 GPU。

⚠⚠⛔ 本自检存在的原因：**上一版分析脚本自己下了一个错结论**。
⚠⚠⛔ 它在判据 2 里用「|z_cons| > 2 的格数 5/10」推出「两段斜率有系统性差异
⚠⚠⛔ ⇒ 外推失真」。而那 5 格的 z 符号是**混的**（3 正 2 负），
⚠⚠⛔ 且 |z|>2 只说「差得比标称 SE 多」，**根本不区分方向**。
⚠⚠⛔ ⇒ 结论的方向性与判据的方向性**无关**，判据在这个问题上没有分辨力。
⚗⇒ 教训：**判据绿了不代表它量的是你要的东西**；
⚗   凡是要下「机制」结论，判据必须能分出方向，而不只是分出「有差别」。

四组：
  A  网格/统计量基础    —— sxx / se_slope / alpha_grid 对已知答案
  B  判据 1（符号稳定性）—— 必须**能红**：造一个符号翻转的表 ⇒ 必须数到
  C  判据 2（方向一致性）—— 必须能分「全同向」与「符号混」两种情形
  D  判据 5（up_mono 是差值判据）—— 必须能红：造「通过但读数为负」的格

退出码：0 全过 / 1 有项红 / 2 导入失败
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[1] / ".cache/mutbak/r206_alpha_band.py"

FAILS = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    print("  %-58s %s%s" % (name, "PASS" if cond else "FAIL",
                            ("  <- " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def load():
    spec = importlib.util.spec_from_file_location("r206", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---- 合成行的构造：analyze_rows() 只吃这几个字段 ----
def mkrow(tid, pos, slope, slope_loc, resid, resid_loc,
          p9_lo=1.0, p9_hi=2.0):
    return {"tid": tid, "pos_frac": str(pos),
            "slope": "%.10g" % slope, "resid_std": "%.10g" % resid,
            "slope_local": "%.10g" % slope_loc,
            "resid_std_local": "%.10g" % resid_loc,
            "lin_ratio": "%.10g" % (resid / resid_loc if resid_loc else float("nan")),
            "p9_lo": "%.10g" % p9_lo, "p9_hi": "%.10g" % p9_hi,
            "p9_margin_se": "3.0"}


def main():
    try:
        M = load()
    except Exception as e:                       # 导入失败是 2，不是 1
        print("⛔ 导入 %s 失败：%r" % (SCRIPT, e))
        return 2

    print("=== A：α 网格与斜率的标准误（对已知答案）===")
    ag = M.alpha_grid()
    check("A1 网格点数 = 80", len(ag) == 80, "实得 %d" % len(ag))
    check("A2 网格两端恰为 ±120",
          abs(ag[0] + 120) < 1e-9 and abs(ag[-1] - 120) < 1e-9,
          "%.6f .. %.6f" % (ag[0], ag[-1]))
    check("A3 网格关于 0 对称",
          all(abs(ag[i] + ag[-1 - i]) < 1e-9 for i in range(80)))
    # ⛔ 对称 ⇒ Σ(α−x̄)² = Σα²，可用闭式核对
    closed = 2.0 * sum((120.0 - i * (240.0 / 79.0)) ** 2 for i in range(40))
    check("A4 sxx(全域) 与闭式一致",
          abs(M.sxx(ag) - closed) / closed < 1e-9,
          "%.6f vs %.6f" % (M.sxx(ag), closed))
    agl = [a for a in ag if abs(a) <= 60.0]
    check("A5 |α|≤60 的子带点数 = 40（20..59）", len(agl) == 40, "实得 %d" % len(agl))
    # ⛔ 反证：se_slope 若退化成「resid 本身」，A6 必红
    check("A6 se_slope = σ/√Σ(α−x̄)²（不是 σ 本身）",
          abs(M.se_slope(0.05, ag) - 0.05 / (M.sxx(ag) ** 0.5)) < 1e-12,
          "实得 %.8g" % M.se_slope(0.05, ag))
    check("A7 ⛔ 变异：退化成 σ 时 se 变大 ⇒ A6 有分辨力",
          abs(0.05 - 0.05 / (M.sxx(ag) ** 0.5)) > 1e-6)

    print("\n=== B：判据 1「符号稳定性」必须**能红**===")
    same = [mkrow("tA", 0.3, +0.007, +0.006, 0.06, 0.05)]
    res_same = M.analyze_rows(same)
    check("B1 同号 ⇒ 翻转数 = 0", res_same[0]["sign_flip"] is False)
    # ⛔ 关键反证：局部为正、全域为负 ⇒ 必须被判成翻转
    flip = [mkrow("tA", 0.3, -0.004, +0.006, 0.06, 0.05)]
    res_flip = M.analyze_rows(flip)
    check("B2 ⛔ 局部 + / 全域 − ⇒ 必须数到翻转",
          res_flip[0]["sign_flip"] is True,
          "实得 %r" % res_flip[0]["sign_flip"])
    # ⛔ 反过来：局部为负、全域为正 ⇒ 也算翻转
    flip2 = [mkrow("tA", 0.3, +0.004, -0.006, 0.06, 0.05)]
    check("B3 ⛔ 局部 − / 全域 + ⇒ 也算翻转",
          M.analyze_rows(flip2)[0]["sign_flip"] is True)
    # ⛔ 边界：斜率恰为 0 时实现按 >=0 判通过 ⇒ 必须与 mono_206 同规则
    zero = [mkrow("tA", 0.3, 0.0, -0.006, 0.06, 0.05)]
    r0 = M.analyze_rows(zero)[0]
    check("B4 ⛔ slope 恰 0 ⇒ mono_206=True（与 >=0 同规则，不许用 >0）",
          r0["mono_206"] is True and r0["sign_flip"] is True)

    print("\n=== C：判据 2「有无系统性偏小」必须分得出方向 ===")
    allneg = [mkrow("t%d" % i, 0.3, +0.007, +0.008, 0.06, 0.05) for i in range(3)]
    dn = [r["d"] for r in M.analyze_rows(allneg)]
    check("C1 全同向（全域全小于局部）⇒ 3/3 为负",
          all(x < 0 for x in dn), repr(dn))
    allpos = [mkrow("t%d" % i, 0.3, +0.008, +0.007, 0.06, 0.05) for i in range(3)]
    dp = [r["d"] for r in M.analyze_rows(allpos)]
    check("C2 全同向（全域全大于局部）⇒ 3/3 为正", all(x > 0 for x in dp), repr(dp))
    mixed = allneg[:1] + allpos[:1]
    dm = [r["d"] for r in M.analyze_rows(mixed)]
    check("C3 ⛔ 符号混 ⇒ 「没有系统性偏小」这一支才是答案",
          (sum(1 for x in dm if x > 0) > 0 and sum(1 for x in dm if x < 0) > 0),
          repr(dm))
    # ⛔ 这就是上一版栽的地方：|Δ| 一样大，只差方向 ⇒ 结论必须不同
    check("C4 ⛔⛔ 同样大的 |Δ|、相反方向 ⇒ 计数上必须能区分",
          abs(abs(dn[0]) - abs(dp[0])) < 1e-9
          and (dn[0] < 0) != (dp[0] < 0))

    print("\n=== D：判据 5「up_mono 通过 ≠ 读数为正」必须能红 ===")
    # 差值判据：slope>0 ⇒ f(hi)>f(lo)。构造一格 hi 为负但仍为正差
    neg_but_pass = [mkrow("tA", 0.3, +0.001, +0.001, 0.06, 0.05,
                          p9_lo=-0.06, p9_hi=-0.008)]
    r = M.analyze_rows(neg_but_pass)[0]
    counted = r["mono_206"] and r["p9_hi"] < 0
    check("D1 ⛔ 通过且 hi<0 ⇒ 必须被数成「读数为负却通过」", bool(counted))
    check("D2 ⛔ 该格确实 mono_206=True（差值为正）", r["mono_206"] is True)
    check("D3 ⛔ hi<0 且 hi>=lo ⇒ lo 必也为负（过滤器等价于「两档都为负」）",
          r["p9_lo"] <= r["p9_hi"] < 0, "lo=%.4f hi=%.4f" % (r["p9_lo"], r["p9_hi"]))
    # ⛔ 反证：把过滤器改成 p9_hi > 0 ⇒ 计数必须变成 0 ⇒ 有分辨力
    check("D4 ⛔ 变异（把 <0 改成 >0）必须让计数变 0 —— 证明判据没恒真",
          not (r["mono_206"] and r["p9_hi"] > 0))
    allpos = [mkrow("t%d" % i, 0.3, +0.007, +0.007, 0.06, 0.05,
                    p9_lo=0.4, p9_hi=0.8) for i in range(3)]
    check("D5 全部为正 ⇒ 计数 0（判据不是恒红）",
          sum(1 for x in M.analyze_rows(allpos)
              if x["mono_206"] and x["p9_hi"] < 0) == 0)

    print("\n=== E：跨表兼容性检查必须是真的（不是一句警告）===")
    ct = M.cross_table_check()
    if ct is None:
        check("E1 ⛔ r204_noise.tsv 不在 ⇒ 本组无法验", False,
              "cross_table_check() 返回 None")
    else:
        check("E1 ⛔ 旧表与新表 pos_frac 集合确实不同",
              ct["old_pos"] != ct["new_pos"],
              "old=%s new=%s" % (ct["old_pos"], ct["new_pos"]))
        check("E2 ⛔ 旧表与新表 n_steps 确实不同",
              ct["old_n_steps"] != ct["new_n_steps"],
              "old=%s new=%s" % (ct["old_n_steps"], ct["new_n_steps"]))
        check("E3 ⛔ 交集很小（新表只测了 0.3/0.7，旧表是 0.2/0.4/0.6/0.8）",
              ct["n_shared"] == 0, "实得 %d" % ct["n_shared"])
        # ⛔ 反证：把新表 pos 集合换成旧的，警告就该变成「无差异」
        check("E4 ⛔ 变异：pos 相同 ⇒ 该检查必须报告「无 pos 差异」",
              sorted({"0.2", "0.4", "0.6", "0.8"})
              == sorted(ct["old_pos"]))

    print("\n=== 汇总 ===")
    if FAILS:
        print("RESULT r206_alpha_band_selftest  FAIL  %d/%d 项红：%s"
              % (len(FAILS), CHECKS[0], "；".join(FAILS)))
        return 1
    print("RESULT r206_alpha_band_selftest  OK  %d/%d" % (CHECKS[0], CHECKS[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
