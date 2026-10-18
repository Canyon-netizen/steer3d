"""Tests for the unit-basis design math."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.unit_design import (  # noqa: E402
    blend_vectors,
    omp_unit_vectors,
    silu,
    silu_derivative,
    unit_activations,
    unit_coefficients,
    unit_direction_matrix,
)


def test_silu_derivative_matches_finite_difference():
    z = np.linspace(-3.0, 3.0, 21)
    eps = 1e-6
    finite = (silu(z + eps) - silu(z - eps)) / (2 * eps)
    assert np.allclose(silu_derivative(z), finite, atol=1e-7)


def test_unit_coefficients_match_directional_derivative():
    rng = np.random.default_rng(0)
    h = rng.standard_normal(8)
    gate = rng.standard_normal((6, 8)) * 0.2
    up = rng.standard_normal((6, 8)) * 0.2
    g = rng.standard_normal(8)
    g = g / np.linalg.norm(g)
    activation, z, value = unit_activations(h, gate, up)
    c = unit_coefficients(g, z, value, gate, up)
    eps = 1e-6
    plus, _, _ = unit_activations(h + eps * g, gate, up)
    minus, _, _ = unit_activations(h - eps * g, gate, up)
    assert np.allclose(c, (plus - minus) / (2 * eps), atol=1e-7)


def test_unit_direction_matrix_columns_are_normalized():
    rng = np.random.default_rng(1)
    h = rng.standard_normal(5)
    gate = rng.standard_normal((7, 5))
    up = rng.standard_normal((7, 5))
    matrix = unit_direction_matrix(h, gate, up)
    assert matrix.shape == (5, 7)
    assert np.allclose(np.linalg.norm(matrix, axis=0), 1.0)


def test_omp_reconstruction_improves_with_k():
    rng = np.random.default_rng(2)
    unit_matrix = rng.standard_normal((10, 18))
    unit_matrix = unit_matrix / np.linalg.norm(unit_matrix, axis=0, keepdims=True)
    target = unit_matrix[:, 0] + 0.5 * unit_matrix[:, 3]
    target = target / np.linalg.norm(target)
    result = omp_unit_vectors(target, unit_matrix, [1, 2, 5], max_iter=5)
    for k in [1, 2, 5]:
        assert result["vectors"][k].shape == (10,)
        assert np.isclose(np.linalg.norm(result["vectors"][k]), 1.0)
    assert result["records"][5]["reconstruction_cos"] >= result["records"][1]["reconstruction_cos"]


def test_blend_endpoints():
    unit = np.array([1.0, 0.0])
    dense = np.array([0.0, 1.0])
    assert np.allclose(blend_vectors(unit, dense, 0.0), unit)
    assert np.allclose(blend_vectors(unit, dense, 1.0), dense)
    mixed = blend_vectors(unit, dense, 0.5)
    assert np.isclose(np.linalg.norm(mixed), 1.0)

