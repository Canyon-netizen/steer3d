#!/usr/bin/env python3
"""最终答案层面的「净变化 0」到底是什么意思 —— 功效与选择效应。

## 为什么要重算

`InterventionOutcomePanel` 印着「本批答对数净变化为 0」。
这句话单独看是对的，但**它不说明没有效应，只说明这个设计看不到效应**。
本项目一直在为别的结论算 CI（§4.13 的配对、§4.11 的 sem），
唯独这一句是裸的。

## 这一层的三个额外麻烦（都比 token 层严重）

**① 分母是被筛出来的。**
`answer_readout.json` 的 `selection.rule` 是
「两臂都跑完 </think>、严格口径下能解析出答案、**且两臂答案不同**」。
批次共 **23** 题（planned 24），只有 **10** 题进了这张表。
⇒ 算净变化的那 10 个，是**按「答案确实变了」挑出来的**。

**② 剩下 13 题的去向不明。**
它们可能是两臂答案相同（正常），也可能是没跑完 / 严格口径解析不出来。
**产物里没有分开记**，所以「答案改变率 = 10/23」这个数只能说是个上界。

**③ 长度偏倚。**
入选要求**两臂都跑完 `</think>`**，而两臂的步数比在 0.93×–1.53× 之间。
跑得更长更容易入选 ⇒ 入选集偏向「两臂都跑到底」的题，
而那正是干预影响最大的那些题。

## 功效：需要 6 个同向翻转

10 个入选题里只有 2 个翻转了正确性（1 正 1 反）。
符号检验（双侧精确）：k 个翻转全部同向时 p = 2 × 0.5^k。

    k=2 → 0.500    k=3 → 0.250    k=4 → 0.125
    k=5 → 0.063    k=6 → 0.031  ← 第一个 < 0.05

⇒ **这个设计需要 10 个里 6 个同向翻转才能拒绝零假设。**
实测是 2 个翻转、一正一反 —— 这是零假设下的**典型**结果，
不是「接近显著」。

## 自证前置（缺一条即 ABORT）

1. 批次题数必须与 `cot_effect_32k.json` 的 `n_problems` 一致（否则分母错了）
2. 入选 10 个的 verdict 计数必须与 `selection.by_verdict` 一致
3. 基线答对数与注入后答对数必须能由 items 重算出来

用法：python3 .cache/xcheck/answer_power.py
"""
import json
import math
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
DATA = ROOT / "frontend/public/latent/data"
OUT = DATA / "answer_power.json"


def clopper_pearson(k, n, alpha=0.05):
    """二项比例的精确区间（Clopper–Pearson）。n=10 时正态近似很难看。

    ⚠ 第一版是我自己手搓的二分，而且把 `alpha/2` 当成了下界条件。
    Clopper–Pearson 的下界解的是 `P(X >= k | p) = alpha/2`，
    也就是 `binom_cdf(k-1) = 1 - alpha/2` —— 我写成了 `= alpha/2`，
    于是 1/10 的下界跑成了 0.308（真值约 0.0025）。
    ⇒ 这里直接用 scipy 的 Beta 分位数（与 `scipy.stats.beta.ppf` 同一公式），
    并且在下面 assert 它与解析式一致。
    """
    from scipy.stats import beta as _beta
    lo = 0.0 if k == 0 else float(_beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(_beta.ppf(1 - alpha / 2, k + 1, n - k))
    # 交叉验证：下界处 P(X >= k | lo) 应恰为 alpha/2
    if 0 < k < n:
        tail = 1.0 - sum(math.comb(n, i) * lo ** i * (1 - lo) ** (n - i)
                         for i in range(k))
        assert abs(tail - alpha / 2) < 1e-6, \
            "CP 下界不自洽：P(X>=k|lo)=%.6f，应为 %.6f" % (tail, alpha / 2)
    return (lo, hi)


def sign_test_two_sided(k):
    """k 个翻转全部同向时的双侧精确 p = 2 × 0.5^k。"""
    return 2.0 * (0.5 ** k)


def main():
    ans = json.loads((DATA / "answer_readout.json").read_text(encoding="utf-8"))
    eff = json.loads((DATA / "cot_effect_32k.json").read_text(encoding="utf-8"))
    problems = []

    def need(c, m):
        if not c:
            problems.append(m)

    items = ans["items"]
    bv = ans["selection"]["by_verdict"]

    # ---- 自证 1：分母 ----
    n_problems = int(eff["n_problems"])
    need(ans["n_runs_analysed"] == eff["n_runs"],
         "两产物的 run 数对不上：answer %d vs cot_effect %d"
         % (ans["n_runs_analysed"], eff["n_runs"]))
    need(len(items) == ans["selection"]["n_shipped"],
         "items %d 条 ≠ n_shipped %d" % (len(items), ans["selection"]["n_shipped"]))

    # ---- 自证 2：verdict 计数 ----
    from collections import Counter
    got = Counter(i["verdict"] for i in items)
    need(dict(got) == bv, "verdict 计数重算 %s ≠ 产物 %s" % (dict(got), bv))

    # ---- 自证 3：基线/注入后答对数 ----
    # ⚠⚠ 第一版把 `right->wrong` 也算进「注入后答对」，于是算出
    #    基线 1 / 注入后 2 / **净变化 +1**。而 `right->wrong` 的意思是
    #    **注入后答错** —— 方向正好相反。
    #    入选规则要求两臂答案**不同**，所以不存在 `right->right` 这一类，
    #    于是两个数都可以直接从 verdict 的两个方向类数出来。
    #    这是「核对表格时派生量比原量更危险」的又一例：一个符号错误
    #    把「无净变化」变成了「净提升 1」。
    base_right = bv.get("right->wrong", 0)      # 注入后变错 ⇒ 基线本来对
    steer_right = bv.get("wrong->right", 0)     # 注入后变对
    n = len(items)
    need(base_right + steer_right + bv.get("wrong->wrong", 0) == n,
         "verdict 三类之和 %d ≠ items %d"
         % (base_right + steer_right + bv.get("wrong->wrong", 0), n))
    problems = [p for p in problems if p]

    up = bv.get("wrong->right", 0)
    down = bv.get("right->wrong", 0)
    flips = up + down
    same_dir = max(up, down)

    up_ci = clopper_pearson(up, n)
    dn_ci = clopper_pearson(down, n)
    p_obs = sign_test_two_sided(flips) if flips else 1.0
    # 要达到 p<0.05 需要多少个同向翻转
    k_needed = next((k for k in range(1, n + 1) if sign_test_two_sided(k) < 0.05), None)

    ratios = [float(i["steps_ratio"]) for i in items if i.get("steps_ratio")]
    not_both = [i["label"] for i in items if not i.get("both_in_domain")]

    if problems:
        print("ABORT 自证不过，不产出文件：")
        for p in problems:
            print("  ✗ " + p)
        return 2

    payload = {
        "schema": "answer_power/1",
        "what": "「本批答对数净变化为 0」这句话的欠功效分析与选择效应",
        "n_problems_in_batch": n_problems,
        "n_shipped": n,
        "selection_rule": ans["selection"]["rule"],
        "direction": ans["direction"],
        "strength": ans["strength"],
        "baseline_correct": base_right,
        "steered_correct": steer_right,
        "net_change": steer_right - base_right,
        "verdicts": dict(bv),
        "flips": flips,
        "flips_up": up, "flips_down": down,
        "up_rate_ci95": list(up_ci),
        "down_rate_ci95": list(dn_ci),
        "two_sided_sign_p_if_all_same_direction": p_obs,
        "flips_needed_for_p05": k_needed,
        "flip_rate_ceiling_over_batch": n / float(n_problems),
        "steps_ratio_min": min(ratios) if ratios else None,
        "steps_ratio_max": max(ratios) if ratios else None,
        "labels_not_both_in_domain": not_both,
        "verdict": (
            "「净变化 0」在这批数据上是**零假设下的典型结果**，不是「接近显著」。\n"
            "① 分母是被筛出来的：%d 题里只有 %d 题进了这张表，"
            "而且入选条件之一是**两臂答案不同** —— 算净变化的样本天然偏向「确实变了」的题。\n"
            "② 只有 %d 个翻转（%d 正 %d 反）。符号检验双侧精确 p = 2×0.5^k，"
            "要 p < 0.05 需要 **%s 个同向翻转**；本设计（%d 题）最多也只能给到 %d 个。\n"
            "⇒ 本批能说的是「在 %d 题的入选子集上，正负翻转各 1 次」，"
            "**不能**说「干预不影响答案正确性」。\n"
            "③ 还有长度偏倚：入选要求两臂都跑完 </think>，"
            "而两臂步数比在 %.2f×–%.2f× 之间 ⇒ 入选集偏向两臂都跑到底的题，"
            "那正是干预影响最大的题。\n"
            "④ 上界：答案改变率 ≤ %d/%d = %.0f%%（剩下 %d 题的去向"
            "（答案相同 / 未跑完 / 解析不出）产物里没分开记，不能编）。"
            % (n_problems, n, flips, up, down, k_needed, n_problems, n,
               n, min(ratios) if ratios else 0, max(ratios) if ratios else 0,
               n, n_problems, 100.0 * n / n_problems, n_problems - n)),
        "not_claimed": (
            "① 不能说「干预对答案正确性无影响」—— 这是**欠功效**，不是零效应。\n"
            "② 不能拿这 %d 题当 23 题的随机样本：它们按「答案不同」筛过。\n"
            "③ 这 %d 题是 %s 一条轴的 −0.2 单档；"
            "另外 3 条命名轴、以及正的 confidence_up 臂都不在这里。\n"
            "④ L7（改变的是概念而非位置/格式）**一次都没测** —— "
            "「答案对不对」这个指标连位置轴对照都没有。"
            % (n, n, ans["direction"])),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("自证全过（3 条）")
    print("  批次 %d 题 → 入选 %d 题（条件含「两臂答案不同」）"
          % (n_problems, n))
    print("  基线答对 %d / 注入后答对 %d ⇒ 净变化 %+d"
          % (base_right, steer_right, steer_right - base_right))
    print("  翻转 %d 个（%d 正 %d 反），若全同向双侧 p = %.3f"
          % (flips, up, down, p_obs))
    print("  要 p<0.05 需要 %s 个同向翻转（本设计上限 %d 个）"
          % (k_needed, n))
    print("  翻正率 95%% CI = [%.3f, %.3f]   翻负率 95%% CI = [%.3f, %.3f]"
          % (up_ci[0], up_ci[1], dn_ci[0], dn_ci[1]))
    print()
    print("已写", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
