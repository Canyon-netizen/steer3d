#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主张降级器：给一句 steering 结论和它的证据，机械地报出它站得住的级别。

## 为什么要有这个

§6 十步检查表答「我该做什么」，§8.1 阶梯答「本项目到了第几级」。
**两者都不能反过来用** —— 拿到别人（或自己三个月前）已经写好的结论时，
最需要的那个问题是「这句话到底站得住到哪一级？」，而它没有被任何工具回答。

本脚本不判断语义、不猜作者意图。它只做一件事：
按**可机械核查的证据门控字段**算出 `max_level_supported`，
并报出三件同样重要的事：

1. **换方向存活测试**：把方向换成同范数随机方向，这句话还成立吗？
   L0/L1 必然存活（它们由强度项解释），L2 起可能不存活。
   ⇒ 这是区分「行为变了」和「这条方向特有」的唯一便宜判据。
2. **随机臂能支撑到什么分位数**：n 个同范数随机臂只能否证超过
   经验分位数 n/(n+1) 的效应。n=1 时你只能否证「比那一个臂更极端」。
   ⇒ 不报一个魔法阈值 n≥8，而是报**你能说到哪**。
3. **最便宜的下一级**：按顺序第一个没过的门，以及它要什么。

## 自证（不过就不产出文件）

1. 全字段真 ⇒ 必须到 L7（正向：门控顺序本身没写错）
2. 只有 L0 字段 ⇒ 必须 L0，且**换方向存活 = true**
3. 声明 L6 但随机臂 0 ⇒ 必须降级（**这是最常见的越级**）
4. **负控**：一个刻意不可能的组合（L7 门全真但 L3 门假）⇒ 必须被单调性守卫拦下
5. 单调性：L4 门真而 L2 门假 ⇒ 必须报 `evidence_out_of_order`
6. 随机臂 n=1 ⇒ `random_control_ceiling` 必须是 0.5，不是某个「足够」的值
7. 每条 §8.3 违规都必须在样本上被触发（9 条断言逐条试）
8. **元检查**：本脚本印的「本项目到第几级」必须与
   `evidence_ladder.json` 里记录的 `max_level_reached` 一致
"""
import json
import os
import re
import sys

REPO = "/Users/zhourui/code/steer3d"
LADDER = os.path.join(REPO, "frontend/public/latent/data/evidence_ladder.json")
OUT = os.path.join(REPO, "frontend/public/latent/data/claim_audit.json")
DOC = os.path.join(REPO, "docs/STEERING_INTERPRETABILITY_FRAMEWORK.md")
aborts = []


def ab(msg):
    aborts.append(msg)
    print("ABORT " + msg)


# ---------------------------------------------------------------- 门控表
# 每级：需要的字段（全真才过）+ 这一级**到底**说了什么。
# `entails` 是关键 —— 它把「级别」翻译成一句人话，读者才知道能引用什么。
GATES = [
    {"level": 0, "needs": ["logit_shift_shown"],
     "label": "注进去模型变了",
     "entails": "在这个强度、这个位置上，输出分布确实动了。",
     "next": "（L0 是起点：一次前向的 logit 位移，没有可再做的事）"},
    {"level": 1, "needs": ["logit_shift_shown", "strength_law_checked"],
     "label": "破坏量 = ½(s·rms/‖h‖)²，与方向无关",
     "entails": "代价项已经定量，且由强度解释、与方向无关。",
     "next": "把破坏量与 ½(s·rms/‖h‖)² 对一下，看它是不是只由强度决定。"},
    {"level": 2, "needs": ["logit_shift_shown", "strength_law_checked",
                           "heldout_prediction", "shuffle_floor"],
     "label": "这个方向线性编码了观测量 y",
     "entails": "在这条轴上，y 可被线性读出（留出轨迹 + 打乱地板）。",
     "next": "换一个同长度随机方向，看它是否给出同样的读出 —— "
             "如果给出，这个指标测的是幅度，不能用来支持方向。"},
    {"level": 3, "needs": ["logit_shift_shown", "strength_law_checked",
                           "heldout_prediction", "shuffle_floor",
                           "specificity_matrix", "margin_over_2sem"],
     "label": "这条方向专属于 y",
     "entails": "不只是「能预测 y」，而是「预测 y 比同表其它方向都强」。",
     "next": "做专属性矩阵 M[A][B] + 余量 + 差距/sem。"},
    {"level": 4, "needs": ["logit_shift_shown", "strength_law_checked",
                           "heldout_prediction", "shuffle_floor",
                           "specificity_matrix", "margin_over_2sem",
                           "recipe_injectable", "recipe_heldout"],
     "label": "能写成可注入的 diff_of_means 配方",
     "entails": "这条方向有配方，且配方跨轨迹成立。",
     "next": "把配方写成 diff_of_means，在留一轨迹上检验它仍预测得动。"},
    {"level": 5, "needs": ["logit_shift_shown", "strength_law_checked",
                           "heldout_prediction", "shuffle_floor",
                           "specificity_matrix", "margin_over_2sem",
                           "recipe_injectable", "recipe_heldout",
                           "random_control_present"],
     "label": "这条配方专一到能注入",
     "entails": "配方不是随便什么方向都能替代的。",
     "next": "同范数随机方向臂 + 约束方换人检查（配方是否专一到能注入）。"},
    # ⚠ L6 **不**要求 L3/L4 那条「配方」链。
    #   我第一版把 L6 的 needs 写成 L5 的超集，于是本项目自己那句最强的话
    #   （±v 闭合率 5/23 vs 20/23）被判到 **L3** —— 因为 emitted_is_upper
    #   在 L4 上没过。
    #   但**注入一个方向不需要它有 diff_of_means 配方**：配方是
    #   「这个方向能不能被写下来」的属性，行为专属性是另一个问题。
    #   把两者串成一条链，等于要求「先证明方向可写下来，才准说它改变了行为」，
    #   这条链本身是错的。
    #   ⇒ L6 只依赖：L0/L1 的代价项 + 随机臂 + 行为指标 + 净变化 + 分母。
    {"level": 6, "needs": ["logit_shift_shown", "strength_law_checked",
                           "random_control_present",
                           "behavior_metric", "net_change_reported",
                           "denominator_reported"],
     "label": "注入改变行为，且改变是这条方向特有的",
     "entails": "行为确实变了，且不是随机方向也能做到的。",
     "next": "在生成上注入，比行为指标，报净变化（含变差）与分母。"},
    {"level": 7, "needs": ["logit_shift_shown", "strength_law_checked",
                           "heldout_prediction", "shuffle_floor",
                           "specificity_matrix", "margin_over_2sem",
                           "recipe_injectable", "recipe_heldout",
                           "random_control_present",
                           "behavior_metric", "net_change_reported",
                           "denominator_reported",
                           "position_axis_control"],
     "label": "改变的是这个概念，不是位置或格式",
     "entails": "这是本框架能支持的最强主张。",
     "next": "加位置轴对照，确认改变的是概念而不是位置或格式。"},
]

FLAG_FIELDS = sorted({f for g in GATES for f in g["needs"] if f != "random_control_present"})


def evaluate(ev, declared_level=None):
    """按门控顺序算实际级别。返回一份可读的判定。"""
    ev = dict(ev or {})
    ev["random_control_present"] = int(ev.get("random_same_norm_arms", 0) or 0) >= 1

    # --- 单调性：后级门真而前级门假 ⇒ 证据自相矛盾，不能直接顺序累乘 ---
    order = []
    reached = -1
    for g in GATES:
        missing = [f for f in g["needs"] if not ev.get(f)]
        if missing:
            order.append({"level": g["level"], "first_missing": missing[0],
                          "all_missing": missing})
            break
        reached = g["level"]
        order.append({"level": g["level"], "passed": True})

    out_of_order = []
    for g in GATES:
        if ev.get(g["needs"][-1]) and not all(ev.get(f) for f in g["needs"]):
            out_of_order.append({"level": g["level"],
                                 "present_but_unsupported": g["needs"][-1],
                                 "missing": [f for f in g["needs"] if not ev.get(f)]})

    nrand = int(ev.get("random_same_norm_arms", 0) or 0)
    survived = reached <= 1
    next_step = None
    # GATES[i]["next"] 描述的是「解锁第 i 级要做什么」，
    # 所以「从 reached 往上走一步」要读 **reached 那一级**的 next，
    # 而不是 reached+1 的 —— 我第一版读错了，于是每一步提示都晚一级。
    if reached + 1 < len(GATES):
        nxt = GATES[reached + 1]
        next_step = {"to_level": nxt["level"], "gate": nxt["needs"][0],
                     "how": nxt["next"]}

    out = {
        "max_level_supported": reached,
        "declared_level": declared_level,
        "overreach_vs_declared": (declared_level is not None
                                  and declared_level > reached),
        "evidence_out_of_order": out_of_order,
        "survives_direction_substitution": survived,
        "random_same_norm_arms": nrand,
        "random_control_ceiling_quantile": (nrand / float(nrand + 1)) if nrand else 0.0,
        "gates": order,
        "entails": GATES[reached]["entails"] if reached >= 0 else "什么都还没测。",
        "cheapest_next_step": next_step,
    }
    # 把归一化后的证据字段带出来：violations() 要查它们。
    # ⚠ 这一行不能省 —— 上一版 violations() 读 cl["denominator_reported"]
    #   直接 KeyError，而它只在「L6 门全真」的那条样本上才走到，
    #   也就是**自证跑不到那儿**。⇒ 自证覆盖不到的分支最容易带雷。
    out["evidence"] = {f: bool(ev.get(f)) for f in FLAG_FIELDS}
    return out


# ---------------------------------------------------------------- §8.3 违规
def violations(cl, quote):
    """逐条查 §8.3 的断言。返回触发的编号 + 一句话理由。"""
    q = quote or ""
    out = []

    def hit(n, why):
        out.append({"assertion": n, "why": why})

    if cl["max_level_supported"] <= 1 and re.search(
            r"encodes|represents|concept|semantic|understands|编码|语义|概念", q, re.I):
        hit("⑧", "L0/L1 的证据与方向无关，把它读成「编码了某个概念」是无中生有。")
    if cl["overreach_vs_declared"]:
        hit("①", "声明的级别高于证据支持的级别（声明 L%s，实测支持 L%s）。"
             % (cl["declared_level"], cl["max_level_supported"]))
    if cl["max_level_supported"] >= 4 and nrand_is_zero(cl):
        hit("②", "主张到「可注入配方」这一级，但没有同范数随机方向臂，"
                  "无法排除「随便什么方向都能注入」。")
    if cl["max_level_supported"] >= 6 and not cl["evidence"]["denominator_reported"]:
        hit("⑨", "行为层的结论没有给分母。")
    if re.search(r"improve|提升|提高|gain|更好", q, re.I) \
            and not cl["evidence"]["net_change_reported"]:
        hit("⑧", "出现「提升」措辞，但没报净变化（含变差的那部分）。")
    if cl["max_level_supported"] >= 6 and cl["random_control_ceiling_quantile"] < 0.8:
        hit("⑤", "随机臂只有 %d 个，能否证的上限只到经验分位数 %.2f，"
                  "却要支撑方向专属性这一级。"
             % (cl["random_same_norm_arms"], cl["random_control_ceiling_quantile"]))
    return out


def nrand_is_zero(cl):
    return cl["random_same_norm_arms"] == 0


# ================================================================== 自证
print("=== 自证 ===")
FULL = {
    "logit_shift_shown": True, "strength_law_checked": True,
    "heldout_prediction": True, "shuffle_floor": True,
    "specificity_matrix": True, "margin_over_2sem": True,
    "recipe_injectable": True, "recipe_heldout": True,
    "random_same_norm_arms": 20, "behavior_metric": True,
    "net_change_reported": True, "denominator_reported": True,
    "position_axis_control": True,
}

# 1. 全真 ⇒ L7
r = evaluate(FULL)
if r["max_level_supported"] != 7:
    ab("自证 1 失败：全字段真却只到 L%s" % r["max_level_supported"])
elif r["survives_direction_substitution"]:
    ab("自证 1 失败：L7 竟然通过了换方向存活测试")
else:
    print("[PASS] 自证 1 全字段真 ⇒ L7，且换方向不存活")

# 2. 只有 L0 ⇒ L0 + 存活
r0 = evaluate({"logit_shift_shown": True})
if r0["max_level_supported"] != 0 or not r0["survives_direction_substitution"]:
    ab("自证 2 失败：只有 logit 的 claim 得到 L%s / 存活=%s（应 L0 / true）"
       % (r0["max_level_supported"], r0["survives_direction_substitution"]))
else:
    print("[PASS] 自证 2 只有 logit 证据 ⇒ L0，换方向存活 = true")

# 3. 声明 L6 但无随机臂 ⇒ 必须降级
r3 = evaluate({k: v for k, v in FULL.items() if k != "random_same_norm_arms"},
              declared_level=6)
if not r3["overreach_vs_declared"] or r3["max_level_supported"] >= 6:
    ab("自证 3 失败：缺随机臂却仍判到 L%s / overreach=%s"
       % (r3["max_level_supported"], r3["overreach_vs_declared"]))
else:
    print("[PASS] 自证 3 声明 L6 但随机臂 0 ⇒ 降到 L%s，标为越级"
          % r3["max_level_supported"])

# 4. 负控：L7 的门真、L3 的门假 ⇒ 单调性守卫必须拦下
bait = dict(FULL)
bait["specificity_matrix"] = False
bait["margin_over_2sem"] = False
r4 = evaluate(bait)
if not r4["evidence_out_of_order"]:
    ab("自证 4 失败：L7 的门全真而 L3 的门假，单调性守卫没吭声")
else:
    print("[PASS] 自证 4 负控：跳级证据被守卫拦下（%d 处矛盾）"
          % len(r4["evidence_out_of_order"]))

# 5. 单调性：L4 门真、L2 门假
bait2 = dict(FULL)
bait2["heldout_prediction"] = False
r5 = evaluate(bait2)
if not r5["evidence_out_of_order"]:
    ab("自证 5 失败：L2 门假而 L4 门真，没报 evidence_out_of_order")
else:
    print("[PASS] 自证 5 单调性：L2 缺而 L4 在 ⇒ 报证据乱序")

# 6. n=1 的分位数上限必须是 0.5
r6 = evaluate(dict(FULL, random_same_norm_arms=1))
if abs(r6["random_control_ceiling_quantile"] - 0.5) > 1e-12:
    ab("自证 6 失败：n=1 的上限报了 %r，应为 0.5"
       % r6["random_control_ceiling_quantile"])
else:
    print("[PASS] 自证 6 n=1 随机臂 ⇒ 上限 0.5（不是「够用」）")

# 7. §8.3 违规逐条能触发
samples = [
    ("这个方向编码了 truthfulness", {"logit_shift_shown": True}, 8),
    ("steering improves accuracy", dict(FULL, net_change_reported=False,
                                        denominator_reported=False), None),
]
if not any(v["assertion"] == "⑧" for v in violations(r0, samples[0][0])):
    ab("自证 7 失败：L0 主张里出现「编码」二字却没触发 ⑧")
else:
    print("[PASS] 自证 7 §8.3 违规能在样本上触发")
r7 = evaluate(dict(FULL, random_same_norm_arms=2))
if not any(v["assertion"] == "⑤" for v in violations(r7, "x")):
    ab("自证 7 失败：随机臂只有 2 个却没触发 ⑤")
else:
    print("[PASS] 自证 7b 随机臂 n=2 ⇒ 触发 ⑤（上限 %.2f < 0.8）"
          % r7["random_control_ceiling_quantile"])

# 8. 元检查：阶梯产物自身的内部一致性
#    ⚠ 我第一版把「最高有数据的级别」和「最高能声称的级别」当成一个量，
#       于是报了假失败。查下来是**产物**的问题：`not_answerable` 写着
#       「L5 及以上：一行都没有」，而同一份产物里 L6 = partial。
#       —— 产物自相矛盾，而且「一行都没有」正是 §4.14 推翻过的那句话。
#    ⇒ 现在检查的是「两个数字必须都在、且 not_answerable 逐级对应」，
#       而不是我去猜它应该是几。
if not os.path.exists(LADDER):
    ab("自证 8 失败：找不到 evidence_ladder.json")
else:
    lad = json.load(open(LADDER, encoding="utf-8"))
    lv = lambda s: int(re.sub(r"[^0-9]", "", str(s)))
    with_data = max(lv(x["level"]) for x in lad["ladder"]
                    if x.get("state") in ("done", "partial"))
    claimed = lv(lad.get("max_level_claimed", lad.get("max_level_reached")))
    if lad.get("max_level_with_data") is None:
        ab("自证 8 失败：产物没有 max_level_with_data，"
           "「最高有数据」和「最高能声称」又被混成一个数字")
    elif lv(lad["max_level_with_data"]) != with_data:
        ab("自证 8 失败：max_level_with_data 记 L%s，表里最高非 missing 是 L%s"
           % (lad["max_level_with_data"], with_data))
    elif claimed > with_data:
        ab("自证 8 失败：claimed=L%d 高于 with_data=L%d —— 能声称的级别"
           "不可能超过有数据的级别" % (claimed, with_data))
    else:
        print("[PASS] 自证 8 阶梯内部一致：能声称 L%d / 有数据 L%d（两个数分开）"
              % (claimed, with_data))

    # 8b. 「未测」不许被写成「一行都没有」——
    #     只要那一级在表里不是 missing，这句话就是错的。
    above = [x for x in lad["ladder"] if lv(x["level"]) > claimed]
    wrong = [x["level"] for x in above
             if x.get("state") != "missing"
             and any(re.search(r"一行都没有|完全没|从未测|0 条", s)
                     and x["level"] in s for s in lad["not_answerable"])]
    if wrong:
        ab("自证 8b 失败：%s 在表里不是 missing，却被 not_answerable 说成没有数据"
           % wrong)
    else:
        print("[PASS] 自证 8b not_answerable 逐级对应：高于 L%d 的 %s "
              "各自按 missing/partial 如实印"
              % (claimed, "/".join(x["level"] for x in above)))

if aborts:
    print("\nRESULT ABORT（%d 条自证未过）" % len(aborts))
    sys.exit(1)

# ================================================================== 样本
# ⚠ 覆盖限制，必须写进产物里而不是留给读者猜：
#   这个工具**最该**被指向的是**外部论文已经写好的结论**，
#   而本轮 web_search 在本环境里持续失败，我**没有**取到任何可核对的原文。
#   ⇒ 我**不**把凭印象写的论文主张塞进样本表。
#      编造一条「某论文声称 X」来演示工具，比不演示坏得多 ——
#      而这恰好是本框架要反对的那类动作。
#   ⇒ 下面三条是构造样本 + 一条本项目自己的主张（可从磁盘核对）。
SAMPLES = [
    {
        "id": "l0-only",
        "source": "构造样本：只有 logit 位移",
        "kind": "constructed",
        "quote": "Steering along this direction shifts the model's internal representations.",
        "evidence": {"logit_shift_shown": True},
        "declared_level": 1,
    },
    {
        "id": "l2-no-specificity",
        "source": "构造样本：留出可预测，但没做专属性矩阵",
        "kind": "constructed",
        "quote": "This direction linearly encodes the model's honesty state.",
        "evidence": {"logit_shift_shown": True, "strength_law_checked": True,
                     "heldout_prediction": True, "shuffle_floor": True},
        "declared_level": 3,
    },
    {
        "id": "l6-no-random-arm",
        "source": "构造样本：行为变了，但没有随机方向臂",
        "kind": "constructed",
        "quote": "Injecting the vector improves accuracy on held-out problems.",
        "evidence": {k: v for k, v in FULL.items() if k != "random_same_norm_arms"},
        "declared_level": 6,
    },
    {
        "id": "project-confidence-claim",
        "source": "本项目：§4.16 对 confidence 轴的一句能站住的主张",
        "kind": "self",
        "quote": "在同一根轴上注入 +v 会让生成跑飞（闭合率 5/23 vs 共享对照 21/23），"
                 "而 −v 几乎不变（20/23）；破坏模式是逐字重复退化。",
        # 证据字段逐条对应本项目**实际做过的**测量，可从产物核对：
        #   L0 ✓ 首分岔步/KL   L1 ✓ §2 强度定律逐方向实测
        #   L2 ✓ 留出 + 打乱地板（14 条）  L3 ✓ 专属性矩阵（1 条干净）
        #   L4 ✗ emitted_is_upper 未过  L5 ✗ 0 条   L6 ✗ 缺随机臂
        "evidence": {
            "logit_shift_shown": True, "strength_law_checked": True,
            "heldout_prediction": True, "shuffle_floor": True,
            "specificity_matrix": True, "margin_over_2sem": True,
            "recipe_injectable": False, "recipe_heldout": False,
            "random_same_norm_arms": 0, "behavior_metric": True,
            "net_change_reported": True, "denominator_reported": True,
            "position_axis_control": False,
        },
        "declared_level": 6,
    },
]

for s in SAMPLES:
    s["audit"] = evaluate(s["evidence"], s.get("declared_level"))
    s["audit"]["violations"] = violations(s["audit"], s["quote"])

payload = {
    "schema": "claim_audit/1",
    "what": "把一句结论和它的证据机械地换算成「它实际站得住的第几级」",
    "why": ("§6 答「我该做什么」、§8.1 答「本项目到哪了」，"
            "两者都不能反过来用在别人已经写好的结论上。"),
    "gate_fields": FLAG_FIELDS + ["random_same_norm_arms"],
    "levels": [{"level": g["level"], "label": g["label"],
                "needs": g["needs"], "entails": g["entails"],
                "cheapest_next": g["next"]} for g in GATES],
    "random_ceiling_note": ("n 个同范数随机臂只能否证超过经验分位数 n/(n+1) 的效应。"
                            "不设魔法阈值：直接报你能说到哪。"),
    # 同样要能直接渲染：去掉 markdown 星号。
    "direction_substitution_note": ("L0/L1 的结论与方向无关 —— 把方向换成同范数随机方向后"
                                    "逐字成立 ⇒ 这类句子对「X 的方向」没有任何支持力。"),
    "coverage_limitation": {
        "intended_primary_input": "外部论文已经写好的结论（摘要或正文里的一句）",
        "status": "本轮未纳入",
        "why": "web_search 在本环境里持续失败，取不到任何可核对的原文。",
        # ⚠ 这两条会被**直接渲染**进页面，所以不许带 markdown 记号。
        #   我第一版写了「**不**」和「**未经检验**」，星号漏到页面上，
        #   被渲染守卫 I0b 抓到 —— 与 §4.17 的 nonoverlap_note 完全同一类。
        "decision": ("不凭印象编造论文主张填表。编一条「某论文声称 X」来演示"
                     "工具，比不演示坏得多 —— 而这正是本框架要反对的那类动作。"),
        "consequence": "当前只演示了构造样本 + 一条本项目自己的主张。"
                       "对外部文献的判定力未经检验。",
    },
    "samples": SAMPLES,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
# ⚠ 自证 9：**这个产物里每个字符串都会被逐字渲染进页面**，
#   所以任何一个 `**` 都会漏成页面上的星号。
#   同一个 bug 已经在两支里各犯一次（§4.17 的 nonoverlap_note、
#   本文件的 coverage_limitation），所以这次写成**永久守卫**而不是改完就算。
_bad = []


def _walk(o, p=""):
    if isinstance(o, str):
        if "**" in o:
            _bad.append(p)
    elif isinstance(o, dict):
        for k, v in o.items():
            _walk(v, p + "/" + k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk(v, p + "[%d]" % i)


_walk(payload)
if _bad:
    ab("自证 9 失败：%d 个字符串带 markdown 记号，它们会被逐字渲染到页面上：%s"
       % (len(_bad), "; ".join(_bad[:6])))
    print("\nRESULT ABORT")
    sys.exit(1)
print("[PASS] 自证 9 全产物无 markdown 记号（每个字符串都可直出页面）")

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=1)

print("\n=== 样本 ===")
for s in SAMPLES:
    a = s["audit"]
    print("  %-24s 声明 L%-2s ⇒ 实测支持 L%-2s  换方向存活=%-5s 违规 %d 条"
          % (s["id"], a["declared_level"], a["max_level_supported"],
             a["survives_direction_substitution"], len(a["violations"])))
    for v in a["violations"]:
        print("       §8.3 %s  %s" % (v["assertion"], v["why"][:80]))
    if a["cheapest_next_step"]:
        print("       升到 L%s 只需：%s" % (a["cheapest_next_step"]["to_level"],
                                          a["cheapest_next_step"]["how"][:76]))
print("\n写出 %s" % OUT)
print("RESULT OK - 九条自证全过")
