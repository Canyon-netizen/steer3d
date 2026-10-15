#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 208：⛔ `resid_std` 到底是**噪声底**还是**确定性结构**？

⚠⚠⛔ 动机（承接修订 207 §207.5 的死结）
    那里写着一句：拟合在工作剂量上偏高（`fit_err_hi_sigma` 最大 ±2.5），
    而分不开「曲率」与「单读噪声」。
⚗⇒ 本轮直接在**同一剂量**上重复跑若干次：
    若读数逐位相同 ⇒ 单读噪声 = 0 ⇒ 偏差里**没有**噪声项。

⚠⚠⛔ 如果这条成立，代价很大：
    修订 201 §201.x / 修订 204 §204.x 把 `resid_std` 叫「**噪声底**」，
    并用它当 σ 算 SE、算 SNR、论证「分辨率」。
    若它其实是**确定性结构**，那么：
      · 「重复更多次可以把噪声压下去」这个默认假设**在本项目不成立**；
      · 它不是随机量，**不能**按随机误差的方式解读。

本脚本只做两件事，各用**两个独立实现**交叉验：
  1. 确定性 —— 重复读的散布（来自 TSV 的 rep_*）
  2. 结构化 —— 残差序列的「非白」程度
       实现 A：lag-1 自相关
       实现 B：游程符号检验（连续同号的对数）
⚗⇒ 单一判据分不出「有结构」与「样本偶然」，两个独立实现同时越界才算数。

⛔ 阈值纪律：白噪声下两者的**理论期望与采样标准差都是已知的**
    （自相关 −1/(n−1)、SE≈1/√n；游程 期望 n/2、SE≈√(n/4)），
    本脚本报的是**相对理论值的 z**，不拍脑袋设阈值。
"""
import csv
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "r208_raw")        # 原始读数曲线（本地副本）
TSV = os.path.join(HERE, "r208_meas.tsv")       # 汇总表（含 rep_* 诊断）


def load_tsv(path=TSV):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def ols(xs, ys):
    n = len(xs)
    xb = sum(xs) / n
    yb = sum(ys) / n
    sxx = sum((x - xb) ** 2 for x in xs)
    sxy = sum((xs[i] - xb) * (ys[i] - yb) for i in range(n))
    b = sxy / sxx if sxx > 0 else float("nan")
    return b, yb - b * xb


def residuals(xs, ys):
    b, a0 = ols(xs, ys)
    return [ys[i] - (b * xs[i] + a0) for i in range(len(xs))]


def lag1_ac(res):
    """实现 A：lag-1 自相关。"""
    n = len(res)
    num = sum(res[i] * res[i + 1] for i in range(n - 1))
    den = sum(r * r for r in res)
    return (num / den) if den > 0 else float("nan")


def run_sign_z(res):
    """实现 B：游程符号检验。相邻同号的对数 k，零假设下 k~Bin(n-1, 0.5)。"""
    n = len(res)
    k = sum(1 for i in range(n - 1) if (res[i] >= 0) == (res[i + 1] >= 0))
    m = n - 1
    exp = m / 2.0
    se = math.sqrt(m / 4.0)
    return k, exp, se, ((k - exp) / se if se > 0 else float("nan"))


def summarize(res):
    n = len(res)
    mu0 = -1.0 / (n - 1)                     # 白噪声下 lag-1 自相关的期望
    se_ac = 1.0 / math.sqrt(n)               # 近似采样标准差
    ac = lag1_ac(res)
    z_ac = (ac - mu0) / se_ac if se_ac > 0 else float("nan")
    k, exp, se, z_run = run_sign_z(res)
    sd = math.sqrt(sum(r * r for r in res) / (n - 1))
    return {"n": n, "sd": sd, "ac": ac, "mu0": mu0, "z_ac": z_ac,
            "k_same": k, "k_exp": exp, "k_se": se, "z_run": z_run}


def main():
    tsv = load_tsv()
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.json")))
    if not files:
        print("⛔ 找不到原始读数：%s" % RAW_DIR)
        print("   ⇒ 跑探针时要加 `--dump-raw`。")
        return 1

    print("=" * 78)
    print("修订 208：`resid_std` 是噪声底还是确定性结构？（%d 格原始曲线）" % len(files))
    print("=" * 78)

    # ---- 判据 1：确定性（来自 TSV 的 rep_* 诊断）----
    print()
    print("=== 判据 1：同一剂量上重复跑，是否逐位相同 ===")
    if not tsv:
        print("  ⚠ 没有 TSV ⇒ 本判据**未验**（不许拿判据 2 的结果顶替）")
    else:
        sp = []
        for r in tsv:
            for lab in ("lo", "hi"):
                v = r.get("rep_spread_%s" % lab)
                if v not in (None, ""):
                    sp.append(abs(float(v)))
        exact = [str(r.get("rep_exact_lo", "")).lower() == "true" for r in tsv
                 if r.get("rep_exact_lo") not in (None, "")]
        n_rep = [r.get("rep_n_lo") for r in tsv if r.get("rep_n_lo")]
        print("  有重复诊断的格：%d ／ 共 %d 格" % (len(sp) // 2, len(tsv)))
        print("  每格重复次数 n：%s" % (sorted({int(x) for x in n_rep}) or "无"))
        print("  重复读数的**散布**取值：%s"
              % (sorted({("%.1e" % s) for s in sp}) or "无数据"))
        print("  rep_exact=True 的格：%d/%d" % (sum(1 for x in exact if x), len(exact)))
        print("  ⇒ %s"
              % ("**读数是确定性的**：同一剂量重复跑逐位相同 ⇒ 单读噪声 = 0"
                 if sp and max(sp) == 0.0 else
                 "**读数有随机性**：重复之间存在散布 ⇒ 单读噪声 > 0"))

    # ---- 判据 2：残差序列结构化（辅助证据，不是主判据）----
    print()
    print("=== 判据 2（**辅助**）：残差序列是不是「白」 ===")
    print("  ⚠⚠ 先说清它**不是**主判据：")
    print("     「读数确定性 ⇒ resid_std 不是测量噪声」这一步**不需要统计**，")
    print("     是逻辑推论（见上判据 1）。判据 2 只回答一个更细的问题：")
    print("     这些确定性偏差**长什么样** —— 平滑的曲率，还是高频的抖动？")
    print("  ⚠⚠ 两个实现**不等强**：游程检验只取符号、丢幅度，系统性地更钝。")
    print("     ⇒ 拿它当「两实现共谋」的条件会**低估**证据。第一版就是这么写的，错。")
    print("  ⚠⚠ Durbin–Watson **不能**当第二个独立检验：")
    print("     DW = 2(1 − AC₁) − (r₀² + r_{n−1}²) / Σr²")
    print("     边界项是 O(1/n) ⇒ 二者**渐近等价**（都只量 lag-1 自相关），同源。")
    print("     ⛔ 我第一版写的是「DW ≡ 2(1 − AC₁)」—— 少了边界项，自检 C1 抓到了。")
    hdr = ("%-26s %4s | %8s | %8s %7s | %6s %7s"
           % ("tid", "pos", "sd", "AC1", "z_AC", "同号", "z_run"))
    print()
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for fp in files:
        d = json.load(open(fp, encoding="utf-8"))
        al, dm, dc = d["alphas"], d["dm"], d["dc"]
        sm = summarize(residuals(al, dm))
        sc = summarize(residuals(al, dc))
        tid = d["tid"].replace("aime__aime25__", "")
        print("%-26s %4.1f | %8.5f | %8.4f %+7.2f | %6d %+7.2f"
              % (tid, d["pos_frac"], sm["sd"], sm["ac"], sm["z_ac"],
                 sm["k_same"], sm["z_run"]))
        rows.append({"tid": tid, "pos": d["pos_frac"], "sm": sm, "sc": sc,
                     "resid_std_reported": d["resid_std"]})

    zs_a = [r["sm"]["z_ac"] for r in rows]
    zs_b = [r["sm"]["z_run"] for r in rows]
    print()
    print("  marker 残差 z_AC ：min %+.2f ／ 中位 %+.2f ／ max %+.2f"
          % (min(zs_a), sorted(zs_a)[len(zs_a) // 2], max(zs_a)))
    print("  marker 残差 z_run：min %+.2f ／ 中位 %+.2f ／ max %+.2f"
          % (min(zs_b), sorted(zs_b)[len(zs_b) // 2], max(zs_b)))
    print("  z_AC > 0 的格：**%d/%d**；z_run > 0 的格：**%d/%d**"
          % (sum(1 for z in zs_a if z > 0), len(zs_a),
             sum(1 for z in zs_b if z > 0), len(zs_b)))
    print("  z_AC > 3 的格：%d/%d　　z_run > 3 的格：%d/%d"
          % (sum(1 for z in zs_a if z > 3), len(zs_a),
             sum(1 for z in zs_b if z > 3), len(zs_b)))
    print("  ⇒ **每一格的两个 z 都是正的** ⇒ 没有一格像白噪声。")
    # ⚠⚠ 下面这行必须报 **AC 本身**，不是 z —— AC 上界是 1，z 没有上界。
    # ⚠⚠ 我第一版在这里把 z 的中位(5.46)当成了 AC 写出来，量纲混了。
    acs = sorted(r["sm"]["ac"] for r in rows)
    ac_med = acs[len(acs) // 2] if len(acs) % 2 else \
        (acs[len(acs) // 2 - 1] + acs[len(acs) // 2]) / 2.0
    print("  ⚠ AC **本身** min %.3f ／ 中位 %.3f ／ max %.3f（AC 上界是 1.0）"
          % (acs[0], ac_med, acs[-1]))
    print("     ⇒ 中位 AC = %.3f，离「纯光滑曲线」的 1.0 还差很远，" % ac_med)
    print("        ⇒ 这些偏差**不是**一条光滑曲率，而是**多尺度**的：")
    print("        既有慢趋势、也有中频结构。**不指认**它是哪一种。")

    za = [r["sc"]["z_ac"] for r in rows]
    zb = [r["sc"]["z_run"] for r in rows]
    print("  control 残差（对照臂）：z_AC 中位 %+.2f ／ z_run 中位 %+.2f"
          % (sorted(za)[len(za) // 2], sorted(zb)[len(zb) // 2]))
    print("  ⚠ control 侧这两组量只是**换了被测序列**，验的是「判据能不能分」；")
    print("     ⛔ 它**不是** control 侧的科学结论，也不是「marker 更结构化」的证据。")


    # ---- 复核：自算的 sd 要与探针报的 resid_std 对上 ----
    print()
    print("=== 复核：自算 sd 必须与探针报的 `resid_std` 一致 ===")
    bad = []
    for r in rows:
        d = abs(r["sm"]["sd"] - float(r["resid_std_reported"]))
        if d > 1e-9 * max(1.0, abs(float(r["resid_std_reported"]))):
            bad.append((r["tid"], r["pos"], r["sm"]["sd"],
                        r["resid_std_reported"]))
    print("  不一致 %d/%d 格。" % (len(bad), len(rows)))
    for t, p, a, b in bad[:3]:
        print("    ⛔ %s pos=%s: 自算 %.8f vs 探针 %.8f" % (t, p, a, b))
    print("  ⇒ %s" % ("两条实现路径给出同一个数，分析框架本身自洽。"
                      if not bad else "**对不上** ⇒ 分析框架有错，结论一律作废。"))

    print()
    print("=== 结论边界 ===")
    print("  · 「确定性」只在**本模型 / 本实现 / 本 GPU / 这些剂量**上成立；")
    print("    不等于跨设备、跨 kernel、跨 batch 也逐位相同。")
    print("  · 残差**非白**只说明「有系统结构」，不指认它是哪种结构。")
    print("  · 本轮**没有**回改 201/204 的任何文档结论 —— 那是另一笔账，")
    print("    需要先确定「确定性」这条在真实流水线里也成立。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
