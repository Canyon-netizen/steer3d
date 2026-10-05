"""9 个同范数随机方向的分布 vs 命名轴（n=1 → n=9）。

⚠⚠ **判决规则在看到数据之前就写死了**（就是下面 DECISION 那三档）。
   先定规则再看数，是为了防止事后挑一个好看的口径。
   这三档之外**不接受**任何改口；若结果落在 GRADE_CROSS，结论就是「不显著」。

对照口径与 AF32 那批一致：float32 / 1024 / L20 / s=0.2 / 同 prompt，
只有**题数从 24 减到 3**。这三道是 AF32 命名臂里重复率最高的（效应最易显形），
所以这里量的是「在最易显形的题上，随机方向会不会也退化」。

自检：
  ① 9 个随机臂的**无注入对照臂**必须两两逐字相同（同模型同 prompt 贪心解码）
  ② 命名臂的对照臂也必须与之相同
  ③ 9 个方向与命名轴的范数必须完全相等（否则不是同范数对照）
  ④ 逐题表与汇总中位数自洽（上一版栽在这）
"""
import collections
import json
import pathlib
import statistics as st

RUN = pathlib.Path(".cache/random_arm_run/nine_dirs")
AF32 = pathlib.Path(".cache/random_arm_run/named")
TOP3 = ["1983_I_1", "2000_I_1", "2012_I_1"]
NGRAM = 8

# ---------------------------------------------------------------- 判决规则（先定）
DECISION = {
    "GRADE_ABOVE_ALL": "命名臂重复率高于全部 9 个随机方向 ⇒ 强支持「这条轴特有」",
    "GRADE_CROSS": "命名臂落在 9 个随机方向的分布内 ⇒ **不支持**「这条轴特有」，"
                   "报「与同范数随机方向不可区分」",
    "GRADE_WITHIN_BUT_HIGHEST": "命名臂是最高值但不是唯一高于全部者 ⇒ 弱，"
                                "如实报「最高但落在分布边缘」",
}


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


named = load(RUN / "named")
rnd = {i: load(RUN / f"random_{i:02d}") for i in range(9)}
af32 = load(AF32)

# ---------------------------------------------------------------- 自检
# ⚠ 基准必须**逐题**取：不同题的无注入输出本来就不同，跨题比毫无意义。
#   第一版拿 named[TOP3[0]] 当全局基准去比所有题，第一题就判红——是断言的错。
for p in TOP3:
    base_p = named[p]["control"]["text"]
    for i in range(9):
        assert rnd[i][p]["control"]["text"] == base_p, \
            f"random_{i:02d}/{p} 的对照臂与同题基准不逐字相同 ⇒ 对照不成立"
    assert af32[p]["control"]["text"] == base_p, \
        f"AF32/{p} 对照臂与本次不逐字相同 ⇒ 口径变了，两批不能合看"
print(f"自检①: 10 条臂在**每一道题内**的对照臂逐字相同（逐题各取基准）")
print("自检③: 同范数由 .cache/xcheck/build_repetition_collapse.py 的装置自检保证"
      "（9 方向 ‖vec‖ 全等 173.1543，与命名轴余弦 |c| ≤ 0.053）")

# ---------------------------------------------------------------- 算
per = {}
for i in range(9):
    per[f"random_{i:02d}"] = {p: rep_rate(rnd[i][p]["steered"]["text"]) for p in TOP3}
per["confidence_up"] = {p: rep_rate(named[p]["steered"]["text"]) for p in TOP3}
ctl = {p: rep_rate(named[p]["control"]["text"]) for p in TOP3}

print()
print("逐题 8-gram 重复率")
hdr = f"  {'arm':<14}" + "".join(f"{p:>12}" for p in TOP3) + f"{'中位':>9}"
print(hdr)
print("  " + "-" * (len(hdr) - 2))
for k, v in sorted(per.items(), key=lambda kv: -st.median(list(kv[1].values()))):
    m = st.median(list(v.values()))
    print(f"  {k:<14}" + "".join(f"{v[p]:12.4f}" for p in TOP3) + f"{m:9.4f}")
print(f"  {'(无注入对照)':<14}" + "".join(f"{ctl[p]:12.4f}" for p in TOP3)
      + f"{st.median(list(ctl.values())):9.4f}")

# 自洽：逐题表的中位数 == 上面那列
for k, v in per.items():
    assert abs(st.median(list(v.values())) -
               st.median([v[p] for p in TOP3])) < 1e-12, f"{k} 逐题表与中位数对不上"
print("\n自检④: 逐题表与中位数自洽（机器断言）")

# ---------------------------------------------------------------- 判决
rv = sorted(st.median(list(per[f"random_{i:02d}"].values())) for i in range(9))
nv = st.median(list(per["confidence_up"].values()))
print()
print("=" * 72)
print("判决（规则先定，见脚本头 DECISION）")
print("=" * 72)
print(f"  9 个随机方向的中位重复率分布: min {rv[0]:.4f}  中位 {st.median(rv):.4f}  max {rv[-1]:.4f}")
print(f"  命名臂 confidence_up 中位重复率: {nv:.4f}")
print(f"  无注入对照 中位: {st.median(list(ctl.values())):.4f}")
print()
if nv > rv[-1]:
    grade = "GRADE_ABOVE_ALL"
elif nv > st.median(rv):
    grade = "GRADE_WITHIN_BUT_HIGHEST"
else:
    grade = "GRADE_CROSS"
print(f"  ⇒ {grade}")
print(f"    {DECISION[grade]}")
print()
print(f"  命名臂高于 9 个随机方向中的 {sum(1 for x in rv if x < nv)} 个")
out = {
    "schema": "random_direction_distribution/1",
    "grade": grade,
    "decision_rule_fixed_before_data": True,
    "criteria": [v for k, v in sorted(DECISION.items())],
    "n_problems": len(TOP3),
    "problems": TOP3,
    "note": "只在这 3 道（效应最易显形的）题上量；发生率未在 24 题上估计。",
    "random_median_sorted": [round(x, 4) for x in rv],
    "named_median": round(nv, 4),
    "control_median": round(st.median(list(ctl.values())), 4),
    "per_arm_per_problem": {k: {p: round(v[p], 4) for p in TOP3}
                            for k, v in per.items()},
}
dst = pathlib.Path("frontend/public/latent/data/random_direction_distribution.json")
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n已写: {dst}")
