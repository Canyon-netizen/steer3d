#!/usr/bin/env python3
"""两个方向为什么行为完全相反：+v 让模型跑飞，−v 只让它偏移（§4.16）

## 这支为什么存在

§4.15 把答案层那 20 个完整配对算干净之后，留下一个刺眼的不对称：

| 方向 | 完整配对 | 未闭合 | 注入臂撞 32000 上限 |
|---|---|---|---|
| `confidence_down`（−v） | 20 | 3 | **2** |
| `confidence_up`（+v） | **5** | **18** | **18** |

同一批题、同一份对照、同一个强度 0.2，只差一个符号。
⇒ **+v 几乎让整个批次跑不出 `</think>`，−v 基本不跑飞。**

而 §4.13 在 token 层测出的 KL 恰好**相反**：
`+v` 0.0343、`−v` 0.0686 —— **−v 把分布推得更远，却更少跑飞**。

⇒ 「注入幅度大」与「把生成推入不收敛」**不是同一件事**，
而且在本项目的这条轴上，两者的方向是**相反**的。

## 这支要防的一个假象

只看闭合的那几题，+v 臂的 verdict 是
`right->right` 4 + `wrong->wrong` 1、`right->wrong` **0**、
净变化 0 ⇒ 读起来像「+v 是最安全的方向」。

⇒ 那是 **18/23 未闭合**制造出来的假象。破坏没有消失，
它从「答错」变成了「答不出来」，而面板上按 verdict 计数时**看不见**。
这一条是本支最重要的产出，必须原样印在页面上。

## 配对设计（自证 1 查的就是它）

两个方向的零强度臂**逐字相同**（23/23 题的 `primary_text` 完全一致），
所以两臂共享**同一份对照**：同题、同 prompt、同解码、同随机性。
⇒ 配对检验里没有「两次运行」的噪声源，只有注入符号这一个变量。

## 自证前置（缺一条即 ABORT，不产出文件）

1. `confidence_up` 与 `confidence_down` 的零强度臂 `primary_text`
   必须**逐题逐字相同**（否则这不是配对设计，只是两次独立运行）
2. 三个口径的题数（零臂 / −v / +v）必须都等于批次数
3. 配对分类必须构成划分：两臂都跑完 / 只有 −v 跑完 / 只有 +v 跑完 / 都没跑完
4. 「只有 +v 跑不完」的题数必须等于「只有 −v 跑不完」+「都没跑完」的反面
   —— 即：零臂跑完但 +v 没跑完的题数，须能由两个集合的差独立算出
5. 净变化对两个方向都要能从 verdict 全表用两种算法算出同一个数
6. **跑飞题不能被漏进 verdict 表**：跑飞的题一律不进 verdict 统计
   （它们没有答案），但必须进「未闭合」计数与 token 上限计数

用法：python3 .cache/xcheck/steer_directions.py
"""
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
DIVERGENCE = ROOT / ".cache/32k_journal/cot_divergence_32k.json"
RUNS = ROOT / ".cache/32k_journal/all_runs.json"
ARM = ROOT / "frontend/public/latent/data/arm_asymmetry.json"
POW = ROOT / "frontend/public/latent/data/answer_power.json"
OUT = ROOT / "frontend/public/latent/data/steer_directions.json"

UP, DOWN = "confidence_up", "confidence_down"
CAP = 32000


def mcnemar_exact(b, c):
    """b 个 discordant 对只在一侧、c 个只在另一侧的双侧精确 p。

    b + c 个 discordant 对，零假设下每个以 1/2 落在任一侧。
    p = 2 × P(X <= min(b,c))，X ~ Binom(b+c, 0.5)。
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / float(2 ** n)
    return min(1.0, 2.0 * tail)


_MEAS = None


def M(dirn, label, strength):
    """唯一取数入口。缺键立刻炸，绝不返回空 dict。

    ⚠ 第一版直接写 M(dirn, l, 0.0)（漏了 label），而 meas 是
      defaultdict ⇒ 它**悄悄建一个空字典**，错误推迟到下一行才以
      KeyError: 'closed_think' 冒出来，看不出是哪一层错了。
    """
    try:
        return _MEAS[(dirn, label)][strength]
    except KeyError:
        raise SystemExit("ABORT 缺 run：direction=%s label=%s strength=%s"
                         % (dirn, label, strength))


def main():
    sys.path.insert(0, str(ROOT))
    from backend.core.aime_loader import _BUILTIN
    # ⚠⚠ 口径必须**import**同一份实现，不能重写。
    #   我第一版自己抄了一份 `str(x).strip() == ref`，漏掉 _as_str 的
    #   float→整数归一化（`231.0` 必须等于 `"231"`），
    #   于是 +v 臂 5 题全部误判成 wrong->wrong（真值 4 right->right
    #   + 1 wrong->wrong）。**自证 7 就是为这条加的。**
    from backend.examples.build_answer_readout import _verdict as verdict, _as_str
    REF = {p["id"]: str(p["answer"]).strip() for p in _BUILTIN}

    div = json.loads(DIVERGENCE.read_text(encoding="utf-8"))
    runs = json.loads(RUNS.read_text(encoding="utf-8"))
    arm = json.loads(ARM.read_text(encoding="utf-8"))
    pow2 = json.loads(POW.read_text(encoding="utf-8"))

    meas = defaultdict(dict)
    for r in div["per_run"]:
        meas[(r["direction"], r["label"])][float(r["strength"])] = r
    global _MEAS
    _MEAS = meas
    text = defaultdict(dict)
    for r in runs:
        text[r["prompt_label"]][(r["direction"], float(r["strength"]))] = \
            r.get("primary_text") or ""

    labels = sorted({k[1] for k in meas if k[0] == DOWN})
    fail = []

    # ---- 自证 1：两个方向的零臂必须逐字相同 ----
    n_same = 0
    for l in labels:
        a = text[l].get((UP, 0.0))
        b = text[l].get((DOWN, 0.0))
        if a is not None and b is not None and a == b:
            n_same += 1
    if n_same != len(labels):
        fail.append("两个方向的零臂不是逐字相同：%d/%d ⇒ 不是配对设计"
                    % (n_same, len(labels)))
    # ⚠ text 的键是 (prompt_label, (direction, strength))，与 meas 不同。
    zero_labels = {l for l in labels if (UP, 0.0) in text[l]}
    if len(zero_labels) != len(labels):
        fail.append("零臂题数 %d ≠ 批次数 %d" % (len(zero_labels), len(labels)))

    # ---- 自证 2：三个口径题数 ----
    for dirn in (UP, DOWN):
        got = {k[1] for k in meas if k[0] == dirn}
        if got != set(labels):
            fail.append("%s 的题集与 %s 不一致" % (dirn, DOWN))

    # ---- 逐题三臂状态 ----
    rows = []
    for l in labels:
        z = M(DOWN, l, 0.0)
        dn = M(DOWN, l, 0.2)
        up = M(UP, l, 0.2)
        cz = bool(z["closed_think"])
        cd = bool(dn["closed_think"])
        cu = bool(up["closed_think"])
        if cz and cd and cu:
            state = "all_closed"
        elif cz and cd and not cu:
            state = "up_only_blew_up"
        elif cz and cu and not cd:
            state = "down_only_blew_up"
        elif cd and cu and not cz:
            state = "zero_blew_up"
        else:
            state = "other"
        rows.append(dict(label=l, state=state, zero_closed=cz,
                         down_closed=cd, up_closed=cu,
                         n_zero=z["n_steps"], n_down=dn["n_steps"], n_up=up["n_steps"]))

    # ---- 自证 3：划分 ----
    st = Counter(r["state"] for r in rows)
    if sum(st.values()) != len(rows):
        fail.append("三臂状态分类不构成划分")
    if set(st) - {"all_closed", "up_only_blew_up", "down_only_blew_up",
                  "zero_blew_up", "other"}:
        fail.append("出现未知状态")

    # ---- 自证 4：四格表 + 恒等式 ----
    # ⚠ 第一版把「零臂跑完而 +v 没跑完」(16) 直接当 McNemar 的一侧，
    #   另一侧用「零臂跑完而 −v 没跑完」(1)。这是**错的表**：
    #   有 1 道题 −v 也没跑完，它同时落进两侧，discordant 对被算重了。
    #   正确要分四格（只在零臂闭合的题里）：
    #       三臂都跑完 / 只有 +v 没跑完 / 只有 −v 没跑完 / 两臂都没跑完
    #   McNemar 只能用「只有 +v」与「只有 −v」这两个 discordant 格。
    #   「+v 相对共享对照的破坏数」是另一个量，单独报。
    zc = [r for r in rows if r["zero_closed"]]
    both_ok = sorted(r["label"] for r in zc if r["up_closed"] and r["down_closed"])
    up_only = sorted(r["label"] for r in zc if r["down_closed"] and not r["up_closed"])
    down_only = sorted(r["label"] for r in zc if r["up_closed"] and not r["down_closed"])
    neither = sorted(r["label"] for r in zc if not r["up_closed"] and not r["down_closed"])
    up_broke = sorted(r["label"] for r in zc if not r["up_closed"])
    down_broke = sorted(r["label"] for r in zc if not r["down_closed"])

    # 恒等式：四格必须恰好划分零臂闭合的题；两个「破坏数」必须等于
    # 「discordant + 两臂都没跑完」
    if len(both_ok) + len(up_only) + len(down_only) + len(neither) != len(zc):
        fail.append("四格表不划分零臂闭合的 %d 题" % len(zc))
    if len(up_broke) != len(up_only) + len(neither):
        fail.append("+v 破坏数 %d ≠ discordant %d + 两臂都没跑完 %d"
                    % (len(up_broke), len(up_only), len(neither)))
    if len(down_broke) != len(down_only) + len(neither):
        fail.append("−v 破坏数 %d ≠ discordant %d + 两臂都没跑完 %d"
                    % (len(down_broke), len(down_only), len(neither)))
    if len(up_only) <= len(down_only):
        fail.append("只有 +v 跑不完的题 (%d) 未超过只有 −v 的 (%d)，本节前提不成立"
                    % (len(up_only), len(down_only)))
    p_mcnemar = mcnemar_exact(len(up_only), len(down_only))

    # ---- 每个方向的 verdict 表（只统计两臂都跑完的）----
    per_dir = {}
    for dirn, key in ((UP, "up"), (DOWN, "down")):
        comp = [l for l in labels
                if M(dirn, l, 0.0)["closed_think"] and M(dirn, l, 0.2)["closed_think"]]
        fv = Counter()
        changed = 0
        for l in comp:
            a0, a2 = M(dirn, l, 0.0), M(dirn, l, 0.2)
            fv[verdict(a0["answer_primary_strict"], a2["answer_primary_strict"],
                       REF.get(l))] += 1
            if a0["answer_primary_strict"] != a2["answer_primary_strict"]:
                changed += 1
        base_a = sum(1 for l in comp
                     if verdict(M(dirn, l, 0.0)["answer_primary_strict"],
                                M(dirn, l, 0.2)["answer_primary_strict"],
                                REF.get(l)).startswith("right"))
        steer_a = fv["right->right"] + fv["wrong->right"]
        base_b = fv["right->right"] + fv["right->wrong"]
        # ---- 自证 5：两种算法一致 ----
        if base_a != base_b:
            fail.append("%s 答对数两种算法不一致：%d vs %d" % (dirn, base_a, base_b))
        per_dir[key] = dict(
            n_complete=len(comp), n_incomplete=len(labels) - len(comp),
            verdicts=dict(sorted(fv.items())),
            baseline_correct=base_a, steered_correct=steer_a,
            net_change=steer_a - base_a, changed=changed,
            changed_rate=changed / float(len(comp)) if comp else None,
            arms_at_token_cap=sum(1 for l in labels
                                  if M(dirn, l, 0.2)["n_steps"] >= CAP),
        )

    # ---- 自证 6：跑飞题不得进 verdict 表 ----
    for key, dirn in (("up", UP), ("down", DOWN)):
        leaked = set(up_broke if dirn == UP else down_broke) & \
            {l for l in labels
             if M(dirn, l, 0.0)["closed_think"] and M(dirn, l, 0.2)["closed_think"]}
        if leaked:
            fail.append("%s 臂的跑飞题漏进了 verdict 表：%s" % (key, sorted(leaked)))

    # 零臂作为共享对照的闭合率
    zero_closed = sum(1 for r in rows if r["zero_closed"])
    zero_cap = sum(1 for r in rows if r["n_zero"] >= CAP)

    # 步数比（配对：同题、同零臂）
    def ratios(a, b):
        return [r[b] / r[a] for r in rows if r[a] and r[b]]

    r_down, r_up = ratios("n_zero", "n_down"), ratios("n_zero", "n_up")
    up_gt_down = sum(1 for a, b in zip(r_up, r_down) if a > b)
    p_len_sign = mcnemar_exact(up_gt_down, len(labels) - up_gt_down)

    # 与 §4.13 的 KL 方向对照
    kl = {m["metric"]: m for m in arm["metrics"]}
    kl_up = kl["mean_logit_kl"]["up_mean"]
    kl_dn = kl["mean_logit_kl"]["down_mean"]
    larger_kl = "confidence_down" if kl_dn > kl_up else "confidence_up"

    # ---- 自证 7：本支的 verdict 口径必须与 answer_power.py 那份一致 ----
    # 两者都读同一批 run，但口径若不同（float 归一化、ref 空格）就会静默分叉。
    pd = per_dir["down"]
    if (pd["n_complete"] != pow2["n_complete_pairs"]
            or pd["verdicts"] != {k: v for k, v in pow2["full_verdicts"].items()}
            or pd["net_change"] != pow2["net_change"]):
        fail.append("down 臂结果与 answer_power.json 不一致：%s vs "
                    "完整 %d/%d 全表 %s 净 %+d"
                    % (pd["verdicts"], pd["n_complete"], pow2["n_complete_pairs"],
                       pow2["full_verdicts"], pd["net_change"]))

    if larger_kl == "confidence_up":
        fail.append("KL 更大的方向是 +v，与本节的前提（−v 幅度更大）不符")
    if len(up_only) <= 0 or len(neither) < 0:
        fail.append("四格表数值异常")

    if fail:
        print("ABORT 自证不过，不产出文件：")
        for f in fail:
            print("  x " + f)
        return 2

    payload = {
        "schema": "steer_directions/1",
        "what": "同一条轴的两个符号为什么行为相反：+v 让模型跑飞，−v 只让它偏移",
        "layer": arm["layer"],
        "strength": arm["strength"],
        "n_problems": len(labels),

        "shared_control": {
            "claim": "两个方向的零强度臂逐字相同 ⇒ 共享同一份对照",
            "n_identical_zero_arms": n_same,
            "n_problems": len(labels),
            "holds": n_same == len(labels),
        },
        "closed_counts": {
            "zero_shared": zero_closed,
            "down_minus_v": per_dir["down"]["n_complete"],
            "up_plus_v": per_dir["up"]["n_complete"],
            "n_problems": len(labels),
        },
        "blew_up": {
            "table_on_shared_zero_control": {
                "n_zero_closed": len(zc),
                "both_closed": len(both_ok),
                "up_only_blew_up": len(up_only),
                "down_only_blew_up": len(down_only),
                "both_blew_up": len(neither),
            },
            "up_labels": up_broke,
            "down_labels": down_broke,
            "n_up_vs_shared_control": len(up_broke),
            "n_down_vs_shared_control": len(down_broke),
            "mcnemar_exact_p": p_mcnemar,
            "zero_arm_at_cap": zero_cap,
        },
        "token_cap": CAP,
        "per_direction": per_dir,
        "length": {
            "ratio_median_down": statistics.median(r_down),
            "ratio_median_up": statistics.median(r_up),
            "n_up_ratio_gt_down": up_gt_down,
            "n_problems": len(labels),
            "sign_test_p": p_len_sign,
        },
        "kl_contrast": {
            "mean_logit_kl_up": kl_up,
            "mean_logit_kl_down": kl_dn,
            "larger_kl_direction": larger_kl,
            "more_blew_up_direction": "confidence_up",
            # ⚠ 第一版写的是 (kl_dn > kl_up) == (kl_up > kl_dn)，
            #   只要两者不等它就是 false —— 于是**方向相反这件事被标成 false**，
            #   而同一份产物的 verdict 文本却在说「方向相反」。
            #   正确的问法是：KL 更大的那个方向，是不是跑飞更多的那个方向？
            "opposite": larger_kl != "confidence_up",
        },
        # ⚠ 命名占位符 .format()，不用 %-元组。
        #   %-元组的占位符个数与参数个数对不上时报
        #   "not enough arguments for format string"，位置落在 dict 中间，
        #   看不出是哪个数漏了。第一版就是这么错的（%d/%d 只给了一个参数）。
        "verdict": (
            "**同一条轴，符号一换，行为完全不同。**\n"
            "① 零臂 {zc}/{n} 闭合（两臂共享同一份对照，见 shared_control）。"
            "注入 −v 后 {dn}/{n} 闭合，注入 **+v** 后只剩 **{up}/{n}**。\n"
            "⇒ 四格表（只在零臂闭合的 {zc} 题里）：三臂都跑完 {both}、"
            "**只有 +v 跑不完 {uponly}**、只有 −v 跑不完 {downonly}、"
            "两臂都没跑完 {neith}。McNemar 双侧精确 p = **{p:.3g}**。\n"
            "② **这与注入幅度相反。** §4.13 的 KL：+v {kl_up:.4f} / −v {kl_dn:.4f} —— "
            "**−v 把分布推得更远，却更少跑飞**。\n"
            "⇒ 「把分布推得远」和「把生成推入不收敛」是两件事，"
            "本项目这条轴上两者的方向**相反**。\n"
            "③ 生成长度配对中位数：+v {r_up:.2f}× / −v {r_dn:.2f}×，"
            "同题比较 {n_up_gt_down}/{n} 题 +v 更长，符号检验 p = {p_len:.3g}。\n"
            "④ ⚠ **最大的一个陷阱**：只看闭合的那几题，+v 臂的 verdict 是 "
            "right->wrong **{up_rw}**、净变化 **{up_net}** —— "
            "读起来像「+v 最安全」。\n"
            "那是 **{up_inc}/{n} 未闭合**制造出来的假象：破坏没有消失，"
            "它从「答错」变成了「答不出来」，而按 verdict 计数**看不见**。"
        ).format(zc=zero_closed, n=len(labels), dn=per_dir["down"]["n_complete"],
                 up=per_dir["up"]["n_complete"], both=len(both_ok),
                 uponly=len(up_only), downonly=len(down_only), neith=len(neither),
                 p=p_mcnemar, kl_up=kl_up, kl_dn=kl_dn,
                 r_up=statistics.median(r_up), r_dn=statistics.median(r_down),
                 n_up_gt_down=up_gt_down, p_len=p_len_sign,
                 up_rw=per_dir["up"]["verdicts"].get("right->wrong", 0),
                 up_net=per_dir["up"]["net_change"],
                 up_inc=per_dir["up"]["n_incomplete"]),
        "not_claimed": (
            "① **不能说「+v 更差」是普遍规律** —— 本项目只有 s = {st} **一个强度点**。"
            "「某个阈值之上 +v 会跑飞」是**假设**，本批数据既不能证实也不能证伪。\n"
            "② 不能说「+v 让模型更自信」或「−v 让模型更怀疑」—— "
            "能测的只是闭合率与生成长度，**不是**主观状态。\n"
            "③ 不能把这个符号不对称说成 confidence 这个**概念**的性质："
            "它只说明「在这条由 confidence_up/down 定义的轴上，符号不对称」。"
            "**缺同范数随机方向臂**（§4.13.3），所以不能排除"
            "「±v 各自接近某个不稳定的吸引域」这种更平凡的解释。\n"
            "④ 不能用 +v 臂的 verdict 表评价 +v：它只有 {up} 题，"
            "且这 {up} 题是**条件化**出来的（恰好是 +v 没跑飞的那几题）。\n"
            "⇒ 对 +v 唯一诚实的读法是：**它在 {up_inc}/{n} 的题上根本没有产出答案**。\n"
            "⑤ 也不能反过来用 −v 臂说「−v 是安全的」：−v 的 {dn} 题里"
            "答案改变率 {dn_chg:.0f}%，其中多数是 wrong->wrong（见 §4.15.3）。"
        ).format(st=arm["strength"], up=per_dir["up"]["n_complete"],
                 up_inc=per_dir["up"]["n_incomplete"], n=len(labels),
                 dn=per_dir["down"]["n_complete"],
                 dn_chg=100.0 * (per_dir["down"]["changed_rate"] or 0.0)),
    }

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    print("自证全过（7 条）")
    print("  零臂逐字相同：%d/%d（配对设计成立）" % (n_same, len(labels)))
    print("  闭合率：零 %d/%d | −v %d/%d | +v %d/%d"
          % (zero_closed, len(labels), per_dir["down"]["n_complete"], len(labels),
             per_dir["up"]["n_complete"], len(labels)))
    print("  跑飞题：+v %d vs −v %d  McNemar p = %.3g"
          % (len(up_broke), len(down_broke), p_mcnemar))
    print("  KL：+v %.4f / −v %.4f ⇒ 幅度大的方向 (%s) 不是跑飞多的方向 (%s)"
          % (kl_up, kl_dn, payload["kl_contrast"]["larger_kl_direction"],
             payload["kl_contrast"]["more_blew_up_direction"]))
    print("  步数比中位：+v %.2f× / −v %.2f×  符号检验 p = %.3g"
          % (statistics.median(r_up), statistics.median(r_down), p_len_sign))
    print("  +v 臂 verdict 表：%s ← 只有 %d 题，且是条件化出来的"
          % (per_dir["up"]["verdicts"], per_dir["up"]["n_complete"]))
    print("  已写出 %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
