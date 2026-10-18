"""Tests for the self-contained workbench HTML builder."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.workbench_html import svg_bars, svg_heatmap, svg_line, svg_scatter  # noqa: E402


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "workbench_builder", ROOT / "backend/examples/build_steering_workbench.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_svg_helpers_render_expected_tags():
    line = svg_line([{"name": "raw", "color": "#fff", "points": [(0, 0.2), (1, 0.4)]}], x_labels=["0", "1"])
    assert "<svg" in line and "<path" in line and "<circle" in line
    bars = svg_bars([{"label": "w", "value": 0.2, "color": "#fff"}])
    assert "<rect" in bars and "<svg" in bars
    scatter = svg_scatter([{"x": 1e-3, "y": 0.1, "color": "#fff"}])
    assert "<circle" in scatter
    heatmap = svg_heatmap([[0.0, 0.1], [0.2, -0.1]], marker_columns=[1])
    assert "<rect" in heatmap and "<line" in heatmap


def test_build_html_has_all_sections_and_downloads():
    module = load_builder()
    text = module.build_html()
    assert len(text) > 100000
    for needle in [
        "Hidden-State Steering Workbench",
        'data-tab="overview"',
        'data-tab="readout"',
        'data-tab="construction"',
        'data-tab="transfer"',
        'data-tab="sweep"',
        'data-tab="unit"',
        'data-tab="recipe"',
        'data-tab="algorithm"',
        'data-tab="design"',
        "7196_sparse_g.npy",
        "10061_mean_g.npy",
        "6771_w.npy",
        "data:application/octet-stream;base64,",
        "Intervention algorithm guide",
        "Unit design",
        "OMP",
    ]:
        assert needle in text, needle
    assert "NaN" not in text
    assert "undefined" not in text

