#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 212：`probe(all)` 与流水线锚点，**双剂量**（0.5·gap 与 1.0·gap）对账。

⚖ 承接：
    修订 211 —— 10/10 格逐位一致，但只覆盖 α = 56.737 **一个**剂量，
                且那个锚点跑的是 `--alpha 56.737`（截断值），
                与探针的 0.5·gap 差 2.0e-04 ⇒ 靠 bf16 抹平。
⚗⇒ 本轮锚点改用**精确剂量**，并同时覆盖 1.0·gap（= P9 的最高工作剂量）。

⛔⛔ 两条硬规矩（都从踩过的坑里来）
  1. 对账**只用落盘原始浮点**，绝不用日志里的打印值。
  2. 剂量必须**逐字相等**。若两边剂量不同，先说清差多少、为什么读数仍相同
     （上次是 bf16 相对精度把 3.6e-06 的相对差抹平了 —— 那是**另一回事**）。

判据：Δ 恰为 0.0（不是「小于某个容差」）。理由见修订 209：A/B/C 三配置 Δ 全为 0。
"""
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHORS = os.path.join(HERE, "r212_anchors.json")
PROBE_TSV = os.path.join(HERE, "r210_all10.tsv")

# 探针里哪个量对哪个剂量
PROBE_COL = {"0.5": "p9_lo_meas", "1.0": "p9_hi_meas"}


def load_tsv(p):
    if not os.path.exists(p):
        return None
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def nearest_dose(alpha, gap):
    """把锚点剂量归到 0.5·gap 还是 1.0·gap，并报出剂量差。"""
    for tag, mult in (("0.5", 0.5), ("1.0", 1.0)):
        ref = mult * gap
        if abs(alpha - ref) < 1e-9:
            return tag, 0.0
    # 都没逐字对上 ⇒ 取最近的那个并报出差
    best = min((("0.5", 0.5 * gap), ("1.0", gap)), key=lambda x: abs(alpha - x[1]))
    return best[0], alpha - best[1]


def main():
    for p in (ANCHORS, PROBE_TSV):
        if not os.path.exists(p):
            print("⛔ 找不到 %s" % p)
            return 1
    anc = json.load(open(ANCHORS, encoding="utf-8"))
    probe = load_tsv(PROBE_TSV)
    pmap = {(r["tid"], r["pos_frac"]): r for r in probe}
    gaps = sorted({float(r["gap"]) for r in probe if r.get("gap")})
    if len(gaps) > 1:
        print("⛔⛔ 探针表里有**多个 gap**（%s）⇒ 必须逐格核对，不能一栏概括。" % gaps)
        return 4
    gap = gaps[0]

    print("=" * 78)
    print("修订 212：probe(all) vs 流水线锚点，双剂量对账")
    print("=" * 78)
    print("  gap = %.12f ⇒ 两个工作剂量：0.5·gap = %.12f，1.0·gap = %.12f"
          % (gap, 0.5 * gap, gap))
    print("  锚点落盘剂量：%s" % ["%.12f" % x for x in anc["alphas"]])
    print()

    # ---- 剂量核对：逐字相等吗 ----
    print("=== 剂量核对（⛔ 不逐字相等就必须先说清差多少）===")
    dose_map = {}
    for al in anc["alphas"]:
        tag, d = nearest_dose(al, gap)
        # ⛔⛔ 键必须是**同一个字符串**：探针脚本把 by_alpha 建成
        #    "%.12f" % alpha 的键，而 JSON 里的 alphas 仍是原始浮点。
        #    ⛔ 我第一版用原始浮点建字典、再拿字符串去查 ⇒ KeyError。
        dose_map["%.12f" % al] = tag
        print("  锚点 α=%.12f ⇒ 对应探针的 %s；剂量差 %+.3e"
              % (al, PROBE_COL[tag], d))
        if d != 0.0:
            print("     ⛔ **不逐字相等** ⇒ 下面的一致性可能只是 bf16 把差抹平了。")
    print()

    n_by_tag = {}
    for tag in dose_map.values():
        n_by_tag[tag] = n_by_tag.get(tag, 0) + 1
    print("  锚点剂量覆盖：%s%s"
          % (n_by_tag,
             "" if len(n_by_tag) == 2 else "  ⛔ 两个工作剂量**没有**都覆盖！"))
    print()

    rows = []
    n_zero = n_cmp = 0
    for c in anc["cells"]:
        tid, pos = c["tid"], str(c["pos_frac"])
        if (tid, pos) not in pmap:
            continue
        r = pmap[(tid, pos)]
        for _al, blk in c["by_alpha"].items():
            if _al not in dose_map:
                print("⛔⛔ 锚点 JSON 里的剂量键 %r 在 alphas 里找不到 ⇒ 跳过并报错"
                      % _al)
                return 4
            tag = dose_map[_al]

            col = PROBE_COL[tag]
            pv = float(r["b_mark"]) + float(r[col])
            d_cfg = [x for x in blk["configs"] if x["name"].startswith("D")][0]
            a_cfg = [x for x in blk["configs"] if x["name"].startswith("A")][0]
            av = d_cfg["mark"]
            d = pv - av
            ok = (d == 0.0)
            n_cmp += 1
            n_zero += ok
            rows.append((tid.replace("aime__aime25__", ""), pos, tag,
                         av, pv, d, ok, a_cfg["mark"]))

    hdr = ("%-24s %4s %4s | %20s %20s | %11s | %s"
           % ("tid", "pos", "剂量", "流水线锚点(D)", "probe(all)", "Δ", "逐位"))
    print(hdr)
    print("-" * len(hdr))
    for x in rows:
        print("%-24s %4s %4s | %20r %20r | %11.3e | %s"
              % (x[0], x[1], x[2], x[3], x[4], x[5], "✅" if x[6] else "⛔"))
    print()
    print("  逐位一致：**%d/%d**" % (n_zero, n_cmp))
    for tag in sorted({x[2] for x in rows}):
        sub = [x for x in rows if x[2] == tag]
        z = sum(1 for x in sub if x[6])
        print("    %s·gap（探针列 %s）：%d/%d"
              % (tag, PROBE_COL[tag], z, len(sub)))

    gapsAD = [abs(x[7] - x[3]) for x in rows]
    print()
    print("  口径代价 |A−D|：中位 %.6f ／ max %.6f"
          % (sorted(gapsAD)[len(gapsAD) // 2], max(gapsAD)))
    n_pos = sum(1 for g in gapsAD if x is not None)
    print("  ⚠ 这个差**有正有负**（见修订 211）⇒ 不是修正项。")

    print()
    print("=== 判据的反证（把一个锚点挪 1e-6）===")
    t0, p0, g0, a0, v0, d0, ok0, _ = rows[0]
    bad_d = v0 - (a0 + 1e-6)
    print("  变异后 Δ = %+.3e ⇒ 判「不一致」：%s"
          % (bad_d, "✅ 有分辨力" if bad_d != 0.0 else "⛔ 无分辨力"))

    print()
    print("=== 边界 ===")
    print("  · 只覆盖 P9 的两个工作剂量；⛔ α 网格中间点未对。")
    print("  · 只比**第 0 步**（读完 prefix 那一刻）；生成后续步未验。")
    print("  · 锚点与探针**同一块 GPU、同一模型** ⇒ 跨设备等价性未验。")
    print("  · 10 格来自 3 条轨迹 × 2 位置。")
    return 0 if n_zero == n_cmp and n_cmp > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
