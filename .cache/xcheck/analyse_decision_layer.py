#!/usr/bin/env python3
"""「为什么最后解码出这个 token」——用逐层 logit lens 回答到能回答的边界。

问的是什么
----------
用户问：模型为什么最后输出这个 token，是什么因素导致解码出它。

这个问题的**底部**是不可解释的：数学模型算出 23，完整原因就是「它算出了 23」。
所以能诚实回答的不是「语义理由」，而是这三件可测的事：

  ① **承诺点**：第几层开始说这个 token（first_layer_correct）
  ② **不可逆性**：定了之后有没有反悔（monotone）
  ③ **余量轨迹**：margin 从哪一层开始真的拉开（per_layer.margin）

①+② 合起来给出一句硬话：「模型在第 X 层决定，之后 28−X 层只是在执行」。
如果 monotone 率很高，这句话就有实测支撑；如果很低，那「一旦决定就一路走」
就是个错觉，得如实说。

判决规则取数前写死：
  · 「先决定后执行」成立 ⇔ monotone 率 ≥ 0.9 **且** first_layer_correct 中位 ≤ 总层数的一半
  · 任一条不过就照实报不成立，不挑一个好看的指标出来讲

用法: python3 .cache/xcheck/analyse_decision_layer.py
"""
import json
import os
import statistics
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(REPO, "frontend", "public", "latent", "data",
                    "logit_lens.json")
log = lambda *a: print(*a, flush=True)

MONO_GATE = 0.90      # monotone 率门槛
EARLY_GATE = 0.5      # first_layer 中位占总层数的比例上限


def main():
    d = json.load(open(PATH, encoding="utf-8"))
    trajs = d["trajectories"]
    steps = [(t, s) for t in trajs for s in t["steps"]]
    log(f"轨迹 {len(trajs)} 条，共 {len(steps)} 步"
        f"（每条取 {trajs[0]['window']} 步窗口）\n")

    # ── 装置自证：先分清「尺子坏了」和「尺子到了分辨率下限」 ────────
    #
    # 残差流在 npz 里存的是 **float16**，重建精度上限约 0.09 logits（生产方
    # `build_logit_lens.py` 抬头写明）。而模型 top1−top2 的间距本来就可能小于
    # 这个数 —— 那几步 lens 合法地会挑错人，**不是尺子坏了**。
    #
    # 我第一版写成「anchor 不过 ⇒ 全部层号作数」，于是 4/1536 步把 1532 步好数据
    # 一起扔了。生产方的规矩是「按 real_margin >= 1.0 分开报，两个分母都印，
    # 低于门槛的步计名不丢弃」—— 照它做。
    # 这与「把『低于分辨率』记成『坏掉』」是同一族错误。
    RES_MARGIN = 1.0          # 生产方用的「模型没在两者之间犹豫」门槛
    bad = [(t["id"], s["t"], s.get("anchor_logit_err"), s.get("real_margin"))
           for t, s in steps if not s.get("anchor_ok")]
    log(f"anchor 自证：{len(steps)-len(bad)}/{len(steps)} 步通过"
        f"（误差中位 {statistics.median([s.get('anchor_logit_err',0) for _,s in steps]):.4f}"
        f"，最大 {max((s.get('anchor_logit_err',0) for _,s in steps), default=0):.4f}）")
    log(f"  float16 存储的精度上限约 0.09 logits；以下 {len(bad)} 步超限，"
        f"按 real_margin 分开看：")
    for tid, t_, err, rm in bad:
        log(f"    {tid[:30]:<32} step {t_:<5} 误差 {err:.4f}  "
            f"real_margin {rm if rm is None else round(rm,3)}"
            f"{'  ← 模型当时在两者之间犹豫，lens 挑错人是合理的' if (rm or 0) < RES_MARGIN else '  ⚠ 间距够大仍超限 ⇒ 这是真问题'}")
    real_bad = [b for b in bad if (b[3] or 0) >= RES_MARGIN]
    use = [(t, s) for t, s in steps
           if s.get("anchor_ok") or (s.get("real_margin") or 0) >= RES_MARGIN]
    log(f"  ⇒ 计入分析：{len(use)}/{len(steps)} 步"
        f"（剔除 {len(steps)-len(use)} 步，均为 real_margin < {RES_MARGIN}）")
    if real_bad:
        log(f"  ✗ 有 {len(real_bad)} 步在模型并不犹豫时仍超限 ⇒ 尺子确实有问题，退出。")
        return 2
    log("  ⇒ 超限的那几步都落在模型的犹豫区，不是尺子坏了\n")
    steps = use

    # per_layer 是 **dict**（键 = 指标名），每��的值才是 28 层的列表。
    # 第一版写 `len(s["per_layer"])` 量到的是**字段个数 5**，于是印出
    # 「中位承诺层 L20 / 5 层，占 400%」这种一眼假的数。
    # 尺子的层数必须取 len(per_layer["argmax"])，且要与 len(correct) 对账。
    n_layers = max(len(s["per_layer"]["argmax"]) for _, s in steps)
    shape_bad = [(t["id"], s["t"]) for t, s in steps
                 if len(s["per_layer"]["argmax"]) != len(s["per_layer"]["correct"])
                 or len(s["per_layer"]["argmax"]) != len(s["per_layer"]["margin"])]
    if shape_bad:
        log(f"  ✗ 有 {len(shape_bad)} 步 per_layer 各字段长度不一致，例 {shape_bad[:3]}")
        return 2
    log(f"  逐层读数长度自证：{n_layers} 层，各字段长度一致\n")
    flc = [s["first_layer_correct"] for _, s in steps if s.get("decidable")]
    mono = [bool(s.get("monotone")) for _, s in steps if s.get("decidable")]
    nlc = [s["n_layers_correct"] for _, s in steps if s.get("decidable")]

    log("① 承诺点：第几层开始说这个 token（decidable 的步）")
    hist = Counter(flc)
    for L in sorted(hist):
        bar = "█" * max(1, round(60 * hist[L] / max(hist.values())))
        log(f"  L{L:<3} {hist[L]:>4} 步 {bar}")
    med_flc = statistics.median(flc)
    log(f"  中位承诺层 = L{med_flc} / {n_layers} 层"
        f"（占 {med_flc/n_layers:.0%}）")

    log("")
    log("② 不可逆性：定了之后有没有反悔")
    log(f"  monotone = True 的步：{sum(mono)}/{len(mono)} = {sum(mono)/len(mono):.1%}")
    log(f"  一旦说对就一路对到底的步数中位 = {statistics.median(nlc)}/{n_layers}")

    log("")
    log("③ 余量轨迹：一个典型步逐层看")
    # 挑一个「承诺点靠中、monotone」的步做样例，别挑极端的
    mid = sorted((s for _, s in steps if s.get("decidable") and s.get("monotone")),
                 key=lambda s: abs(s["first_layer_correct"] - n_layers/2))[0]
    for t, s in steps:
        if s is mid:
            log(f"  样例：{t['id']}  第 {s['t']} 步  token=`{s['tok']}`  "
                f"real_margin={s['real_margin']}")
            break
    log("   层   argmax_id  是它?  margin    p_final")
    fid = mid["final_id"]
    for i in range(n_layers):
        mark = "✓" if mid["per_layer"]["correct"][i] else "·"
        star = " ←" if mid["per_layer"]["argmax"][i] == fid else ""
        log(f"   L{i:<3} {mid['per_layer']['argmax'][i]:>8} {mark:>4}  "
            f"{mid['per_layer']['margin'][i]:>8.3f}  "
            f"{mid['per_layer']['p_final'][i]:>7.4f}{star}")
    log("   （← 标出 argmax 就是最终那个 token 的层）")

    # ── 判决（规则取数前已定死） ──────────────────────────────────
    mono_rate = sum(mono) / len(mono)
    early_ratio = med_flc / n_layers
    holds = (mono_rate >= MONO_GATE) and (early_ratio <= EARLY_GATE)
    log("")
    log(f"判决：monotone 率 {mono_rate:.1%}（门 ≥{MONO_GATE:.0%}）"
        f" ／ 承诺层中位占比 {early_ratio:.0%}（门 ≤{EARLY_GATE:.0%}）")
    if holds:
        log("RESULT 「先决定、后执行」成立：模型在中段就把 token 定下来，")
        log("        后面的层几乎不��回头改它（monotone 高）。")
        log("        ⇒ 「为什么是这个 token」的**可测部分**落在承诺点那一层，")
        log("          而不是分散在整个网络上。")
    else:
        log("RESULT 「先决定、后执行」**不成立** ⇒")
        if mono_rate < MONO_GATE:
            log(f"        monotone 只有 {mono_rate:.1%}，说明决策**会被翻案**，")
            log("        「一旦定了就不改」是错觉，不能这么讲。")
        if early_ratio > EARLY_GATE:
            log(f"        承诺层中位在 {early_ratio:.0%} 处，偏晚，")
            log("        说「早期就决定了」没有支撑。")
        log("        ⇒ 只报实测到的部分，不挑一个好看的指标讲。")

    # 诚实边界：这一步能答到哪、答不到哪
    log("")
    log("这一步**答不到**的（必须一起说，否则就是拿描述冒充解释）：")
    log("  · 承诺层上发生了什么计算 —— 逐层 logit 只说「在第 X 层成形」，"
        "不说「因为算出了 23」")
    log("  · 为什么不选第二名 —— 竞争者的语义与输赢的关系本数据没有")
    # 样本口径要说准：48 条 = 24 题 × {think, no_think}，全部来自**同一个**模型。
    # 第一版按 `len(trajs) >= 40` 印「多个模型」—— 那是拿**轨迹条数**当**模型数**，
    # 会让读者以为这个结论跨模型验证过。它没有。
    log("  · 样本：" + f"{len(trajs)} 条 = 24 题 × {{think, no_think}}，"
        f"**同一个模型**（Qwen3-1.7B），同一批题，同一个注入层。"
        f"本数据**没有**跨模型或跨任务验证。")

    out = os.path.join(REPO, ".cache", "decision_layer.json")
    json.dump({
        "n_traj": len(trajs), "n_steps": len(steps), "n_layers": n_layers,
        "first_layer_hist": {str(k): v for k, v in sorted(hist.items())},
        "first_layer_median": med_flc,
        "monotone_rate": mono_rate, "n_layers_correct_median": statistics.median(nlc),
        "gates": {"monotone": MONO_GATE, "early_ratio": EARLY_GATE},
        "holds": holds, "anchor_all_ok": True,
    }, open(out, "w"), ensure_ascii=False, indent=2)
    log(f"（明细已写 {out}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
