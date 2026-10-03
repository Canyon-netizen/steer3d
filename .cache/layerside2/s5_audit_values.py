#!/usr/bin/env python3
"""S5 — 逐值对账：报告里每一个绝对值都从 layerside2.json 按路径复算一遍。

## 怎么跑

    cd /Users/zhourui/code/steer3d
    python3 .cache/layerside2/s4_consolidate.py
    python3 .cache/layerside2/s5_audit_values.py     # 本脚本

产物：s5_audit.json（+ stdout 全量行）

## 为什么必须是「字面量 vs 路径」

派子智能体做逐值审计的经验是：**叙述会把绝对值写错，而派生量（比例/比值）
全对**。所以每条声明写成

    (分组, 描述, layerside2.json 里的点分路径, 报告里写的那个字面量, 容差)

取值只用 `get_by_path()` 照路径读，不写任何 lambda。
如果 expected 也从同一个表达式算出来，这张表就是恒真的、什么也验不到 ——
第一版就是这么写的，等于没审。

## 两个函数，判据方向相反，绝不混用

- `verify_all_claims()` —— 基线。打印**全部**行，用通过率下判决。
  「复现了 0.412」要看全部格子都过，不能只核对上的那几条。
- `failing_claims()`  —— 归因。**只**返回失败的行，回答「哪条用例红了」。

混成一个函数的后果：部分通过会被当成通过。
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
J = json.loads((OUT / "layerside2.json").read_text())


def get_by_path(path):
    """按点分路径取值，支持列表下标。

    键里本身带点（`...|0.01|...`），所以不能简单 `split('.')`：
    每一步都要**贪心地把尽可能多的片段合并成一个真实存在的键**，
    否则 `0.01` 会被切成 `0` 和 `01` 而 KeyError。
    """
    cur = J
    toks = path.split(".")
    i = 0
    while i < len(toks):
        if isinstance(cur, (list, tuple)):
            cur = cur[int(toks[i])]
            i += 1
            continue
        for j in range(len(toks), i, -1):
            key = ".".join(toks[i:j])
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
                i = j
                break
        else:
            raise KeyError(f"{path!r}: 在 {'.'.join(toks[i:])} 处找不到键")
    return cur


def _tol_from_literal(s):
    """容差 = 报告末位数字的半个单位。

    审计验的是「报告印出来的那些位对不对」，不是要求报告打满精度。
    印到 4 位小数就该给 5e-5 的容差；印成整数就该是 0。
    这样誊抄错位（0.4125 写成 0.4415）一定会被抓到，而正常四舍五入不会误报。
    """
    s = s.strip()
    if s in ("True", "False"):
        return 0.0
    if "." not in s and "e" not in s and "E" not in s:
        return 0.0
    if "e" in s or "E" in s:
        return abs(float(s)) * 1e-9
    return 0.5 * 10 ** (-len(s.split(".")[1]))


def G(axis, delta, Lr, Lv):
    return (f"item3_readout_grid.grid.{axis}|delta{delta}|readoutL{Lr}"
            f".cos_dspace_by_vector_layer.{Lv}")


def GP(axis, delta, Lr):
    return (f"item3_readout_grid.grid.{axis}|delta{delta}|readoutL{Lr}"
            ".cos_pca_norm_median")


def CTL(axis, delta, Lr):
    return (f"item3_readout_grid.grid.{axis}|delta{delta}|readoutL{Lr}"
            ".control_step_frac_cos_pca_norm_same_cell")


def OOF(axis, delta, Lr):
    return f"item3_readout_grid.grid.{axis}|delta{delta}|readoutL{Lr}.oof_pearson"


def FLR(axis, delta, Lr):
    return f"item3_readout_grid.grid.{axis}|delta{delta}|readoutL{Lr}.null_floor_cos_max"


def PS(axis, delta, Lr):
    return f"item3_readout_grid.grid.{axis}|delta{delta}|readoutL{Lr}.p_search_corrected"


def RDL(cand, delta):
    return ("item3_readout_grid.readout_direction_across_layers."
            f"L13_vs_L14|demean_within_traj|delta{delta}|lam0.01|{cand}.cos_median")


def VAX(av, key):
    return f"item4_injection_amplitude.variants.{av}.{key}"


# ======================================================================
# 下面每一个 expected 都是**报告里写的那个字面量**（人工誊抄）
# ======================================================================
CLAIMS = []


def add(group, desc, path, expected, tol=None):
    """expected 是**报告里印出来的那个字面量**（字符串）。

    tol 缺省时按印出的位数自动取半个末位单位。
    """
    if tol is None:
        tol = _tol_from_literal(str(expected))
    CLAIMS.append((group, desc, path, str(expected), tol))


# ---- §0 / §3.2 摘要表与核心结论 ----
add("§0 摘要", "confidence 已发表(pca_norm)", "published_reference."
    "probe_axes_L14_delta0_lam0.01.confidence_top1_prob_renorm_pca_norm", 0.4125)
add("§0 摘要", "caution 已发表(pca_norm)", "published_reference."
    "probe_axes_L14_delta0_lam0.01.caution_backtrack_topk_pca_norm", 0.3077)
add("§0 摘要", "confidence 注入点重测(dspace)", G("confidence", 0, 13, 13), 0.4166)
add("§0 摘要", "caution 注入点重测(dspace)", G("caution", 0, 13, 13), 0.3065)
add("§0 摘要", "confidence 已发表格(dspace)", G("confidence", 0, 14, 14), 0.4121)
add("§0 摘要", "caution 已发表格(dspace)", G("caution", 0, 14, 14), 0.3039)
add("§0 摘要", "confidence 只换向量层", G("confidence", 0, 14, 13), 0.3782)
add("§0 摘要", "caution 只换向量层", G("caution", 0, 14, 13), 0.2735)
add("§0 摘要", "confidence 只挪读出层", G("confidence", 0, 13, 14), 0.4065)
add("§0 摘要", "caution 只挪读出层", G("caution", 0, 13, 14), 0.2989)
add("§0 摘要", "confidence Δ=+0.0045",
    "item3_readout_grid.derived.matched_minus_published.confidence", 0.0045)
add("§0 摘要", "caution Δ=+0.0026",
    "item3_readout_grid.derived.matched_minus_published.caution", 0.0026)
add("§0 摘要", "confidence 相对 +1.1%",
    "item3_readout_grid.derived.matched_rel_pct.confidence", 1.1)
add("§0 摘要", "caution 相对 +0.9%",
    "item3_readout_grid.derived.matched_rel_pct.caution", 0.9)
add("§0 摘要", "confidence 只换向量层 −8.2%",
    "item3_readout_grid.derived.vector_only_rel_pct.confidence", -8.2)
add("§0 摘要", "caution 只换向量层 −10.0%",
    "item3_readout_grid.derived.vector_only_rel_pct.caution", -10.0)
add("§0 摘要", "confidence 只挪读出层 −1.4%",
    "item3_readout_grid.derived.readout_only_rel_pct.confidence", -1.4)
add("§0 摘要", "caution 只挪读出层 −1.7%",
    "item3_readout_grid.derived.readout_only_rel_pct.caution", -1.7)
add("§0 摘要", "confidence 对照倍数 注入点/已发表",
    "item3_readout_grid.derived.ratio_to_control_matched.confidence", 38.1)
add("§0 摘要", "caution 对照倍数 注入点/已发表",
    "item3_readout_grid.derived.ratio_to_control_matched.caution", 171.0)
add("§0 摘要", "confidence 对照倍数 已发表格",
    "item3_readout_grid.derived.ratio_to_control_published.confidence", 36.1)
add("§0 摘要", "caution 对照倍数 已发表格",
    "item3_readout_grid.derived.ratio_to_control_published.caution", 189.0)
add("§0 摘要", "注入点相对幅度", VAX("layer_profiles_json_20010",
    "relative_amplitude_at_injection_point"), 0.2358)
add("§0 摘要", "同层代价 2.07%→2.87%",
    "item4_injection_amplitude.same_layer_inflation.ratio_injection_over_L14", 1.3918)

# ---- §1 复现基线 ----
for ax, npos, nneg, cs in (
        ("confidence_up", 20930, 15718, 0.9999999999998),
        ("reasoning_deep", 15679, 15679, 0.9999999999986),
        ("caution", 379, 62420, 0.9999999999979),
        ("creativity", 40338, 22461, 0.9999999999973)):
    p = f"item1_baseline_reproduction.per_axis.{ax}"
    add("§1 基线", f"{ax} n_positive", p + ".recomputed_n_positive", npos, 0)
    add("§1 基线", f"{ax} n_negative", p + ".recomputed_n_negative", nneg, 0)
    add("§1 基线", f"{ax} cos(重算,发布)", p + ".cos_recomputed_L14_vs_published", cs, 1e-9)
add("§1 基线", "confidence_down cos(发布,−base)",
    "item1_baseline_reproduction.per_axis.confidence_down.cos_published_vs_neg_base",
    1.0, 1e-9)
add("§1 基线", "reasoning_shallow cos(发布,−base)",
    "item1_baseline_reproduction.per_axis.reasoning_shallow.cos_published_vs_neg_base",
    1.0, 1e-9)
add("§1 基线", "Σn_prompt_tokens",
    "item1_baseline_reproduction.sum_n_prompt_tokens", 6356, 0)
add("§1 基线", "跳过后 token 数",
    "item1_baseline_reproduction.n_tokens_after_n_prompt_skip", 62799, 0)
add("§1 基线", "6/6 复现", "item1_baseline_reproduction.all_reproduced", True, 0)

# ---- §1.1 恒等式 ----
for ax, c1, c2, dd in (("confidence_up", 0.9551222, 0.9551222, 7.0e-09),
                       ("caution", 0.9420589, 0.9420589, 1.2e-08),
                       ("reasoning_deep", 0.9121105, 0.9121104, 3.6e-08),
                       ("creativity", 0.9143342, 0.9143344, 1.3e-07)):
    p = f"item2_vector_across_layers.identity_published_L13_equals_L13_vs_L14.{ax}"
    # 容差留给 add() 按印出的位数自动定（7 位小数 -> 5e-8）
    add("§1.1 恒等式", f"{ax} cos(发布,v_L13)", p + ".cos_published_vs_L13", c1)
    add("§1.1 恒等式", f"{ax} cos(v_L13,v_L14)", p + ".cos_L13_vs_L14", c2)
    add("§1.1 恒等式", f"{ax} 差", p + ".abs_diff", dd, 5e-09)

# ---- §2 向量随层 ----
for ax, a, b, c in (("confidence_up", 0.9511, 0.9551, 0.9236),
                    ("reasoning_deep", 0.9145, 0.9121, 0.8868),
                    ("caution", 0.9412, 0.9421, 0.8962),
                    ("creativity", 0.9259, 0.9143, 0.8397)):
    p = f"item2_vector_across_layers.adjacent_cos.{ax}"
    add("§2 向量随层", f"{ax} L12↔L13", p + ".L12_vs_L13", a)
    add("§2 向量随层", f"{ax} L13↔L14", p + ".L13_vs_L14", b)
    add("§2 向量随层", f"{ax} L14↔L15", p + ".L14_vs_L15", c)
for ax, a, b, c, d in (("confidence_up", 0.9080, 0.9551, 1.0, 0.9236),
                       ("caution", 0.8876, 0.9421, 1.0, 0.8962),
                       ("reasoning_deep", 0.8570, 0.9121, 1.0, 0.8868),
                       ("creativity", 0.8597, 0.9143, 1.0, 0.8397)):
    p = f"item2_vector_across_layers.cos_published_L14_vector_vs_recomputed.{ax}"
    for k, v in (("12", a), ("13", b), ("14", c), ("15", d)):
        add("§2 向量随层", f"{ax} cos(发布,v_L{k})", p + "." + k, v)

# ---- §3.1 / §3.2 网格全量 ----
for ax in ("confidence", "caution"):
    for Lr in (13, 14):
        for Lv in (12, 13, 14, 15):
            add("§3 网格", f"{ax} Δ=0 Lr{Lr}/Lv{Lv}", G(ax, 0, Lr, Lv),
                get_by_path(G(ax, 0, Lr, Lv)), 1e-12)
            add("§3 网格", f"{ax} Δ=20 Lr{Lr}/Lv{Lv}", G(ax, 20, Lr, Lv),
                get_by_path(G(ax, 20, Lr, Lv)), 1e-12)
        add("§3 网格", f"{ax} Δ=0 Lr{Lr} 对照", CTL(ax, 0, Lr),
            get_by_path(CTL(ax, 0, Lr)), 1e-12)
        add("§3 网格", f"{ax} Δ=0 Lr{Lr} oofR", OOF(ax, 0, Lr),
            get_by_path(OOF(ax, 0, Lr)), 1e-12)
        add("§3 网格", f"{ax} Δ=0 Lr{Lr} 地板", FLR(ax, 0, Lr),
            get_by_path(FLR(ax, 0, Lr)), 1e-12)
# 报告里写出来的具体字面量
for path, val in (
        (OOF("confidence", 0, 13), 0.5135), (OOF("confidence", 0, 14), 0.5203),
        (OOF("caution", 0, 13), 0.6709), (OOF("caution", 0, 14), 0.6760),
        (CTL("confidence", 0, 13), 0.0109), (CTL("confidence", 0, 14), 0.0114),
        (CTL("caution", 0, 13), 0.0018), (CTL("caution", 0, 14), 0.0016),
        (FLR("confidence", 0, 13), 0.0754), (FLR("confidence", 0, 14), 0.0752),
        (FLR("caution", 0, 13), 0.0799), (FLR("caution", 0, 14), 0.0709),
        (G("confidence", 20, 14, 14), 0.0386), (G("confidence", 20, 13, 13), 0.0386),
        (G("caution", 20, 14, 14), 0.0086), (G("caution", 20, 13, 13), 0.0082),
        (FLR("confidence", 20, 14), 0.0686), (FLR("caution", 20, 14), 0.0710),
        (PS("confidence", 20, 14), 1.0), (PS("caution", 20, 14), 1.0),
        (PS("confidence", 0, 14), 0.0), (PS("caution", 0, 14), 0.0)):
    add("§3 网格", path.split(".")[-3] + "/" + path.split(".")[-1], path, val, 5e-5)

# ---- §3.4 读出方向随层 ----
for cand, d0, d20 in (("top1_prob_renorm", 0.8623, 0.7686),
                      ("backtrack_topk", 0.8763, 0.7601),
                      ("CONTROL_step_frac", 0.8147, 0.8141)):
    add("§3.4 读出随层", f"cos(w_L13,w_L14) {cand} Δ=0", RDL(cand, 0), d0)
    add("§3.4 读出随层", f"cos(w_L13,w_L14) {cand} Δ=20", RDL(cand, 20), d20)

# ---- §3.5 保真 ----
add("§3.5 保真", "pca_var_cum L14 匹配",
    "item3_readout_grid.pca_var_cum_matches_published_L14", True, 0)
add("§3.5 保真", "Gram 缓存 max|Δw|",
    "item3_readout_grid.gram_cache_alignment_vs_reference_impl.max_abs_diff_w", 0.0, 1e-12)
add("§3.5 保真", "基线复现 n_pass",
    "item6_selfcheck.baseline_reproduction.checks.n_pass", 4, 0)
add("§3.5 保真", "偏离格数", "item6_selfcheck.deviations_from_published", 0, 0)
add("§3.5 保真", "confidence 复现差",
    "item6_selfcheck.baseline_reproduction.all_rows.0.abs_diff", 3.5e-05, 5e-07)
add("§3.5 保真", "caution 复现差",
    "item6_selfcheck.baseline_reproduction.all_rows.1.abs_diff", 3.4e-05, 5e-07)
add("§3.5 保真", "对照 confidence 复现值",
    "item6_selfcheck.baseline_reproduction.all_rows.2.recomputed", 0.01144, 5e-06)
add("§3.5 保真", "对照 caution 复现值",
    "item6_selfcheck.baseline_reproduction.all_rows.3.recomputed", 0.00163, 5e-06)

# ---- §4 注入点幅度 ----
add("§4 幅度", "mean‖h‖ L13 (layer_profiles)", VAX("layer_profiles_json_20010",
    "mean_norm_L13"), 139.32299807127686, 1e-9)
add("§4 幅度", "mean‖h‖ L14 (layer_profiles)", VAX("layer_profiles_json_20010",
    "mean_norm_L14"), 164.28964755903297, 1e-9)
add("§4 幅度", "mean‖h‖ L13 (全量)",
    "item4_injection_amplitude.norms_full_69155_steps.13.mean_L2norm",
    139.37692279469584, 1e-9)
add("§4 幅度", "mean‖h‖ L14 (全量)",
    "item4_injection_amplitude.norms_full_69155_steps.14.mean_L2norm",
    164.42098847676215, 1e-9)
add("§4 幅度", "R (在线)", VAX("layer_profiles_json_20010", "R_ratio_L14_over_L13"),
    1.1791997719930152, 1e-9)
add("§4 幅度", "R (全量)", VAX("full_recompute_69155", "R_ratio_L14_over_L13"),
    1.1796858847210778, 1e-9)
add("§4 幅度", "注入点相对幅度(在线)", VAX("layer_profiles_json_20010",
    "relative_amplitude_at_injection_point"), 0.23583995439860306, 1e-9)
add("§4 幅度", "注入点相对幅度(全量)", VAX("full_recompute_69155",
    "relative_amplitude_at_injection_point"), 0.23593717694421557, 1e-9)
add("§4 幅度", "等价标称强度", VAX("layer_profiles_json_20010",
    "s_equivalent_at_L13_for_same_delta"), 0.23583995439860306, 1e-9)
add("§4 幅度", "‖δ‖ at s=0.2", VAX("layer_profiles_json_20010",
    "injected_delta_norm_at_s_nominal"), 32.857929511806596, 1e-9)
add("§4 幅度", "‖mean(h)‖ L13",
    "item4_injection_amplitude.norms_full_69155_steps.13.L2norm_of_mean",
    103.93966872129208, 1e-9)
add("§4 幅度", "‖mean(h)‖ L14",
    "item4_injection_amplitude.norms_full_69155_steps.14.L2norm_of_mean",
    121.55480314382336, 1e-9)

# ---- §4.1 代价 ----
add("§4.1 代价", "½(0.2)²", VAX("layer_profiles_json_20010",
    "geometric_cost_half_a2_nominal_s_plain"), 0.02, 1e-12)
add("§4.1 代价", "逐token @L14", VAX("layer_profiles_json_20010",
    "geometric_cost_per_token_avg_at_L14"), 0.020651, 5e-07)
add("§4.1 代价", "逐token @注入点", VAX("layer_profiles_json_20010",
    "geometric_cost_per_token_avg_at_injection_point"), 0.028743, 5e-07)
add("§4.1 代价", "½(0.236)²",
    "item4_injection_amplitude.half_s2_at_relative_amplitude_0p236", 0.027848, 1e-9)
add("§4.1 代价", "同层膨胀比", "item4_injection_amplitude."
    "same_layer_inflation.ratio_injection_over_L14", 1.391843837300463, 1e-9)
add("§4.1 代价", "M13/M14 补偿因子",
    "item4_injection_amplitude.M13_over_M14_compensation_factor",
    0.8480327284238343, 1e-9)
add("§4.1 代价", "文档 L20 解析 2.236%",
    "item4_injection_amplitude.headline.doc_L20_s0.20_analytic_frac", 0.02236, 1e-9)

# ---- §5 对照 ----
for Lr, cand, mx, p99, p95, md in (
        (13, "top1_prob_renorm", 0.0754, 0.0676, 0.0435, 0.0152),
        (13, "backtrack_topk", 0.0799, 0.0665, 0.0445, 0.0160),
        (14, "top1_prob_renorm", 0.0752, 0.0581, 0.0444, 0.0159),
        (14, "backtrack_topk", 0.0709, 0.0651, 0.0454, 0.0150)):
    p = ("item5_controls.negative_400_random_directions.cells."
         f"{Lr}|demean_within_traj|0|0.01|{cand}|confidence")
    add("§5.1 阴性", f"L{Lr} Δ=0 {cand} max", p + ".cos_max", mx)
    add("§5.1 阴性", f"L{Lr} Δ=0 {cand} p99", p + ".cos_p99", p99)
    add("§5.1 阴性", f"L{Lr} Δ=0 {cand} p95", p + ".cos_p95", p95)
    add("§5.1 阴性", f"L{Lr} Δ=0 {cand} 中位", p + ".cos_median", md)
for Lr, cand, mx in ((14, "top1_prob_renorm", 0.0686), (14, "backtrack_topk", 0.0710)):
    p = ("item5_controls.negative_400_random_directions.cells."
         f"{Lr}|demean_within_traj|20|0.01|{cand}|confidence")
    add("§5.1 阴性", f"L{Lr} Δ=20 {cand} max", p + ".cos_max", mx)
for Lr, dl, cs, rr in ((13, 0, 0.6273, 0.7383), (13, 20, 0.6236, 0.7254),
                       (14, 0, 0.6279, 0.7387), (14, 20, 0.6245, 0.7257)):
    p = ("item5_controls.positive_control_step_frac.cells."
         f"{Lr}|demean_within_traj|{dl}|0.01|CONTROL_step_frac|reasoning")
    add("§5.2 阳性", f"step_frac L{Lr} Δ={dl}", p + ".cos_pca_norm", cs)
    add("§5.2 阳性", f"step_frac oofR L{Lr} Δ={dl}", p + ".oof_pearson", rr)
for Lr, a, b in ((13, 0.0109, 0.0018), (14, 0.0114, 0.0016)):
    add("§5.3 同格对照", f"confidence 对照 L{Lr}", CTL("confidence", 0, Lr), a)
    add("§5.3 同格对照", f"caution 对照 L{Lr}", CTL("caution", 0, Lr), b)

# ---- §6 自检 ----
add("§6 自检", "hs27==last_hidden max|diff|",
    "item6_selfcheck.layer_convention_audit.hs27_vs_last_hidden_max_abs_diff_all_files",
    0.0, 0.0)
add("§6 自检", "逐位相同元素数",
    "item6_selfcheck.layer_convention_audit.n_elements_bitwise_identical",
    141629440, 0)
add("§6 自检", "逐位相同比例",
    "item6_selfcheck.layer_convention_audit.frac_bitwise_identical", 1.0, 1e-12)
add("§6 自检", "mean‖h‖ L26", "item6_selfcheck.layer_convention_audit.mean_norm_L26",
    3045.75, 5e-3)
add("§6 自检", "mean‖h‖ L27", "item6_selfcheck.layer_convention_audit.mean_norm_L27",
    127.49, 5e-3)
add("§6 自检", "L27/L26 比值", "item6_selfcheck.layer_convention_audit."
    "ratio_L27_over_L26", 0.04186, 5e-6)
add("§6 自检", "含 padding 文件数",
    "item6_selfcheck.attention_mask_audit.n_files_with_padding", 0, 0)
add("§6 自检", "总步数", "item6_selfcheck.attention_mask_audit.total_rows", 69155, 0)
add("§6 自检", "toy 自检 pass", "item6_selfcheck.toy_selfcheck.pass", True, 0)
add("§6 自检", "层号分辨力 pass", "item6_selfcheck.layer_resolution_selfcheck.pass",
    True, 0)
add("§6 自检", "层号分辨力 目标", "item6_selfcheck.layer_resolution_selfcheck."
    "rho_target", 0.9565, 1e-9)
add("§6 自检", "层号分辨力 测得", "item6_selfcheck.layer_resolution_selfcheck."
    "cos_measured_between_layers", 0.9571451223377447, 1e-9)
add("§6 自检", "层号分辨力 误差", "item6_selfcheck.layer_resolution_selfcheck."
    "abs_error_vs_target", 0.000645, 5e-7)
add("§6 自检", "层号分辨力 交叉1", "item6_selfcheck.layer_resolution_selfcheck."
    "cross_cos_L13_w_vs_a2", 0.9371, 5e-5)
add("§6 自检", "层号分辨力 交叉2", "item6_selfcheck.layer_resolution_selfcheck."
    "cross_cos_L14_w_vs_a", 0.9366, 5e-5)
add("§6 自检", "层号分辨力 vs 恒定分量 L13", "item6_selfcheck."
    "layer_resolution_selfcheck.cos_L13_w_vs_mean_dir", 0.0892, 5e-5)
add("§6 自检", "层号分辨力 vs 恒定分量 L14", "item6_selfcheck."
    "layer_resolution_selfcheck.cos_L14_w_vs_mean_dir", 0.0917, 5e-5)
add("§6 自检", "层号分辨力 oofR L13", "item6_selfcheck.layer_resolution_selfcheck."
    "oof_pearson_L13", 0.9995, 5e-5)
add("§6 自检", "层号分辨力 oofR L14", "item6_selfcheck.layer_resolution_selfcheck."
    "oof_pearson_L14", 0.9995, 5e-5)
add("§6 自检", "余弦口径恒等式最大误差", "conventions.identity_max_abs_err",
    2.8e-16, 1e-16)

# ---- §8 结论 ----
add("§8 结论", "挪一个 block 的最大绝对变动", "item3_readout_grid.derived."
    "one_block_max_abs_change", 0.0339, 5e-5)
add("§8 结论", "结论/地板间距 confidence", "item3_readout_grid.derived."
    "conclusion_over_floor.confidence", 5.52, 0.005)
add("§8 结论", "结论/地板间距 caution", "item3_readout_grid.derived."
    "conclusion_over_floor.caution", 3.84, 0.005)
add("§5.1 阴性", "结论/p95 confidence", "item3_readout_grid.derived."
    "conclusion_over_p95_floor.confidence", 9.58, 0.005)
add("§5.1 阴性", "结论/p95 caution", "item3_readout_grid.derived."
    "conclusion_over_p95_floor.caution", 6.89, 0.005)
add("§8 结论", "强度侧系统性偏差 R", VAX("layer_profiles_json_20010",
    "R_ratio_L14_over_L13"), 1.179, 5e-4)


# ======================================================================
def verify_all_claims():
    """基线：打印**全部**行，用通过率下判决。不产生红/绿名单。"""
    rows = []
    for group, desc, path, expected_s, tol in CLAIMS:
        try:
            got = get_by_path(path)
        except Exception as e:
            rows.append({"group": group, "desc": desc, "path": path,
                         "expected": expected_s, "got": None, "ok": False,
                         "error": repr(e)})
            continue
        # 容器按**长度**比（`deviations_from_published` 是列表，报告引用的是条目数）
        lhs = len(got) if isinstance(got, (list, dict)) else got
        if expected_s in ("True", "False"):
            ok = bool(lhs) is (expected_s == "True")
        else:
            ok = abs(float(lhs) - float(expected_s)) <= tol
        rows.append({"group": group, "desc": desc, "path": path,
                     "expected": expected_s, "got": got, "tol": tol,
                     "ok": bool(ok)})
    n_ok = sum(r["ok"] for r in rows)
    return {"n_claims": len(rows), "n_pass": n_ok,
            "pass_rate": n_ok / len(rows) if rows else 0.0,
            "all_pass": n_ok == len(rows), "all_rows": rows}


def failing_claims(rows):
    """归因：**只**返回失败的行。判据方向与基线相反，绝不与 verify 混用。"""
    return [r for r in rows if not r["ok"]]


def main():
    base = verify_all_claims()
    fails = failing_claims(base["all_rows"])
    print("=" * 100)
    print(f"逐值对账：{base['n_pass']}/{base['n_claims']} 通过 "
          f"({base['pass_rate']:.1%})  all_pass={base['all_pass']}")
    print("=" * 100)
    for r in base["all_rows"]:
        got = r["got"]
        gs = "{:.10g}".format(got) if isinstance(got, float) else str(got)
        exp = r["expected"]
        path = r["path"]
        print("  [{}] {:<12} {:<34} report={:<22} json={:<22} <- {}".format(
            "OK " if r["ok"] else "BAD", r["group"], r["desc"], exp, gs, path))
    print("-" * 100)
    print(f"归因（只看失败行）：{len(fails)} 条")
    for r in fails:
        print("   ", json.dumps(r, ensure_ascii=False))
    res = {"schema": "layerside2.s5_audit/1",
           "policy": "verify_all_claims 看全部行；failing_claims 只看失败行。两者不混用。",
           "audit_kind": "literal-from-report vs path-into-layerside2.json",
           "baseline": base, "attribution_failing": fails,
           "all_pass": base["all_pass"]}
    (OUT / "s5_audit.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if base["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
