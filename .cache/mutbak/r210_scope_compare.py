#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修订 210：探针 `inject_scope=all` 能不能量到流水线的那个量？

⚠⚠⛔ 修订 209 的结论是「探针 ≠ 流水线」，全部差异来自**注入范围**：
    `ResidualSteerer._hook` 是 `x + vector`（(1,1,-1) 广播到**所有**位置），
    而探针写的是 `h[:, inj, :]`（只 1 个位置）。
    实测第 0 步 Δ = **−0.154685**，**大于** resid_std（0.05–0.10）。

⚗⇒ 解法不是「改口径」（那会重写修订 205–208），而是**加一条口径**：
    探针加 `--inject-scope {single,all}`，默认 `single` 保持既有读数可复现。

⛔⛔ 本脚本有一条必须守住的规矩：**对账只用落盘的原始浮点，
   绝不用日志里的打印值。** 我第一版拿 `%.6f` 的转录值当权威，
   把 4.3e-07 的舍入差判成了「不一致」—— 判决门限用错了口径。

三个问题
  Q1 单格锚点：probe(all) 与流水线的落盘值是否**逐位一致**？
  Q2 10 格上 single 与 all 的判决差多少格？往哪边偏？
  Q3 两个口径的 resid_std / 斜率差多少？⇒ 「剂量响应」本身变不变？
"""
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALL_TSV = os.path.join(HERE, "r210_all10.tsv")       # 本轮：inject_scope=all
SINGLE_TSV = os.path.join(HERE, "r208_meas.tsv")     # 修订 208：inject_scope=single
R209_JSON = os.path.join(HERE, "r209_gen.json")      # 流水线的落盘原始值


def load_tsv(p):
    if not os.path.exists(p):
        return None
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def key(r):
    return (r["tid"], r["pos_frac"])


def q(xs, p):
    xs = sorted(x for x in xs if x == x)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] if lo == hi else xs[lo] * (hi - k) + xs[hi] * (k - lo)


def main():
    allr = load_tsv(ALL_TSV)
    if not allr:
        print("⛔ 找不到 %s" % ALL_TSV)
        return 1
    print("=" * 78)
    print("修订 210：`inject_scope=all` 能不能量到流水线的量？")
    print("=" * 78)

    # ---- Q1：单格锚点 ----
    print()
    print("=== Q1：单格锚点（tid=p00__no_think pos=0.30，α_lo=0.5·gap=56.737）===")
    if not os.path.exists(R209_JSON):
        print("  ⛔ 找不到 %s ⇒ Q1 **未验**（不许拿 Q2 顶替）" % R209_JSON)
    else:
        ref = json.load(open(R209_JSON, encoding="utf-8"))
        pipe = [c for c in ref["configs"] if c["name"].startswith("D")][0]["mark"]
        sing = [c for c in ref["configs"] if c["name"].startswith("A")][0]["mark"]
        row = [r for r in allr if r["tid"] == "aime__aime25__p00__no_think"
               and r["pos_frac"] == "0.3"]
        if not row:
            print("  ⛔ 本轮表里没有这一格 ⇒ Q1 **未验**")
        else:
            pa = float(row[0]["b_mark"]) + float(row[0]["p9_lo_meas"])
            print("  流水线原样(D) 落盘原始值 = %r" % pipe)
            print("  探针 single(A) 落盘原始值 = %r" % sing)
            print("  探针 all      本轮落盘值   = %r" % pa)
            print()
            d1 = pa - pipe
            d2 = pipe - sing
            print("  probe(all) − pipeline   = %+.3e  ⇒ %s"
                  % (d1, "**逐位一致** ✅" if d1 == 0.0 else "⛔ 不一致"))
            print("  pipeline  − probe(single) = %+.6f" % d2)
            print()
            if d1 == 0.0:
                print("  ⇒ ✅ **探针在 `all` 口径下量到的就是流水线的那个量**")
                print("     （同一格、同一 α、逐位一致）。")
                print("  ⚠⚠ 但这只验了 **1 格 / 1 个 α** ⇒ 不能推广到全部。")
            else:
                print("  ⇒ ⛔ 两者仍不同 ⇒ `all` 口径**没有**对齐流水线。")

    # ---- Q2 / Q3：10 格对照 ----
    print()
    print("=== Q2/Q3：10 格上两个口径的对照 ===")
    sing_r = load_tsv(SINGLE_TSV)
    if not sing_r:
        print("  ⛔ 找不到 %s ⇒ Q2/Q3 **未验**" % SINGLE_TSV)
        return 4
    s = {key(r): r for r in sing_r}
    a = {key(r): r for r in allr}
    shared = sorted(set(s) & set(a))
    print("  两表交集：**%d/%d 格**（all 表 %d 格）"
          % (len(shared), len(allr), len(allr)))
    if len(shared) != len(allr):
        print("  ⛔ 交集小于本轮格数 ⇒ 不可比，逐格列差：")
        for k in sorted(set(a) - set(s)):
            print("    ⛔ 缺 single 侧：%s" % (k,))

    hdr = ("%-26s %4s | %10s %10s | %5s %5s | %9s %9s"
           % ("tid", "pos", "single_up", "all_up", "s单", "s全",
              "slope单", "slope全"))
    print()
    print(hdr)
    print("-" * len(hdr))
    flips = []
    deltas = []
    for k in shared:
        rs, ra = s[k], a[k]
        ms = (rs.get("up_mono_meas") or "").strip().lower()
        ma = (ra.get("up_mono_meas") or "").strip().lower()
        # ⛔⛔ 三态：空串 ⇒ 没测到，绝不能当 False
        ms = None if ms in ("", "none", "null") else (ms == "true")
        ma = None if ma in ("", "none", "null") else (ma == "true")
        tid = k[0].replace("aime__aime25__", "")
        print("%-26s %4s | %10s %10s | %5s %5s | %+9.6f %+9.6f"
              % (tid, k[1], rs.get("p9_hi_meas", "")[:10],
                 ra.get("p9_hi_meas", "")[:10], ms, ma,
                 float(rs["slope"]), float(ra["slope"])))
        if ms is not None and ma is not None and ms != ma:
            flips.append((tid, k[1], ms, ma,
                          float(rs["p9_hi_meas"]), float(ra["p9_hi_meas"])))
        deltas.append(float(ra["p9_hi_meas"]) - float(rs["p9_hi_meas"]))

    print()
    print("  up_mono 判决翻转：**%d/%d 格**" % (len(flips), len(shared)))
    for tid, pos, ms, ma, hs, ha in flips:
        print("    ⛔ %s pos=%s：single=%s(%+.4f) → all=%s(%+.4f)"
              % (tid, pos, ms, hs, ma, ha))
    print()
    print("  Δ(p9_hi_meas) = all − single：min %+.4f ／ 中位 %+.4f ／ max %+.4f"
          % (min(deltas), q(deltas, 0.5), max(deltas)))
    print("  |Δ| 中位 %.4f" % q([abs(x) for x in deltas], 0.5))
    rs_ = [float(s[k]["resid_std"]) for k in shared]
    ra_ = [float(a[k]["resid_std"]) for k in shared]
    print("  resid_std：single 中位 %.6f ／ all 中位 %.6f"
          % (q(rs_, 0.5), q(ra_, 0.5)))
    ss_ = [float(s[k]["slope"]) for k in shared]
    sa_ = [float(a[k]["slope"]) for k in shared]
    print("  slope    ：single 中位 %+.6f ／ all 中位 %+.6f"
          % (q(ss_, 0.5), q(sa_, 0.5)))

    print()
    print("=== 边界 ===")
    print("  · Q1 只验了 1 格/1 α；Q2/Q3 的 10 格来自 3 条轨迹 × 2 位置。")
    print("  · ⛔ 翻转数是**计数**，不是比例的置信区间。")
    print("  · ⛔ 修订 205–208 的读数**仍在** single 口径下成立，")
    print("    本轮**没有**改写它们；只是**多**了一条 all 口径的线。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
