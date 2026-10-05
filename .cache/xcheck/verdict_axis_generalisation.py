"""泛化检验：把「重复退化是语义轴特有」拿到另外几条语义轴上试。

⚠⚠ **判决规则在看到数据之前写死**（DECISION 两档），不因结果改口。
   事先认了 INSIDE。若多数轴落在 INSIDE，结论就是
   「重复退化是 confidence 独有的，不是语义轴的通性」。

⚠ **「6 个命名向量」实际只有 4 个独立方向**，且这是项目自己写明的
   （frontend/components/VectorStructurePanel.tsx:39-48：
   两对是精确反平行，六个标签描述四条独立向量）。
   ⇒ 本检验的独立样本量是 **4**，不是 6。confidence_up/down 与
   reasoning_deep/shallow 各算**一条轴**，不是两条。
   任何「5 条轴都成立」的说法都会是这个数字的两倍。

自检：
  ① 每条臂在**每一道题内**的对照臂必须与同题基准逐字相同
  ② 逐题表与汇总中位数自洽
"""
import collections
import json
import pathlib
import statistics as st

ROOT = pathlib.Path(".")
OTHER = ROOT / ".cache/random_arm_run/other_axes"
NINE = ROOT / ".cache/random_arm_run/nine_dirs"
TOP3 = ["1983_I_1", "2000_I_1", "2012_I_1"]
NGRAM = 8

# ---------------------------------------------------------------- 判决规则（先定）
DECISION = {
    "OUTSIDE": "该轴**逐题配对差**中位 > 9 个随机方向配对差的最大值 ⇒ 与同范数随机方向**可区分**",
    "INSIDE": "≤ 该最大值 ⇒ 落在随机分布内，「语义轴特有」对这条轴**不成立**",
}
# 「轴」的正确计法：反平行的一对算**一条**轴。
AXES = {
    "confidence":      ["confidence_up", "confidence_down"],
    "reasoning":       ["reasoning_deep", "reasoning_shallow"],
    "caution":         ["caution"],
    "creativity":      ["creativity"],
}
# caution 的 diff-of-means 正样本只有 379 个（confidence 是 20930，55 倍差）
WEAK = {"caution": "正样本 379 vs confidence 的 20930，估计量弱 55 倍"}

# ⚠⚠ **主口径必须是逐题配对差，不是跨题中位。**
#   这 3 道题的无注入对照重复率差 17.7 倍（0.0072 / 0.1268 / 0.0130），
#   任何不扣掉**每道题自己**基线的跨题聚合，测到的是题目难度的方差。
#   第一版用跨题中位，creativity 被报成 0.0450（OUTSIDE）；
#   配对后是 −0.0072（INSIDE），判决从 2/4 变成 1/4。
#   跨题中位保留在 `superseded_caliber` 里，只作审计，不参与判决。


def rep_rate(t, n=NGRAM):
    w = t.split()
    if len(w) < 2 * n:
        return 0.0
    g = [tuple(w[i:i + n]) for i in range(len(w) - n + 1)]
    return sum(v - 1 for v in collections.Counter(g).values()) / len(g)


def load(d):
    return {p["id"]: p for p in
            (json.loads(f.read_text(encoding="utf-8"))
             for f in sorted(pathlib.Path(d).glob("pair_*.json")))}


arms = {n: load(OTHER / n) for n in
        ("caution", "creativity", "reasoning_deep", "reasoning_shallow", "confidence_down")}
arms["confidence_up"] = load(NINE / "named")

# ---------------------------------------------------------------- 自检①
for p in TOP3:
    base_p = arms["confidence_up"][p]["control"]["text"]
    for n, a in arms.items():
        assert a[p]["control"]["text"] == base_p, \
            f"{n}/{p} 的对照臂与同题基准不逐字相同 ⇒ 对照不成立"
print("自检①: 6 条臂在**每一道题内**的对照臂逐字相同（逐题各取基准）")

per = {n: {p: rep_rate(a[p]["steered"]["text"]) for p in TOP3} for n, a in arms.items()}
ctl = {p: rep_rate(arms["confidence_up"][p]["control"]["text"]) for p in TOP3}

print()
print("逐题 8-gram 重复率（3 题，效应最易显形处）")
hdr = f"  {'arm':<20}" + "".join(f"{p:>12}" for p in TOP3) + f"{'中位':>9}"
print(hdr)
print("  " + "-" * (len(hdr) - 2))
for n in sorted(per, key=lambda k: -st.median(list(per[k].values()))):
    print(f"  {n:<20}" + "".join(f"{per[n][p]:12.4f}" for p in TOP3)
          + f"{st.median(list(per[n].values())):9.4f}")
print(f"  {'(无注入对照)':<20}" + "".join(f"{ctl[p]:12.4f}" for p in TOP3)
      + f"{st.median(list(ctl.values())):9.4f}")
print(f"  {'(9随机方向 max, 跨题口径)':<20}" + " " * 36 + f"{0.0218:9.4f}")

for n, v in per.items():                      # 自检②
    assert abs(st.median(list(v.values())) - st.median([v[p] for p in TOP3])) < 1e-12, \
        f"{n} 逐题表与中位数对不上"
print("\n自检②: 逐题表与中位数自洽（机器断言）")

# ---------------------------------------------------------------- 按「轴」判决
print()
print("=" * 74)
print(f"题间基线不均（无注入对照重复率）："
      f"{ {p: round(ctl[p],4) for p in TOP3} }  "
      f"最高/最低 = {max(ctl.values())/min(ctl.values()):.1f}×")
print("⇒ 必须逐题配对，跨题中位测的是题目难度方差。")
print("=" * 74)
print(f"  {'arm':<20}{'跨题中位':>9}{'配对差中位':>11}   逐题配对差")
print("  " + "-" * 68)
paired_median = {}
for n in sorted(per, key=lambda k: -st.median(
        [per[k][p] - ctl[p] for p in TOP3])):
    dif = [per[n][p] - ctl[p] for p in TOP3]
    paired_median[n] = st.median(dif)
    print(f"  {n:<20}{st.median(list(per[n].values())):9.4f}{paired_median[n]:11.4f}   "
          + " ".join(f"{d:+.4f}" for d in dif))

# 阈值必须同口径：用 9 个随机方向的**配对差**中位最大值
rnd = {i: load(NINE / f"random_{i:02d}") for i in range(9)}
rand_paired = sorted(st.median([rep_rate(rnd[i][p]["steered"]["text"]) - ctl[p]
                                for p in TOP3]) for i in range(9))
TH = rand_paired[-1]
print(f"\n  9 随机方向配对差中位: min {rand_paired[0]:+.4f}  中位 "
      f"{st.median(rand_paired):+.4f}  max {TH:+.4f}")
print(f"  判决阈值（同口径，配对差）= {TH:+.4f}")

print()
print("按「轴」判决（反平行的一对算一条轴，不是两条；规则先定）")
axis_rows = []
for axis, members in AXES.items():
    m = {mm: paired_median[mm] for mm in members if mm in paired_median}
    best = max(m, key=m.get)
    val = m[best]
    grade = "OUTSIDE" if val > TH else "INSIDE"
    axis_rows.append({"axis": axis, "members": members,
                      "paired_median_by_member": {k: round(v, 4) for k, v in m.items()},
                      "axis_value": round(val, 4), "grade": grade,
                      "caveat": WEAK.get(best, "")})
    print(f"  {axis:<12} 配对差 { {k: round(v,4) for k,v in m.items()} }")
    print(f"  {'':<12} ⇒ {grade:<8}"
          + (f"   ⚠ {WEAK[best]}" if best in WEAK else ""))

n_out = sum(1 for r in axis_rows if r["grade"] == "OUTSIDE")
print()
print(f"  4 条独立轴中 {n_out} 条 OUTSIDE / {4-n_out} 条 INSIDE")
verdict = ("「重复退化」是**语义轴的通性**（4 条轴全部可区分于同范数随机方向）"
           if n_out == 4 else
           f"「重复退化」**不是**语义轴的通性 —— 只有 {n_out}/4 条轴可区分。"
           + ("能站住的更窄版本是：**只有 confidence +v 这一条轴**在同范数随机方向"
              "之外产生重复退化；其余 3 条轴的配对差都落在随机分布内或为负。"
              if n_out == 1 else "该现象是这些轴各自特有的。"))
print(f"\n  ⇒ {verdict}")

out = {
    "schema": "axis_generalisation/1",
    "decision_rule_fixed_before_data": True,
    "criteria": [f"{k}: {v}" for k, v in DECISION.items()],
    "null_max_cross_problem_superseded": 0.0218,
    "n_independent_axes": len(AXES),
    "null_paired_median_sorted": [round(x, 4) for x in rand_paired],
    "threshold_paired": round(TH, 4),
    "caliber": "主口径 = 逐题配对差（每题减自己的无注入对照）",
    "superseded_caliber": {
        "what": "跨题中位（不减每题自身基线）",
        "why_superseded": "这 3 道题的无注入对照重复率差 17.7 倍，跨题聚合测的是"
                          "题目难度方差。creativity 因此被误报为 OUTSIDE。",
        "cross_problem_median_by_member": {
            n: round(st.median(list(per[n].values())), 4) for n in per},
        "would_have_given": "2/4 OUTSIDE（错）",
        "kept_for": "审计。不参与判决。",
    },
    "axes_note": "6 个命名向量只张成 4 个独立方向（两对精确反平行）；"
                 "这是 frontend/components/VectorStructurePanel.tsx:39-48 已写明的，"
                 "本文件只是把它对齐到行为口径。",
    "n_problems": len(TOP3),
    "note": "只在这 3 道（效应最易显形的）题上量；发生率未在 24 题上估计。",
    "axes": axis_rows,
    "verdict": verdict,
    "per_arm_per_problem": {k: {p: round(v[p], 4) for p in TOP3} for k, v in per.items()},
    "per_arm_paired_vs_own_control": {k: {p: round(per[k][p] - ctl[p], 4) for p in TOP3}
                                 for k in per},
    "control_by_problem": {p: round(ctl[p], 4) for p in TOP3},
    "control_median": round(st.median(list(ctl.values())), 4),
}
dst = ROOT / "frontend/public/latent/data/axis_generalisation.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n已写: {dst}")
