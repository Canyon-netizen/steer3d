"""Tests for gradient-direction helpers."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.steering_gradient import (  # noqa: E402
    GradientError,
    logprob,
    mean_direction,
    normalize,
    sparse_direction,
)


def test_normalize_and_mean_direction():
    assert np.isclose(np.linalg.norm(normalize([3.0, 4.0])), 1.0)
    mean = mean_direction([np.array([1.0, 0.0]), np.array([0.0, 1.0])])
    assert np.isclose(np.linalg.norm(mean), 1.0)
    assert np.allclose(mean, np.array([1.0, 1.0]) / np.sqrt(2.0))
    with pytest.raises(GradientError):
        mean_direction([])


def test_sparse_direction_keeps_top_coordinates():
    vector = np.array([0.1, 5.0, -3.0, 0.2, 0.05])
    sparse = sparse_direction(vector, keep_fraction=0.4)
    assert np.isclose(np.linalg.norm(sparse), 1.0)
    assert sparse[0] == 0.0 and sparse[3] == 0.0
    assert sparse[1] > 0 and sparse[2] < 0
    with pytest.raises(GradientError):
        sparse_direction(vector, keep_fraction=0.0)


def test_logprob_matches_log_softmax():
    assert logprob([0.0, 0.0], 0) == pytest.approx(-np.log(2.0))
    assert logprob([1.0, 0.0], 0) == pytest.approx(-np.log(1.0 + np.exp(-1.0)))
    with pytest.raises(GradientError):
        logprob([0.0, 0.0], 3)

