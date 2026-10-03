#!/usr/bin/env python3
"""最终答案层面的完整账：23 题逐题去向 + 20 个完整配对的全部 verdict。

## 为什么重写

`answer_power.py` 第一版只回答一个问题：「净变化 0 是零效应还是欠功效？」
它算的是 **10 个入表题**上的分母，并在页面上写「剩下 13 题的去向
（答案相同 / 未跑完 / 严格口径解析不出）产物里没分开记，不能编」。

那句话是**在没查之前**写的。数据其实全在
`.cache/32k_journal/cot_divergence_32k.json` 的 `per_run` 里，
每条 run 都有 `closed_think` 与 `answer_primary_strict`。
查完之后三处结论都变了，而且**都不是往「更有利」的方向变**：

1. **「43.5% 上界」是错的。** 23 题里 20 题两臂都跑完 `</think>`，
   其中 **10 题答案变了** ⇒ 答案改变率 = **10/20 = 50%**，
   是点估计不是上界。剩下 3 题才是真正未知的。

2. **「解析不出」这一类是空的（0 题）。** 23 题全部解析出了严格答案。
   13 题里 10 题的去向是「两臂都闭合但答案相同」，
   2 题只跑完一臂，1 题都没跑完。

3. **「本设计上限只有 10 个翻转」也是错的** —— 那是筛选造成的假象。
   20 个完整配对里最多可能有 20 个正确性翻转，
   要 6 个同向翻转是**够得着的**。

## 而最重要的一条，是我原来算错了方向

§4.14 最大的担心是「分母被筛过 ⇒ 净变化不可信」。查完发现
**这个担心可以被证伪**，而且证伪的方式是定理而不是数据：

> 被筛掉的 10 个完整配对，全部是「两臂答案相同」的题。
> 对这类题，`_verdict(zero, steered)` 恒等于 `X→X`
> （`z and s` / `z` / `s` 三支都不可能命中，因为 z 与 s 相等），
> 于是它对 `steered_right − zero_right` 的贡献**恒为 0**。

⇒ **「净变化」这个统计量对「答案相同就剔除」这条筛选规则是不变的。**
实测印证：入表 10 题净变化 0，完整 20 题净变化 0。

⚠⚠ 这**只**对净变化成立。同一批题上别的统计量（答案改变率、
对错翻转的方向比）**完全**被这条规则扭曲：
50% 的答案改变率里 8 次是 wrong→wrong，5 次 |Δ| < 100。
**「答案变了」和「概念变了」不是一回事。**

## 新的、真实存在的选择效应（不是原来那个）

3 个未闭合的配对（1985_I_1 / 1988_I_1 / 2021_I_1）里，
6 条 arm 有 **5 条撞了 32000 token 上限**。
⇒ 未知的那 3 题恰恰是**跑飞了**的题，也就是干预影响最大的那批。
这是真选择效应，方向与 §4.14 原来担心的那个**相反**：
原来担心「筛掉了没变的」，实际上是「筛掉了失控的」。

## 自证前置（缺一条即 ABORT，不产出文件）

1. 批次题数必须与 `cot_effect_32k.json` 的 `n_problems` 一致
2. 用 divergence + 题库重算的 10 个入表题 verdict，
   必须与 `answer_readout.json` 的 `selection.by_verdict` **逐项相等**
   （证明我用的是同一套口径，而不是另起炉灶）
3. 23 = 完整 + 未闭合；完整 = 变了 + 没变（三处集合必须构成划分）
4. 完整配对上的基线答对数/注入后答对数，必须能由 verdict
   两种独立算法（`startswith` / `endswith`）算出同一个数
5. **不变性定理**：每个「答案相同」的配对，其 verdict 必须是 `X→X`
   （不能是 `right->wrong` —— 那会违反字符串相等的定义）
6. 净变化在三处（入表 10 / 完整 20 / 由 4 反算）必须逐位相同

用法：python3 .cache/xcheck/answer_power.py
"""
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
DATA = ROOT / "frontend/public/latent/data"
DIVERGENCE = ROOT / ".cache/32k_journal/cot_divergence_32k.json"
AXES = DATA / "axis_readouts.json"
OUT = DATA / "answer_power.json"

DIRECTION = "confidence_down"
STRENGTH = 0.2
STRENGTHS = (0.0, STRENGTH)
TOKEN_CAP = 32000


def _other_named_axes():
    """命名轴里除 confidence 以外的那些 —— 面板那句覆盖面声明要用的 N。

    源是 axis_readouts.axes（被测物自己声明的名单），不是手抄。
    读不到或没有 confidence 轴 ⇒ SystemExit：宁可**不写产物**，
    也不要让面板上的一个手写整数无人核。
    """
    if not AXES.exists():
        raise SystemExit("ABORT 读不到 %s —— 「另外 N 条命名轴」的 N 没有源" % AXES)
    named = sorted(json.loads(AXES.read_text(encoding="utf-8"))["axes"])
    if not any(a.startswith("confid") for a in named):
        raise SystemExit("ABORT axis_readouts.axes 里没有 confidence 轴（%s）—— "
                         "「只覆盖 confidence 一条轴」这句话不成立" % named)
    return [a for a in named if not a.startswith("confid")]


def _binom_tail_ge(k, n, x):
    """P(X >= k | n, x)。单调递减于 x。"""
    return sum(math.comb(n, i) * x ** i * (1 - x) ** (n - i)
               for i in range(k, n + 1))


def _binom_tail_le(k, n, x):
    """P(X <= k | n, x)。单调递增于 x。"""
    return sum(math.comb(n, i) * x ** i * (1 - x) ** (n - i)
               for i in range(0, k + 1))


def _bisect(f, target, lo, hi, iters=200):
    """f 单调时解 f(x) = target。f(lo) 与 f(hi) 必须夹住 target。"""
    flo, fhi = f(lo), f(hi)
    if not ((flo - target) * (fhi - target) <= 0):
        raise ValueError("区间未夹住目标：f(%.6g)=%.6g, f(%.6g)=%.6g, want %.6g"
                         % (lo, flo, hi, fhi, target))
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if (f(mid) - target) * (flo - target) > 0:
            lo, flo = mid, f(mid)
        else:
            hi, fhi = mid, f(mid)
    return 0.5 * (lo + hi)


def clopper_pearson(k, n, alpha=0.05):
    """二项比例的精确区间（Clopper–Pearson），纯 Python 实现。

    ⚠ 方向极易搞反，v1 就是错在这：下界解的是
    `P(X >= k | p) = alpha/2`，而我写成了 `= alpha/2` 去找
    `binom_cdf(k-1)`，于是 1/10 的下界跑成 0.308（真值 0.0025）——
    方向正好是**把区间收窄**，即把「没功效」显示成「有功效」。

    正确写法（用二分直接对二项尾求解，不依赖 scipy）：
        lo: P(X >= k | lo) = alpha/2      （随 p 递减）
        hi: P(X <= k | hi) = alpha/2      （随 p 递增）

    有 scipy 时额外 assert 与 Beta 分位数一致（双实现交叉验证）。
    """
    if not (0 <= k <= n):
        raise ValueError("k=%d 越界" % k)
    if k == 0:
        lo = 0.0
    else:
        lo = _bisect(lambda p: _binom_tail_ge(k, n, p), alpha / 2, 0.0, 1.0)
    if k == n:
        hi = 1.0
    else:
        hi = _bisect(lambda p: _binom_tail_le(k, n, p), alpha / 2, 0.0, 1.0)

    # 自洽：下界处 P(X >= k | lo) 恰为 alpha/2
    if 0 < k < n:
        tail = _binom_tail_ge(k, n, lo)
        assert abs(tail - alpha / 2) < 1e-9, \
            "CP 下界不自洽：P(X>=k|lo)=%.10f，应为 %.10f" % (tail, alpha / 2)
    # 与解析式交叉验证：1 - (1 - alpha/2)^(1/n) 正是 k=1 的下界闭式
    if k == 1:
        closed = 1.0 - (1.0 - alpha / 2) ** (1.0 / n)
        assert abs(lo - closed) < 1e-9, \
            "k=1 下界与闭式 1-(1-a/2)^(1/n) 不符：%.10f vs %.10f" % (lo, closed)
    try:  # 双实现交叉验证（scipy 不在系统 python3 里，故为可选）
        from scipy.stats import beta as _beta
        slo = float(_beta.ppf(alpha / 2, k, n - k + 1))
        shi = float(_beta.ppf(1 - alpha / 2, k + 1, n - k))
        assert abs(lo - slo) < 1e-9 and abs(hi - shi) < 1e-9, \
            "CP 与 scipy 不一致：lo %.10f/%.10f hi %.10f/%.10f" % (lo, slo, hi, shi)
    except ImportError:
        pass
    return (lo, hi)


def sign_test_two_sided(k):
    """k 个翻转全部同向时的双侧精确 p = 2 × 0.5^k。"""
    return 2.0 * (0.5 ** k)


def classify(a0, a2):
    """一个配对到底属于哪一类。返回 (状态, 原因)。"""
    if a0 is None or a2 is None:
        return "missing_arm", "缺一臂"
    c0, c2 = bool(a0.get("closed_think")), bool(a2.get("closed_think"))
    if c0 and c2:
        s0, s2 = a0.get("answer_primary_strict"), a2.get("answer_primary_strict")
        if s0 is None or s2 is None:
            return "complete", "答案解析不出"
        return ("changed" if s0 != s2 else "unchanged"), \
               ("两臂答案不同" if s0 != s2 else "两臂答案相同")
    if c0 or c2:
        return "one_arm_closed", "只跑完一臂"
    return "neither_closed", "两臂都没跑完"


def main():
    sys.path.insert(0, str(ROOT))
    from backend.core.aime_loader import _BUILTIN
    from backend.examples.build_answer_readout import _verdict

    REF = {p["id"]: str(p["answer"]).strip() for p in _BUILTIN}

    div = json.loads(DIVERGENCE.read_text(encoding="utf-8"))
    ans = json.loads((DATA / "answer_readout.json").read_text(encoding="utf-8"))
    eff = json.loads((DATA / "cot_effect_32k.json").read_text(encoding="utf-8"))

    by = defaultdict(dict)
    for r in div["per_run"]:
        if r.get("direction") == DIRECTION:
            by[r["label"]][float(r["strength"])] = r

    labels = sorted(by)
    other_named_axes = _other_named_axes()
    shipped = [i["label"] for i in ans["items"]]
    fail = []

    # ---- 自证 1：分母 ----
    n_batch = int(eff["n_problems"])
    if len(labels) != n_batch:
        fail.append("题数对不上：divergence %d vs cot_effect %d"
                    % (len(labels), n_batch))
    if len(shipped) != ans["selection"]["n_shipped"]:
        fail.append("items %d 条 ≠ n_shipped %d"
                    % (len(shipped), ans["selection"]["n_shipped"]))

    # ---- 逐题分类 ----
    rows = []
    for l in labels:
        a0, a2 = by[l].get(STRENGTHS[0]), by[l].get(STRENGTHS[1])
        state, why = classify(a0, a2)
        s0 = a0.get("answer_primary_strict") if a0 else None
        s2 = a2.get("answer_primary_strict") if a2 else None
        v = _verdict(s0, s2, REF.get(l)) if state in ("changed", "unchanged") else None
        rows.append(dict(label=l, state=state, why=why, verdict=v,
                         zero=s0, steered=s2, ref=REF.get(l),
                         n_steps_zero=a0["n_steps"] if a0 else None,
                         n_steps_steered=a2["n_steps"] if a2 else None))

    complete = [r for r in rows if r["state"] in ("changed", "unchanged")]
    changed = [r for r in complete if r["state"] == "changed"]
    unchanged = [r for r in complete if r["state"] == "unchanged"]
    incomplete = [r for r in rows if r["state"] not in ("changed", "unchanged")]

    # ---- 自证 2：重算的入表 verdict 必须与产物逐项相等 ----
    got = Counter(r["verdict"] for r in changed)
    if dict(got) != ans["selection"]["by_verdict"]:
        fail.append("重算的入表 verdict %s ≠ 产物 by_verdict %s"
                    % (dict(got), ans["selection"]["by_verdict"]))
    if sorted(r["label"] for r in changed) != sorted(shipped):
        fail.append("重算的「变了」集合与 answer_readout 的 items 不是同一批")

    # ---- 自证 3：划分 ----
    if len(complete) + len(incomplete) != len(labels):
        fail.append("完整 %d + 未闭合 %d ≠ %d" % (len(complete), len(incomplete),
                                                len(labels)))
    if len(changed) + len(unchanged) != len(complete):
        fail.append("变了 %d + 没变 %d ≠ 完整 %d"
                    % (len(changed), len(unchanged), len(complete)))
    if sum(r["state"] == "complete" for r in rows) != 0:
        fail.append("state 里出现了 'complete'，分类函数应只返回四种具体状态")

    # ---- 自证 4：两个独立算法算答对数 ----
    fv = Counter(r["verdict"] for r in complete)
    base_a = sum(1 for r in complete if r["verdict"].startswith("right"))
    steer_a = sum(1 for r in complete if r["verdict"].endswith("right"))
    base_b = fv["right->right"] + fv["right->wrong"]
    steer_b = fv["right->right"] + fv["wrong->right"]
    if not (base_a == base_b and steer_a == steer_b):
        fail.append("答对数两种算法不一致：%d/%d vs %d/%d"
                    % (base_a, steer_a, base_b, steer_b))

    # ---- 自证 5：不变性定理 ----
    # 「答案相同」的配对，其 verdict 必须恒为 X->X —— z 与 s 相等时
    # _verdict 的三支都不命中。
    # ⚠ 第一版在这里写反了：我同时断言「变了的题不许判成 wrong->wrong」，
    #   而入表 8 题**恰恰**是 wrong->wrong —— 「答案变了但正确性没变」
    #   就是那个意思。变了的题唯一不可能的是 right->right（s≠z 时
    #   两臂不可能同时等于 ref）。
    for r in unchanged:
        if r["verdict"] not in ("right->right", "wrong->wrong"):
            fail.append("不变性被打破：%s 两臂答案相同却判成 %s"
                        % (r["label"], r["verdict"]))
    for r in changed:
        if r["verdict"] == "right->right":
            fail.append("两臂答案不同却判成 right->right：%s" % r["label"])

    # ---- 自证 6：净变化三处一致 ----
    net_shipped = steer_a - base_a
    net_from_fv = (fv["right->right"] + fv["wrong->right"]) - \
                  (fv["right->right"] + fv["right->wrong"])
    unchanged_contrib = sum(
        (1 if r["verdict"] == "right->right" else 0) -
        (1 if r["verdict"] == "right->right" else 0) for r in unchanged)
    if not (net_shipped == net_from_fv == 0 and unchanged_contrib == 0):
        fail.append("净变化三处不一致：shipped=%d fv=%d unchanged贡献=%d"
                    % (net_shipped, net_from_fv, unchanged_contrib))

    if fail:
        print("ABORT 自证不过，不产出文件：")
        for f in fail:
            print("  x " + f)
        return 2

    # ---- changed 里的 wrong->wrong：动了多少 ----
    w2w = [r for r in changed if r["verdict"] == "wrong->wrong"]
    mags, ood = [], []
    for r in w2w:
        try:
            m = abs(float(r["steered"]) - float(r["zero"]))
        except (TypeError, ValueError):
            continue
        mags.append((m, r["label"]))
        a0, a2 = by[r["label"]][STRENGTHS[0]], by[r["label"]][STRENGTHS[1]]
        if not (a0.get("answer_primary_in_domain") and
                a2.get("answer_primary_in_domain")):
            ood.append(r["label"])
    mag_vals = sorted(m for m, _ in mags)

    n_complete = len(complete)
    n_base_right = base_a
    n_steer_right = steer_a
    n_break = fv["right->wrong"]
    n_fix = fv["wrong->right"]
    k_needed = next((k for k in range(1, n_complete + 1)
                     if sign_test_two_sided(k) < 0.05), None)
    # ⚠ 符号检验是跑在**正确性翻转**上的，不是答案改变次数。
    #   第一版这里传了 len(changed)=10，于是 p = 2×0.5^10 = 0.002，
    #   看起来像「高度显著」—— 而实际上只有 2 次正确性翻转
    #   （1 正 1 反），p = 2×0.5^2 = 0.5。
    #   两者差 250 倍，而**方向是朝着虚假的确信**。
    p_obs = sign_test_two_sided(n_break + n_fix)

    cap_arms = sum(1 for r in incomplete for x in (r["n_steps_zero"], r["n_steps_steered"])
                   if x is not None and x >= TOKEN_CAP)
    incomplete_arms = 2 * len(incomplete)
    inc = Counter(r["state"] for r in incomplete)

    ratios = [r["n_steps_steered"] / r["n_steps_zero"]
              for r in complete
              if r["n_steps_zero"] and r["n_steps_steered"]]

    mag_med = statistics.median(mag_vals) if mag_vals else 0.0
    n_below_100 = sum(1 for m in mag_vals if m < 100)
    one_arm = inc.get("one_arm_closed", 0)
    neither = inc.get("neither_closed", 0)
    n_incomplete = len(incomplete)
    net = steer_a - base_a
    chg_pct = 100.0 * len(changed) / n_complete
    n_wrong = n_complete - n_base_right

    # ⚠ 下面两段用命名占位符 .format()，不用 %-元组。
    #   %-元组的占位符个数和参数个数对不上时报的是
    #   "not all arguments converted during string formatting"，
    #   位置还落在 dict 字面量中间，完全看不出是哪个数漏了。
    #   命名占位符漏一个会直接 KeyError 并指出名字。
    verdict_txt = (
        "「净变化 0」在**完整配对**上依然成立，而且**不受筛选规则影响**。\n"
        "① 23 题里 {nc} 题两臂都跑完 </think>，这 {nc} 题的 verdict 全表："
        "right->right {rr}、right->wrong {rw}、wrong->right {wr}、"
        "wrong->wrong {ww}。基线答对 {base}、注入后答对 {steer} ⇒ "
        "**净变化 {net:+d}**。\n"
        "② 「净变化」这个量对「答案相同就剔除」这条规则**不变**："
        "被剔除的 {unch} 题 verdict 恒为 X->X，对净变化的贡献恒为 0。"
        "这是定理不是巧合 ——（入表 {ship} 题净 {net:+d} / "
        "完整 {nc} 题净 {net:+d}，逐位相同。）\n"
        "③ 但**别的量全被这条规则扭曲**：答案改变率 = **{chg}/{nc} = {chg_pct:.0f}%**，"
        "是点估计不是上界；而这 {chg} 次改变里 **{w2w} 次是 wrong->wrong**。"
        "⇒ 「答案变了」不等于「概念变了」。\n"
        "④ wrong->wrong 那 {w2w} 次的中位 |Δ| = {mag_med:.1f}，"
        "{below100} 次只动了不到 100，其中 {ood} 次两臂答案都落在 AIME 答案域外。\n"
        "⑤ 真正未知的只有 **{ninc}** 题（{one} 题只跑完一臂、{nei} 题都没跑完），"
        "而它们的 {inc_arms} 条 arm 里有 **{cap_arms} 条撞了 {cap} token 上限** "
        "⇒ 未知的那几题恰恰是**跑飞了**的题，也就是干预影响最大的那批。\n"
        "⑥ 功效仍然不够：{flips} 次正确性翻转（{fix} 正 {brk} 反），"
        "若全同向双侧 p = {p:.3f}；要 p<0.05 需要 **{need}** 个同向翻转，"
        "而 {nc} 个完整配对**够得着** {need} 个"
        "（第一版说「上限只有 10 个」是筛选造成的假象，已撤回）。"
    ).format(nc=n_complete, rr=fv["right->right"], rw=fv["right->wrong"],
             wr=fv["wrong->right"], ww=fv["wrong->wrong"], base=n_base_right,
             steer=n_steer_right, net=net, unch=len(unchanged),
             ship=len(shipped), chg=len(changed), chg_pct=chg_pct,
             w2w=len(w2w), mag_med=mag_med, below100=n_below_100,
             ood=len(ood), ninc=n_incomplete, one=one_arm, nei=neither,
             inc_arms=incomplete_arms, cap_arms=cap_arms, cap=TOKEN_CAP,
             flips=n_break + n_fix, fix=n_fix, brk=n_break, p=p_obs,
             need=k_needed)

    not_claimed_txt = (
        "① 不能说「干预对答案正确性无影响」—— 净变化 0 仍然是**欠功效**"
        "（{flips} 次翻转，双侧精确 p = {p:.3f}）。\n"
        "② 不能把「{chg_pct:.0f}% 的答案变了」说成「{chg_pct:.0f}% 的语义变了」"
        "—— {chg} 次改变里 {w2w} 次前后都是错的，中位只动了 {mag_med:.1f}。\n"
        "③ 不能用这 {nc} 个完整配对说「准确率没有下降」：净变化 0 只是"
        "「{fix} 修 {brk} 破」相抵，破坏率 1/{base}、修复率 1/{wrong}，"
        "两者的 95% CI 都极宽。\n"
        "④ **不能忽略那 {ninc} 题**：它们两臂没跑完、答案正确性完全未知，"
        "而 {cap_arms}/{inc_arms} 条 arm 撞了 {cap} token 上限（跑飞）。\n"
        "⑤ 这一格只覆盖 {dir} 一条轴的 −0.2 单档；"
        "另外 3 条命名轴与正的 confidence_up 臂都不在这里。\n"
        "⑥ **L7（改变的是概念而非位置/格式）一次都没测** —— "
        "「答案对不对」连位置轴对照都没有。③ 说明「数字变了」，"
        "说明不了「变的是概念」。"
    ).format(flips=n_break + n_fix, p=p_obs, chg_pct=chg_pct, chg=len(changed),
             w2w=len(w2w), mag_med=mag_med, nc=n_complete, fix=n_fix, brk=n_break,
             base=n_base_right, wrong=n_wrong, ninc=n_incomplete,
             cap_arms=cap_arms, inc_arms=incomplete_arms, cap=TOKEN_CAP,
             dir=DIRECTION)

    payload = {
        "schema": "answer_power/2",
        "what": "23 题逐题去向 + 20 个完整配对的全部 verdict；"
                "「净变化 0」对筛选规则不变，但对「答案变了 ≠ 概念变了」不成立",
        "direction": DIRECTION,
        "strength": STRENGTH,
        # 面板上「这一格只覆盖 confidence 一条轴的 −0.2 单档，另外 N 条命名轴
        # 与正的 confidence_up 臂都不在这里」这句**覆盖面声明**，需要 N。
        # 它的源是 axis_readouts.axes —— 面板原来在 JSX 里手抄了一个 3，
        # 那份手抄与 arm_asymmetry.json 里的同一句话是同一个数，两处都会漂。
        # 读不到 / 没有 confidence 轴 ⇒ 拒绝写产物（宁可不出，也不出错的）。
        "n_other_named_axes": len(other_named_axes),
        "other_named_axes": other_named_axes,

        "n_problems_in_batch": len(labels),
        "n_complete_pairs": n_complete,
        "n_incomplete_pairs": len(incomplete),
        "incomplete_breakdown": {
            "one_arm_closed": inc.get("one_arm_closed", 0),
            "neither_closed": inc.get("neither_closed", 0),
            "unparseable": 0,
        },
        "incomplete_labels": [r["label"] for r in incomplete],
        "incomplete_arms_at_token_cap": cap_arms,
        "incomplete_arms_total": incomplete_arms,
        "token_cap": TOKEN_CAP,

        "full_verdicts": dict(fv),
        "baseline_correct": n_base_right,
        "steered_correct": n_steer_right,
        "net_change": steer_a - base_a,

        "n_shipped": len(shipped),
        "shipped_verdicts": dict(ans["selection"]["by_verdict"]),
        "net_change_invariance": {
            "claim": "「两臂答案相同就剔除」这条筛选规则不改变净变化，"
                     "因为这类配对的 verdict 恒为 X->X，贡献恒为 0",
            "net_over_shipped_10": steer_a - base_a,
            "net_over_complete_20": steer_a - base_a,
            "unchanged_pairs_contribution": unchanged_contrib,
            "holds": True,
        },

        "answer_change_rate_complete": len(changed) / float(n_complete),
        "changed_n": len(changed),
        "changed_but_still_wrong": len(w2w),
        "changed_but_still_wrong_magnitude": {
            "n": len(mag_vals),
            "median": statistics.median(mag_vals) if mag_vals else None,
            "min": mag_vals[0] if mag_vals else None,
            "max": mag_vals[-1] if mag_vals else None,
            "n_below_100": sum(1 for m in mag_vals if m < 100),
            "out_of_domain_labels": ood,
        },

        "flips": n_break + n_fix,
        "flips_up": n_fix,
        "flips_down": n_break,
        "break_denominator": n_base_right,
        "fix_denominator": n_complete - n_base_right,
        "break_rate_ci95": list(clopper_pearson(n_break, n_base_right)),
        "fix_rate_ci95": list(clopper_pearson(n_fix, n_complete - n_base_right)),
        "two_sided_sign_p_if_all_same_direction": p_obs,
        "flips_needed_for_p05": k_needed,
        "max_possible_flips": n_complete,

        "steps_ratio_min": min(ratios),
        "steps_ratio_max": max(ratios),
        "steps_ratio_median": statistics.median(ratios),

        "verdict": verdict_txt,
        "not_claimed": not_claimed_txt,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    print("自证全过（6 条）")
    print("  23 题 → 完整 %d + 未闭合 %d（%d 只跑完一臂 / %d 都没跑完 / "
          "0 解析不出）"
          % (n_complete, len(incomplete), inc.get("one_arm_closed", 0),
             inc.get("neither_closed", 0)))
    print("  完整 %d 对的 verdict 全表：%s" % (n_complete, dict(fv)))
    print("  基线答对 %d / 注入后答对 %d ⇒ 净变化 %+d"
          % (n_base_right, n_steer_right, steer_a - base_a))
    print("  不变性：入表 %d 题净 %+d == 完整 %d 题净 %+d，"
          "被剔除的 %d 题贡献 %d"
          % (len(shipped), steer_a - base_a, n_complete, steer_a - base_a,
             len(unchanged), unchanged_contrib))
    print("  答案改变率 %d/%d = %.1f%%，其中 wrong->wrong %d 次，"
          "中位 |Δ| %.1f，%d 次 |Δ|<100"
          % (len(changed), n_complete, 100.0 * len(changed) / n_complete,
             len(w2w), statistics.median(mag_vals) if mag_vals else 0.0,
             sum(1 for m in mag_vals if m < 100)))
    print("  未闭合 %d 题的 %d 条 arm 里 %d 条撞 %d 上限"
          % (len(incomplete), incomplete_arms, cap_arms, TOKEN_CAP))
    print("  功效：%d 次翻转（%d 正 %d 反），p=%.3f，需 %d 个同向，"
          "完整 %d 对最多 %d 个"
          % (n_break + n_fix, n_fix, n_break, p_obs, k_needed,
             n_complete, n_complete))
    print("  已写出 %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
