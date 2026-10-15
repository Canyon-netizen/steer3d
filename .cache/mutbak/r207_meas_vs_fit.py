#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 207：P9 的两个工作剂量上**真测**读数 ⇒ 拟合代入有没有把判决带偏。

⚠⚠⚴ 动机（账本 R6_RERUN_PREREG.md:25789 / :25824）
    规格写的是 `w+@1.0 >= w+@0.5`，而 :25824 自己标注
    「P9 的 `up_mono` 用的是**单次读数**，不是拟合」。
    ⇒ 修订 205/206 探针把两个剂量**代进拟合直线**取值，那是**替换**。
⚗⇒ 本轮在 α=0.5·gap 与 α=1.0·gap 上**各真跑一次 forward**，得到
    规格真正要的那两个数，并与拟合版**逐格对账**。

⛔ 与修订 206 那张表的关系（本脚本**自己验**，不是断言）
    r206_p9band.tsv 与 r207_meas.tsv 的配置**逐项相同**（pos 集合、
    n_steps、α 网格、gap 都一样），本轮只**多采了两个读数**。
    ⇒ 网格那 80 点的读数应当**逐位相同**。
⚗⇒ 所以脚本先核对这一点：对不上 ⇒ 两表**不可比**，直接退出 4。

问的三个问题
  Q1 拟合代入把 `up_mono` 的判决带偏了几格？带偏的是往哪边？
  Q2 拟合在工作剂量上偏了多少（用 resid_std 当 σ 的尺子）？
     —— 偏得是**常数**（截距口径问题）还是**随剂量增长**（曲率问题）？
  Q3 实测版下「两档读数都为负却通过」这类格还剩几格？
"""
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TSV = os.path.join(HERE, "r207_meas.tsv")
REF = os.path.join(HERE, "r206_p9band.tsv")     # 修订 206 的同一批格

# 两表应当逐位相同的列（网格侧；本轮没动过这些量）
SAME_COLS = ["t", "n_gen", "P", "n_steps", "slope", "resid_std",
             "slope_local", "resid_std_local", "lin_ratio", "n_distinct",
             "min_adj_diff", "ctl_n_distinct", "ctl_min_adj_diff",
             "dm_min", "dm_max", "gap", "p9_lo", "p9_hi",
             "p9_se_lo", "p9_se_hi", "p9_up_mono", "p9_margin_se"]


def load(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return float("nan")


def key(r):
    return (r["tid"], r["pos_frac"])


def verify_same_grid(rows):
    """⛔ 两表是不是同一批网格读数 —— 对不上就**不许**做后续对比。"""
    if not os.path.exists(REF):
        print("⛔ 找不到参照表 %s ⇒ 本轮**无法**与修订 206 对账。" % REF)
        return None
    ref = {key(r): r for r in load(REF)}
    got = {key(r): r for r in rows}
    shared = sorted(set(ref) & set(got))
    if not shared:
        print("⛔⛔ 两表 (tid,pos) 交集为 **0 格** ⇒ 不可比。")
        return None
    bad = []
    for k in shared:
        for c in SAME_COLS:
            a, b = ref[k].get(c), got[k].get(c)
            if a is None or b is None:
                bad.append((k, c, "缺列"))
            elif num(a) != num(b) and a != b:
                bad.append((k, c, "%s vs %s" % (a, b)))
    return {"n_shared": len(shared), "bad": bad}


def classify(rows):
    out = []
    for r in rows:
        fit_mono = (r.get("p9_up_mono") or "").strip().lower() == "true"
        ms = (r.get("up_mono_meas") or "").strip().lower()
        # ⛔ 没测到时它会被写成空串 ⇒ 必须区别于 False，不能当 False。
        meas_mono = None if ms in ("", "none", "null") else (ms == "true")
        out.append({
            "tid": r["tid"], "pos": num(r["pos_frac"]),
            "fit_lo": num(r["p9_lo"]), "fit_hi": num(r["p9_hi"]),
            "ms_lo": num(r.get("p9_lo_meas")),
            "ms_hi": num(r.get("p9_hi_meas")),
            "fit_mono": fit_mono, "meas_mono": meas_mono,
            "err_lo": num(r.get("fit_err_lo")),
            "err_hi": num(r.get("fit_err_hi")),
            "err_hi_sigma": num(r.get("fit_err_hi_sigma")),
            "margin_fit": num(r.get("p9_margin_se")),
            "margin_meas": num(r.get("margin_meas")),
            "resid": num(r.get("resid_std")),
            "lin_ratio": num(r.get("lin_ratio")),
        })
    return out


def q(xs, p):
    xs = sorted(x for x in xs if x == x)      # 丢 nan
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - k) + xs[hi] * (k - lo)


def main():
    rows = load(TSV)
    if not rows:
        print("⛔ TSV 为空：%s" % TSV)
        return 1
    chk = verify_same_grid(rows)
    if chk is None:
        return 4
    print("=" * 78)
    print("修订 207：P9 工作剂量的**实测读数** vs 拟合代入（%d 格）" % len(rows))
    print("=" * 78)
    if chk["bad"]:
        print("⛔⛔ 与修订 206 表**对不上**，本轮不可比，共 %d 处不同：" % len(chk["bad"]))
        for k, c, v in chk["bad"][:5]:
            print("    %s %s: %s" % (k, c, v))
        return 4
    print("✅ 与修订 206 表的 %d 格**逐位相同**（%d 列全等）"
          % (chk["n_shared"], len(SAME_COLS)))
    print("   ⇒ 两表是**同一批网格读数**，本轮只多采了 2 个剂量点。")
    print()

    cs = classify(rows)
    not_meas = [r for r in cs if r["meas_mono"] is None]
    if not_meas:
        print("⛔⛔ **%d/%d 格没有实测读数**（up_mono_meas 为空）——"
              " 不得把空读成 False。" % (len(not_meas), len(cs)))
        return 4

    print("=== Q1：拟合代入把 up_mono 的判决带偏了吗 ===")
    hdr = ("%-30s %4s | %9s %9s | %9s %9s | %5s %5s"
           % ("tid", "pos", "fit_lo", "fit_hi", "ms_lo", "ms_hi",
              "拟合", "实测"))
    print(hdr)
    print("-" * len(hdr))
    for r in cs:
        print("%-30s %4.1f | %+9.4f %+9.4f | %+9.4f %+9.4f | %5s %5s"
              % (r["tid"], r["pos"], r["fit_lo"], r["fit_hi"],
                 r["ms_lo"], r["ms_hi"], r["fit_mono"], r["meas_mono"]))

    dis = [r for r in cs if r["fit_mono"] != r["meas_mono"]]
    flip_g2m = [r for r in dis if r["fit_mono"] and not r["meas_mono"]]
    flip_m2g = [r for r in dis if r["meas_mono"] and not r["fit_mono"]]
    print()
    print("  判决不一致：**%d/%d 格**" % (len(dis), len(cs)))
    print("    拟合说通过、实测说不过：%d 格" % len(flip_g2m))
    for r in flip_g2m:
        print("      ⛔ %s pos=%.1f  实测 lo=%+.4f hi=%+.4f（**hi 比 lo 更低**）"
              % (r["tid"], r["pos"], r["ms_lo"], r["ms_hi"]))
    print("    实测说通过、拟合说不过：%d 格" % len(flip_m2g))
    for r in flip_m2g:
        print("      %s pos=%.1f  实测 lo=%+.4f hi=%+.4f"
              % (r["tid"], r["pos"], r["ms_lo"], r["ms_hi"]))
    print("  拟合通过率 %d/%d ／ 实测通过率 %d/%d"
          % (sum(1 for r in cs if r["fit_mono"]), len(cs),
             sum(1 for r in cs if r["meas_mono"]), len(cs)))

    print()
    print("=== Q2：拟合在工作剂量上偏了多少（σ = resid_std）===")
    es = [r["err_hi_sigma"] for r in cs]
    print("  fit_err_hi_sigma：min %+.2f ／ 中位 %+.2f ／ max %+.2f"
          % (min(es), q(es, 0.5), max(es)))
    print("  正（拟合**低估**）%d/%d，负（拟合**高估**）%d/%d"
          % (sum(1 for x in es if x > 0), len(cs),
             sum(1 for x in es if x < 0), len(cs)))
    print("  |fit_err_hi_sigma| > 1 的格数：%d/%d" % (sum(1 for x in es if abs(x) > 1), len(cs)))
    print()
    print("  ⚖ 是**常数偏移**还是**曲率**？判别量 = err_hi − err_lo")
    print("  （两个剂量不同 ⇒ 若拟合只是整体平移，这个差会≈0；若有曲率，它会≠0）")
    dif = [r["err_hi"] - r["err_lo"] for r in cs]
    print("  err_hi − err_lo：min %+.4f ／ 中位 %+.4f ／ max %+.4f"
          % (min(dif), q(dif, 0.5), max(dif)))
    offs = [r["err_lo"] for r in cs]
    print("  err_lo（常数偏移量）：中位 %+.4f" % q(offs, 0.5))
    print("  ⇒ 偏移中位数 %+.4f，剂量间变化中位数 %+.4f（前者/后者 = %.2f）"
          % (q(offs, 0.5), q(dif, 0.5),
             abs(q(offs, 0.5)) / abs(q(dif, 0.5)) if q(dif, 0.5) else float("inf")))
    print()
    print("  ⛔⛔⛔ **本节不下「偏移 vs 曲率」的结论**，理由：")
    print("     每个剂量上的读数是**一次 forward**。于是")
    print("        err_hi − err_lo = （真·剂量间变化） + （两次单读噪声之差）")
    print("     而**本表里没有任何量能把它剥掉** —— 没有重复读数、没有跨格 σ。")
    print("     ⛔ 单读噪声有多大，本表**测不到** ⇒ 两个项谁主导，说不清。")
    print("     ⚠⚠ 第一版这里写了「主要是曲率」—— 那是**越权**：")
    print("        判别量看起来是曲率占优，但在没量到单读噪声之前，")
    print("        同样的数字也能由「纯噪声 + 零曲率」产生。")
    print("     ⚗ 与修订 206 §206.6 同一个病：数字整齐，但判据量不出我要的轴。")
    print("  ⚗⇒ 要解这个混淆，必须让探针**导出原始读数曲线 dm**（或对同一剂量")
    print("     重复跑若干次量单读噪声）。本轮**没做**。")

    print()
    print("=== Q3：实测版下「两档读数都为负」还剩几格 ===")
    negpass = [r for r in cs if r["meas_mono"] and r["ms_hi"] < 0]
    negall = [r for r in cs if r["ms_hi"] < 0]
    print("  实测 hi < 0 的格：%d/%d" % (len(negall), len(cs)))
    print("  ⛔ 其中「实测通过」：**%d** 格" % len(negpass))
    for r in negpass:
        print("    ⛔ %s pos=%.1f  lo=%+.4f hi=%+.4f margin=%.2f sigma"
              % (r["tid"], r["pos"], r["ms_lo"], r["ms_hi"], r["margin_meas"]))
    if not negpass:
        print("  ⇒ 实测口径下，「读数为负却通过 up_mono」这类格**归零**。")

    print()
    print("=== 裕度：拟合的 SE 与实测的 σ 不是一回事 ===")
    print("  margin_meas（实测差 ÷ resid_std）：min %.2f ／ 中位 %.2f ／ max %.2f"
          % (min(r["margin_meas"] for r in cs),
             q([r["margin_meas"] for r in cs], 0.5),
             max(r["margin_meas"] for r in cs)))
    print("  margin(拟合 SE)：min %.2f ／ 中位 %.2f ／ max %.2f"
          % (min(r["margin_fit"] for r in cs),
             q([r["margin_fit"] for r in cs], 0.5),
             max(r["margin_fit"] for r in cs)))
    print("  ⚠⚠ 这两列**分母不同**（一个是标准误、一个是残差 std），")
    print("     **不可互换**，也不可拿它们的比值下任何结论。")

    print()
    print("=== 边界 ===")
    print("  · %d 格来自 3 条轨迹 × 2 位置（承修订 206 §206.9）" % len(cs))
    print("  · resid_std 是**这一格内部** 80 个读数的残差，不是跨格噪声底")
    print("    ⇒ fit_err_hi_sigma 是「相对本格噪声」，不是显著性检验。")
    print("  · 口径冻结：本轮只**换读数来源**，不改判据定义。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
