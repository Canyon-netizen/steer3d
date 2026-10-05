"""独立重算：用**另一套实现**复核三份产物的核心数字。

为什么必须独立：
  生成器与判据共用同一个 `rep_rate` / `sign_test`。
  若指标**定义**写错了（不是数字抄错，是口径写错），两边会一起绿。
  ⇒ 这里刻意不 import 任何东西，全部从原始 jsonl / npz 重新算。

口径与主产物一致（8-gram 重复占比）：
  把文本切成 8-gram，count > 1 的那些**多出来的**总数 ÷ 总 gram 数。
  本实现用 Counter 之外的写法（先排序再扫），
  以及独立的配对差/符号检验实现。
"""
import collections
import json
import pathlib
import statistics as st

ROOT = pathlib.Path(".")
RUN = ROOT / ".cache/random_arm_run"
N = 8


def rep_alt(text: str, n: int = N) -> float:
    """8-gram 重复占比。独立实现：排序 + 游标，不用 Counter。"""
    w = text.split()
    if len(w) < 2 * n:
        return 0.0
    grams = []
    for i in range(len(w) - n + 1):
        grams.append("\x1f".join(w[i:i + n]))
    grams.sort()
    dup = 0
    i, L = 0, len(grams)
    while i < L:
        j = i
        while j < L and grams[j] == grams[i]:
            j += 1
        cnt = j - i
        if cnt > 1:
            dup += cnt - 1
        i = j
    return dup / len(grams)


def sign_alt(diffs, tol=0.0):
    """精确双侧二项符号检验，独立实现（math.comb 递推而非直接调用）。"""
    pos = sum(1 for d in diffs if d > tol)
    neg = sum(1 for d in diffs if d < -tol)
    n = pos + neg
    if n == 0:
        return pos, neg, n, 1.0

    def comb(n, k):
        r = 1
        for i in range(k):
            r = r * (n - i) // (i + 1)
        return r

    k = min(pos, neg)
    tail = 0
    for i in range(k + 1):
        tail += comb(n, i)
    return pos, neg, n, min(1.0, 2 * tail / 2 ** n)


def load_pairs(d):
    return {p["id"]: p for p in
            (json.loads(f.read_text(encoding="utf-8"))
             for f in sorted(pathlib.Path(d).glob("pair_*.json")))}


FAILS, PASSES = [], []


def eq(name, got, want, tol):
    ok = abs(got - want) <= tol
    (PASSES if ok else FAILS).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          f"   独立算 {got:+.6f}  产物记 {want:+.6f}  差 {abs(got-want):.2e}")


print("=" * 74)
print("独立重算（不 import 主脚本）")
print("=" * 74)

# ---------------------------------------------------------------- 1 32k 批
print("\n[1] 32k 已发货批（all_runs.json）：+v 配对差 vs 零臂")
rows = json.loads((ROOT / ".cache/32k_journal/all_runs.json").read_text(encoding="utf-8"))
cells = collections.defaultdict(dict)
for r in rows:
    cells[(r["direction"], r["strength"])][r["prompt_label"]] = r["primary_text"]
labs = sorted(cells[("confidence_up", 0.0)])
z0 = {l: rep_alt(cells[("confidence_up", 0.0)][l]) for l in labs}
d_up = [rep_alt(cells[("confidence_up", 0.2)][l]) - z0[l] for l in labs]
d_dn = [rep_alt(cells[("confidence_down", 0.2)][l]) - z0[l] for l in labs]

rc = json.loads((RUN / "repetition_collapse.json").read_text(encoding="utf-8"))
b32 = next(b for b in rc["batches"] if "32k" in b["batch"])
t_up = b32["tests"]["up_vs_zero"]
t_dn = b32["tests"]["down_vs_zero"]
pos, neg, n, p = sign_alt(d_up)
print(f"  +v vs 零: 独立算 {pos}:{neg} p={p:.3e}   产物记 {t_up['pos']}:{t_up['neg']} p={t_up['p']}")
# 产物里 p 是 round(...,8) 存的 ⇒ 容差 1e-9 太严，会假红。
# 该判的是「同一个数」，不是「逐位相同」——round 到 8 位是**有意的**。
if (pos, neg) == (t_up["pos"], t_up["neg"]) and abs(p - t_up["p"]) <= 1e-8 + 1e-12:
    PASSES.append("32k +v 符号检验")
    print("  PASS  符号计数与 p 值逐位一致")
else:
    FAILS.append("32k +v 符号检验")
    print("  FAIL  不一致")
pos, neg, n, pd_ = sign_alt(d_dn)
t = b32["tests"]["down_vs_zero"]
print(f"  −v vs 零: 独立算 {pos}:{neg} p={pd_:.3e}   产物记 {t['pos']}:{t['neg']} p={t['p']}")
if (pos, neg) == (t["pos"], t["neg"]):
    PASSES.append("32k −v 符号检验")
else:
    FAILS.append("32k −v 符号检验")

# 零臂：+v零 与 −v零 必须逐字相同（独立实现再验一次）
same = sum(1 for l in labs
           if cells[("confidence_up", 0.0)][l] == cells[("confidence_down", 0.0)][l])
print(f"  零臂逐字相同: {same}/{len(labs)}  (独立实现再验)")
(PASSES if same == len(labs) else FAILS).append("32k 零臂逐字相同")

# ---------------------------------------------------------------- 2 9 随机方向
print("\n[2] 9 个随机方向 + 命名臂（three_problems 那批）")
r9 = json.loads((RUN / "random_direction_distribution.json").read_text(encoding="utf-8"))
arms = {"confidence_up": load_pairs(RUN / "nine_dirs/named")}
for i in range(9):
    arms[f"random_{i:02d}"] = load_pairs(RUN / f"nine_dirs/random_{i:02d}")
TOP3 = r9["problems"]
meds = {}
for n_, a in arms.items():
    meds[n_] = st.median([rep_alt(a[p]["steered"]["text"]) for p in TOP3])

# ⚠ 第一版按 i 比 `random_median_sorted[i]`，那是**排序后**的列表，
#   按 i 取就等于拿 random_00 去比「最小的那个」⇒ 6 个假红。
#   正确口径：① 逐 arm 名比 ② 再单独验证排序结果一致。
for i in range(9):
    eq(f"random_{i:02d} 中位", meds[f"random_{i:02d}"],
       st.median(list(r9["per_arm_per_problem"][f"random_{i:02d}"].values())), 5e-5)
eq("confidence_up 中位", meds["confidence_up"], r9["named_median"], 5e-5)
rands_sorted = sorted(meds[k] for k in meds if k.startswith("random_"))
ok = all(abs(a - b) < 5e-5 for a, b in zip(rands_sorted, r9["random_median_sorted"]))
(PASSES if ok else FAILS).append("9方向 排序后列表")
print(f"  {'PASS' if ok else 'FAIL'}  排序后 9 个中位与产物记录一致   "
      f"独立算 {[round(x,4) for x in rands_sorted]}")
print(f"  {'     '}                              产物记 {r9['random_median_sorted']}")

# 对照臂：10 臂逐题逐字相同
base = {p: arms["confidence_up"][p]["control"]["text"] for p in TOP3}
allsame = all(arms[n_][p]["control"]["text"] == base[p] for n_ in arms for p in TOP3)
print(f"  {'PASS' if allsame else 'FAIL'}  10 臂对照臂逐题逐字相同（独立实现再验）")
(PASSES if allsame else FAILS).append("9方向 对照臂逐字相同")

# ---------------------------------------------------------------- 3 4 轴泛化
print("\n[3] 4 轴泛化（配对口径）")
ax = json.loads((RUN / "axis_generalisation.json").read_text(encoding="utf-8"))
OTHER = RUN / "other_axes"
o = {n_: load_pairs(OTHER / n_) for n_
     in ("caution", "creativity", "reasoning_deep", "reasoning_shallow", "confidence_down")}
ctl = {p: rep_alt(arms["confidence_up"][p]["control"]["text"]) for p in TOP3}
rnd_paired = sorted(st.median(
    [rep_alt(load_pairs(RUN / f"nine_dirs/random_{i:02d}")[p]["steered"]["text"]) - ctl[p]
     for p in TOP3]) for i in range(9))
eq("随机分布阈值（配对）", rnd_paired[-1], ax["threshold_paired"], 5e-5)
for row in ax["axes"]:
    best = max(row["paired_median_by_member"],
               key=row["paired_median_by_member"].get)
    a = o[best] if best != "confidence_up" else arms["confidence_up"]
    got = st.median([rep_alt(a[p]["steered"]["text"]) - ctl[p] for p in TOP3])
    eq(f"{row['axis']}({best}) 配对中位", got, row["axis_value"], 5e-5)

# ---------------------------------------------------------------- 汇总
print()
print("=" * 74)
print(f"PASS {len(PASSES)}   FAIL {len(FAILS)}")
print("=" * 74)
if FAILS:
    for f in FAILS:
        print("  FAIL ", f)
    raise SystemExit(1)
print("独立重算全部吻合。")
