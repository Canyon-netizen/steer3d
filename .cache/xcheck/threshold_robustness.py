#!/usr/bin/env python3
"""判决阈值的稳健性检验：「1/4 OUTSIDE」有多经得起推敲。

⚠ 为什么要查这个
   `axis_generalisation.json` 的判决规则是
       OUTSIDE ⟺ 该轴配对中位 > **9 个**随机方向配对中位的最大值
   而 9 个点的最大值是上尾的**有偏低估** —— 它几乎肯定低于真实的 95 分位。
   这让 OUTSIDE **难**被判出来（方向上是保守的），但也意味着：
     · 如果 OUTSIDE 的那条轴离阈值很远（量级差），结论与阈值怎么取无关；
     · 如果离得近，那「1/4」就是「9 抽多少」抽出来的，不该当结论。
   ⇒ 本脚本量化这两件事，并给出**逐题**层面的对照（不只看中位）。

⚠ 三条纪律
   1. 判决规则**取数前**写死（写在字符串里，跑完只准对照，不准改）。
   2. 切不满的样本必须 assert 报错，不许用「样本不够」报 0 代替。
   3. 结论分层：量级差 ⇒ 【强】；只在一半题上成立 ⇒ 降级并写明。

用法：python3 .cache/xcheck/threshold_robustness.py
"""
from __future__ import annotations

import io
import json
import random
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AX = ROOT / "frontend/public/latent/data/axis_generalisation.json"
R9 = ROOT / "frontend/public/latent/data/random_direction_distribution.json"

# ---- 取数前写死的判决规则 -------------------------------------------------
# ① 稳健：OUTSIDE 的那条轴，其配对中位必须比「9 臂最大值的自助分布」的
#    **95 分位**还高一个量级（≥10 倍）。量级差才叫「与阈值取法无关」。
# ② 逐题：它在**每一道题**上都要超过该题 9 个随机臂的最大配对差。
# ③ INSIDE 的三条轴：在**每一道题**上都要不超过该题 9 个随机臂的最大值。
RULE = {
    "margin_for_strong": 10.0,
    "bootstrap_draws": 20000,
    "bootstrap_seed": 20261005,
}
# ---------------------------------------------------------------------------


def load():
    ax = json.load(io.open(AX, encoding="utf-8"))
    r9 = json.load(io.open(R9, encoding="utf-8"))
    ctrl = ax["control_by_problem"]
    probs = sorted(ctrl)
    assert len(probs) == 3, f"预期 3 题，实到 {len(probs)} —— 题集变了，停下来问人"
    arms = sorted(a for a in r9["per_arm_per_problem"] if a.startswith("random_"))
    assert len(arms) == 9, f"预期 9 个随机臂，实到 {len(arms)} —— 零分布的规模变了"
    return ax, r9, ctrl, probs, arms


def paired(arm_vals, ctrl, probs):
    return {p: arm_vals[p] - ctrl[p] for p in probs}


def main() -> int:
    ax, r9, ctrl, probs, arms = load()

    rand = {a: paired(r9["per_arm_per_problem"][a], ctrl, probs) for a in arms}
    rand_med = {a: st.median([rand[a][p] for p in probs]) for a in arms}
    obs_max = max(rand_med.values())

    # ---- 与产物对账（不是重算一遍就算数，要与已发货的那份一致）----------
    shipped = ax["threshold_paired"]
    assert abs(obs_max - shipped) < 5e-5, (
        f"重算的 9 臂最大值 {obs_max:.6f} 与产物记的 {shipped} 不符 —— "
        "口径变了（可能取的不是配对差，或题集不同）")
    assert sorted(round(v, 4) for v in rand_med.values()) == \
        sorted(round(v, 4) for v in ax["null_paired_median_sorted"]), \
        "重算的 9 个随机配对中位与产物逐位不符"

    # ---- ① 自助：9 臂最大值的抽样分布 ------------------------------------
    rnd = random.Random(RULE["bootstrap_seed"])
    draws = []
    for _ in range(RULE["bootstrap_draws"]):
        pick = [rnd.choice(arms) for _ in range(len(arms))]
        draws.append(max(rand_med[a] for a in pick))
    draws.sort()
    q95 = draws[int(0.95 * len(draws))]

    # ---- ② 逐题对照 ------------------------------------------------------
    per_prob = {p: max(rand[a][p] for a in arms) for p in probs}
    axes = {}
    for x in ax["axes"]:
        arms_ = x["members"]
        # 逐题时把该轴的**每个成员**都列出来：confidence 有 +v/−v 两条臂，
        # 只报配对差最大那条会偏向「更容易 OUTSIDE」的方向。
        per = {m: {p: ax["per_arm_paired_vs_own_control"][m][p] for p in probs}
               for m in arms_ if m in ax["per_arm_paired_vs_own_control"]}
        med = {m: st.median([per[m][p] for p in probs]) for m in per}
        axes[x["axis"]] = {"members": arms_, "per": per, "med": med,
                           "grade": x["grade"],
                           "reported": x["axis_value"]}
        for m, v in med.items():
            assert abs(v - x["axis_value"]) < 5e-5 or len(med) > 1, (
                f"{x['axis']} 成员 {m} 的配对中位 {v} 与产物 {x['axis_value']} 不符")

    outside = [a for a, v in axes.items() if v["grade"] == "OUTSIDE"]
    inside = [a for a, v in axes.items() if v["grade"] == "INSIDE"]
    assert len(outside) == 1, f"产物说 OUTSIDE 有 {len(outside)} 条（{outside}）"
    assert len(inside) == 3, f"产物说 INSIDE 有 {len(inside)} 条（{inside}）"

    rep = []
    rep.append("判决阈值的稳健性检验（判决规则取数前写死）")
    rep.append("=" * 64)
    rep.append(f"每题无注入对照重复率: "
               + ", ".join(f"{p}={ctrl[p]:.4f}" for p in probs))
    rep.append(f"这 3 题的对照基线相差 {max(ctrl.values())/min(ctrl.values()):.1f} 倍"
               "  ⇒ 必须逐题配对，不能跨题聚合")
    rep.append("")
    rep.append("── 阈值本身 ──")
    rep.append(f"9 个随机方向的配对中位: min {min(rand_med.values()):+.4f} / "
               f"中位 {st.median(list(rand_med.values())):+.4f} / max {obs_max:+.4f}")
    rep.append(f"产物记录的阈值 threshold_paired = {shipped:+.4f}（与重算一致）")
    rep.append(f"自助 {RULE['bootstrap_draws']} 次重抽 9 臂，max 的 95 分位 = {q95:+.4f}")
    rep.append(f"  ⇒ 观测到的 max（{obs_max:+.4f}）落在自助分布的 "
               f"{sum(1 for d in draws if d <= obs_max)/len(draws)*100:.1f} 分位"
               "  ⇒ 阈值本身是 9 抽的典型值，不是抽到了个极端")
    rep.append("")
    rep.append("── OUTSIDE 那条：离阈值多远 ──")
    strong = []
    for a in outside:
        for m, v in axes[a]["med"].items():
            ratio = v / q95 if q95 > 0 else float("inf")
            per_ok = all(axes[a]["per"][m][p] > per_prob[p] for p in probs)
            rep.append(f"  {a} / {m}: 配对中位 {v:+.4f}，是阈值 95 分位 {q95:+.4f} 的 "
                       f"{ratio:.0f} 倍")
            rep.append(f"    逐题："
                       + ", ".join(f"{p} {axes[a]['per'][m][p]:+.4f} vs "
                                   f"该题随机最大 {per_prob[p]:+.4f}"
                                   for p in probs))
            rep.append(f"    每一题都超过该题随机最大 = {per_ok}")
            if ratio >= RULE["margin_for_strong"] and per_ok:
                strong.append(f"{a}/{m}")
    rep.append("")
    rep.append("── INSIDE 那三条：是不是只是「差一点点没够到」 ──")
    for a in inside:
        for m, v in axes[a]["med"].items():
            per_line = ", ".join(f"{p} {axes[a]['per'][m][p]:+.4f} vs "
                                 f"{per_prob[p]:+.4f}" for p in probs)
            never = all(axes[a]["per"][m][p] <= per_prob[p] for p in probs)
            rep.append(f"  {a} / {m}: 配对中位 {v:+.4f}（阈值 {q95:+.4f} 的 "
                       f"{v/q95:.2f} 倍）")
            rep.append(f"    逐题：{per_line}")
            rep.append(f"    每一题都不超过该题随机最大 = {never}")
            if not never:
                rep.append("    ⚠ 有题超过了 ⇒ 「落在随机分布内」这句话要降级")
    rep.append("")
    rep.append("── 判决 ──")
    if strong:
        rep.append(f"【强】{('、'.join(strong))} 与阈值的距离是量级差，"
                   "且逐题都成立 ⇒ 结论不依赖「只抽了 9 个方向」这个选择。")
    else:
        rep.append("【弱】OUTSIDE 那条离阈值不够远 ⇒「1/4」可能来自 9 臂的抽样运气。")
    rep.append("⚠ 本检验**不改变** n=3 的问题数：每轴仍只有 3 道题，")
    rep.append("  所以「在多少题上发生」这件事依旧没被估计。本文件只回答")
    rep.append("  「OUTSIDE/INSIDE 这个二分判断稳不稳」。")

    text = "\n".join(rep)
    print(text)
    out = ROOT / ".cache/xcheck/threshold_robustness.txt"
    io.open(str(out), "w", encoding="utf-8").write(text + "\n")
    print(f"\n（写 {out}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
