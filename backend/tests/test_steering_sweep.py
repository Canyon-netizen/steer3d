"""Tests for the alpha / side-effect sweep helpers."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.steering_sweep import (  # noqa: E402
    SweepError,
    aggregate_sweep,
    entropy,
    kl_divergence,
    log_softmax,
    marker_summary,
)


def test_log_softmax_and_entropy():
    logits = np.array([0.0, 0.0, 0.0])
    logp = log_softmax(logits)
    assert np.isclose(np.exp(logp).sum(), 1.0)
    assert entropy(logits) == pytest.approx(np.log(3.0))
    assert kl_divergence(logits, logits) == pytest.approx(0.0)
    assert kl_divergence(logits, np.array([10.0, 0.0, 0.0])) > 0.0


def test_marker_summary_has_target_and_side_effect_fields():
    base = np.array([0.0, 1.0, 2.0, 3.0])
    injected = np.array([0.0, 1.0, 3.0, 2.0])
    summary = marker_summary(base, injected, target=3, other_markers=[0, 1, 2])
    assert summary["target_probability"] > 0
    assert summary["other_marker_mass"] > 0
    assert summary["kl"] >= 0
    assert np.isfinite(summary["entropy"])
    with pytest.raises(SweepError):
        marker_summary(base, injected, target=99, other_markers=[0])


def test_aggregate_sweep_means():
    rows = [
        {"marker": 7196, "direction": "mean_g", "dose": 0.02, "delta_logp": 0.2, "kl": 0.1, "delta_entropy": -0.2, "delta_other_marker_mass": 0.0},
        {"marker": 7196, "direction": "mean_g", "dose": 0.02, "delta_logp": 0.4, "kl": 0.3, "delta_entropy": -0.4, "delta_other_marker_mass": 0.0},
    ]
    aggregate = aggregate_sweep(rows)
    cell = aggregate["7196"]["directions"]["mean_g"][0]
    assert cell["mean_delta_logp"] == pytest.approx(0.3)
    assert cell["mean_kl"] == pytest.approx(0.2)
    assert cell["improved_fraction"] == 1.0
    with pytest.raises(SweepError):
        aggregate_sweep([])

