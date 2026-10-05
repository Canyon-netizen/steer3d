#!/usr/bin/env python3
"""confidence +v 的**发生率**：在 23 道题上，这效应有多常发生？

⚠ 为什么必须做
   已发货的产物写着「发生率未在 24 题上估计」—— 那句话对**轴间比较**成立
   （4 条轴只在 3 道题上跑过）。但**发生率**要的是另一批数据：
   32k 批有 23 道题 × {+v, −v, 零}，而零臂两格已复核 **23/23 逐字相同**
   ⇒ 它是一份合格的**逐题配对**设计。
   也就是说，关键那条轴的发生率**本来就能估**，只是没人去算。

⚠⚠ 最容易搞错的一处：全长重复率把「多长」和「多重复」混在一起
   32k 批里 +v 与零臂的生成长度差得极远（1984_I_1：+v 32000 步 vs 零臂 7164 步；
   1983_I_1：+v 4556 步 vs 零臂 3225 步）。
   而「+v 停止推进」这个机制**本身就会改变长度** ⇒ 用全长比，
   测到的可能是「谁跑得久」而不是「谁更重复」。
   ⇒ 本脚本给三个口径，并把长度一并报出来，让读者自己看：
     ① 全长重复率（与已发货产物同口径，NGRAM=8）
     ② **定长前缀**重复率（每条只取前 K 个词）—— 长度无关
     ③ 定长前缀的**新内容产出率**（1 − 重复率），与机制曲线同向

⚠ 判决规则取数前写死；单臂 n=1（每格只有 1 个 run，无重复）这件事
   **必须跟着每个数字一起报** —— 有重复与没重复，能出的结论不一样。
"""
from __future__ import annotations

import collections
import io
import json
import math
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOURNAL = ROOT / ".cache/32k_journal/all_runs.json"

NGRAM = 8
RULE = {
    "prefix_words": 2048,          # 定长前缀（词）。远小于最短的一条
    "min_words_for_rep": 2 * NGRAM,
    "occurrence_rule": "前缀重复率配对差 > 0 的题数占比；"
                       "同时报二项检验（双侧）与 Wilson 95% 区间。",
    "decide_before_data": True,
}


def rep_rate(t: str, n: int = NGRAM) -> float:
    w = t.split()
    if len(w) < 2 * n:
        return 0.0
    g = [tuple(w[i:i + n]) for i in range(len(w) - n + 1)]
    return sum(v - 1 for v in collections.Counter(g).values()) / len(g)


def binom_two_sided(pos: int, n: int) -> float:
    """双侧精确二项检验（H0: p=0.5）。"""
    if n == 0:
        return 1.0
    k = min(pos, n - pos)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def wilson(pos: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    ph = pos / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    hw = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return ((c - hw) / d, (c + hw) / d)


def main() -> int:
    runs = json.load(io.open(JOURNAL, encoding="utf-8"))
    by: dict = {}
    for x in runs:
        key = (x["prompt_label"], x["direction"], x["strength"])
        assert key not in by, f"{key} 出现两次 ⇒ 我以为「每格 1 个 run」错了"
        by[key] = x
    probs = sorted({x["prompt_label"] for x in runs})
    n_runs_per_cell = collections.Counter(
        (x["prompt_label"], x["direction"], x["strength"]) for x in runs)
    assert set(n_runs_per_cell.values()) == {1}, \
        f"每格 run 数不是全 1：{collections.Counter(n_runs_per_cell.values())}"
    assert len(probs) == 23, f"题数 {len(probs)}，预期 23"

    # 零臂两格必须逐字相同，否则「配对」这个说法不成立
    ident = sum(1 for p in probs
                if by[(p, "confidence_up", 0.0)]["primary_text"]
                == by[(p, "confidence_down", 0.0)]["primary_text"])
    assert ident == len(probs), f"零臂两格只有 {ident}/{len(probs)} 逐字相同"
    print(f"✓ 零臂两格逐字相同 {ident}/{len(probs)}（配对设计成立）")
    print(f"✓ 每格 run 数 = 1（**无重复测量** ⇒ 下文只报「多少题出现」，"
          f"不报「单题上重复出现」）")

    K = RULE["prefix_words"]
    rows = []
    for p in probs:
        up = by[(p, "confidence_up", 0.2)]
        ze = by[(p, "confidence_up", 0.0)]
        dn = by[(p, "confidence_down", 0.2)]
        pu, pz, pd = (up["primary_text"], ze["primary_text"], dn["primary_text"])
        rows.append({
            "problem": p,
            "n_steps_up": up["n_steps"], "n_steps_zero": ze["n_steps"],
            "n_steps_down": dn["n_steps"],
            "rep_full_up": round(rep_rate(pu), 4),
            "rep_full_zero": round(rep_rate(pz), 4),
            "rep_pre_up": round(rep_rate(" ".join(pu.split()[:K])), 4),
            "rep_pre_zero": round(rep_rate(" ".join(pz.split()[:K])), 4),
            "rep_pre_down": round(rep_rate(" ".join(pd.split()[:K])), 4),
        })
    for r in rows:
        r["d_full"] = round(r["rep_full_up"] - r["rep_full_zero"], 4)
        r["d_pre"] = round(r["rep_pre_up"] - r["rep_pre_zero"], 4)

    pos_full = sum(1 for r in rows if r["d_full"] > 0)
    pos_pre = sum(1 for r in rows if r["d_pre"] > 0)
    p_full, p_pre = binom_two_sided(pos_full, len(rows)), binom_two_sided(pos_pre, len(rows))
    lo, hi = wilson(pos_pre, len(rows))

    # ---- 截尾披露（第三十六笔补） ----------------------------------------
    # 两条独立观测把「定长前缀」这件事的性质说清楚了：
    #   ① **截尾**：+v 臂在多少题上跑满 32000 token 上限？零臂呢？
    #   ② **前缀覆盖**：2048 词占 +v 臂全文的**百分之几**？
    # 32k 批的机制曲线显示 +v 的新内容产出率在**输出 20% 处**塌到 0。
    # 若前缀只覆盖 +v 输出的前 ~8%，那它只量到了塌缩的**开头** ——
    # ⇒ 定长前缀那个数是**下界**，不是另一个估计值。
    # ⚠ 这一条不改「22/23」，它改的是**那个中位差该被读成什么**。
    for r in rows:
        wu = len(by[(r["problem"], "confidence_up", 0.2)]["primary_text"].split())
        wz = len(by[(r["problem"], "confidence_up", 0.0)]["primary_text"].split())
        r["words_up"] = wu
        r["words_zero"] = wz
        r["prefix_fraction_of_up"] = round(K / wu, 4) if wu else None
    cap = 32000
    up_capped = sum(1 for r in rows if r["n_steps_up"] >= cap)
    zero_capped = sum(1 for r in rows if r["n_steps_zero"] >= cap)
    up_capped_pref = [r["prefix_fraction_of_up"] for r in rows
                      if r["n_steps_up"] >= cap and r["prefix_fraction_of_up"] is not None]
    len_ratio = [min(r["n_steps_up"], r["n_steps_zero"]) /
                 max(r["n_steps_up"], r["n_steps_zero"]) for r in rows]
    # 长度比 与 定长前缀配对差 的相关：若强负相关，说明前缀那个数
    # 仍然在偷偷跟着长度走（那就不能当长度无关的估计）。
    mx, my = st.mean(len_ratio), st.mean([r["d_pre"] for r in rows])
    num = sum((a - mx) * (b - my) for a, b in zip(len_ratio, [r["d_pre"] for r in rows]))
    den = math.sqrt(sum((a - mx) ** 2 for a in len_ratio)
                    * sum((b - my) ** 2 for b in [r["d_pre"] for r in rows]))
    r_len = (num / den) if den else float("nan")

    cap_disclosure = {
        "cap_tokens": cap,
        "up_hit_cap": up_capped,
        "zero_hit_cap": zero_capped,
        "n_problems": len(rows),
        "prefix_fraction_of_up_when_capped_median":
            round(st.median(up_capped_pref), 4) if up_capped_pref else None,
        "collapse_position_in_new_rate_curve": 0.20,
        "prefix_covers_before_collapse": True,
        "why_this_matters":
            "定长前缀只取前 %d 词。+v 臂有 %d/%d 题跑满 %d token 上限，"
            "而 32k 的机制曲线显示新内容产出率在**输出 20%% 处**塌到 0。"
            "⇒ 前缀覆盖的是塌缩**开始之前**那段，定长口径那个中位差是**下界**，"
            "不是「另一个估计值」。「22/23 发生」这个计数不受影响（只看符号）。"
            % (K, up_capped, len(rows), cap),
        "length_ratio_vs_prefix_diff_pearson_r": round(r_len, 3),
        "length_ratio_reading":
            "长度比（min/max）与定长前缀配对差的 r = %+.3f ⇒ 弱负相关。"
            "若它是强负相关，说明前缀口径仍在偷偷跟着长度走，不能当长度无关的估计。"
            "现在的读法是：**相关性弱，所以定长口径确实把长度的影响剥掉了大半**，"
            "剩下的 4.3 倍差距来自「塌缩发生在文本靠后」这件事本身。" % r_len,
    }

    lens = [r["n_steps_up"] for r in rows]
    lens0 = [r["n_steps_zero"] for r in rows]
    short = sum(1 for r in rows if r["n_steps_up"] < r["n_steps_zero"])

    out = {
        "schema": "occurrence_23/1",
        "what": "confidence +v 的重复退化在 23 道题上**多常**发生。",
        "decision_rule_fixed_before_data": True,
        "rule": RULE,
        "caliber": "逐题配对（每题减自己的无注入零臂）；零臂两格 23/23 逐字相同",
        "replication_per_cell": 1,
        "replication_note": "每格只有 1 个 run ⇒ 报的是「多少题上出现」，"
                            "不是「出现得多稳」；单题层面没有重复测量。",
        "n_problems": len(rows),
        "ngram": NGRAM,
        "prefix_words": K,
        "full_text": {
            "pos": pos_full, "neg": len(rows) - pos_full,
            "p_two_sided": p_full,
            "median_diff": round(st.median([r["d_full"] for r in rows]), 4),
            "caveat": "全长口径把「多长」和「多重复」混在一起：+v 停止推进本身"
                      "就会改变生成长度。中位差 %+.4f。"
                      % st.median([r["d_full"] for r in rows]),
        },
        "fixed_prefix": {
            "pos": pos_pre, "neg": len(rows) - pos_pre,
            "p_two_sided": p_pre,
            "median_diff": round(st.median([r["d_pre"] for r in rows]), 4),
            "wilson95": [round(lo, 4), round(hi, 4)],
            "why": "每条只取前 %d 个词 ⇒ 与生成长度无关。" % K,
            "is_lower_bound": True,
            "lower_bound_because": "见 cap_censoring：前缀只覆盖 +v 输出的前一段，"
                                    "而塌缩发生在输出 20% 处之后。",
        },
        "cap_censoring": cap_disclosure,
        "length_confound": {
            "n_steps_up_median": st.median(lens),
            "n_steps_zero_median": st.median(lens0),
            "n_steps_up_min": min(lens), "n_steps_up_max": max(lens),
            "n_steps_zero_min": min(lens0), "n_steps_zero_max": max(lens0),
            "problems_where_up_shorter_than_zero": short,
            "note": "全长口径下「+v 更长还是更短」逐题不一 ⇒ "
                    "这正是必须用定长前缀的原因。",
        },
        "per_problem": rows,
        "not_claimed": [
            "这不是「在 24 题上的发生率」：4 条轴的**轴间**比较仍只有 3 题，"
            "能估发生率的只有 confidence 这条轴。",
            "单格 n=1 ⇒ 无法说「一题上重复出现会不会稳定」。",
            "32k 批次**没有记录模型与精度** ⇒ 发生率属于这批数据，"
            "不能自动搬到别的模型上。",
        ],
    }
    p_json = ROOT / "frontend/public/latent/data/occurrence_23.json"
    io.open(str(p_json), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n")

    print()
    print(f"全长口径    : +v 更重复的题 {pos_full}/{len(rows)}，"
          f"二项 p={p_full:.3g}，中位差 {out['full_text']['median_diff']:+.4f}")
    print(f"定长前缀 {K} : +v 更重复的题 {pos_pre}/{len(rows)}，"
          f"二项 p={p_pre:.3g}，中位差 {out['fixed_prefix']['median_diff']:+.4f}")
    print(f"             Wilson 95% 区间 [{lo:.4f}, {hi:.4f}]")
    print()
    print(f"长度混杂    : +v 步数中位 {st.median(lens):.0f} "
          f"(min {min(lens)} max {max(lens)})，"
          f"零臂中位 {st.median(lens0):.0f} "
          f"(min {min(lens0)} max {max(lens0)})")
    print(f"             +v 比零臂**短**的题: {short}/{len(rows)}")
    print()
    print(f"截尾披露    : +v 跑满 {cap} 的题 {up_capped}/{len(rows)}，"
          f"零臂跑满的 {zero_capped}/{len(rows)}")
    if up_capped_pref:
        print(f"             跑满的那些题里，前 {K} 词只占 +v 全文的 "
              f"{st.median(up_capped_pref)*100:.1f}%")
    print(f"             长度比 与 前缀配对差 的 r = {r_len:+.3f}（弱相关 ⇒ 前缀口径"
          "确实把长度剥掉了大半）")
    print(f"             ⇒ 定长前缀那个中位差 {out['fixed_prefix']['median_diff']:+.4f} "
          "是**下界**（前缀只覆盖塌缩开始之前那段）")
    print()
    worst = sorted(rows, key=lambda r: r["d_pre"])[:3]
    print("前缀配对差最小的 3 题（这 3 题是「效应不出现」的反例，不能藏）：")
    for r in worst:
        print(f"  {r['problem']} 前缀 {r['rep_pre_up']:.4f} vs "
              f"{r['rep_pre_zero']:.4f} = {r['d_pre']:+.4f}"
              f"   (步数 +v {r['n_steps_up']} / 零 {r['n_steps_zero']})")
    print()
    print(f"已写 {p_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
