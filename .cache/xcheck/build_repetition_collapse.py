"""重复退化 = 置信轴的特有机制：三批独立复现 + 新内容产出率曲线。

生成 `.cache/random_arm_run/repetition_collapse.json`（**先不进发货目录**，
等定去向）。这个脚本同时是一份**判据**：下面的 assert 是真断言，
不是印给人看的自检 —— 上一版就是「印给人看」栽的（逐题表与中位数对不上）。

三批的分工（别混）：
  A32  = .cache/32k_journal/all_runs.json      32k 上限 23 题，**已发货 steer_directions 的来源**
  AF32 = .cache/random_arm_run/named           1024 上限 24 题，本次新跑（float32）
  ARND = .cache/random_arm_run/random          1024 上限 24 题，本次新跑（同范数随机方向）
  A16  = .cache/random_arm_run/dtype_test/*    1024 上限 3 题，bfloat16 复核
  ✗ 不作为对照：backend/examples/output/intervention/cot_long.json
      —— 那是 1025 步族，build_cot_effect.py:31-34 显式声明「无模型字段、
      留在仓里不进 bundle」；且零臂与 AF32/A16 全部 0/24 逐字不同，不是同一实验。
"""
import collections
import json
import pathlib
import statistics as st
from math import comb

ROOT = pathlib.Path(".")
OUT = ROOT / "frontend/public/latent/data/repetition_collapse.json"
NGRAM = 8
WIN = 200
NSEG = 10


def _json_or_none(path):
    """读一个已生成的小 JSON；没有就返回空 dict，让产物仍然生成得出来。"""
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"_missing": str(path)}


# ---------------------------------------------------------------- 指标
def rep_rate(t, n=NGRAM):
    """8-gram 重复占比：把文本切 n-gram 后，重复出现的那些占比多少。"""
    w = t.split()
    if len(w) < 2 * n:
        return 0.0
    g = [tuple(w[i:i + n]) for i in range(len(w) - n + 1)]
    return sum(v - 1 for v in collections.Counter(g).values()) / len(g)


def new_rate_curve(t, n=NGRAM, nseg=NSEG, win=None):
    """新内容产出率：按位置切成 nseg 段，每段里「首次出现」的 n-gram 占比。

    健康生成全程接近 1；原地打转会在某一点塌到 0 并保持。
    比标量重复率更能说清**什么时候**停止进展。

    ⚠ 窗宽自适应，且**段数不够就报错**。
      固定窗宽 + 空段填 0 会把「样本不够」报成「值是 0」——
      1024 token 的文本只有约 950 个 8-gram，按 200 一窗切不满 10 段，
      第一版就产出了 0/1 交替的假曲线。
    """
    w = t.split()
    g = [tuple(w[i:i + n]) for i in range(len(w) - n + 1)]
    if win is None:
        win = max(20, len(g) // nseg)
    n_win = len(g) // win
    assert n_win >= nseg, (
        f"文本太短：新内容率切不出 {nseg} 段（grams={len(g)} win={win} "
        f"⇒ 只有 {n_win} 窗）。**不能**拿这个指标报这批数据。")
    seen, per = set(), []
    for w_i in range(n_win):                     # 只取**完整**窗，残窗丢弃
        ch = g[w_i * win:(w_i + 1) * win]
        per.append(sum(1 for x in ch if x not in seen) / len(ch))
        seen.update(ch)
    assert len(per) == n_win >= nseg, "窗数与 nseg 不匹配"
    return ([st.mean(per[j * n_win // nseg:(j + 1) * n_win // nseg])
             for j in range(nseg)], win)


def sign_test(a, b, tol=0.0):
    d = [x - y for x, y in zip(a, b)]
    pos = sum(1 for x in d if x > tol)
    neg = sum(1 for x in d if x < -tol)
    n = pos + neg
    if n == 0:
        return {"pos": 0, "neg": 0, "ties": len(d), "p": 1.0, "median_diff": 0.0}
    k = min(pos, neg)
    return {"pos": pos, "neg": neg, "ties": len(d) - n,
            "p": round(min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n), 8),
            "median_diff": round(st.median(d), 6)}


# ---------------------------------------------------------------- 取数
def load_pairs(d):
    return {p["id"]: p for p in
            (json.loads(f.read_text(encoding="utf-8"))
             for f in sorted(pathlib.Path(d).glob("pair_*.json")))}


a32 = collections.defaultdict(dict)
for r in json.loads((ROOT / ".cache/32k_journal/all_runs.json").read_text(encoding="utf-8")):
    a32[(r["direction"], r["strength"])][r["prompt_label"]] = r["primary_text"]

af32, arnd = load_pairs(".cache/random_arm_run/named"), load_pairs(".cache/random_arm_run/random")
a16n = load_pairs(".cache/random_arm_run/dtype_test/named_bf16")
a16r = load_pairs(".cache/random_arm_run/dtype_test/rand_bf16")

# ---------------------------------------------------------------- 自检（真断言）
def cells32():
    labs = sorted(set.intersection(*[set(v) for v in a32.values()]))
    return labs


L32 = cells32()
# ① 32k 的零臂必须逐字相同（零向量 × 任何方向仍是零）
z_up = a32[("confidence_up", 0.0)]
z_dn = a32[("confidence_down", 0.0)]
assert all(z_up[l] == z_dn[l] for l in L32), "32k 零臂不逐字相同 ⇒ 批次自检失败"
# ② 本次两臂的零臂必须逐字相同
assert all(af32[p]["control"]["text"] == arnd[p]["control"]["text"] for p in af32), \
    "本次两臂零臂不逐字相同 ⇒ 对照不成立"
# ③ 题集一致
assert set(af32) == set(arnd), "本次两臂题集不同"
# ④ 排除族必须真的与本次不同（否则「排除」这个说法要重新审视）
cot = {r["prompt_label"]: r["primary_text"] for r in json.loads(
    (ROOT / "backend/examples/output/intervention/cot_long.json").read_text(encoding="utf-8"))
    if r["direction"] == "confidence_up" and r["strength"] == 0.0}
shared = sorted(set(af32) & set(cot))
n_diff = sum(1 for p in shared if af32[p]["control"]["text"] != cot[p])
assert n_diff == len(shared) and shared, \
    f"排除族与本次零臂并非全部不同（{n_diff}/{len(shared)}）⇒ not_claimed 要改写"

# ---------------------------------------------------------------- 逐批算
def batch(name, up, dn, zero, labels):
    U = [rep_rate(up[l]) for l in labels]
    D = [rep_rate(dn[l]) for l in labels]
    Z = [rep_rate(zero[l]) for l in labels]
    def _curves(d):
        # 全批**统一**窗宽（含三条臂），曲线才能横向比。
        # 逐题自适应会让 32k 批的窗宽从 86 跨到 2585，
        # 再把不同窗宽的曲线取中位数 —— 那不是同一个量。
        cs = [new_rate_curve(d[l], win=BATCH_WIN[0])[0] for l in labels]
        return [round(x, 3) for x in _med_curve(cs)], BATCH_WIN[0]

    BATCH_WIN = [max(20, min(
        len(x[l].split()) - NGRAM + 1
        for l in labels for x in (up, dn, zero)) // NSEG)]
    cu, wu = _curves(up)
    cd, wd = _curves(dn)
    cz, wz = _curves(zero)
    return {
        "batch": name, "n": len(labels),
        "rep_median": {"up": round(st.median(U), 4), "down": round(st.median(D), 4),
                       "zero": round(st.median(Z), 4)},
        # ⚠ 自洽断言要比**未舍入**的中位数。拿 round(...,4) 的输出去比 1e-9
        #   会被自己的舍入判红（第一版就这么栽的），那不是列错位。
        "_raw_median": {"up": st.median(U), "down": st.median(D), "zero": st.median(Z)},
        "_pp_raw": {l: (rep_rate(up[l]), rep_rate(dn[l]), rep_rate(zero[l])) for l in labels},
        "tests": {"up_vs_down": sign_test(U, D), "up_vs_zero": sign_test(U, Z),
                  "down_vs_zero": sign_test(D, Z)},
        "new_rate_curve": {"up": cu, "down": cd, "zero": cz,
                           "_window_sizes": {"up": wu, "down": wd, "zero": wz}},
        "_per_problem": {l: {"up": round(rep_rate(up[l]), 4), "down": round(rep_rate(dn[l]), 4),
                             "zero": round(rep_rate(zero[l]), 4)} for l in labels},
    }


def _med_curve(cs):
    return [st.median([c[j] for c in cs]) for j in range(NSEG)]


# --- 自洽断言：逐题表的中位数必须等于报出去的中位数（上一版栽在这）---
b32 = batch("A32 已发货 32k / 23 题",
            a32[("confidence_up", 0.2)], a32[("confidence_down", 0.2)], z_up, L32)
labsA = sorted(af32)
bF = batch("AF32 本次 float32 / 24 题",
           {p: af32[p]["steered"]["text"] for p in af32},
           {p: arnd[p]["steered"]["text"] for p in af32},      # 这里 dn 位放随机臂，见下方说明
           {p: af32[p]["control"]["text"] for p in af32}, labsA)

for b in (b32, bF):
    for j, arm in enumerate(("up", "down", "zero")):
        vals = [v[j] for v in b["_pp_raw"].values()]
        assert abs(st.median(vals) - b["_raw_median"][arm]) < 1e-12, \
            f"{b['batch']} {arm}: 未舍入逐题表与中位数对不上（数据有 bug）"
        shown = [b["_per_problem"][l][arm] for l in b["_per_problem"]]
        assert abs(st.median(shown) - b["rep_median"][arm]) < 1e-4, \
            f"{b['batch']} {arm}: 读者看到的那张表与报出的中位数对不上（列错位？）"

doc = {
    "schema": "repetition_collapse/1",
    "what": "置信 +v 轴把生成推进不下去，然后用剩余 token 预算把复读填满；"
            "−v 与同范数随机方向都不这样。",
    "metric": {
        "rep_rate": f"8-gram 重复占比（重复出现的 gram 数 / 总 gram 数）",
        "new_rate_curve": f"按位置切 {NSEG} 段，每段「首次出现」的 8-gram 占比；"
                          f"塌到 0 = 停止进展并复读",
    },
    "batches": [b32, bF],
    "dtype_recheck": {
        "why": "dtype 会改变无注入的基线生成，需要确认它不会改变这个效应",
        "control_arm_identical_fp32_vs_bf16": all(
            af32[p]["control"]["text"] != a16n[p]["control"]["text"] for p in a16n),
        "rep_up_fp32": {p: round(rep_rate(af32[p]["steered"]["text"]), 4) for p in a16n},
        "rep_up_bf16": {p: round(rep_rate(a16n[p]["steered"]["text"]), 4) for p in a16n},
        "rep_random_bf16": {p: round(rep_rate(a16r[p]["steered"]["text"]), 4) for p in a16r},
    },
    "excluded_family": {
        "file": "backend/examples/output/intervention/cot_long.json",
        "why": "build_cot_effect.py:31-34 声明 1025 步族「无 log 无模型字段，"
               "留在仓里不进 bundle」；实测其零臂与本次两批 0/24 逐字相同，"
               "⇒ 不是同一个实验，不能作为反证。",
        "zero_arm_differs_from_ours": f"{n_diff}/{len(shared)}",
    },
    "random_direction_distribution": {
        "why": "单一个随机方向只能回答「这个方向会不会退化」；"
               "9 个方向才能回答「随机方向会不会退化」。判决规则先定死再取数。",
        "source": ".cache/random_arm_run/random_direction_distribution.json",
        **_json_or_none(ROOT / ".cache/random_arm_run/random_direction_distribution.json"),
    },
    "not_claimed": [
        "① **两阶段，别把两批读成同一个证据。** 退化是两阶段的："
        "先「重复率升高但仍在推进」（1024 token 那批能看到），"
        "后「停止推进、用复读填满剩余预算」（32k 那批能看到："
        "新内容率在 20% 处塌到 0.00 并保持）。"
        "⇒ 1024 批**不能**用来证明停摆，32k 批**不能**用来证明早期重复率。",
        "② 9 个同范数随机方向只在 **3 道题**上跑过。那 3 道是按**本次 1024 批**"
        "的重复率挑的；放到 32k 已发货批的 23 题里，它们的 +v 配对差排名是第 "
        "20 / 12 / 1 名，基线覆盖 178.5 倍量程 —— **既不是最强也不是最弱**，"
        "所以这 3 道对其他轴**不构成**「专门挑的容易题」。"
        "⚠ 但**发生率可能被高估**：用 32k 批唯一的可校准臂 confidence_down "
        "做对照，3 题给的配对差中位比 23 题真实值高 81%、正例率 67% vs 52%。"
        "**这只有 1 个校准点**，不足以当通则，只能当「存在高估风险」的提示 —— "
        "所以本文件报的是「是否落在随机分布之外」（离散判断），"
        "**不报**任何发生率数字。",
        "③ 随机方向只有 1 个强度点（s=0.2）、1 个注入层（L20）、1 个模型；"
        "不能外推到其他强度/层/模型。",
        "④ 1024 上限那批的闭合率是退化的（全批仅 1/24 闭合），"
        "不能与 32k 的 +v 5/23、−v 21/23 直接对标。",
        "⑤ 本文件度量的是**生成文本的重复退化**，不是模型的「自信/怀疑」状态；"
        "也不能推出「+v 更差」是普遍规律（只有 s=0.2 一个强度点）。",
        "⑥ 已发货 32k 批次的模型与精度无法从仓内产物追溯："
        ".cache/32k_journal/z46_shard.sh:52 那行 model= 留痕的输出未保存，"
        "32k_journal/ 下无 .log。--layer-rms 865.77 是调用方传入的常量，"
        "不是模型自己报告的数，**不能**用来证明模型身份。",
    ],
    "self_check": "本文件由 .cache/xcheck/build_repetition_collapse.py 生成，"
                  "含机器断言（32k 零臂逐字相同 / 本次两臂零臂逐字相同 / "
                  "逐题表与中位数自洽 / 排除族确与本次不同）。",
}
for b in doc["batches"]:
    b.pop("_per_problem")
    b.pop("_raw_median")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

print("全部断言通过。已写:", OUT)
print()
for b in (b32, bF):
    print(f"[{b['batch']}]  n={b['n']}  重复率中位 +v {b['rep_median']['up']} / "
          f"−v或随机 {b['rep_median']['down']} / 零 {b['rep_median']['zero']}")
    for k, t in b["tests"].items():
        print(f"    {k:<12} {t['pos']}:{t['neg']} 平{t['ties']}  p={t['p']}")
    print(f"    新内容率曲线 +v: {b['new_rate_curve']['up']}")
    print(f"    新内容率曲线 零: {b['new_rate_curve']['zero']}")
    print()
print("排除族零臂与本次不同:", doc["excluded_family"]["zero_arm_differs_from_ours"])
print("dtype 复核 fp32→bf16 的 +v 重复率:",
      list(doc["dtype_recheck"]["rep_up_fp32"].values()), "→",
      list(doc["dtype_recheck"]["rep_up_bf16"].values()))
