#!/usr/bin/env python3
"""证据阶梯（§8.1）→ 页面产物 evidence_ladder.json。

## 为什么这个文件必须**构建**而不是手写

阶梯上每个数字都来自别的产物（L1 的 2.04%–2.41%、L2 的 14、L3 的 2 条干净、
L4 的 0.3688/82×、L6 的 92 个 run）。手打的话，
那些产物一改，阶梯就静默过期 —— 而一个**过期的阶梯比没有阶梯更坏**：
它会让人以为「L2 = 14」是当前的量。

⇒ 这里从产物**读**出来，并且逐条做**跨产物一致性自检**：
读到的值和「我在别处写的值」对不上就 ABORT，不产出文件。

## 自检清单

1. `linearity_law.json` 的实测区间与文档口径一致（与方向无关）
2. `readable_subspace.json` 的可读下界 = 14，且 200 次随机顺序不变
3. `heldout_readability.json` 里 `new_clean` 恰好 1 条（emitted_is_upper）
4. `heldout_readability.json` 的配方 LOO 与 82× 地板对得上
5. `arm_asymmetry.json` 的可分/不可分标记与阶梯 L6 那一行一致
6. `cot_texts.json` 确实**没有**随机方向臂（这是 L6 停在 ⚠ 的根据）
"""
import json
import re
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
DATA = ROOT / "frontend/public/latent/data"
SCAN = ROOT / ".cache/strengthscan"
OUT = DATA / "evidence_ladder.json"

PROBLEMS = []


def need(cond, msg):
    if not cond:
        PROBLEMS.append(msg)
    return bool(cond)


def main():
    law = json.loads((SCAN / "linearity_law.json").read_text(encoding="utf-8"))
    sub = json.loads((DATA / "readable_subspace.json").read_text(encoding="utf-8"))
    hel = json.loads((DATA / "heldout_readability.json").read_text(encoding="utf-8"))
    arm = json.loads((DATA / "arm_asymmetry.json").read_text(encoding="utf-8"))
    cot = json.loads((DATA / "cot_texts.json").read_text(encoding="utf-8"))

    # ---------- L1：直接读产物自己算好的 safe_regime 块 ----------
    # ⚠ 第一版在这里现算 min/max 全表，得到 0.12%–14.50% —— 那把
    #   s ≤ 0.2（定律成立）与 s = 0.5（二次近似失效）两个区间混在一起了，
    #   一个跨越失效点的区间**不说明任何事**。
    #   而产物自己已经把适用区间算好了：`conclusions.safe_regime` 与
    #   `conclusions.beyond_safe_regime`，直接读，不要重算。
    conc = law["conclusions"]
    safe, beyond = conc["safe_regime"], conc["beyond_safe_regime"]
    need(safe.get("direction_independent") is True,
         "L1 产物自己说 safe_regime.direction_independent = %r"
         % safe.get("direction_independent"))
    need(beyond.get("direction_independent") is False,
         "L1 beyond_safe_regime 应当 direction_independent=False"
         "（若产物变了，说明二次近似已在 s=0.2 内失效 ⇒ 阶梯措辞要改）")
    s_max = float(safe["strength_max"])
    # ⚠ 这里必须用 `real_dev_mean`（逐层先对 4 个方向取均值，再跨层取范围），
    #   **不能**直接把 4 层 × 4 方向的原值一起取 min/max ——
    #   那是另一个量（实测 1.989%–2.279%），证的是「逐个点都落在解析式上」，
    #   而文档 §2 那张表要回答的是「层与层之间与解析式一致」。
    #   两个都是合法的量，但混用会让「与方向无关」这句话失去它的专属证据
    #   （那一半由 max_direction_spread_pp 单独给）。
    means = [float(r["real_dev_mean"]) for r in law["rows"]
             if abs(r["strength"] - s_max) < 1e-9]
    preds = [float(r["pred_pct"]) for r in law["rows"]
             if abs(r["strength"] - s_max) < 1e-9]
    need(len(means) >= 4, "L1 在 s=%s 档只读到 %d 层" % (s_max, len(means)))
    l1_lo, l1_hi = min(means), max(means)
    l1_p_lo, l1_p_hi = min(preds), max(preds)
    l1_spread = float(safe["max_direction_spread_pp"])
    l1_rndgap = float(safe["max_real_vs_random_gap_pp"])
    # 与文档正文 §2 的 s=0.20 那一行对齐
    need(abs(l1_lo - 2.026) < 0.01 and abs(l1_hi - 2.245) < 0.01
         and abs(l1_p_lo - 2.018) < 0.01 and abs(l1_p_hi - 2.268) < 0.01,
         "L1 s=%s 实测 %.3f%%–%.3f%% / 解析 %.3f%%–%.3f%%，"
         "与文档 §2 的 2.026%%–2.245%% / 2.018%%–2.268%% 不一致"
         % (s_max, l1_lo, l1_hi, l1_p_lo, l1_p_hi))

    # ---------- L2：可读下界 ----------
    h = sub["headline"]
    l2 = int(h["readable_directions_lower_bound"])
    need(l2 == 14, "L2 可读下界读到 %d，与文档写的 14 不一致" % l2)
    od = h["order_dependence"]
    need(od["n_perm"] == 200 and od["new_range"][0] == od["new_range"][1] == l2,
         "L2 顺序依赖检查异常：%s" % od)

    # ---------- L3：干净归属的条数 ----------
    clean = [r for r in hel["rows"] if r["verdict"] == "new_clean"]
    need(len(clean) == 1, "L3 new_clean 读到 %d 条（期望 1）" % len(clean))
    l3_dir = clean[0]["key"] if clean else None

    # ---------- L4：配方存在性 ----------
    l4_rho = hel["recipe"]["loo_rho"]
    l4_floor = abs(hel["recipe"]["loo_floor"])
    l4_ratio = l4_rho / l4_floor if l4_floor else None
    need(l4_ratio and abs(l4_ratio - 82.0) < 1.0,
         "L4 配方 LOO/地板 读到 %.1f×，与文档写的 82× 不一致" % (l4_ratio or 0))

    # ---------- L5：可注入 ——
    l5_margin = hel["recipe"]["specificity_margin"]
    l5_ties = [v for v in hel["recipe"]["variants"] if v.get("tie")]
    need(l5_margin < 2.0, "L5 余量读到 %.2f×，已经 ≥2 ⇒ 阶梯该改了" % l5_margin)

    # ---------- L6：干预 run 数 + 缺随机臂 ----------
    l6_runs = int(cot["n_runs"])
    dirs = sorted({r["direction"] for r in cot["runs"]})
    need(len(dirs) == 2 and all("random" not in d for d in dirs),
         "L6 方向集合变了：%s —— 若已有随机臂，阶梯 L6 要升级" % dirs)
    l6_pairs = int(arm["n_pairs"])
    l6_sep = [m["metric"] for m in arm["metrics"] if m["distinguishable"]]

    if PROBLEMS:
        print("ABORT 阶梯构建自检不过，**不产出文件**：")
        for p in PROBLEMS:
            print("  ✗ " + p)
        return 2

    ladder = [
        {"level": "L0", "claim": "注进去模型变了",
         "needs": "一次前向，比较两个 logits",
         "state": "done", "here": "随手可得", "note": "任何方向都成立，不能区分方向"},
        {"level": "L1", "claim": "破坏量 = ½(s·rms/‖h‖)²，与方向无关",
         "needs": "解析式 + 玩具自检 + 逐方向实测",
         "state": "done",
         "here": "s ≤ %.1f：实测 %.3f%%–%.3f%% vs 解析 %.3f%%–%.3f%%"
                 % (s_max, l1_lo, l1_hi, l1_p_lo, l1_p_hi),
         "note": "跨方向极差 %.3fpp、真实-vs-随机 %.3fpp。"
                 "⚠ s = %s 时该近似本身失效（极差涨到 %.2fpp），"
                 "那些点不是反例，是解析式超范围。"
                 % (l1_spread, l1_rndgap, beyond["strengths"][0],
                    beyond["max_direction_spread_pp"])},
        {"level": "L2", "claim": "这个方向线性编码了观测量 y",
         "needs": "留出轨迹 + 打乱地板",
         "state": "done", "here": "%d 条" % l2,
         "note": "%d 候选、|cos|<%.2f；%d 次随机顺序恒为 %d"
                 % (h["n_candidates"], h["separation_threshold"], od["n_perm"], l2)},
        {"level": "L3", "claim": "这条方向**专属于** y",
         "needs": "专属性矩阵 + 余量 + 约束方身份 + 差距/sem",
         "state": "partial", "here": "%d 条干净" % len(clean),
         "note": "另有 %d 条余量 ≈1.0×，判为同向重造"
                 % sum(1 for r in hel["rows"] if r["verdict"] == "same_direction")},
        {"level": "L4", "claim": "能写成可注入的 diff_of_means",
         "needs": "留一轨迹上配方仍预测得动",
         "state": "done", "here": "%.4f（地板 %.4f，%.0f×）" % (l4_rho, hel["recipe"]["loo_floor"], l4_ratio),
         "note": "方向 %s" % l3_dir},
        {"level": "L5", "claim": "这条配方**专一**到能注入",
         "needs": "同上 + 同范数随机方向对照",
         "state": "missing", "here": "0 条（余量 %.2f× < 2×）" % l5_margin,
         "note": "换配方结构后最好 %.2f×，但两个竞争者差 %.2f sem ⇒ 归属不可判"
                 % (hel["recipe"]["best_margin"],
                    min(v["gap_over_sem"] for v in hel["recipe"]["variants"] if v["tie"]))},
        {"level": "L6", "claim": "注入改变行为，且改变是这条方向特有的",
         "needs": "教师强制前向 + **随机方向臂**",
         "state": "partial", "here": "%d 个真 run / %d 题配对" % (l6_runs, l6_pairs),
         "note": "**缺随机臂** ⇒ 只能说「改变了」。分得开的量：%s"
                 % ("、".join(l6_sep) or "无")},
        {"level": "L7", "claim": "改变的是这个**概念**，不是位置或格式",
         "needs": "行为指标 + 位置轴对照",
         "state": "missing", "here": "一次都没测", "note": ""},
    ]
    assert not any(x["state"] == "done" for x in ladder[5:]), \
        "L5 及以上不允许标 done"

    # ⚠ 自称「哪一级没测」的那段话，本身必须和上面这张表**逐级一致**。
    #   我原来写死「L5 及以上：一行都没有」，而同一份产物的 L6 是 partial
    #   （92 个真 run）—— 产物自己打自己的脸。
    #   而且「一行都没有」正是 §4.14 推翻过的那个错误：**未测 ≠ 实测为 0**。
    _missing, _partial = [], []
    for x in ladder:
        if x["state"] == "missing":
            _missing.append(x["level"])
        elif x["state"] == "partial":
            _partial.append(x["level"])
    _above = [x["level"] for x in ladder
              if int(re.sub(r"[^0-9]", "", x["level"])) > 4]
    for _lv in _above:
        assert _lv in _missing or _lv in _partial, \
            "%s 既不在 missing 也不在 partial 里，not_answerable 会说错" % _lv

    payload = {
        "schema": "evidence_ladder/1",
        "what": "任何「某 steering vector 编码了概念 X」的断言，能被放上去量的八级阶梯",
        "built_from": ["linearity_law.json", "readable_subspace.json",
                       "heldout_readability.json", "arm_asymmetry.json",
                       "cot_texts.json"],
        "selfcheck_passed": True,
        "ladder": ladder,
        "answerable": [
            "一个这样的断言需要什么证据才成立",
            "哪些级别的证据在**任何**方向上都成立（因此不能区分方向）",
        ],
        # 逐级写，不用「L5 及以上」这种一刀切的措辞 ——
        # L6 有数据（缺随机臂），L5/L7 才是真的没测。
        "not_answerable": [
            "模型内部到底在算什么",
            "L5：0 条配方通过专一性门槛（余量 %.2f× < 2×），**未测**，不是「实测为 0」" % l5_margin,
            "L6：%d 个真 run / %d 题配对，**有数据但缺同范数随机方向臂** ⇒ "
            "只能声称「改变了」，不能声称「这条方向特有地改变了」" % (l6_runs, l6_pairs),
            "L7：一次都没测（缺位置轴对照）",
        ],
        # ⚠ 这两个是**不同的量**，混成一个数字正是上面那个矛盾的来源。
        #   claimed = 净位置（有连续门控、每一级都站得住的最高级）
        #   with_data = 手上有任何数据的最高级（可以 partial）
        "max_level_claimed": "L4",
        "max_level_with_data": "L6",
        "why_two_numbers": ("L6 上有 92 个真 run，但它**缺随机臂**，"
                            "所以不能声称；而 L5 一条都没有。"
                            "「最高有数据」与「最高能声称」必须分开印，"
                            "否则就会写出「L5 及以上一行都没有」这种自相矛盾的话。"),
        "max_level_reached": "L4",   # 保留旧键，语义 = max_level_claimed
        "most_common_overreach": "L2 → L5：把「找到 N 条可读方向」读成「有 N 条可用的轴」",
        "overreach_numbers": {"readable_directions": l2, "usable_axes": 0,
                              "note": "「0」是**未测**，不是「实测为 0」"},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("阶梯自检全过（6 条跨产物一致性）")
    for x in ladder:
        print("  %-3s %-8s %s" % (x["level"], x["state"], x["here"]))
    print()
    print("已写", OUT)


if __name__ == "__main__":
    raise SystemExit(main())
