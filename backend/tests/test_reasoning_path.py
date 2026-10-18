"""Tests for reasoning-path geometry helpers."""
import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "reasoning_builder", ROOT / "backend/examples/build_reasoning_path.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downsample_keeps_anchor():
    builder = load_builder()
    indices = builder.downsample_indices(1000, 50, [400])
    assert len(indices) <= 51
    assert 400 in indices
    assert indices == sorted(set(indices))


def test_fit_pca_recovers_three_directions():
    builder = load_builder()
    rng = np.random.default_rng(0)
    base = rng.standard_normal((60, 8))
    base[:, 3:] *= 0.01
    mean, components, explained = builder.fit_pca(base, k=3)
    assert mean.shape == (8,)
    assert components.shape == (3, 8)
    assert len(explained) == 3
    assert explained[0] >= explained[1] >= explained[2]
    assert np.isfinite(explained).all()


def test_project_preserves_shape_and_centering():
    builder = load_builder()
    rng = np.random.default_rng(1)
    points = rng.standard_normal((20, 6))
    mean, components, _ = builder.fit_pca(points, k=2)
    projected = builder.project(points, mean, components)
    assert projected.shape == (20, 2)
    assert np.allclose(projected.mean(axis=0), 0.0, atol=1e-10)

