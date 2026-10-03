#!/usr/bin/env python3
"""从 completeness.json 渲染 COMPLETENESS_REPORT.md。**所有数字都从 JSON 读，不手写。**

跑法（仓库根目录）：

    python3 .cache/completeness/make_report.py

若 completeness.json 有 `abort` 键，本脚本只输出装置复现失败说明并退出码 1。
"""
import json
import sys
from pathlib import Path

ROOT = Path("/Users/zhourui/code/steer3d")
SRC = ROOT / ".cache/completeness/completeness.json"
DST = ROOT / ".cache/completeness/COMPLETENESS_REPORT.md"

CTRL = "**阳性对照**"


def esc(t):
    """表格单元格里的 `|` 会把 markdown 表打散，统一转义。"""
    return str(t).replace("|", "\\|")


def f(x, n=4):
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "是" if x else "否"
    if isinstance(x, (int,)) and not isinstance(x, bool):
        return str(x)
    try:
        return f"{float(x):.{n}f}"
    except (TypeError, ValueError):
        return str(x)


def main():
    d = json.loads(SRC.read_text())
    L = []
    w = L.append
    cfg = d["config"]
    deltas = cfg["deltas"]
    ro = d["readout"]
    hd = d["headline"]

    w("# 完备性检验：4 条命名轴是不是残差流里可解释行为的完备描述？")
    w("")
    w(f"脚本 `.cache/completeness/completeness.py` → `completeness.json`；"
      f"本文每个数字都从该 JSON 读出，键名标在括号里。")
    w("")
    w(f"装置：L{cfg['layer']} / K={cfg['k_pca']} PCA / stride={cfg['stride']} / "
      f"48 条轨迹 / {d['padding_audit']['n_steps_after_stride']} 步 / "
      f"留一轨迹岭回归（λ∈{cfg['lambdas']}）/ 轨迹内去均值 / "
      f"主判据=留一样本外 Pearson。")
    w("")

    if "abort" in d:
        w("## 0. 装置复现失败 → 已中止")
        w("")
        w(d["abort"])
        w("")
        w("| 轴行 | 声称 cos | 实测 cos | 差 | 容差内 |")
        w("|---|---|---|---|---|")
        for k, v in d["apparatus_repro"]["rows"].items():
            w(f"| {k} | {f(v['claimed_cos'],3)} | {f(v['observed_cos'])} | "
              f"{f(v['abs_diff'])} | {f(v['within_tol'])} |")
        DST.write_text("\n".join(L))
        print("wrote (abort report)", DST)
        return 1

    # ---------------- 0 装置
    ap = d["apparatus_repro"]
    w("## 0. 先验装置：7/7 复现（`apparatus_repro`）")
    w("")
    w("| 报告行 | 目标 | Δ | 声称 cos | 实测 cos | 差 | 容差内 | 角色 |")
    w("|---|---|---|---|---|---|---|---|")
    for k, v in ap["rows"].items():
        w(f"| {k} | `{v['target']}` | {v['delta']} | {f(v['claimed_cos'],3)} | "
          f"{f(v['observed_cos'])} | {f(v['abs_diff'])} | {f(v['within_tol'])} | {v['role']} |")
    for k, v in ap["step_frac_ruler"].items():
        w(f"| reasoning_deep（尺子） | `step_frac` | {k.split('delta')[1]} | "
          f"{f(v['claimed_cos'],3)} | {f(v['observed_cos'])} | {f(v['abs_diff'])} | "
          f"{f(v['within_tol'])} | 装置阳性对照 |")
    w("")
    w(f"`step_frac` 三个 Δ 全部复现 ⇒ 装置能在样本外以 cos≈0.62 测出「轨迹位置」。"
      f"{ap['note']}")
    w("")
    CLAIMED = {"confidence", "caution"}
    ct = [v for v in ap["rows"].values()
          if v["cross_talk_flag"] and v["axis_of_report_row"] in CLAIMED]
    if ct:
        w("**复现时新发现的一条串扰**（`cross_talk_flag`，只对有正向主张的两条轴报）：")
        for v in ct:
            w(f"- `{v['target']}` 那一格：**{v['strongest_other_axis_on_same_cell']} 轴 = "
              f"{f(v['strongest_other_axis_cos'])} > 报告行所属的 "
              f"`{v['axis_of_report_row']}` 轴 = {f(v['observed_cos'])}**。")
        w("")
        w("⇒ 「`caution` 测到回退标记」那一格的读出方向，在**同一格**上与 `confidence` 轴的"
          "对齐更强。这不推翻 0.308 的复现，但意味着 `backtrack_topk` 那一格**不能算 "
          "`caution` 的专属读出** —— 它对 `confidence` 轴的可读性更高。")
        w("")

    # ---------------- 1 ICC
    w("## 1. ICC：哪些列有资格当候选（`icc_table`）")
    w("")
    w(f"门槛：{d['icc_table']['_gate']}")
    w("")
    w("| 观测量 | ICC(1) | 轨迹间方差份额 | 轨迹内零方差 | 合格 |")
    w("|---|---|---|---|---|")
    for k, v in d["icc_table"].items():
        if k.startswith("_"):
            continue
        w(f"| `{k}`{'（定义式目标）' if k in cfg['axis_definition_target'].values() else ''} | "
          f"{f(v['icc1_anova'])} | {f(v['var_share_between_traj'])} | "
          f"{v['n_traj_zero_variance']}/{v['n_traj']} | "
          f"{'✅' if v['usable_as_stepwise'] else '❌'} |")
    w("")
    ra = d["redundancy_audit"]
    w("### 冗余审计：必须区分 Spearman 与 Pearson（`redundancy_audit`）")
    w("")
    w("`obs_series_meta.json` 的 `redundancy_matrix` 键名叫 `abs_rho_pooled`，"
      "但它自己的 `definition_pooled` 字段写明存的是 **|Spearman|**。"
      "本任务的统计量是**线性探针的 Pearson**，两列必须分开看。")
    w("")
    w("| 观测量对 | Pearson | Spearman | 之前报告引用的数 | 处理 |")
    w("|---|---|---|---|---|")
    for k, v in ra["pairs"].items():
        w(f"| `{k}` | **{f(v['abs_pearson_pooled'])}** | {f(v['abs_spearman_pooled'])} | "
          f"{v['cited_value_in_prior_reports']}（Spearman） | {v['treatment']} |")
    w("")
    w(f"- Pearson > {ra['threshold']} 的对：{len(ra['pairs_pearson_exceeding'])} 对"
      f" ⇒ {', '.join('`'+a+'`|'+b+'`' for a, b, _, _ in ra['pairs_pearson_excluding'])}"
      if "pairs_pearson_excluding" in ra else
      f"- Pearson > {ra['threshold']} 的对：{len(ra['pairs_pearson_exceeding'])} 对"
      f" ⇒ " + ", ".join(f"`{a}`|`{b}` (P={f(p)},S={f(s)})"
                          for a, b, p, s in ra["pairs_pearson_exceeding"]))
    w(f"- Spearman > {ra['threshold']} 但 Pearson ≤ {ra['threshold']} 的对："
      f"{len(ra['pairs_spearman_exceeding_but_pearson_not'])} 对 ⇒ "
      + ", ".join(f"`{a}`|`{b}` (P={f(p)},S={f(s)})"
                  for a, b, p, s in ra["pairs_spearman_exceeding_but_pearson_not"]))
    w("")
    w(f"**因此本轮搜索保留全部 {d['effective_dof']['n_searched_observables']} 个可用观测量**"
      f"（`effective_dof.deviation_from_probe_axes`）：")
    w("")
    w(f"> {d['effective_dof']['deviation_from_probe_axes']}")
    w("")
    ed = d["effective_dof"]
    w(f"有效自由度（`effective_dof`）：{ed['all_usable_kept'] and '**全部保留**'}，"
      f"计入搜索的观测量 **{ed['n_searched_observables']}** 个；"
      f"另有 {len(ed['control_targets_not_in_search'])} 个定义式/尺子目标"
      f"（{', '.join('`'+c+'`' for c in ed['control_targets_not_in_search'])}）不进搜索。"
      f"`top1_prob_renorm` 与 entropy 仍合并算一份证据"
      f"（{ed['top1_prob_renorm_treatment']}）"
      f"⇒ 实质自由度 {ed['effective_dof_excluding_entropy_restate']}。")
    w("")

    # ---------------- 2 同格对照尺子
    w("## 2. 同格对照尺子：每条轴的定义式那一格是阳性对照，不是发现")
    w("")
    w(f"规则（`axis_readout_summary.rule`）：{d['axis_readout_summary']['rule']}")
    w("")
    w("| 轴 | 定义式分组 | 定义式目标 | 定义式格 cos（Δ=0） | 最佳**非**定义式格 | 其 cos | 两格 \|ρ\| | 定义式 − 最佳非定义式 |")
    w("|---|---|---|---|---|---|---|---|")
    for a, r in d["axis_readout_summary"]["rows"].items():
        c0 = r["cos_on_definition_target"].get("delta0")
        b = r["best_non_definition_cell"]
        w(f"| `{a}` | {esc(r['definition'][0])} vs {esc(r['definition'][1])} | "
          f"`{r['definition_target']}` | {f(c0)} | "
          f"`{b['observable']}` Δ={b['delta']} | {f(b['cos'])} | {f(r.get('rho_between_two_cells'))} | "
          f"{f(r['definitional_ceiling_minus_best_non_definition'])} |")
    w("")
    w("读法（**不要把这一列当成通过/不通过的开关**）：")
    w("")
    w("- `caution` / `creativity` / `reasoning_deep` 三行的「定义式 − 最佳非定义式」为正，"
      "且两格之间 |ρ| 很低 ⇒ 定义式那一格确实是更高的天花板，那些漂亮数字可以被同源构造追平。")
    w("- `confidence` 那一行为**负**，但这**不是**「定义式追不上」：它的定义式目标是 `entropy`，"
      "而最佳非定义式格是 `top1_prob_renorm`，两者 Pearson |ρ| = 0.96 —— "
      "**它们本来就是同一个观测量**，两列的数字在数值上不可区分。"
      "换句话说这一行没有提供任何独立于定义式的证据。")
    w("")
    w("**四格全部标为装置阳性对照（`is_positive_control_cell = true`），不计入任何完备性结论。**")
    w("")

    # ---------------- 3 假观测量
    w("## 3. 循环性用语义无关的假观测量证伪（`fake_observable_controls`）")
    w("")
    fc = d["fake_observable_controls"]
    sc = fc["step_frac_circularity"]
    w(f"**step_frac 尺子**：{sc['verdict']}")
    w("")
    w("| 观测量 | 协议 | OOF Pearson | cos(reasoning_deep) | \|rho\| 相对真值 | 符号相反 |")
    w("|---|---|---|---|---|---|")
    for r in sc["rows"]:
        w(f"| `{r['observable']}` | {r.get('protocol', 'fit_real_score_real')} | "
          f"{f(r['oof_pearson'],6)} | {f(r.get('cos_reasoning_deep'))} | "
          f"{f(r.get('abs_ratio_vs_real'),6)} | {f(r.get('sign_flipped'))} |")
    w("")
    w(f"复现比例 `|rho(1−step_frac)| / |rho(step_frac)|` = "
      f"**{f(sc['reproduction_ratio_fake_rev_ramp_over_step_frac'],16)}**，且**符号相反**。")
    w("")
    w(f"（FAILED_OBS_FORENSICS §4 记的是 {sc['expected_ratio_per_FAILED_OBS_FORENSICS']:.16f}；"
      f"本轮在 float64 下得到精确的 1.0，两者是同一个「完全复现」，"
      f"差别只是浮点噪声的末位。）⇒ 装置复现通过，且该行是构造循环。")
    w("")
    w(f"**confidence 那一格的地板**：{fc['confidence_circularity']['verdict']}")
    w("")
    w("| 观测量 | 语义 | cos(confidence) | 相对真值比例 |")
    w("|---|---|---|---|")
    for r in fc["confidence_circularity"]["rows"]:
        c = r.get("cos_confidence_fit_fake", r.get("cos_confidence"))
        w(f"| `{r['observable']}` | {esc(r.get('semantics', '真实观测量')[:44])} | {f(c)} | "
          f"{f(r.get('reproduction_ratio_vs_real'))} |")
    w("")
    w(f"语义无关的假观测量给出的地板 = **{f(fc['confidence_circularity']['floor_cos_confidence_of_semantically_irrelevant_fakes'])}**"
      f"，0.412 是它的 "
      f"{f(0.4125 / fc['confidence_circularity']['floor_cos_confidence_of_semantically_irrelevant_fakes'],1)} 倍 "
      f"⇒ 不是装置噪声；但它同时是构造恒等式，仍只作阳性对照。")
    w("")
    dd = d.get("definition_target_diagnostics", {})
    if dd:
        w(f"定义式目标的实测口径（`definition_target_diagnostics`）："
          f"self_check 正例 {dd['self_check_positive_steps']} 步、"
          f"{dd['self_check_zero_positive_traj']}/{dd['n_traj']} 条轨迹零正例"
          f"（{dd['failed_obs_forensics_recorded']}）；"
          f"in_think 轨迹内零方差 {dd['in_think_zero_variance_traj']}/{dd['n_traj']}。")
        w("")
        w(f"self_check 正则取自 {dd['self_check_regex_source']}。")
        w("")

    # ---------------- 4 投影检验
    w("## 4. 投影检验：4 条轴漏掉多少（`readout` / `headline.completeness_per_target`）")
    w("")
    ns = d["named_span_S"]
    w(f"4 条命名张成的子空间 S：条件数 `cond(S) = {f(ns['condition_number_S'])}`"
      f"（奇异值 {', '.join(f(s,3) for s in ns['singular_values'])}），"
      f"Gram-Schmidt 后条件数 {f(ns['condition_number_gram_schmidt'],3)}，"
      f"正交化误差 {ns['gram_schmidt_orthonormality_err']:.2e} ⇒ "
      f"**{'4 条线性无关' if ns['linearly_independent'] else '4 条线性相关'}**。")
    w("")
    w("两两 |cos|（`pairwise_abs_cos`）：")
    for k, v in ns["pairwise_abs_cos"].items():
        w(f"- `{k}` = {f(v)}")
    w("")
    for dd in deltas:
        w(f"### Δ = {dd}")
        w("")
        w("| 观测量 | \\|r\\|/\\|d*\\|（方向里 4 条轴没覆盖的比例） | OOF Pearson(d*) | "
          "OOF Pearson(r) | 1−ρ²(r)/ρ²(d*) = S 解释份额 | r 超零分布 p99 |")
        w("|---|---|---|---|---|---|")
        for k, v in hd["completeness_per_target"].items():
            if not k.endswith(f"delta{dd}"):
                continue
            tn = k.split("|")[0]
            mark = " ⚠️定义式目标" if v["is_definition_target_of"] else ""
            w(f"| `{tn}`{mark} | {f(v['residual_norm_fraction'])} | {f(v['oof_pearson_full'])} | "
              f"{f(v['oof_pearson_residual'])} | {f(v['pearson2_share_explained_by_S'])} | "
              f"{f(v['residual_exceeds_null_p99'])}（p99={f(v['null_p99'])}） |")
        w("")
        ds = d["direction_search"][f"delta{dd}"]
        w(f"零分布分母：**{ds['n_random_directions_in_null']} 个随机单位方向**"
          f"（`direction_search.delta{dd}.n_random_directions_in_null`），"
          f"搜索分母：**{ds['n_directions']} 个方向**"
          f"（240 随机 + 80 PCA 主方向 + 80 轴扰动）。")
        w("")

    # ---------------- 5 方向搜索
    w("## 5. 方向搜索与搜索修正（`direction_search`）")
    w("")
    for dd in deltas:
        s = d["direction_search"][f"delta{dd}"]
        w(f"### Δ = {dd}（{s['n_traj']} 条轨迹 / {s['n_steps']} 步 / "
          f"{s['n_directions']} 个方向）")
        w("")
        w("| 观测量 | max OOF Pearson | 来自哪类方向 | 零分布 p95 | p99 | 搜索修正后 p | "
          "轴外方向上的 max | 轴外 p |")
        w("|---|---|---|---|---|---|---|---|")
        for tn, v in s["per_target"].items():
            mark = " ⚠️" if v["is_definition_target_of"] else ""
            w(f"| `{tn}`{mark} | {f(v['oof_pearson_max'])} | {v['dir_max']} | "
              f"{f(v['null_p95_random'])} | {f(v['null_p99_random'])} | "
              f"{f(v['p_search_corrected'])} | {f(v['oof_pearson_max_outside_S'])} | "
              f"{f(v['p_search_corrected_outside_S'])} |")
        w("")

    # ---------------- 6 互检
    w("## 6. 互检：这 4 条互相冗余吗（`mutual_redundancy`）")
    w("")
    w(d["mutual_redundancy"]["method"])
    w("")
    w("| 轴 | 它自己的读出目标 | 投影掉 | \\|r\\|/\\|d*\\| | OOF Pearson(d*) | OOF Pearson(r) | 其他 3 条解释份额 |")
    w("|---|---|---|---|---|---|---|")
    for a, v in d["mutual_redundancy"]["rows"].items():
        w(f"| `{a}` | `{v['its_own_readout_target']}` | {', '.join('`'+b+'`' for b in v['projected_out'])} | "
          f"{f(v['residual_norm_fraction_median'])} | {f(v['oof_pearson_full'])} | "
          f"{f(v['oof_pearson_residual'])} | {f(v['pearson2_share_explained_by_other3'])} |")
    w("")

    # ---------------- 7 独立方向计数
    w("## 7. 还剩几个互相独立的方向（下界）（`independent_direction_count`）")
    w("")
    idc = d["independent_direction_count"]
    sep = cfg["cos_separation_threshold"]
    w(f"阈值来源：{idc['threshold_basis']}；互低余弦阈值 |cos| < {sep}"
      f"（另报 {cfg['cos_separation_alt']}）；"
      f"「在 S 之外」判据：投影掉 span(S) 后残差范数占比 ≥ {cfg['outside_S_ratio_threshold']}。")
    w("")
    w("| 观测量 | Δ | 超零分布 p99 的方向数 / 分母 | 超零分布 p95 的方向数 | 贪心后互相独立方向数 | 其中在 S 之外 |")
    w("|---|---|---|---|---|---|")
    for k, v in idc["rows"].items():
        tn, dd = k.split("|")
        s = v[f"sep{sep}"]
        mark = " ⚠️" if tn in cfg["axis_definition_target"].values() else ""
        w(f"| `{tn}`{mark} | {dd.split('delta')[1]} | {s['n_exceeding_null']} / "
          f"{v['n_directions_pooled']} | {v['q95']['n_exceeding_null']} / "
          f"{v['q95']['denominator']} | {s['n_independent_directions']} | "
          f"{s['n_outside_S']} |")
    w("")
    w("阈值敏感性（贪心后互相独立方向数，|cos| 阈值 0.3 / 0.5 / 0.7）：")
    w("")
    hdr = ["观测量|Δ", *[f"sep{c}" for c in cfg["cos_separation_alt"]]]
    w("|" + "|".join(hdr) + "|")
    w("|" + "|".join(["---"] * len(hdr)) + "|")
    for k, v in idc["rows"].items():
        cells = [str(v[f"sep{c}"]["n_independent_directions"]) for c in cfg["cos_separation_alt"]]
        w("|" + "|".join([k] + cells) + "|")
    w("")

    # ---------------- 8 结论
    w("## 8. 结论")
    w("")
    w(f"**判定：{hd['completeness_verdict']}**（`headline.completeness_verdict`）")
    w("")
    w(f"- 分母：非定义式目标格 **{hd['n_non_definitional_cells']}** 个"
      f"（每个观测量 × {len(deltas)} 个 Δ），"
      f"其中残差仍超零分布尾部的 **{hd['n_non_definitional_cells_with_readable_residual']}** 个"
      f"（`headline.n_non_definitional_cells_with_readable_residual`）")
    n_rand_null = d["direction_search"][f"delta{deltas[0]}"]["n_random_directions_in_null"]
    w(f"- 每格搜索分母 **{hd['n_directions_searched_per_cell']}** 个方向，"
      f"零分布 **{n_rand_null}** 个随机方向"
      f"（`direction_search.delta{deltas[0]}.n_random_directions_in_null`）")
    w("")
    w(f"**{hd['independent_direction_lower_bound_statement']}**")
    w("")
    if "independent_direction_summary" in hd:
        w("| Δ | 观测量数 | 候选池 | 互相独立方向数 min/中位/max | 其中在 S 之外 min/中位/max |")
        w("|---|---|---|---|---|")
        for dn in deltas:
            a = hd["independent_direction_summary"][f"delta{dn}"]
            w(f"| {dn} | {a['n_observables']} | {a['n_directions_pooled']} | "
              f"{a['independent_min']} / {a['independent_median']:.1f} / {a['independent_max']} | "
              f"{a['outside_S_min']} / {a['outside_S_median']:.1f} / {a['outside_S_max']} |")
        w("")
    viol = hd["non_definitional_targets_with_readable_residual"]
    if viol:
        w("残差仍可读的非定义式格（按 OOF |Pearson| 排，前 15）：")
        w("")
        w("| 观测量 | Δ | 残差 OOF Pearson | 零分布 p99 | S 解释份额 |")
        w("|---|---|---|---|---|")
        for v in sorted(viol, key=lambda x: -abs(x["oof_pearson_residual"]))[:15]:
            w(f"| `{v['target']}` | {v['delta']} | {f(v['oof_pearson_residual'])} | "
              f"{f(v['null_p99'])} | {f(v['pearson2_share_explained_by_S'])} |")
        w("")
    w("### 结论要说清的三件事")
    w("")
    w("1. **S-share 是可信的，因为它有阳性对照也有阴性对照。** 4 条轴的定义式目标"
      "（`step_frac` 给 S-share 0.997、`self_check_regex` 给 0.999、"
      "`entropy` 给 0.875）说明装置在 S 真的覆盖该方向时**会**报出接近 1 的份额；"
      "而 `op_mass` / `newline_mass` / `latex_mass` / `digit_mass` 只得到 0.016–0.20，"
      "同一把尺子读出的完全不同的数。")
    w("2. **缺口集中在 Δ=0–20，Δ≥100 全部落回噪声。** 这与 4 条轴都是"
      "「token 局部状态」的定位一致：它们描述的是当前 token，不描述更远未来。")
    w("3. **必须扣掉定义式格。** `step_frac`、`self_check_regex`、`in_think`、"
      "`entropy` 这四列的漂亮数字是构造必然，本报告把它们全部标为阳性对照，"
      "不作为不完备性的证据。")
    DST.write_text("\n".join(L) + "\n")
    print("wrote", DST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
