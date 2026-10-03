#!/usr/bin/env python3
"""S4 — 把 S1/S1b/S2/S3 的原始数值合并成 layerside2.json（唯一权威数值源）。

## 怎么跑

    cd /Users/zhourui/code/steer3d
    python3 .cache/layerside2/s1_cache_facts.py
    python3 .cache/layerside2/s1b_vectors.py
    python3 .cache/layerside2/s2_probe.py
    python3 .cache/layerside2/s3_injection_amp.py
    python3 .cache/layerside2/s4_consolidate.py     # 本脚本

产物：layerside2.json —— 报告里每一个数字都必须能在这里查到，且键名稳定。
报告本身不新增任何数字，只做引用。

## 结构

    item1_baseline_reproduction   复现 6 个发布向量（样本数 + cos）
    item2_vector_across_layers    cos(v_Li, v_Lj) 与 cos(发布向量, v_Lj)
    item3_readout_grid            读出层 Lr × 向量层 Lv 的 2×4 网格 + 同格位置对照
    item4_injection_amplitude     注入点相对幅度与几何代价
    item5_controls                400 随机方向分布 + step_frac 阳性对照
    item6_selfcheck               装置自检（含层号分辨力）
    published_reference           上游已发表数字，仅作对照，本脚本不改写
"""
import json
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROLL = ("lambda_rel=0.01, target_transform=demean_within_traj, stride=2, k_pca=256, "
        "leave-one-trajectory-out 每折重解 w")
AXIS_OF = {"confidence": "confidence_up", "caution": "caution",
           "creativity": "creativity", "reasoning": "reasoning_deep"}
CAND_OF = {"confidence": "top1_prob_renorm", "caution": "backtrack_topk"}


def _p95_null(pf):
    """(轴) -> {'p95': ...}，取 L13/Δ=0 那一格的 400 随机方向分布。"""
    return {ax: {"p95": pf[
        f"13|demean_within_traj|0|0.01|{CAND_OF[ax]}|{ax}"]["null_random_400"]["cos_p95"]}
        for ax in CAND_OF}


def derived_block(grid, cells, s2p95):
    """报告 §0/§8 引用的派生量。全部在这里算，审计脚本只做字面量比对。"""
    def d(axis, delta, Lr, Lv):
        return grid[f"{axis}|delta{delta}|readoutL{Lr}"][
            "cos_dspace_by_vector_layer"][str(Lv)]

    def ctl(axis, delta, Lr):
        return grid[f"{axis}|delta{delta}|readoutL{Lr}"][
            "control_step_frac_cos_pca_norm_same_cell"]

    out = {
        "_definition": {
            "published_cell": "Lr=14, Lv=14",
            "matched_at_injection_cell": "Lr=13, Lv=13",
            "vector_only_cell": "Lr=14, Lv=13（只把向量挪一层）",
            "readout_only_cell": "Lr=13, Lv=14（只把读出挪一层）",
        }
    }
    for ax in CAND_OF:
        pub = d(ax, 0, 14, 14)
        matched = d(ax, 0, 13, 13)
        vonly = d(ax, 0, 14, 13)
        ronly = d(ax, 0, 13, 14)
        out.setdefault("matched_minus_published", {})[ax] = matched - pub
        out.setdefault("matched_rel_pct", {})[ax] = 100 * (matched - pub) / pub
        out.setdefault("vector_only_minus_published", {})[ax] = vonly - pub
        out.setdefault("vector_only_rel_pct", {})[ax] = 100 * (vonly - pub) / pub
        out.setdefault("readout_only_minus_published", {})[ax] = ronly - pub
        out.setdefault("readout_only_rel_pct", {})[ax] = 100 * (ronly - pub) / pub
        out.setdefault("ratio_to_control_matched", {})[ax] = (
            grid[f"{ax}|delta0|readoutL13"]["cos_pca_norm_median"] / ctl(ax, 0, 13))
        out.setdefault("ratio_to_control_published", {})[ax] = (
            grid[f"{ax}|delta0|readoutL14"]["cos_pca_norm_median"] / ctl(ax, 0, 14))
        out.setdefault("conclusion_over_floor", {})[ax] = matched / grid[
            f"{ax}|delta0|readoutL13"]["null_floor_cos_max"]
        out.setdefault("conclusion_over_p95_floor", {})[ax] = (
            matched / s2p95[ax]["p95"])
    # 全部 8 个 Δ=0 格（两轴 × 2 读出层 × 4 向量层）里相对已发表格的最大变动
    chg = {}
    for ax in CAND_OF:
        pub = d(ax, 0, 14, 14)
        chg[ax] = max(abs(d(ax, 0, Lr, Lv) - pub)
                      for Lr in (13, 14) for Lv in (12, 13, 14, 15))
    out["max_abs_change_any_cell"] = max(chg.values())
    out["max_abs_change_per_axis"] = chg
    out["max_rel_change_pct_any_cell"] = 100 * max(
        abs(d(ax, 0, Lr, Lv) / d(ax, 0, 14, 14) - 1)
        for ax in CAND_OF for Lr in (13, 14) for Lv in (12, 13, 14, 15))
    # **只挪一个 block** 的变动：或只把向量挪到 L13，或只把读出挪到 L13。
    # 不能用 max_abs_change_any_cell —— 那个把 L12/L15（相隔两块）也算进来了。
    ob = {}
    for ax in CAND_OF:
        ob[ax] = max(abs(d(ax, 0, 14, 13) - d(ax, 0, 14, 14)),
                     abs(d(ax, 0, 13, 14) - d(ax, 0, 14, 14)))
    out["one_block_max_abs_change_per_axis"] = ob
    out["one_block_max_abs_change"] = max(ob.values())
    out["one_block_max_rel_pct"] = 100 * max(ob.values()) / min(
        d(ax, 0, 14, 14) for ax in CAND_OF)
    return out


def main():
    t0 = time.time()
    s1 = json.loads((OUT / "s1_facts.json").read_text())
    s1b = json.loads((OUT / "s1b_vectors.json").read_text())
    s2 = json.loads((OUT / "s2_probe.json").read_text())
    s3 = json.loads((OUT / "s3_injection_amp.json").read_text())
    pf = s2["per_fold"]
    cells = s2["cells_pca_norm"]

    def cell(Lr, delta, cand, axis):
        return pf[f"{Lr}|demean_within_traj|{delta}|0.01|{cand}|{axis}"]

    def obs(Lr, delta, cand, axis):
        return cells[f"{Lr}|demean_within_traj|{delta}|0.01|{cand}|{axis}"]

    R = {
        "schema": "layerside2.consolidated/1",
        "roll": ROLL,
        "conventions": {
            "pca_norm": "|w_n · normalize(Pᵀv)| —— probe_axes 的口径，先按天花板归一；"
                        "已发表的 0.412/0.308 用的是这个",
            "dspace": "pca_norm × ceiling —— 真 2048 维余弦；本报告的结论用这个",
            "identity_max_abs_err": max(
                v["identity_check_dspace_eq_pca_times_ceiling"] for v in pf.values()),
        },
        "published_reference": {
            "probe_axes_L14_delta0_lam0.01": {
                "confidence_top1_prob_renorm_pca_norm": 0.41250607586097715,
                "caution_backtrack_topk_pca_norm": 0.3076629340648651,
                "control_step_frac_confidence": 0.01143664425822239,
                "control_step_frac_caution": 0.0016281401287450217,
                "pca_var_cum_L14": 0.7287951021859504,
            },
            "layer_side_forensics_claims_being_tested": {
                "mean_hidden_norm_L13": 139.37692279469584,
                "mean_hidden_norm_L14": 164.42098847676215,
                "cos_recomputed_L13_vs_L14": 0.9564887762663499,
                "cos_stored_vs_recomputed_L14": 0.9989588782869807,
            },
        },
    }

    # ---- item 1 ----
    R["item1_baseline_reproduction"] = {
        "method": "用 hidden_L{12..15}.npy 缓存 + 与 compute_steering_vectors.py 逐字相同的"
                  "分组谓词重算 diff_of_means；判据是 n_positive/n_negative 逐个相等"
                  "且 cos > 0.999",
        "sum_n_prompt_tokens": s1b["sum_n_prompt_tokens"],
        "n_tokens_after_n_prompt_skip": s1b["n_tokens_after_n_prompt_skip"],
        "per_axis": s1b["reproduction"],
        "all_reproduced": all(v.get("reproduced") for k, v in s1b["reproduction"].items()
                              if "reproduced" in v),
    }

    # ---- item 2 ----
    R["item2_vector_across_layers"] = {
        "adjacent_cos": s1b["adjacent_cos"],
        "cos_published_L14_vector_vs_recomputed": s1b["cos_published_vs_recomputed"],
        "identity_published_L13_equals_L13_vs_L14":
            s1b["identity_published_L13_equals_L13_vs_L14"],
        "identity": "cos(published_L14, v_L13) 与 cos(v_L13, v_L14) 必须相等；"
                    "上游报的 0.9565 与 0.9546 不等，说明那次重算的 v_L14 并不是"
                    "发布向量（其 cos 仅 0.99896）。修正后两者必然相等。",
    }

    # ---- item 3 ----
    grid = {}
    for axis, cand in CAND_OF.items():
        for delta in (0, 20):
            for Lr in (13, 14):
                c = cell(Lr, delta, cand, axis)
                ctl = cell(Lr, delta, "CONTROL_step_frac", axis)
                grid[f"{axis}|delta{delta}|readoutL{Lr}"] = {
                    "candidate": cand,
                    "cos_pca_norm_median": obs(Lr, delta, cand, axis),
                    "cos_dspace_by_vector_layer": c["cross_layer_cos_dspace_median"],
                    "oof_pearson": c["oof_pearson"],
                    "n_traj_used": c["n_traj_used"],
                    "n_steps_used": c["n_steps_used"],
                    "control_step_frac_cos_pca_norm_same_cell":
                        obs(Lr, delta, "CONTROL_step_frac", axis),
                    "control_step_frac_cos_dspace_same_cell":
                        ctl["cross_layer_cos_dspace_median"],
                    "null_floor_cos_max": c["null_random_400"]["cos_max"],
                    "p_search_corrected": c["p_search_corrected_median_criterion"],
                    "ceiling_readout_layer": {a: c["ceiling"] for a in [cand]},
                }
    R["item3_readout_grid"] = {
        "definition": {
            "readout_layer_Lr": "读出方向 w 由哪一层的隐状态拟合",
            "vector_layer_Lv": "与 w 比余弦的 steering 向量取自哪一层",
            "published_cell": "Lr=14, Lv=14 —— 已发表的 0.412/0.308 就在这一格",
            "matched_at_injection_cell": "Lr=13, Lv=13 —— 注入点所在的层，"
                                         "向量与读出都在同一层",
        },
        "grid": grid,
        "derived": derived_block(grid, cells, _p95_null(pf)),
        "readout_direction_across_layers": s2["readout_direction_across_layers"],
        "pca_var_cum": {k: v["pca_var_cum"] for k, v in s2["per_layer"].items()},
        "pca_var_cum_matches_published_L14": s2["pca_var_cum_match"],
        "gram_cache_alignment_vs_reference_impl": s2["gram_cache_alignment"],
    }

    # ---- item 4 ----
    R["item4_injection_amplitude"] = {
        "code_evidence": s3["code_evidence"],
        "norms_full_69155_steps": s3["norms_full_69155_steps"],
        "layer_profiles_json_mean_norm": s3["layer_profiles_json_mean_norm"],
        "variants": s3["variants"],
        "headline": s3["headline"],
        "half_s2_at_relative_amplitude_0p236": 0.5 * 0.236 ** 2,
        "M13_over_M14_compensation_factor":
            s3["variants"]["layer_profiles_json_20010"]["mean_norm_L13"]
            / s3["variants"]["layer_profiles_json_20010"]["mean_norm_L14"],
        "compensation_note": "把定标层从 14 改成 13，或在注入处乘 M13/M14，"
                             "即可解析地把标称 s 对齐回实际相对幅度，无需重跑实验。",
        "same_layer_inflation": {
            "note": "上游写「比标称暗示的 2.03%–2.25% 高约 24%」，那是拿 L20 的"
                    "2.236% 与 L13 注入点的 2.78% 跨层比。同层比应当是：",
            "per_token_avg_cost_at_injection_L13":
                s3["variants"]["layer_profiles_json_20010"][
                    "geometric_cost_per_token_avg_at_injection_point"],
            "per_token_avg_cost_at_L14":
                s3["variants"]["layer_profiles_json_20010"][
                    "geometric_cost_per_token_avg_at_L14"],
            "ratio_injection_over_L14":
                s3["variants"]["layer_profiles_json_20010"][
                    "geometric_cost_per_token_avg_at_injection_point"]
                / s3["variants"]["layer_profiles_json_20010"][
                    "geometric_cost_per_token_avg_at_L14"],
            "plain_half_s2_ratio":
                (0.5 * (0.2 * s3["variants"]["layer_profiles_json_20010"][
                    "R_ratio_L14_over_L13"]) ** 2) / (0.5 * 0.2 ** 2),
        },
    }

    # ---- item 5 ----
    R["item5_controls"] = {
        "negative_400_random_directions": {
            "seed": s2["config"]["seed"], "n_random": s2["config"]["n_random"],
            "note": "零假设只含随机方向。统计量按折 × 随机方向展开 19200 个值。",
            "cells": s2["null_random_400"],
        },
        "positive_control_step_frac": {
            "why": "step_frac = t/(T−1) 是已发表的强阳性对照（0.61–0.65）。"
                   "测不出它就说明装置坏了，而不是发现。",
            "cells": s2["positive_control_step_frac"],
        },
    }

    # ---- item 6 ----
    R["item6_selfcheck"] = {
        "toy_selfcheck": s2["selfcheck_toy"],
        "layer_resolution_selfcheck": s2["selfcheck_layer_resolution"],
        "attention_mask_audit": s1["attention_mask_audit"],
        "layer_convention_audit": {
            k: v for k, v in s1["layer_convention_audit"].items()
            if k != "mean_norm_per_layer"},
        "baseline_reproduction": s2["baseline_reproduction"],
        "deviations_from_published": s2["deviations"],
    }
    R["elapsed_sec"] = round(time.time() - t0, 1)
    (OUT / "layerside2.json").write_text(json.dumps(R, ensure_ascii=False, indent=1))
    print("wrote", OUT / "layerside2.json")
    print("item1 all_reproduced:", R["item1_baseline_reproduction"]["all_reproduced"])
    print("item6 baseline all_pass:",
          R["item6_selfcheck"]["baseline_reproduction"]["checks"]["all_pass"],
          "deviations:", len(R["item6_selfcheck"]["deviations_from_published"]))
    print("convention identity max err:",
          R["conventions"]["identity_max_abs_err"])


if __name__ == "__main__":
    main()
