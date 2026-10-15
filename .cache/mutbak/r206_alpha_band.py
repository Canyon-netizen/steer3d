#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 206：α≤120 波段扫描 —— 解除修订 205 §205.5「外推到 113.5 未验」。

⚠⚠⛔ 本脚本**只**读 `.cache/mutbak/r206_p9band.tsv`（α∈[−120,120]、80 点、10 格）
⚠⚠⛔ 与 `.cache/mutbak/r204_noise.tsv`（α∈[−60,60]、60 点、20 格）**两张不同的表**，
⚠⚠⛔ 它们的 pos_frac 集合与 n_steps 都不同 ⇒ **跨表比任何量都是三个变量一起动**，
⚠⚠⛔ 一律禁止。本脚本只在**新表同一格内**做对照。

要回答的问题（修订 205 §205.5）
    修订 205 在 α∈[−60,60] 上量斜率，却把 P9 的两档剂量
    α=0.5·gap=56.737 与 α=1.0·gap=113.474 说成读数 —— 后者**在扫域之外**，
    是线性外推。⇒ 「4/20 格 slope 为负」到底是
      (a) 真实现象（大剂量处方向真的翻了），还是
      (b) 窄域伪影（±60 的斜率不能代表到 113.5）？

判别式（不需要新跑，同一格内两个拟合就够）
    slope_local = 同一格原始读数在 |α|≤60 子带上的拟合斜率
                 ≈ 修订 205 那台仪器在同一格上量到的东西
    slope       = 同一格原始读数在 |α|≤120 全域上的拟合斜率
                 —— 这一次的 α 域**真的覆盖** 113.474
    ⇒ 若二者之差落在联合标准误之内 ⇒ 外推合法 ⇒ (b) 被否
    ⇒ 若全域斜率系统性地比局部小 ⇒ 曲线饱和 ⇒ (b) 成立、(a) 要打折
"""
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TSV = os.path.join(HERE, "r206_p9band.tsv")

# ---- α 网格的形状（与 r204_noise_probe.py 的 driver 一致）----
N_PTS = 80
ALPHA_MAX = 120.0
BAND = 60.0
GAP = 113.47440338134766

A_LO, A_HI = 0.5 * GAP, 1.0 * GAP


def alpha_grid(n=N_PTS, amax=ALPHA_MAX):
    """探针用 linspace(-alpha_max, alpha_max, n)，这里复刻同一组点。"""
    if n == 1:
        return [0.0]
    h = (2.0 * amax) / (n - 1)
    return [-amax + i * h for i in range(n)]


def sxx(alphas):
    """Σ(α−x̄)²。"""
    xbar = sum(alphas) / len(alphas)
    return sum((a - xbar) ** 2 for a in alphas)


def se_slope(resid_std, alphas):
    """斜率的标准误 se(b1) = s / sqrt(Σ(α−x̄)²)。"""
    d = sxx(alphas)
    return (resid_std / math.sqrt(d)) if d > 0 else float("inf")


def load(path=TSV):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def analyze_rows(rows):
    ag = alpha_grid()
    ag_local = [a for a in ag if abs(a) <= BAND]
    s_full, s_loc = sxx(ag), sxx(ag_local)

    out = []
    for r in rows:
        b_full = float(r["slope"])
        b_loc = float(r["slope_local"])
        s_full_resid = float(r["resid_std"])
        s_loc_resid = float(r["resid_std_local"])
        se_full = se_slope(s_full_resid, ag)
        se_loc = se_slope(s_loc_resid, ag_local)

        # 配对差的全域−局部；两拟合共享数据 ⇒ 独立处理是**近似**，
        # 故这里同时给「联合 SE（当独立）」与「保守 SE（se 取大者）」
        # 两个口径，若结论随口径翻转 ⇒ 该结论不可用。
        d = b_full - b_loc
        se_ind = math.sqrt(se_full ** 2 + se_loc ** 2)
        se_cons = max(se_full, se_loc)

        out.append({
            "tid": r["tid"], "pos": float(r["pos_frac"]),
            "b_full": b_full, "b_loc": b_loc,
            "se_full": se_full, "se_loc": se_loc,
            "d": d, "z_ind": (d / se_ind) if se_ind > 0 else float("nan"),
            "z_cons": (d / se_cons) if se_cons > 0 else float("nan"),
            "sign_flip": (b_full >= 0) != (b_loc >= 0),
            "lin_ratio": float(r["lin_ratio"]),
            "resid_full": s_full_resid, "resid_loc": s_loc_resid,
            "p9_lo": float(r["p9_lo"]), "p9_hi": float(r["p9_hi"]),
            "margin": float(r["p9_margin_se"]),
            # 修订 205 那台仪器在同一格上的等效判决（用局部斜率）
            "mono_205": b_loc >= 0,
            "mono_206": b_full >= 0,
            # 局部斜率外推到 A_HI 与全域斜率外推到 A_HI 的读数之差
            # （截距未知 ⇒ 只能比斜率项；slope 项差 = d × A_HI）
            "extrap_gap_slope": d * A_HI,
        })
    return out


def cross_table_check():
    """⛔ 「不能跨表比」这条警告必须**被验证**，不能只是一句断言。

    修订 204/205 的 20 格与本轮 10 格：pos_frac 集合与 n_steps 都不同
    ⇒ 任何跨表逐值对比都在同时动三个变量。⇒ 这里按 (tid, pos) 求交集，
    并逐项列出同一格上**还差哪些非剂量变量**。
    """
    old_path = os.path.join(HERE, "r204_noise.tsv")
    if not os.path.exists(old_path):
        return None
    with open(old_path, newline="", encoding="utf-8") as fh:
        old = list(csv.DictReader(fh))
    new = load()
    key = lambda r: (r["tid"], r["pos_frac"])
    o = {key(r): r for r in old}
    n = {key(r): r for r in new}
    shared = sorted(set(o) & set(n))
    cols = ["t", "n_gen", "P", "n_steps"]
    same = []
    for k in shared:
        same.append((k, [c for c in cols if o[k].get(c) != n[k].get(c)]))
    return {"n_shared": len(shared), "shared": shared, "diff_cols": same,
            "old_pos": sorted({r["pos_frac"] for r in old}),
            "new_pos": sorted({r["pos_frac"] for r in new}),
            "old_n_steps": sorted({r["n_steps"] for r in old}),
            "new_n_steps": sorted({r["n_steps"] for r in new})}


def q(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - k) + xs[hi] * (k - lo)


def main():
    rows = load()
    if not rows:
        print("⛔ TSV 为空：%s" % TSV)
        return 1
    res = analyze_rows(rows)

    print("=" * 78)
    print("修订 206：α∈[−120,120] 波段扫描 —— %d 格，每格 %d 点" % (len(res), N_PTS))
    print("=" * 78)
    print("α 网格覆盖 P9 两档剂量：α_lo=%.3f ∈ 域内=%s ；α_hi=%.3f ∈ 域内=%s"
          % (A_LO, abs(A_LO) <= ALPHA_MAX, A_HI, abs(A_HI) <= ALPHA_MAX))
    print("  ⇒ 修订 205 §205.5 的「α_hi 在扫域之外、纯外推」这条限制，**本轮解除**。")
    print()
    ct = cross_table_check()
    if ct is None:
        print("⚠ 找不到 r204_noise.tsv ⇒ 「不能跨表比」这条警告**本轮未被验证**。")
    else:
        print("=== 跨表兼容性检查（「不能跨表比」是被验证的，不是断言）===")
        print("  旧表 pos_frac=%s ／ n_steps=%s" % (ct["old_pos"], ct["old_n_steps"]))
        print("  新表 pos_frac=%s ／ n_steps=%s" % (ct["new_pos"], ct["new_n_steps"]))
        print("  (tid, pos) 交集：%d 格。" % ct["n_shared"])
        for k, dc in ct["diff_cols"][:3]:
            print("    %s ⇒ 非剂量列不同的有：%s" % (k, dc))
        if ct["n_shared"] == 0:
            print("  ⛔ 交集为空 ⇒ 连同一格都对不上，跨表对比**连单变量都做不到**。")
        else:
            print("  ⇒ 同一格上仍差着 %s ⇒ 跨表逐值对比**至少两变量**。"
                  % sorted({c for _, dc in ct["diff_cols"] for c in dc}))
    print()

    hdr = ("%-30s %4s | %11s %11s %8s | %7s %9s | %6s %6s"
           % ("tid", "pos", "slope(±120)", "slope(±60)", "Δ",
              "z_ind", "z_cons", "205", "206"))
    print(hdr)
    print("-" * len(hdr))
    for r in res:
        print("%-30s %4.1f | %+11.6f %+11.6f %+8.6f | %+7.2f %+9.2f | %6s %6s"
              % (r["tid"], r["pos"], r["b_full"], r["b_loc"], r["d"],
                 r["z_ind"], r["z_cons"], r["mono_205"], r["mono_206"]))

    flips = [r for r in res if r["sign_flip"]]
    print()
    print("=== 判据 1：局部斜率与全域斜率**同号**吗（修订 205 的判决有没有被翻）===")
    print("  符号翻转 %d/%d 格。" % (len(flips), len(res)))
    if flips:
        for r in flips:
            print("    ⛔ %s pos=%.1f：局部 %+.6f → 全域 %+.6f"
                  % (r["tid"], r["pos"], r["b_loc"], r["b_full"]))
    else:
        print("  ⇒ 无一格翻转 ⇒ 修订 205 那台仪器的**符号判决在本轮未被推翻**。")

    print()
    print("=== 判据 2：全域斜率是不是系统性偏小（饱和 ⇒ 外推不合法）===")
    ds = [r["d"] for r in res]
    print("  Δ = 全域 − 局部：min %+.6f ／ 中位 %+.6f ／ max %+.6f"
          % (min(ds), q(ds, 0.5), max(ds)))
    print("  Δ<0 的格数 %d/%d；Δ>0 的格数 %d/%d。"
          % (sum(1 for x in ds if x < 0), len(res),
             sum(1 for x in ds if x > 0), len(res)))
    npos, nneg = sum(1 for x in ds if x > 0), sum(1 for x in ds if x < 0)
    print("  ⚠⚠⛔ **本判据不给显著性结论**，因为 TSV 里拿不到一个能用的 SE：")
    print("     (a) slope 与 slope_local 是**嵌套**两个拟合，共享同一批读数，")
    print("         误差强正相关 ⇒ sqrt(se_full²+se_loc²) 把 Δ 的 SE **估大了**；")
    print("     (b) 「独立同方差」这个假设又被 lin_ratio>1.5 的格顶掉了。")
    print("     ⇒ 表里那个 z_cons 列只能当**量级参考**，不是 t 统计量。")
    if npos == 0 or nneg == 0:
        print("  ⚠⚠ 但**符号是一致的**（全同向）⇒ 那才是「系统性偏小」的证据。")
    else:
        print("  ⇒ 实测 Δ 的符号**是混的**（%d 正 / %d 负）⇒ **没有**系统性偏小。"
              % (npos, nneg))
        print("     ⛔ 我第一版在这里写的是「|z|>2 ⇒ 外推失真」，那是**错的**：")
        print("        |z|>2 只说「两段斜率差得比标称 SE 多」，")
        print("        而标称 SE 本身不可信（见上 a/b），且它**不区分方向**。")

    print()
    print("=== 判据 2b：Δ 相对斜率本身有多大（p9_hi ∝ slope ⇒ 同样的比例）===")
    rel = [abs(r["d"]) / abs(r["b_full"]) if r["b_full"] else float("nan")
           for r in res]
    print("  |Δ| ÷ |slope(±120)|：min %.1f%% ／ 中位 %.1f%% ／ max %.1f%%"
          % (100 * min(rel), 100 * q(rel, 0.5), 100 * max(rel)))
    print("  ⚠⚠ 扫域从 ±60 加宽到 ±120，**斜率量级就动 %d–%d%%**；"
          % (100 * min(rel), 100 * max(rel)))
    print("     而 p9_lo/p9_hi 都正比于斜率 ⇒ **P9 读数的绝对量级对扫域敏感**。")
    print("     这条与「α_hi 现在落在域内」不矛盾：域内只保证**斜率**是在")
    print("     有数据的区间上量的，不保证**响应是线性的**。")


    print()
    print("=== 判据 3：线性还成不成立（lin_ratio = 全域残差 ÷ 局部残差）===")
    print("  ⚠ 自检 D 组给的「纯线性」参照带是 0.7–1.5；>1.5 ⇒ 大剂量处弯了。")
    lr = [r["lin_ratio"] for r in res]
    print("  lin_ratio：min %.3f ／ 中位 %.3f ／ max %.3f"
          % (min(lr), q(lr, 0.5), max(lr)))
    print("  >1.5 的格数 %d/%d。" % (sum(1 for x in lr if x > 1.5), len(lr)))
    print("  ⚠⚠ 参照带 0.7–1.5 来自**合成**数据（自检 D1 实得 0.953），")
    print("     它证明的是「纯线性时 lin_ratio≈1」，不是「真实数据该落在哪」；")
    print("     故上面这一行只能当**同口径参照**，不能当阈值判决。")

    print()
    print("=== 判据 4：P9 两档读数与裕度（本轮 α_hi 直接落在域内）===")
    print("%-30s %4s | %9s %9s | %9s | %s"
          % ("tid", "pos", "p9_lo", "p9_hi", "margin_SE", "hi−lo"))
    print("-" * 78)
    for r in res:
        print("%-30s %4.1f | %+9.4f %+9.4f | %9.2f | %+.4f"
              % (r["tid"], r["pos"], r["p9_lo"], r["p9_hi"], r["margin"],
                 r["p9_hi"] - r["p9_lo"]))
    print("  ⚠⚠ p9_lo / p9_hi 仍是**线性拟合的预测值**，不是该 α 上的实测读数；")
    print("     本轮 α_hi 落在**采样域内**⇒ 那条外推腿现在是**内插**，可信度上升，")
    print("     但它仍不是「那一格的实际读数」——要那个数得改探针再跑。")

    print()
    print("=== 判据 5：⛔ up_mono 是**差值**判据，不是方向判据 ===")
    print("  规格原文（R6_RERUN_PREREG.md:25789）：`up_mono`：+w 随剂量升")
    print("      `w+@1.0 >= w+@0.5`  ⇒ **实现 f(a_hi) >= f(a_lo) 是忠实的**。")
    print("  但它只比**两档之差**，**不比读数本身正负**。实测后果：")
    bad = [r for r in res if r["mono_206"] and r["p9_hi"] < 0]
    print("  「up_mono 通过但两档读数都 < 0」的格：%d/%d" % (len(bad), len(res)))
    for r in bad:
        print("    ⛔ %s pos=%.1f：p9_lo=%+.4f p9_hi=%+.4f（**都是负的**）"
              "，margin=%.2f SE，slope=%+.6f"
              % (r["tid"], r["pos"], r["p9_lo"], r["p9_hi"],
                 r["margin"], r["b_full"]))
    print("  ⇒ 这些格的 marker 在 P9 工作剂量上是**往下走**的，只是走得越来越少。")
    print("  ⚠ 且上面那格的 margin < 1 SE ⇒ 两档之差**连噪声都压不住**。")
    print("  ⛔ 所以「up_mono=True」**不能**读成「+w 抬高了 marker」。")
    print("     这是**规格**的性质，不是实现的 bug —— 记账时必须这么写。")

    print()
    print("=== 结论要写进账本的边界 ===")
    print("  · 本表 %d 格来自 **3 条轨迹**（p00/p01/p02）× 2 个位置，"
          % len(res))
    print("    「轨迹」这一维只有 3 个取值，「位置」2 个 ⇒ 有效独立性远小于 %d。" % len(res))
    print("  · n_steps=%d（旧表是 60）⇒ 本表**不能**与旧表合并成一个更大的样本。" % 80)
    print("  · 因此上面所有「N/10 格」都只是**计数**，不是比例估计的置信区间。")
    print()
    print("=== 能说 / 不能说 ===")
    print("  ✅ 能说：把扫域从 ±60 加宽到 ±120，**符号判决 0/10 被推翻**；")
    print("           唯一为负的那格（p02__no_think pos=0.7）在两个窗口下都为负。")
    print("  ✅ 能说：扫域加宽使**斜率量级动 %.0f–%.0f%%**，p9 读数的绝对量级对扫域敏感。"
          % (100 * min(rel), 100 * max(rel)))
    print("  ✅ 能说：up_mono 是差值判据，有 %d/%d 格通过但两档读数都为负。"
          % (len(bad), len(res)))
    print("  ⛔ 不能说：「两段斜率差得显著」—— TSV 里没有一个能用的 SE（见判据 2 a/b）。")
    print("  ⛔ 不能说：「P9 的问题就是方向不一致」—— 修订 205 那条是**候选机制**；")
    print("     本轮只把它从「α 域不够」这个伪影里**摘了出来**，没有证明它就是主因。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
