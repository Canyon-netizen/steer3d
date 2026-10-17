"""Tests for the steering construction helpers."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.steering_construction import (  # noqa: E402
    ConstructionError,
    aggregate_candidates,
    blend,
    normalize,
    quadrant_counts,
    top_by,
)


def test_normalize_and_blend():
    assert np.isclose(np.linalg.norm(normalize([3.0, 4.0])), 1.0)
    mixed = blend(np.array([1.0, 0.0]), np.array([0.0, 1.0]), 1.0)
    assert np.isclose(np.linalg.norm(mixed), 1.0)
    assert mixed[0] > 0 and mixed[1] > 0
    with pytest.raises(ConstructionError):
        normalize([0.0, 0.0])


def test_quadrant_counts_with_explicit_threshold():
    response = [1.0, 2.0, 3.0, 4.0]
    contribution = [1.0, -1.0, 2.0, -2.0]
    counts = quadrant_counts(response, contribution, high_threshold=2.5)
    assert counts["carrier"] == 1
    assert counts["compensator"] == 1
    assert counts["silent"] == 1
    assert counts["neutral"] == 1


def test_top_by_respects_sign():
    values = [-3.0, 1.0, 5.0, -1.0, 4.0]
    assert top_by(values, 2, +1) == [2, 4]
    assert top_by(values, 2, -1) == [0, 3]
    with pytest.raises(ConstructionError):
        top_by(values, 1, 0)


def test_aggregate_candidates_mean_and_improved_fraction():
    sites = [
        {"marker": 7196, "candidates": {"w": {"delta_logp": -0.1}, "gradient": {"delta_logp": 0.2}}},
        {"marker": 7196, "candidates": {"w": {"delta_logp": -0.2}, "gradient": {"delta_logp": 0.1}}},
        {"marker": 10061, "candidates": {"w": {"delta_logp": 0.3}, "gradient": {"delta_logp": 0.4}}},
    ]
    aggregate = aggregate_candidates(sites)
    assert aggregate["7196"]["candidates"]["w"]["mean_delta_logp"] == pytest.approx(-0.15)
    assert aggregate["7196"]["candidates"]["gradient"]["improved_fraction"] == 1.0
    assert aggregate["10061"]["best_candidate"] == "gradient"
    with pytest.raises(ConstructionError):
        aggregate_candidates([])

