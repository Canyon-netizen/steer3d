"""Tests for hidden-state readout statistics."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.readout_atlas import (  # noqa: E402
    AtlasError,
    aggregate_layers,
    aggregate_marker_layers,
    best_layer,
    cohen_d,
    layer_stats,
    rank_auc,
)


def test_rank_auc_perfect_reversed_and_ties():
    labels = np.array([1, 1, 0, 0], dtype=bool)
    assert rank_auc([3, 4, 0, 1], labels) == 1.0
    assert rank_auc([0, 1, 3, 4], labels) == 0.0
    assert rank_auc([1, 1, 1, 1], labels) == 0.5


def test_rank_auc_returns_none_when_a_class_is_absent():
    assert rank_auc([1, 2, 3], [True, True, True]) is None
    assert rank_auc([1, 2, 3], [False, False, False]) is None


def test_cohen_d_handles_empty_and_constant_groups():
    assert cohen_d([], [1.0, 2.0]) is None
    assert cohen_d([1.0, 1.0], [1.0, 1.0]) is None
    assert cohen_d([2.0, 3.0], [0.0, 1.0]) > 0


def test_layer_stats_separate_cosine_from_norm_confound():
    n = 20
    rng = np.random.default_rng(0)
    norm = np.arange(1.0, n + 1.0)[:, None]
    proj = norm + rng.normal(0.0, 0.01, size=norm.shape)
    cos = np.full((n, 1), 0.5)
    labels = (np.arange(n) >= n // 2)
    rows = layer_stats(proj, cos, norm, labels)
    row = rows[0]
    assert row["auc_norm"] == 1.0
    assert row["auc"] == 1.0
    assert abs(row["auc_cos"] - 0.5) < 1e-12
    assert row["auc_proj_resid"] is not None
    assert abs(row["auc_proj_resid"] - 0.5) < 0.2
    assert row["mean_norm_marker"] > row["mean_norm_nonmarker"]


def test_layer_stats_reject_nonfinite_inputs():
    proj = np.zeros((4, 2))
    proj[0, 0] = float("nan")
    with pytest.raises(AtlasError, match="finite"):
        layer_stats(proj, np.zeros((4, 2)), np.ones((4, 2)), [True, False, True, False])


def test_aggregate_and_best_layer_prefer_oriented_cosine():
    per_traj = []
    for sign in (1.0, -1.0):
        rows = []
        for layer in range(3):
            rows.append({
                "layer": layer,
                "auc": 0.5,
                "auc_cos": 0.2 if layer == 1 else 0.5,
                "auc_cos_oriented": 0.8 if layer == 1 else 0.5,
                "cos_orientation": -1 if layer == 1 else 1,
                "auc_norm": 0.5,
                "auc_proj_resid": 0.5,
                "effect": 0.0,
                "effect_cos": 0.0,
                "mean_cos_marker": 0.1,
                "mean_cos_nonmarker": 0.2,
                "mean_norm_marker": 1.0,
                "mean_norm_nonmarker": 1.0,
                "mean_norm": 1.0,
                "n_marker": 2,
                "n_total": 4,
            })
        per_traj.append(rows)
    aggregate = aggregate_layers(per_traj)
    assert best_layer(aggregate) == 1
    assert aggregate[1]["mean_auc_cos_oriented"] == pytest.approx(0.8)
    assert aggregate[1]["cos_orientation"] == -1
    assert aggregate[1]["n_trajectories_negative_orientation"] == 2




def test_aggregate_marker_layers_keeps_signs_separate():
    def rows(auc_layer0, auc_layer1, n=10):
        return [
            {"layer": 0, "auc_cos": auc_layer0, "auc_cos_oriented": max(auc_layer0, 1 - auc_layer0),
             "mean_cos_marker": 0.1, "mean_cos_nonmarker": 0.2, "n_marker": n, "n_total": 100},
            {"layer": 1, "auc_cos": auc_layer1, "auc_cos_oriented": max(auc_layer1, 1 - auc_layer1),
             "mean_cos_marker": 0.1, "mean_cos_nonmarker": 0.2, "n_marker": n, "n_total": 100},
        ]

    per_trajectory = {
        7196: [rows(0.7, 0.6)],
        10061: [rows(0.2, 0.1)],
        80022: [],
    }
    result = aggregate_marker_layers(per_trajectory, [7196, 10061, 80022])
    assert result["7196"]["best_layer"] == 0
    assert result["7196"]["best_layer_orientation"] == 1
    assert result["10061"]["best_layer"] == 1
    assert result["10061"]["best_layer_orientation"] == -1
    assert result["80022"]["n_occurrences"] == 0
    assert result["80022"]["best_layer"] is None

