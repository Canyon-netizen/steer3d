#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 211：`probe(all)` 与流水线锚点，**多格**对账。

⚖ 承接修订 210 的单格结论：
    probe(all) − pipeline = **+0.000e+00**（1 格 / 1 个 α）
⚗⇒ 「两者等价」这句话当时**只在这一格成立**。
⚗⇒ 本脚本把锚点从 1 个扩到 10 格，逐格报 Δ。

⛔⛔ 两条硬规矩（都是从踩过的坑里来的）
  1. 对账**只用落盘原始浮点**，绝不用日志里的 `%.6f` 转录值
     —— 我曾用转录值当权威，把 4.3e-07 的舍入差判成「不一致」。
  2. ⛔ 锚点缺失必须**显式报出**，不许静默跳过 ——
     少比一格而报告仍说「10/10 一致」，那是最坏的一种错。

⚖ 判据
    逐格 Δ = probe(all) − 流水线锚点
    ✅ 逐位一致 ⇒ Δ **恰为 0.0**
    ⛔ 修订 209 已实测三个配置的 Δ 全为 **0**（不是 1e-9 量级），
       ⇒ 正确判据是 `== 0`，不是「小于某个容差」。
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHORS = os.path.join(HERE, "r211_anchors.json")
PROBE_TSV = os.path.join(HERE, "r210_all10.tsv")


def load_tsv(p):
    if not os.path.exists(p):
        return None
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    if not os.path.exists(ANCHORS):
        print("⛔ 找不到锚点 %s" % ANCHORS)
        print("   ⇒ 跑 `r209_pipeline_determinism.py --out` 落盘它。")
        return 1
    if not os.path.exists(PROBE_TSV):
        print("⛔ 找不到探针表 %s" % PROBE_TSV)
        return 1

    anc = json.load(open(ANCHORS, encoding="utf-8"))
    probe = load_tsv(PROBE_TSV)
    pmap = {(r["tid"], r["pos_frac"]): r for r in probe}

    # 锚点取 D 配置（流水线原样）
    amap = {}
    for c in anc["cells"]:
        d = [x for x in c["configs"] if x["name"].startswith("D")][0]
        a = [x for x in c["configs"] if x["name"].startswith("A")][0]
        amap[(c["tid"], str(c["pos_frac"]))] = {"D": d["mark"], "A": a["mark"],
                                               "exact": d["exact"],
                                               "seq_len": c["seq_len"],
                                               "t": c["t"]}

    print("=" * 78)
    print("修订 211：probe(all) vs 流水线锚点，多格对账（%d 个锚点）" % len(amap))
    print("=" * 78)
    print("  锚点剂量 α = %.3f（脚本直接传的 `--alpha`）" % anc["alpha"])
    # ⚠⚠⛔ gap 必须从**探针表**读，不能拿锚点的 alpha 去乘 0.5 ——
    # ⚠⚠⛔ 锚点的 alpha **就是** 0.5·gap 本身，再乘一次就变成 0.25·gap。
    # ⚠⚠⛔ 我第一版就是这么写的，表头印出「28.369」（实际剂量是 56.737），
    # ⚠⚠⛔ **比较本身仍有效**（两边确实同剂量），但那行描述是错的。
    gaps = {float(r["gap"]) for r in probe if r.get("gap")}
    for g in gaps:
        print("  探针 gap = %.6f ⇒ p9_lo_meas 取在 α = 0.5·gap = %.3f"
              % (g, 0.5 * g))
    if len(gaps) > 1:
        print("  ⛔ 探针表里有**多个 gap** ⇒ 必须逐格核对，不能一栏概括。")
    print("  ⚠⚠ 用的是**落盘原始浮点**，不是日志打印值。")

    print()

    missing = [k for k in amap if k not in pmap]
    print("  ⚠ 探针侧缺 %d 格：%s" % (len(missing), missing[:3] if missing else "无"))
    if missing:
        print("  ⛔ 有锚点没比上 ⇒ **不能**报「全部一致」。")

    hdr = ("%-26s %4s | %18s %18s | %12s | %s"
           % ("tid", "pos", "流水线锚点(D)", "probe(all)", "Δ", "逐位一致"))
    print()
    print(hdr)
    print("-" * len(hdr))
    n_zero = n_cmp = 0
    worst = 0.0
    rows = []
    for k in sorted(amap):
        if k not in pmap:
            continue
        r = pmap[k]
        pv = float(r["b_mark"]) + float(r["p9_lo_meas"])
        av = amap[k]["D"]
        d = pv - av
        ok = (d == 0.0)
        n_cmp += 1
        n_zero += ok
        worst = max(worst, abs(d))
        tid = k[0].replace("aime__aime25__", "")
        print("%-26s %4s | %18r %18r | %12.3e | %s"
              % (tid, k[1], av, pv, d, "✅" if ok else "⛔"))
        rows.append((tid, k[1], av, pv, d, ok, amap[k]["A"]))

    print()
    print("  逐位一致：**%d/%d 格**" % (n_zero, n_cmp))
    print("  最大 |Δ| = %.3e" % worst)

    # ⛔ 判据必须能红：把某个锚点人为挪动一点，就必须被抓到
    print()
    print("=== 判据的反证（变异：把一个锚点挪 1e-6）===")
    t0, p0, a0, v0, d0, ok0, _a0 = rows[0]
    bad_d = v0 - (a0 + 1e-6)
    check_red = not (bad_d == 0.0)
    print("  变异后该格 Δ = %+.3e ⇒ 判据仍判「不一致」：%s"
          % (bad_d, "✅ 有分辨力" if check_red else "⛔ 无分辨力"))
    print("  ⇒ 单靠「Δ 恰为 0」这个判据，就能分辨 %+.3e 的差异。" % bad_d)

    print()
    print("=== 附带：A（探针原样 single）与 D（流水线）的差 = 口径代价 ===")
    for (tid, pos, av, pv, d, ok, a_val) in rows:
        print("    %-24s pos=%s  A − D = %+.6f" % (tid, pos, a_val - av))
    gaps = [abs(r[6] - r[2]) for r in rows]
    print("  |A−D| 中位 %.6f ／ max %.6f" % (sorted(gaps)[len(gaps) // 2],
                                            max(gaps)))
    print("  ⚠ 这是**两个口径**的差，不是测量误差；⛔ 两批读数不可混进同一个汇总。")

    print()
    print("=== 边界 ===")
    print("  · 锚点只覆盖 α = %.3f 这**一个**剂量；⛔ 其它剂量未对。" % anc["alpha"])
    print("  · 10 格来自 3 条轨迹 × 2 位置（承修订 206/208）。")
    print("  · ⛔ 锚点与探针都是**同一块 GPU、同一个模型**，")
    print("    ⛔ 跨设备/跨 kernel 的等价性**未验**。")
    return 0 if n_zero == n_cmp and n_cmp > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
