#!/usr/bin/env python3
"""把 probe_axes.json 压成页面可读的小文件。

只取每层 λ=0.01 的那几行，取四个轴 × 五个 Δ 的最优合法候选 + 位置对照。
**必须一起带上的三样东西**（缺任何一样页面就会把对照结果说成发现）：

1. `control_step_frac`：位置对照。它是 `reasoning_deep` 的定义分组。
2. `beats_control`：逐格布尔，页面靠它决定显示"已测"还是"不超对照"。
3. `effective_dof` 与 `n_random`：搜索的代价，页面上要印出来。

页面不允许自己挑候选 —— 最优候选在这里选定，页面只负责显示。
挑在分析侧、显示在展示侧，两者分开才不会在渲染时"顺手"换一个更漂亮的。
"""
import json

import numpy as np
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
SRC = ROOT / ".cache/rolesverify/probe_axes.json"
# 撤回声明的**唯一**来源：completeness.json 的 effective_dof 块（§8.9 第十四笔）。
# 手抄一句「已推翻」进本脚本，就是把一个无源的散文换成一个无源的散文。
COMPLETENESS = ROOT / ".cache/completeness/completeness.json"
OUT = ROOT / "frontend/public/latent/data/axis_readouts.json"
LAM = 0.01
AXES = ["confidence", "caution", "creativity", "reasoning"]

# 轴的中文说法 —— 「已测」的表述必须与余弦的实际大小一致。
# cos=0.308 的含义是「解释了约 9.5% 的方向成分」，所以措辞是「实现里有…这一项」
# 而不是「就是…」。这个区分是从余弦算出来的，不是措辞上的谦虚。
AXIS_META = {
    "confidence": {"label": "高置信 / 低熵", "grouping": "低熵 p30 vs 高熵 p75"},
    "caution": {"label": "谨慎", "grouping": "自我检查 token vs 普通 token"},
    "creativity": {"label": "思维块状态", "grouping": "<think> 内 vs 外"},
    "reasoning": {"label": "深推理 / 后期位置", "grouping": "长轨迹后 25% vs 前 25%"},
}
CAND_MEANING = {
    "top1_prob_renorm": "top-1 概率（熵的重述）",
    "backtrack_topk": "top-64 候选里出现修订类 token 的比例",
    "rep_ngram4": "以本步结尾的 4-gram 是否已出现过",
    "rep_frac_topk": "top-64 候选里已在生成前缀出现的比例",
    "rep_top1": "top-1 token 是否已出现过",
    "digit_mass": "top-64 质量中落在数字 token 上的占比",
    "op_mass": "top-64 质量中落在运算符上的占比",
    "latex_mass": "top-64 质量中落在排版结构上的占比",
    "newline_mass": "top-64 质量中落在换行上的占比",
}


def main():
    d = json.loads(SRC.read_text())
    cfg = d["config"]
    # 把「9 已被推翻」的审计结论从 completeness.json **逐字**读进来。
    # ⚠ 找不到就拒绝写 —— 那样这个字段会变成又一句无源的散文。
    _eff = json.loads(COMPLETENESS.read_text()).get("effective_dof", {})
    _dev = _eff.get("deviation_from_probe_axes")
    if not _dev or not _eff.get("all_usable_kept"):
        raise SystemExit(
            "completeness.json 里找不到 effective_dof.deviation_from_probe_axes，"
            "或 all_usable_kept 不为真 —— 撤回声明会变成无源的散文，拒绝写。")
    _EFFDOF_RETRACTION = (
        "⚠ `effective_dof.after_dropping_redundant = 9` 与 "
        "`redundant_dropped = [backtrack_frac]` 是**已被本项目推翻的数**，"
        "只是历史记录（搜索当时确实只跑了 9 个候选）。审计结论："
        + _dev
        + " ⇒ 面板若要展示「有效自由度」，必须写 10 并说明搜索实际覆盖 "
        + str(_eff.get("n_searched_observables")) + " 个观测量中只用了 9 个。")
    out = {
        "schema": "steer3d.axis_readouts/1",
        "question": str(len(AXES)) + " 条独立轴各自指向哪个逐 token 行为观测量？",
        "convention": {
            "target_transform": "轨迹内去均值（每条轨迹减去自己的均值）",
            "fold": "留一轨迹，每折重解 w",
            "lambda_rel": LAM,
            "axes": len(AXES),
            "n_candidates_searched": len(cfg["candidates_searched"]),
            "n_candidate_cells": cfg["n_candidate_cells"],
            "effective_dof": cfg["effective_dof"],
            "redundant_dropped": cfg["candidates_dropped"],
            # ⚠ §8.9 第十四笔：`cfg["effective_dof"]` 里的 9 是**已被本项目推翻的数**。
            #   completeness.json 的 effective_dof 块做过独立审计，原文：
            #     「probe_axes.py 以 |ρ|(backtrack_topk,backtrack_frac)=0.965 为由把
            #       backtrack_frac 剔出搜索、把有效自由度记成 9。实测该 0.965 是 Spearman；
            #       Pearson 只有 0.27。对线性探针而言二者不是重复，故本轮 10 个全留，
            #       有效自由度按 10 记。」
            #   ⇒ 搜索确实只跑了 9 个（历史事实，不该改数字），
            #     但**不能**让这个 9 看起来像当前结论。
            #   ⇒ 这里把审计结论**逐字**从 completeness.json 读进来（不手抄），
            #     并显式声明「这 9 不是结论」。页面目前不印这一块，
            #     但它一旦被印出来、或被别的判据读到，必须带着这句撤回声明。
            "effective_dof_retraction": _EFFDOF_RETRACTION,
            "n_random_directions": cfg["n_random"],
            # ⚠ §8.9 第十四笔：这段原来每个数都是**字面量**
            #   （"9 候选 × 4 轴" / "400 个随机方向"），
            #   而上面三行 `n_candidates_searched` / `n_random_directions` /
            #   `convention.axes` 就在同一个 dict 里躺着 —— 三个数都能现算。
            #   ⇒ 散文里的数与结构化字段可以各改各的，且没有任何判据会红。
            # ⚠⚠ **修法本身就是最容易犯这个错的地方**：
            #   我第一版把「× N 轴」填成了 `cfg["effective_dof"]["declared"]`（=10），
            #   那是**候选维数**不是**轴数** ⇒ 会把一个错的数写进产物。
            #   凭「同一个 dict 里有这个数」去填是**不够**的 ——
            #   必须确认那���个数与这个位置**语义相同**。
            "p_note": "p 已为「" + str(len(cfg["candidates_searched"])) + " 候选 × "
                      + str(len(AXES)) + " 轴」的搜索付过钱（零假设取 "
                      "max_j max_a 的最大值，" + str(cfg["n_random"]) + " 个随机方向）",
            "control": "CONTROL_step_frac = t/(T-1)，正是 reasoning_deep 的定义分组。"
                       "它不是候选，是尺子。",
        },
        "selfcheck": d["selfcheck"]["pass"],
        "axes": {},
        "per_layer": {},
    }

    for L in sorted(d["per_layer"], key=int):
        rows = {r["delta"]: r for r in d["per_layer"][L]["rows"]
                if abs(r["lambda_rel"] - LAM) < 1e-12}
        ctl = next((c for r in rows.values() for c in r["candidates"]
                    if c["is_control"]), None)
        cells = {}
        for delta, r in rows.items():
            legit = [c for c in r["candidates"] if not c["is_control"]]
            per_axis = {}
            for ax in AXES:
                best = max(legit, key=lambda c: c["cos_per_axis_median"][ax])
                b = round(best["cos_per_axis_median"][ax], 4)
                c0 = round(ctl["cos_per_axis_median"][ax], 4) if ctl else None
                per_axis[ax] = {
                    "candidate": best["candidate"],
                    "candidate_meaning": CAND_MEANING.get(best["candidate"],
                                                        best["candidate"]),
                    "cos": b,
                    "control_cos": c0,
                    "beats_control": bool(c0 is not None and b > c0),
                    "p": best["p_search_corrected"],
                    "oof_pearson": round(best["oof_pearson"], 4),
                }
            cells[str(delta)] = {
                "per_axis": per_axis,
                "n_traj_used": r["n_traj_used"],
            }
        out["per_layer"][L] = {
            "cos_ceiling": {k: round(v, 4) for k, v in
                            d["per_layer"][L]["cos_ceiling"].items()},
            "control_cos_per_delta": {str(dl): round(ctl["cos_per_axis_median"][ax], 4)
                                      for dl in cells for ax in AXES},
            "control_oof_pearson_per_delta": {
                str(dl): round(next(r["candidates"][0]["oof_pearson"]
                                    for r in rows.values() if r["delta"] == int(dl)
                                    and any(c["is_control"] for c in r["candidates"])), 4)
                for dl in cells},
            "cells": cells,
        }

    # 汇总：每条轴的状态。判据只用 Δ=0 那一格，且要求三件事同时成立：
    #   (a) 同一个候选在**全部 3 层**都超过位置对照
    #   (b) 它的余弦在全部 3 层都 ≥ 对照的 3 倍
    #   (c) 三层取中位数时仍然成立
    # 为什么只看 Δ=0：Δ=0 才是「这个方向在这一步实现了什么」这个问题；
    # 大 Δ 上的对齐连「方向」都算不上（creativity 在 L20 的 Δ=1 有 0.173，
    # 但 Δ=0 时 L12/L14 连对照都没超过）。
    # 为什么要求「同一个候选」：真读出方向在不同层会指向同一个观测量；
    # 每格换一个候选是噪声的签名 —— creativity 就是这样
    # （rep_ngram4 / backtrack_topk / latex_mass / digit_mass / newline_mass 轮换）。
    for ax in AXES:
        d0 = {L: out["per_layer"][L]["cells"]["0"]["per_axis"][ax]
              for L in out["per_layer"] if "0" in out["per_layer"][L]["cells"]}
        cands = [c["candidate"] for c in d0.values()]
        modal = max(set(cands), key=cands.count) if cands else None
        modal_cells = [c for c in d0.values() if c["candidate"] == modal] if modal else []
        n_beat = sum(1 for c in modal_cells if c["beats_control"])
        ratios = [c["cos"] / c["control_cos"] for c in modal_cells
                  if c["control_cos"]]
        median_cos = float(np.median([c["cos"] for c in modal_cells])) if modal_cells else 0.0
        median_ctl = float(np.median([c["control_cos"] for c in modal_cells])) \
            if modal_cells else 0.0
        ok = bool(modal_cells and n_beat == len(d0)
                  and ratios and min(ratios) >= 3.0
                  and median_cos > median_ctl)
        cells_flat = [c for pl in out["per_layer"].values()
                      for cell in pl["cells"].values()
                      for a, c in cell["per_axis"].items() if a == ax]
        if ok:
            status = "measured"
        elif ax == "reasoning":
            status = "position_axis"
        else:
            status = "not_measured"
        out["axes"][ax] = {
            "label": AXIS_META[ax]["label"],
            "grouping": AXIS_META[ax]["grouping"],
            "status": status,
            "at_delta0": {
                "modal_candidate": modal,
                "per_layer": {L: {"candidate": c["candidate"], "cos": c["cos"],
                                 "control_cos": c["control_cos"],
                                 "beats_control": c["beats_control"],
                                 "p": c["p"], "oof_pearson": c["oof_pearson"]}
                              for L, c in d0.items()},
                "n_layers_beating_control": n_beat,
                "n_layers": len(d0),
                "median_cos": round(median_cos, 4),
                "median_control_cos": round(median_ctl, 4),
                "min_ratio_over_control": round(min(ratios), 2) if ratios else None,
            },
            "at_delta20_L14": out["per_layer"].get("14", {}).get("cells", {}).get(
                "20", {}).get("per_axis", {}).get(ax),
            "best_cos_any_cell": max(c["cos"] for c in cells_flat),
            "best_control_any_cell": max(c["control_cos"] for c in cells_flat
                                         if c["control_cos"] is not None),
            "n_cells_beating_control": sum(1 for c in cells_flat if c["beats_control"]),
            "n_cells_total": len(cells_flat),
            "criterion": "measured ⟺ Δ=0 上同一个候选在全部 3 层都超过位置对照，"
                         "且每层都 ≥ 对照的 3 倍，中位数仍成立。"
                         "上面每个数都是实测，读者可以自己核。",
        }

    out["headline"] = {
        "measured": [a for a in AXES if out["axes"][a]["status"] == "measured"],
        "position_axis": [a for a in AXES if out["axes"][a]["status"] == "position_axis"],
        "not_measured": [a for a in AXES if out["axes"][a]["status"] == "not_measured"],
        "vocabulary_caveat": "6 个方向标签 = 4 条独立轴；confidence_down≡−confidence_up、"
                             "reasoning_shallow≡−reasoning_deep（cos 恰为 −1.0000）。",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("wrote", OUT, OUT.stat().st_size, "bytes")
    for ax in AXES:
        a = out["axes"][ax]
        d0 = a['at_delta0']
        print(f"  {ax:<12s} {a['status']:<14s} Δ0 众数候选 {str(d0['modal_candidate']):<18s}"
              f" 超对照 {d0['n_layers_beating_control']}/{d0['n_layers']} 层"
              f"  中位 {d0['median_cos']:.3f} vs 对照 {d0['median_control_cos']:.3f}"
              f"  最小倍数 {d0['min_ratio_over_control']}")
        for L, c in sorted(d0['per_layer'].items()):
            print(f"       L{L:<3s} {c['candidate']:<18s} cos={c['cos']:.3f} "
                  f"对照={c['control_cos']:.3f} p={c['p']:.4f} "
                  f"{'超' if c['beats_control'] else '不超'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
