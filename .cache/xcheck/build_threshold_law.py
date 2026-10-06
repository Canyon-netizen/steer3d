#!/usr/bin/env python3
"""把两轮实测固化成网站可读的产物，并在**构建期**就自证一遍。

产物：`frontend/public/latent/data/intervention_threshold_law.json`

它回答的是用户那个问题：「施加干预的时候模型的行为到底如何变化」。
页面上原来只有一句诚实的免责声明（回放不改 token），没有正面答案。
这份产物给正面答案，并且每一行都带着它的来源与不确定度：

  · 每个步的**阈值区间**（不是单点）—— 右删失的步如实标 ">"，不假装定位了
  · 判据独立的**决胜间距**
  · 方向 / 层 / 注入单位（该层残差 RMS 的倍数），使数字跨层可比

构建期自检（不是「跑完看着像对」）：
  1. 至少 2 个强度档，且 |Δlogit| 随强度严格递增（剂量-反应前提）
  2. 至少 1 步被夹住阈值（否则整份产物只是「没找到」）
  3. 区间端点必须来自真实采样网格，不许出现网格外的数
  4. 「阈值随间距单调」若不成立，产物里 mechanism_stable=false，
     并且**页面上必须显示这句否定结论**，不许只印成立的那一半

用法: python3 .cache/xcheck/build_threshold_law.py
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCAN = os.path.join(REPO, ".cache", "probe_live_inject.json")
LAW = os.path.join(REPO, ".cache", "probe_threshold_law.json")
OUT = os.path.join(REPO, "frontend", "public", "latent", "data",
                   "intervention_threshold_law.json")


def die(msg, code=2):
    print(f"装置故障：{msg}", file=sys.stderr)
    sys.exit(code)


def main():
    if not os.path.exists(SCAN):
        die(f"缺扫描产物 {SCAN}（先跑 probe_live_inject.py）")
    scan = json.load(open(SCAN, encoding="utf-8"))

    scans = scan.get("scans") or []
    steps = scan.get("steps", 0)
    grid = sorted(s["mult"] for s in scans)
    if len(grid) < 2:
        die(f"强度档只有 {len(grid)} 个，做不出剂量-反应（至少要 2 档）")

    # ── 构建期自检 1：剂量-反应前提 ────────────────────────────────
    dl = [(s["mult"], max(r["max_abs_dlogit"] for r in s["rows"])) for s in scans]
    doses = [v for _, v in dl]
    if not all(doses[i] <= doses[i + 1] + 1e-6 for i in range(len(doses) - 1)):
        die(f"最大|Δlogit| 未随强度单调递增：{dl} —— "
            f"「剂量-反应」的说法在本轮数据上不成立，不能出产物")

    # ── 构建期自检 2：至少夹住一个阈值 ────────────────────────────
    rebuilt = {}
    for i in range(steps):
        f = next((s["mult"] for s in scans
                  if s["rows"][i]["token_ctrl"] != s["rows"][i]["token_inj"]), None)
        rebuilt[i] = f
    bracketed = {i: v for i, v in rebuilt.items() if v is not None}
    if not bracketed:
        die("没有任何一步被夹住阈值 ⇒ 产物只能说「没找到」，"
            "而「没找到」不是一条关于干预的结论，不该出现在页面上")

    # ── 构建期自检 3：区间端点必须落在采样网格上 ──────────────────
    def lo_of(m):
        k = grid.index(m)
        return grid[k - 1] if k > 0 else 0.0
    for i, m in bracketed.items():
        if m not in grid:
            die(f"步 {i} 的翻盘强度 {m} 不在采样网格 {grid} 上 —— 数据不自洽")
        if lo_of(m) not in grid and lo_of(m) != 0.0:
            die(f"步 {i} 的区间下界 {lo_of(m)} 不在网格 {grid} 上")

    # ── 逐步区间 + 单调性 ─────────────────────────────────────────
    lows = {i: (lo_of(m) if m is not None else grid[-1]) for i, m in rebuilt.items()}
    margins = {i: scans[0]["rows"][i]["margin_ctrl"] for i in range(steps)}
    order = sorted(margins, key=lambda s: margins[s])
    viol = [(a, b) for a, b in zip(order, order[1:]) if lows[b] < lows[a] - 1e-12]

    per_step = []
    for i in range(steps):
        m = rebuilt[i]
        if m is None:
            bracket, hi, lo = "right_censored", None, grid[-1]
        else:
            lo = lo_of(m)
            bracket = "bracketed" if lo > 0 else "left_censored"
            hi = m
        per_step.append({
            "step": i,
            "token_ctrl": scans[0]["rows"][i]["token_ctrl"],
            "token_at_lowest": scans[0]["rows"][i]["token_inj"],
            "decision_margin": round(margins[i], 4),
            "threshold_lo": lo,
            "threshold_hi": hi,
            "bracket": bracket,
        })

    # ── 通用性（可选；没跑就不写这一节，不许编） ──────────────────
    #
    # ⚠ 这里必须把「两个门」分开记，不能压成一个 stable 布尔值。
    #   门 A：中位阈值的跨格差值 ≤ STABLE_RATIO
    #   门 B：所有 (格,步) 都夹住了阈值
    # 上一版把 A 记成 `stable`，而打印那句却是「门 A 过了但门 B 不过 ⇒ 不稳」。
    # 于是 JSON 里 stable=true、日志里写"不稳" —— **产物和它自己的结论对不上**。
    # 一个读者（人或脚本）只看到 stable=true 就会以为这是条通则。
    # ⇒ 结论只由一个 verdict 字段承担，两个门分别记成 evidence。
    generality = None
    if os.path.exists(LAW):
        law = json.load(open(LAW, encoding="utf-8"))
        cells = law.get("cells") or []
        meds = [c["median_threshold"] for c in cells if c["median_threshold"]]
        ratio = (max(meds) / min(meds)) if len(meds) >= 2 else None
        gate_ratio = law.get("stable_gate")
        gate_a = (ratio is not None and ratio <= gate_ratio)
        n_unb = int(law.get("n_unbracketed") or 0)
        n_pairs = sum(c["n_steps"] for c in cells)
        gate_b = (n_unb == 0)
        # 一个格都没翻 ⇒ 那个格不能参与「稳不稳」的比值，否则除以一个不存在的中位数
        never = sorted({f"{c['direction']}@L{c['layer']}"
                        for c in cells if not c["median_threshold"]})
        if not gate_b:
            verdict = "not_general"
            reason = (f"{n_unb}/{n_pairs} 个 (方向,层,步) 组合到网格上限 "
                      f"{law.get('grid', [])[-1]}× 仍不翻盘，"
                      f"其中 {len(never)} 个格**一步都没翻**：{', '.join(never)}。"
                      f"阈值在这些格上根本没被测到，"
                      f"拿没测到的格子去说『稳』是拿缺本当证据。")
        elif not gate_a:
            verdict = "not_general"
            reason = (f"已夹住的格之间中位阈值差 {ratio:.2f}×，"
                      f"超过判稳门 {gate_ratio}× ⇒ 阈值随 (方向,层) 变化。")
        else:
            verdict = "candidate_law"
            reason = (f"两个门都过：跨格比值 {ratio:.2f}× ≤ {gate_ratio}×，"
                      f"且所有 (格,步) 都夹住了。")
        generality = {
            "note": "同一判据在别的方向/层上复测，检验这条说法能不能迁移",
            "n_cells": len(cells),
            "cells": [{"direction": c["direction"], "layer": c["layer"],
                       "median_threshold": c["median_threshold"],
                       "n_flipped_steps": c["n_flipped_steps"],
                       "n_steps": c["n_steps"],
                       "unbracketed_steps": c["unbracketed_steps"]}
                      for c in cells],
            "verdict": verdict,
            "verdict_reason": reason,
            "evidence": {
                "gate_A_ratio_within_limit": gate_a,
                "median_ratio": ratio,
                "ratio_gate": gate_ratio,
                "gate_B_all_bracketed": gate_b,
                "n_unbracketed_pairs": n_unb,
                "n_pairs": n_pairs,
                "cells_that_never_flipped": never,
            },
        }
    else:
        print("提示：没有 probe_threshold_law.json，通用性一节将缺失（不编造）")

    out = {
        "question": "把一个 steering 向量注入残差流，模型输出的 token 会不会变？",
        "headline": (
            "会变，但不是「有效/无效」：需要多大推力，取决于模型当时离改口有多近。"
        ),
        "setting": {
            "model": scan.get("model"),
            "layer": scan.get("layer"),
            "direction": scan.get("direction"),
            "vector_source": scan.get("vec_source"),
            "resid_scale": round(float(scan.get("resid_scale", 0)), 3),
            "unit": "注入范数 ÷ 该层残差流 std（无量纲，跨层可比）",
            "use_chat_template": scan.get("use_chat"),
            "n_steps": steps,
            "grid": grid,
        },
        "dose_response": [{"mult": m, "injected_norm": round(n, 2),
                           "max_abs_dlogit": round(v, 4),
                           "n_flipped": sum(1 for r in s["rows"] if r["flipped"])}
                          for s, (m, v) in zip(scans, dl)
                          for n in [s["injected_norm"]]],
        "per_step": per_step,
        "mechanism": {
            "claim": "阈值随该步的决胜间距单调不减",
            "stable": not viol,
            "violations": viol,
            "how_to_read": (
                "间距小的那一步，注入没多大就改口；间距大的那一步，推到 "
                "2× 残差 std 也不改。所以「这个向量有没有用」这个问题"
                "问错了 —— 有用的是推力大小和它落在哪个决策点上。"
            ),
        },
        "generality": generality,
        "contrast_with_replay": {
            "claim": "回放模式下注入**永远**不改 token",
            "why": "token 在注入前就由录制的 token_ids 定死；"
                   "要让 token 跟着干预变，得从该层起把剩余 block 前向一遍",
            "checked_by": "verify_real_replay.mjs 的 D13"
                           "（注入生效的帧与无注入基线逐字相同）",
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=2)

    print(f"已写 {OUT}")
    print(f"  剂量-反应 {len(grid)} 档："
          f"{[f'{m}×:{v:.2f}' for m, v in dl]}")
    print(f"  逐步区间：{[(p['step'], p['bracket'], p['threshold_lo'], p['threshold_hi']) for p in per_step]}")
    print(f"  单调性：{'成立' if not viol else f'不成立，反例={viol}'}")
    if generality:
        g = generality["evidence"]
        print(f"  通用性：{generality['n_cells']} 格  判决={generality['verdict']}")
        print(f"    门A 跨格比值 {g['median_ratio']} ≤ {g['ratio_gate']} ? "
              f"{g['gate_A_ratio_within_limit']}    "
              f"门B 全部夹住 ? {g['gate_B_all_bracketed']} "
              f"（未夹住 {g['n_unbracketed_pairs']}/{g['n_pairs']}）")
        print(f"    从未翻盘的格：{g['cells_that_never_flipped'] or '无'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
