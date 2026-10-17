#!/usr/bin/env python3
"""Build a self-contained HTML workbench from the steering artifacts.

The page is intentionally dependency-free: HTML + CSS + a small amount of JS,
all charts are pre-rendered SVG, and the recipe vectors are embedded as base64
download links.  It is a presentation layer over the committed artifacts, not a
new measurement.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.workbench_html import esc, fmt, signed, svg_bars, svg_heatmap, svg_line, svg_scatter  # noqa: E402

ATLAS = ROOT / "experiments/readout_atlas_v1/readout_atlas.json"
CONSTRUCTION = ROOT / "experiments/steering_construction_v1/steering_construction.json"
TRANSFER = ROOT / "experiments/steering_transfer_v1/steering_transfer.json"
SWEEP = ROOT / "experiments/steering_sweep_v1/steering_sweep.json"
RECIPE = ROOT / "experiments/steering_recipe_v1/steering_recipe.json"
DESIGN = ROOT / "experiments/steering_design_v1/steering_design.json"
OUT = ROOT / "experiments/steering_workbench_v1/steering_workbench.html"
PUBLIC = ROOT / "frontend/public/steering-workbench.html"

MARKER_ORDER = ["7196", "10061", "6771"]
CANDIDATE_ORDER = ["w", "minus_w", "gradient", "w_plus_gradient", "random"]
CANDIDATE_COLOR = {"w": "#fb7185", "minus_w": "#2dd4bf", "gradient": "#60a5fa", "w_plus_gradient": "#fbbf24", "random": "#94a3b8"}
CANDIDATE_LABEL = {"w": "w", "minus_w": "−w", "gradient": "g", "w_plus_gradient": "w+g", "random": "random"}
TRANSFER_ORDER = ["w", "minus_w", "g_mean", "g_sparse", "random", "oracle_per_site_gradient"]
TRANSFER_LABEL = {"w": "w", "minus_w": "−w", "g_mean": "mean g", "g_sparse": "sparse g", "random": "random", "oracle_per_site_gradient": "oracle g"}
TRANSFER_COLOR = {"w": "#fb7185", "minus_w": "#2dd4bf", "g_mean": "#60a5fa", "g_sparse": "#fbbf24", "random": "#94a3b8", "oracle_per_site_gradient": "#a78bfa"}
SWEEP_ORDER = ["w", "mean_g", "sparse_g", "random"]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def heat_bg(value: float, limit: float = 1.5) -> str:
    t = max(-1.0, min(1.0, float(value) / limit))
    if t < 0:
        return "rgba(251,113,133,%.3f)" % (0.15 + 0.55 * -t)
    return "rgba(45,212,191,%.3f)" % (0.15 + 0.55 * t)


def section(title: str, subtitle: str, body: str, testid: str = "") -> str:
    return (
        '<section class="panel" data-testid="' + esc(testid) + '">'
        '<h2>' + esc(title) + '</h2>'
        '<p class="sub">' + esc(subtitle) + '</p>'
        + body +
        '</section>'
    )


def readout_section(atlas) -> str:
    per_marker = atlas["per_marker"]
    aggregate = atlas["aggregate"]
    marker_ids = [m for m in MARKER_ORDER if m in per_marker]
    rows = []
    for marker in marker_ids:
        item = per_marker[marker]
        rows.append(
            '<tr><td class="mono">' + esc(marker) + '</td>'
            '<td class="mono">' + esc(item.get("n_occurrences")) + '</td>'
            '<td class="mono">' + esc(item.get("best_layer")) + '</td>'
            '<td class="mono ' + ("pos" if (item.get("best_layer_orientation") or 0) > 0 else "neg") + '">' + fmt(item.get("best_layer_mean_auc_cos")) + '</td>'
            '<td class="mono">' + esc(item.get("best_layer_orientation")) + '</td></tr>'
        )
    table = ('<table><thead><tr><th>marker</th><th>n</th><th>best layer</th><th>raw cos AUC</th><th>orientation</th></tr></thead><tbody>'
             + "".join(rows) + '</tbody></table>')
    blocks = []
    aggregate_layers = aggregate["layers"]
    for marker in marker_ids:
        layers = per_marker[marker]["layers"]
        raw = [{"name": "raw cos", "color": "#fb7185", "points": [(row["layer"], row["mean_auc_cos"]) for row in layers]}]
        oriented = [{"name": "oriented", "color": "#2dd4bf", "points": [(row["layer"], row["mean_auc_cos_oriented"]) for row in layers]}]
        norm = [{"name": "norm (aggregate)", "color": "#94a3b8", "points": [(row["layer"], row["mean_auc_norm"]) for row in aggregate_layers]}]
        chart = svg_line(raw + oriented + norm, y_label="AUC", x_labels=[str(i) for i in range(28)], y_min=0.1, y_max=0.9)
        blocks.append('<div data-marker="' + marker + '"><h3>marker ' + marker + '</h3>' + chart + '</div>')
    series = max(atlas["series"], key=lambda item: (int(item.get("n_marker", 0)), -int(item.get("T", 0))))
    cos = series["cos"]
    stride = max(1, (len(cos) + 199) // 200)
    columns = (len(cos) + stride - 1) // stride
    matrix = []
    for layer in range(28):
        row = []
        for column in range(columns):
            values = [float(cos[index][layer]) for index in range(column * stride, min(len(cos), (column + 1) * stride))]
            row.append(sum(values) / max(len(values), 1))
        matrix.append(row)
    markers = [position // stride for position in series.get("marker_positions", []) if position // stride < columns]
    heatmap = svg_heatmap(matrix, markers, width=980, height=340, limit=0.3)
    note = ('<p class="note">set-level raw cos AUC ' + fmt(aggregate.get("best_layer_mean_auc_cos")) +
            ' at layer ' + esc(aggregate.get("best_layer")) + '; orientation ' + esc(aggregate.get("best_layer_orientation")) +
            '; ' + esc(aggregate.get("n_trajectories_negative_orientation")) + '/' + esc(aggregate.get("n_trajectories_with_orientation")) +
            ' trajectories negative. Per-marker: 7196 is positive, the rest negative.</p>')
    body = ('<div class="grid2"><div><table class="compact"><thead><tr><th>marker</th><th>n</th><th>layer</th><th>AUC</th><th>dir</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table>' + note + '</div><div class="chartbox">' + heatmap +
            '<div class="small">sample trajectory: ' + esc(series.get("id")) + '; white ticks = marker next-token; cos(h,w) clipped at ±0.3</div></div></div>'
            + '<div class="marker-charts">' + "".join(blocks) + '</div>')
    return section("Readout atlas：w·h 在哪里读得出 marker", "逐层 rank AUC；raw<0.5 表示 marker 位置的 cos(h,w) 更低。per-marker 符号分裂是设计方向的关键。", body, "readout")


def construction_section(construction) -> str:
    aggregate = construction["aggregate"]
    blocks = []
    for marker in MARKER_ORDER:
        item = aggregate.get(marker)
        if not item:
            continue
        candidates = item["candidates"]
        bars = svg_bars([
            {"label": CANDIDATE_LABEL[name], "value": candidates.get(name, {}).get("mean_delta_logp", 0.0), "color": CANDIDATE_COLOR[name]}
            for name in CANDIDATE_ORDER
        ], y_label="mean delta log p(marker)", y_min=-0.4, y_max=0.7)
        sites = [site for site in construction["sites"] if str(site["marker"]) == marker]
        site_rows = []
        for site in sites:
            cells = []
            for name in CANDIDATE_ORDER:
                value = site["candidates"].get(name, {}).get("delta_logp")
                cells.append('<td class="mono ' + ("pos" if (value or 0) > 0 else "neg") + '">' + signed(value) + '</td>')
            site_rows.append('<tr><td class="mono">' + esc(site["trajectory"]) + '</td><td class="mono">' + esc(site["n_prefix"]) + '</td><td class="mono">' + signed(site.get("baseline_logp"), 3) + '</td>' + "".join(cells) + '</tr>')
        site_table = ('<table class="compact"><thead><tr><th>site</th><th>prefix</th><th>f0</th>'
                      + "".join('<th>Δ' + CANDIDATE_LABEL[name] + '</th>' for name in CANDIDATE_ORDER) + '</tr></thead><tbody>'
                      + "".join(site_rows) + '</tbody></table>')
        blocks.append('<div data-marker="' + marker + '"><h3>marker ' + marker + '</h3><div class="grid2"><div>' + bars + '</div><div>' + site_table + '</div></div></div>')
    first = construction["sites"][0]
    scatter_points = [{"x": point["response"], "y": point["contribution"], "color": "#2dd4bf" if point["contribution"] > 0 else "#fb7185"} for point in construction["scatter"]]
    scatter = svg_scatter(scatter_points, x_label="response |Δa|·||d|| (log)", y_label="c_i", log_x=True)
    units = first["decomposition"]
    def unit_rows(items):
        return "".join('<tr><td class="mono">' + esc(item["layer"]) + '</td><td class="mono">' + esc(item["unit"]) + '</td><td class="mono">' + fmt(item["response"], 2) + '</td><td class="mono">' + signed(item["contribution"], 5) + '</td></tr>' for item in items)
    unit_table = ('<div class="grid2"><div><h4>top carriers (c&gt;0)</h4><table class="compact"><thead><tr><th>layer</th><th>unit</th><th>resp</th><th>c</th></tr></thead><tbody>'
                  + unit_rows(units["top_carriers"]) + '</tbody></table></div><div><h4>top compensators (c&lt;0)</h4><table class="compact"><thead><tr><th>layer</th><th>unit</th><th>resp</th><th>c</th></tr></thead><tbody>'
                  + unit_rows(units["top_compensators"]) + '</tbody></table></div></div>')
    note = ('<p class="note">unit decomposition: c_i = (g·d_i)·Δa_i, first-order; sum c / measured Δw ratio varies across sites, so this is a diagnostic, not mediation. Naive write-direction removal failed in the prototype.</p>')
    return section("Construction probe：梯度方向与原生单元", "block-20 局部梯度 g 在全部 site 上提高目标；w 对 7196 为负、对其它 marker 更弱。四象限来自首个 site 的 unit decomposition。", "".join(blocks) + scatter + unit_table + note, "construction")


def transfer_section(transfer) -> str:
    same = transfer["same_marker"]
    rows = []
    for marker in MARKER_ORDER:
        item = same.get(marker, {})
        cells = "".join('<td class="mono ' + ("pos" if (item.get(name, {}).get("mean_delta_logp") or 0) > 0 else "neg") + '">' + signed(item.get(name, {}).get("mean_delta_logp")) + '</td>' for name in TRANSFER_ORDER)
        rows.append('<tr><td class="mono">' + marker + '</td>' + cells + '</tr>')
    table = ('<table><thead><tr><th>marker</th>' + "".join('<th>' + TRANSFER_LABEL[name] + '</th>' for name in TRANSFER_ORDER) + '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>')
    cross = transfer["cross"]
    cross_rows = []
    for source in MARKER_ORDER:
        cells = []
        for target in MARKER_ORDER:
            cell = cross.get(source, {}).get(target)
            if not cell:
                cells.append('<td class="empty">—</td>')
            else:
                value = cell["mean_delta_logp"]
                cells.append('<td class="mono" style="background:' + heat_bg(value) + '">' + signed(value, 3) + '<div class="tiny">' + str(round(cell["improved_fraction"] * 100)) + '%</div></td>')
        cross_rows.append('<tr><th class="mono">' + source + '</th>' + "".join(cells) + '</tr>')
    cross_table = ('<table class="cross"><thead><tr><th>source -&gt; target</th>' + "".join('<th>' + target + '</th>' for target in MARKER_ORDER) + '</tr></thead><tbody>' + "".join(cross_rows) + '</tbody></table>')
    site_rows = []
    for site in transfer["sites"]:
        cells = "".join('<td class="mono ' + ("pos" if (site["directions"].get(name, {}).get("delta_logp") or 0) > 0 else "neg") + '">' + signed(site["directions"].get(name, {}).get("delta_logp")) + '</td>' for name in ["w", "g_mean", "g_sparse"])
        site_rows.append('<tr><td class="mono">' + esc(site["trajectory"]) + '</td><td class="mono">' + esc(site["marker"]) + '</td><td class="mono">' + esc(site["n_prefix"]) + '</td><td class="mono">' + signed(site.get("baseline_logp"), 3) + '</td>' + cells + '<td class="mono">' + signed(site.get("oracle", {}).get("delta_logp")) + '</td></tr>')
    site_table = ('<table class="compact"><thead><tr><th>site</th><th>marker</th><th>prefix</th><th>f0</th><th>Δw</th><th>Δmean g</th><th>Δsparse g</th><th>Δoracle</th></tr></thead><tbody>' + "".join(site_rows) + '</tbody></table>')
    note = '<p class="note">7196 mean g hurts other markers (cross negative); 10061/6771 mean g helps other markers too. Two calibration + two held-out sites per marker; descriptive.</p>'
    return section("Held-out transfer：方向能不能迁移", "mean g 用 calibration site 构造，在未参与构造的 held-out site 上评估；cross 是 source 方向作用到 target marker。", table + '<div class="grid2"><div><h4>cross-marker mean g</h4>' + cross_table + '</div><div><h4>per held-out site</h4>' + site_table + '</div></div>' + note, "transfer")


def sweep_section(sweep) -> str:
    aggregate = sweep["aggregate"]
    useful = sweep["useful_window"]
    cards = []
    for marker in MARKER_ORDER:
        window = useful.get(marker, {})
        cards.append('<div class="card"><div class="eyebrow">marker ' + marker + '</div><div class="big">' + esc(window.get("direction")) + ' @ ' + esc(window.get("dose")) + '</div><div class="small">Δlogp ' + signed(window.get("mean_delta_logp")) + ' · KL ' + fmt(window.get("mean_kl")) + ' (budget ' + esc(window.get("kl_threshold")) + ')</div></div>')
    blocks = []
    for marker in MARKER_ORDER:
        directions = aggregate[marker]["directions"]
        delta_series = []
        for name in SWEEP_ORDER:
            rows = directions.get(name, [])
            delta_series.append({"name": name, "color": CANDIDATE_COLOR.get(name, "#60a5fa"), "points": [(row["dose"], row["mean_delta_logp"]) for row in rows]})
        delta_chart = svg_line(delta_series, y_label="mean delta log p", x_labels=[str(dose) for dose in sweep["doses"]])
        kl_series = []
        for name in ["mean_g", "sparse_g"]:
            rows = directions.get(name, [])
            kl_series.append({"name": name, "color": CANDIDATE_COLOR.get(name, "#60a5fa"), "points": [(row["dose"], __import__("math").log10(max(row["mean_kl"], 1e-4))) for row in rows]})
        kl_chart = svg_line(kl_series, y_label="log10 mean KL", x_labels=[str(dose) for dose in sweep["doses"]])
        rows_html = []
        for name in ["w", "mean_g", "sparse_g"]:
            for row in directions.get(name, []):
                rows_html.append('<tr><td class="mono">' + name + '</td><td class="mono">' + str(row["dose"]) + '</td><td class="mono ' + ("pos" if row["mean_delta_logp"] > 0 else "neg") + '">' + signed(row["mean_delta_logp"]) + '</td><td class="mono">' + fmt(row["mean_kl"]) + '</td><td class="mono">' + signed(row["mean_delta_entropy"]) + '</td></tr>')
        table = ('<table class="compact"><thead><tr><th>dir</th><th>dose</th><th>Δlogp</th><th>KL</th><th>ΔH</th></tr></thead><tbody>' + "".join(rows_html) + '</tbody></table>')
        blocks.append('<div data-marker="' + marker + '"><h3>marker ' + marker + '</h3><div class="grid2"><div>' + delta_chart + '</div><div>' + kl_chart + '</div></div>' + table + '</div>')
    note = '<p class="note">mean g 效果大但 KL/熵代价大；sparse g 同 dose 更省；w 最安全但更弱。高 dose 的 −w 极端 off-manifold，表里保留、图中省略。</p>'
    return section("Alpha / side-effect sweep：按 KL 预算选窗口", "dose 是 block-20 input L2 范数的比例；KL 是完整 softmax 对 baseline 的散度。", '<div class="cards">' + "".join(cards) + '</div>' + "".join(blocks) + note, "sweep")


def recipe_section(recipe) -> str:
    cards = []
    for marker in MARKER_ORDER:
        entry = recipe["markers"].get(marker)
        if not entry:
            continue
        compiled = entry["compiled"]
        verification = entry["verification"]
        file_path = ROOT / compiled["file"]
        encoded = base64.b64encode(file_path.read_bytes()).decode("ascii") if file_path.exists() else ""
        download = ('data:application/octet-stream;base64,' + encoded) if encoded else "#"
        sites = "".join('<tr><td class="mono">' + esc(site["trajectory"]) + '</td><td class="mono">' + esc(site["t"]) + '</td><td class="mono">' + signed(site["delta_logp"]) + '</td><td class="mono">' + fmt(site["kl"]) + '</td></tr>' for site in verification.get("sites", []))
        cards.append(
            '<div class="card recipe" data-marker="' + marker + '">'
            '<div class="eyebrow">marker ' + marker + '</div>'
            '<div class="big">' + esc(compiled["direction"]) + ' @ ' + esc(compiled["dose"]) + '</div>'
            '<div class="small">expected Δ ' + signed(compiled["expected_delta_logp"]) + ' / KL ' + fmt(compiled["expected_kl"]) + '</div>'
            '<div class="small">verified Δ ' + signed(verification["mean_delta_logp"]) + ' / KL ' + fmt(verification["mean_kl"]) + ' (n=' + str(verification["n_sites"]) + ')</div>'
            '<div class="small">readout layer ' + esc(entry["readout"]["best_layer"]) + ' · AUC ' + fmt(entry["readout"]["raw_cos_auc"]) + ' · orientation ' + esc(entry["readout"]["orientation"]) + '</div>'
            '<a class="download" download="' + esc(file_path.name) + '" href="' + download + '">download ' + esc(file_path.name) + '</a>'
            '<details><summary>verification sites</summary><table class="compact"><thead><tr><th>site</th><th>t</th><th>Δlogp</th><th>KL</th></tr></thead><tbody>' + sites + '</tbody></table></details>'
            '<ul class="tiny">' + "".join('<li>' + esc(item) + '</li>' for item in entry.get("caveats", [])) + '</ul>'
            '</div>'
        )
    usage = ('<pre class="code">import numpy as np<br>'
             'v = np.load("experiments/steering_recipe_v1/vectors/7196_sparse_g.npy")<br>'
             'alpha = dose * np.linalg.norm(h_block20_last)<br>'
             'h_block20_last += alpha * v<br>'
             '# re-measure target logp / KL on your own prefix</pre>')
    note = '<p class="note">recipe 的 verification 复用 transfer/sweep 的 held-out site，不是第三个独立 split；换前缀/层/模型/剂量后必须重新验证。</p>'
    return section("Compiled recipe：可下载的候选向量", "每个 marker 一个 .npy + dose + held-out 验证；它是可复现起点，不是生产级向量。", '<div class="cards">' + "".join(cards) + '</div>' + usage + note, "recipe")


def design_section(design) -> str:
    layers = design["layers"]
    layer_rows = "".join('<tr><td class="mono">' + str(row["layer"]) + '</td><td class="mono">' + signed(row["block_mean"]) + '</td><td class="mono">' + signed(row["restore_mean"]) + '</td><td class="mono">' + signed(row["support"]) + '</td><td class="mono">' + esc(row["action"]) + '</td><td class="mono">' + signed(row["net_effect_primary"]) + '</td></tr>' for row in layers)
    layer_table = ('<table class="compact"><thead><tr><th>layer</th><th>block</th><th>restore</th><th>support</th><th>action</th><th>+v effect</th></tr></thead><tbody>' + layer_rows + '</tbody></table>')
    rec_cards = []
    for rec in design["recommendations"]:
        rec_cards.append('<div class="card small-card"><div class="eyebrow">' + esc(rec["priority"]) + ' · ' + esc(rec["action"]) + '</div><div class="small">' + esc(rec["reason"]) + '</div><ul class="tiny">' + "".join('<li>' + esc(item) + '</li>' for item in rec.get("evidence", [])) + '</ul></div>')
    warnings = "".join('<li>' + esc(item) + '</li>' for item in design.get("warnings", []))
    return section("Design guide：从证据到设计决策", "层策略、剂量、方向、构造、迁移、副作用与 recipe 的完整建议；每条带 evidence 与 confidence。", '<h3>layer strategy（multiplication / block-restore）</h3>' + layer_table + '<h3>recommendations</h3><div class="cards">' + "".join(rec_cards) + '</div><h3>warnings</h3><ul class="caveats">' + warnings + '</ul>', "design")


def algorithm_section() -> str:
    rows = [
        ("目标定义", "marker 读出 vs correctness 效应是不同目标；+v 对 correctness 为负、对 7196 为负。", "先固定 target；不要用 w·U 的 marker 可读性代替 correctness。"),
        ("读出层", "per-marker best layer 17/21/27；set-level 21 是反相关。", "读出层用于诊断，不要直接当注入层；注入层当前固定 block 20。"),
        ("方向", "mean g 在 held-out 上最好；7196 sparse g@0.02；10061 mean g@0.02；6771 w@0.1。", "per-marker 方向；7196 方向对其它 marker 为负，不能共享。"),
        ("剂量", "KL≤0.1 窗口；mean g 效果大但 KL 大；sparse g 更省。", "按 KL 预算选 dose，不选最大 Δlogp。"),
        ("干预算法", "one-shot fixed recipe 已验证；per-token 梯度控制器未测；unit block/restore 的 naive 修复失败。", "先部署 one-shot；per-token 控制器作为下一实验；unit 级需要精确 ∇_h a_i。"),
        ("验证", "当前 held-out 与 verification 共用 site；没有任务级指标。", "独立第三 split + 任务级副作用 + 第二模型后再升级。"),
    ]
    trs = "".join('<tr><td>' + esc(a) + '</td><td>' + esc(b) + '</td><td>' + esc(c) + '</td></tr>' for a, b, c in rows)
    table = '<table><thead><tr><th>决策</th><th>当前证据</th><th>建议</th></tr></thead><tbody>' + trs + '</tbody></table>'
    options = [
        ("A. One-shot fixed vector（当前）", "compiled recipe：3 个 marker，held-out 验证，KL 预算内；成本最低。", "直接用于离线前缀干预；换前缀/层/模型必须重验。"),
        ("B. Per-token gradient controller", "未测；每 token 需一次 backward，成本高；可能跟踪 target 更好，也可能漂移。", "下一实验：固定前缀生成中每步注入 λg_t，比较 Δlogp/KL/生成质量。"),
        ("C. Unit-level block/restore", "原生单元分解是诊断；naive write-direction 移除失败。", "先算精确 ∇_h a_i，再做 unit patch/block；不要用 d_i 投影代替。"),
        ("D. Sparse / low-rank direction", "sparse g 在相同 dose 下 KL 更低，保留大部分 Δlogp。", "候选；在独立 split 上比较 sparse vs dense 的 KL/任务副作用。"),
    ]
    opt_rows = "".join('<tr><td>' + esc(a) + '</td><td>' + esc(b) + '</td><td>' + esc(c) + '</td></tr>' for a, b, c in options)
    opt_table = '<table><thead><tr><th>算法</th><th>证据/状态</th><th>下一步</th></tr></thead><tbody>' + opt_rows + '</tbody></table>'
    next_steps = [
        "独立第三 held-out split（当前 verification 复用 transfer/sweep site）。",
        "任务级副作用：正确率、其它 marker 的 per-marker 概率、生成质量，而不是只有 KL。",
        "Per-token controller 与 one-shot recipe 的对照实验。",
        "正则化方向（clip / low-rank / unit-sparse）在相同 Δlogp 下比较 KL。",
        "第二模型/第二向量；把选窗口规则预登记。",
    ]
    return section("Intervention algorithm guide：下一步怎么设计", "把当前证据映射到向量与干预算法的选择；区分已验证、未验证与失败的方向。", table + '<h3>算法选项</h3>' + opt_table + '<h3>推荐的下一批实验</h3><ol class="caveats">' + "".join('<li>' + esc(item) + '</li>' for item in next_steps) + '</ol>', "algorithm")


def overview_section(recipe, design) -> str:
    cards = []
    for marker in MARKER_ORDER:
        entry = recipe["markers"][marker]
        compiled = entry["compiled"]
        verification = entry["verification"]
        cards.append('<div class="card" data-marker="' + marker + '"><div class="eyebrow">marker ' + marker + '</div><div class="big">' + esc(compiled["direction"]) + ' @ ' + esc(compiled["dose"]) + '</div><div class="small">readout layer ' + esc(entry["readout"]["best_layer"]) + ' · AUC ' + fmt(entry["readout"]["raw_cos_auc"]) + ' · orientation ' + esc(entry["readout"]["orientation"]) + '</div><div class="small">verified Δ ' + signed(verification["mean_delta_logp"]) + ' / KL ' + fmt(verification["mean_kl"]) + '</div></div>')
    flow = (
        '<div class="flow">'
        '<div class="step"><b>1. Target</b><span>选 marker；定义 f</span></div>'
        '<div class="arrow">→</div>'
        '<div class="step"><b>2. Readout</b><span>w·h 在哪层可读</span></div>'
        '<div class="arrow">→</div>'
        '<div class="step"><b>3. Construct</b><span>mean g / sparse g</span></div>'
        '<div class="arrow">→</div>'
        '<div class="step"><b>4. Transfer</b><span>held-out site</span></div>'
        '<div class="arrow">→</div>'
        '<div class="step"><b>5. Dose</b><span>Δlogp vs KL</span></div>'
        '<div class="arrow">→</div>'
        '<div class="step"><b>6. Recipe</b><span>.npy + verify</span></div>'
        '</div>'
    )
    intro = ('<p class="lead">这个工作台把一次 steering vector 的生命周期串起来：<b>读得出什么</b>、'
             '<b>能构造什么</b>、<b>能否迁移</b>、<b>剂量与副作用</b>、<b>最终可下载的 recipe</b>。'
             '左侧选 marker，下面各 tab 会切换对应证据。</p>')
    stats = ('<div class="cards">'
             '<div class="card"><div class="eyebrow">readout</div><div class="big">30</div><div class="small">trajectories · 384 marker occurrences</div></div>'
             '<div class="card"><div class="eyebrow">construction</div><div class="big">6</div><div class="small">sites · 3 markers · gradient vs w</div></div>'
             '<div class="card"><div class="eyebrow">transfer</div><div class="big">2 + 2</div><div class="small">calibration + held-out per marker</div></div>'
             '<div class="card"><div class="eyebrow">sweep</div><div class="big">6</div><div class="small">doses · Δlogp/KL/entropy</div></div>'
             '<div class="card"><div class="eyebrow">recipe</div><div class="big">3</div><div class="small">.npy candidates · verified</div></div>'
             '</div>')
    return section("Overview：从 hidden states 到可执行向量", "目标：把 hidden-state 可解释性变成可复现的 steering vector 与干预算法设计。", intro + flow + stats + '<h3>当前 marker 的 recipe</h3><div class="cards">' + "".join(cards) + '</div>', "overview")


def build_html() -> str:
    atlas = load(ATLAS)
    construction = load(CONSTRUCTION)
    transfer = load(TRANSFER)
    sweep = load(SWEEP)
    recipe = load(RECIPE)
    design = load(DESIGN)
    marker_options = "".join('<option value="' + marker + '">marker ' + marker + '</option>' for marker in MARKER_ORDER)
    css = '''
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#080e1a;color:#e2e8f0;font:13px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans SC",sans-serif}
header{position:sticky;top:0;z-index:5;background:rgba(8,14,26,.96);border-bottom:1px solid #1e293b;padding:18px 28px 12px}
.wrap{max-width:1480px;margin:0 auto;padding:0 20px}
h1{font-size:24px;margin:0 0 4px;letter-spacing:-.02em}
.lead{color:#94a3b8;max-width:1000px;margin:6px 0 10px}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.tabs button{background:#0f172a;color:#94a3b8;border:1px solid #1e293b;border-radius:8px;padding:7px 12px;cursor:pointer;font-size:12px}
.tabs button.active{color:#5eead4;border-color:#0f766e;background:#042f2e}
.markerbox{display:flex;align-items:center;gap:8px;margin-top:10px;color:#94a3b8;font-size:12px}
select{background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:7px;padding:6px 10px}
main{max-width:1480px;margin:0 auto;padding:18px 20px 60px}
.panel{background:#0b1220;border:1px solid #1e293b;border-radius:16px;padding:18px;margin:14px 0}
.panel h2{margin:0 0 4px;font-size:17px}
.panel h3{margin:18px 0 8px;font-size:14px;color:#cbd5e1}
.panel h4{margin:8px 0;font-size:12px;color:#94a3b8}
.sub{color:#94a3b8;margin:0 0 12px;font-size:12px;max-width:1100px}
.note{color:#94a3b8;font-size:12px;border-left:3px solid #0f766e;padding:6px 10px;background:#0f172a;border-radius:6px;margin:10px 0}
.small{color:#94a3b8;font-size:11px}
.tiny{color:#64748b;font-size:11px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.pos{color:#2dd4bf}.neg{color:#fb7185}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}
@media(max-width:1000px){.grid2{grid-template-columns:1fr}}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.card{background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:12px}
.card .big{font-size:18px;font-weight:600;margin:4px 0;color:#f8fafc}
.eyebrow{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#64748b}
.small-card .small{font-size:11px}
.recipe .download{display:inline-block;margin-top:8px;color:#5eead4;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #1e293b;vertical-align:top}
th{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#64748b}
table.compact td,table.compact th{padding:4px 6px}
table.cross td,table.cross th{text-align:center;border:1px solid #1e293b}
.empty{color:#334155;text-align:center}
.flow{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:12px 0}
.step{background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:8px 10px;min-width:120px}
.step b{display:block;color:#5eead4;font-size:11px}
.step span{display:block;color:#94a3b8;font-size:11px}
.arrow{color:#475569}
.chartbox{background:#0b1220;border:1px solid #1e293b;border-radius:10px;padding:6px}
svg{width:100%;height:auto;display:block}
pre.code{background:#050a14;border:1px solid #1e293b;border-radius:10px;padding:12px;color:#cbd5e1;overflow:auto;font-size:11px}
ul.caveats{color:#94a3b8;font-size:12px;padding-left:20px}
.marker-charts{margin-top:12px}
[hidden]{display:none!important}
footer{max-width:1480px;margin:0 auto;padding:0 20px 40px;color:#475569;font-size:11px}
'''
    js = '''
const tabs = Array.from(document.querySelectorAll('[data-tab]'));
const panels = Array.from(document.querySelectorAll('[data-panel]'));
function showTab(name) {
  panels.forEach(function(panel){ panel.hidden = panel.getAttribute('data-panel') !== name; });
  tabs.forEach(function(tab){ tab.classList.toggle('active', tab.getAttribute('data-tab') === name); });
  window.scrollTo({top:0, behavior:'smooth'});
}
tabs.forEach(function(tab){ tab.addEventListener('click', function(){ showTab(tab.getAttribute('data-tab')); }); });
const markerSelect = document.getElementById('marker-select');
function setMarker(marker) {
  document.querySelectorAll('[data-marker]').forEach(function(element){ element.hidden = element.getAttribute('data-marker') !== marker; });
}
markerSelect.addEventListener('change', function(){ setMarker(markerSelect.value); });
setMarker(markerSelect.value);
showTab('overview');
'''
    body = (
        '<header><div class="wrap"><h1>Hidden-State Steering Workbench</h1>'
        '<p class="lead">从 hidden states 出发，把 steering vector 的读出、构造、迁移、剂量/副作用与最终 recipe 放在同一条设计链上。'
        '所有数字来自已入库的实验产物；页面本身不重跑模型。</p>'
        '<div class="tabs">'
        '<button data-tab="overview">Overview</button>'
        '<button data-tab="readout">Readout</button>'
        '<button data-tab="construction">Construction</button>'
        '<button data-tab="transfer">Transfer</button>'
        '<button data-tab="sweep">Dose / side effects</button>'
        '<button data-tab="recipe">Recipe</button>'
        '<button data-tab="algorithm">Algorithm guide</button>'
        '<button data-tab="design">Design guide</button>'
        '</div>'
        '<div class="markerbox"><label for="marker-select">当前 marker</label><select id="marker-select">' + marker_options + '</select>'
        '<span>页面按 marker 切换 readout / construction / sweep / recipe 卡片</span></div>'
        '</div></header>'
        '<main>'
        '<div data-panel="overview">' + overview_section(recipe, design) + '</div>'
        '<div data-panel="readout" hidden>' + readout_section(atlas) + '</div>'
        '<div data-panel="construction" hidden>' + construction_section(construction) + '</div>'
        '<div data-panel="transfer" hidden>' + transfer_section(transfer) + '</div>'
        '<div data-panel="sweep" hidden>' + sweep_section(sweep) + '</div>'
        '<div data-panel="recipe" hidden>' + recipe_section(recipe) + '</div>'
        '<div data-panel="algorithm" hidden>' + algorithm_section() + '</div>'
        '<div data-panel="design" hidden>' + design_section(design) + '</div>'
        '</main>'
        '<footer><div class="wrap">vector SHA-256: ' + esc(recipe["vector"]["sha256"]) + '<br>'
        'artifacts: experiments/{readout_atlas_v1,steering_construction_v1,steering_transfer_v1,steering_sweep_v1,steering_recipe_v1,steering_design_v1}<br>'
        'schema: ' + esc(recipe["schema"]) + ' · generated by backend/examples/build_steering_workbench.py</div></footer>'
    )
    html = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Hidden-State Steering Workbench</title><style>' + css + '</style></head><body>'
            + body + '<script>' + js + '</script></body></html>')
    return html


def main() -> int:
    html = build_html()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(html, encoding="utf-8")
    print("[ok] workbench:", OUT, "bytes", len(html))
    print("[ok] public:", PUBLIC, "bytes", len(html))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

