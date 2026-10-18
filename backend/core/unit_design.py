"""Interpretable unit-basis construction of a steering vector.

The injection-space vector is built from native SwiGLU unit input directions at
the injection layer:

    a_i(h) = silu(W_gate[i] . h) * (W_up[i] . h)
    u_i(h) = d a_i / d h
           = silu'(z_i) * v_i * W_gate[i] + silu(z_i) * W_up[i]
    c_i    = g . u_i
    v_k    = normalize( sum_{i in top-k by |c_i|} c_i * u_i )

This is a first-order local construction, not a causal claim.  It makes the
design variables explicit: layer, unit count k, coefficients c_i, and dose.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence, Tuple

import numpy as np


class UnitDesignError(ValueError):
    """Raised when a unit-basis vector cannot be built."""


def silu(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64)
    sig = 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))
    return z * sig


def silu_derivative(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64)
    sig = 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))
    return sig * (1.0 + z * (1.0 - sig))


def unit_activations(h: np.ndarray, gate_weight: np.ndarray, up_weight: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    h = np.asarray(h, dtype=np.float64)
    gate_weight = np.asarray(gate_weight, dtype=np.float64)
    up_weight = np.asarray(up_weight, dtype=np.float64)
    if h.ndim != 1 or gate_weight.shape[1] != h.shape[0] or up_weight.shape != gate_weight.shape:
        raise UnitDesignError("expected h [d] and gate/up weights [m, d]")
    z = gate_weight @ h
    value = up_weight @ h
    return silu(z) * value, z, value


def unit_coefficients(g: np.ndarray, z: np.ndarray, value: np.ndarray, gate_weight: np.ndarray, up_weight: np.ndarray) -> np.ndarray:
    g = np.asarray(g, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    value = np.asarray(value, dtype=np.float64)
    if g.ndim != 1 or z.shape != value.shape or z.shape[0] != gate_weight.shape[0]:
        raise UnitDesignError("expected g [d], z/value [m], weights [m, d]")
    gate_dot = gate_weight @ g
    up_dot = up_weight @ g
    return silu_derivative(z) * value * gate_dot + silu(z) * up_dot


def unit_input_vector(
    coefficients: np.ndarray,
    z: np.ndarray,
    value: np.ndarray,
    gate_weight: np.ndarray,
    up_weight: np.ndarray,
    k: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    coefficients = np.asarray(coefficients, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    value = np.asarray(value, dtype=np.float64)
    if not 1 <= int(k) <= coefficients.shape[0]:
        raise UnitDesignError("k out of range")
    order = np.argsort(-np.abs(coefficients))[: int(k)]
    mask = np.zeros_like(coefficients)
    mask[order] = 1.0
    weighted_gate = mask * coefficients * silu_derivative(z) * value
    weighted_up = mask * coefficients * silu(z)
    vector = gate_weight.T @ weighted_gate + up_weight.T @ weighted_up
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm == 0.0:
        raise UnitDesignError("zero/nonfinite unit vector")
    return vector / norm, order, coefficients


def normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm == 0.0:
        raise UnitDesignError("zero/nonfinite vector")
    return vector / norm


def blend_vectors(unit_vector: np.ndarray, dense_vector: np.ndarray, unit_weight: float) -> np.ndarray:
    """normalize((1-w)*unit + w*dense), w=0 unit basis, w=1 mean g."""
    if not 0.0 <= float(unit_weight) <= 1.0:
        raise UnitDesignError("blend weight must be in [0, 1]")
    return normalize((1.0 - float(unit_weight)) * normalize(unit_vector) + float(unit_weight) * normalize(dense_vector))


def average_vectors(vectors: Sequence[np.ndarray]) -> np.ndarray:
    if not vectors:
        raise UnitDesignError("no vectors to average")
    stacked = np.stack([normalize(vector) for vector in vectors], axis=0)
    return normalize(stacked.mean(axis=0))


def top_units(
    coefficients: Sequence[np.ndarray],
    k: int = 12,
    layer: int = 20,
) -> list:
    if not coefficients:
        return []
    stacked = np.stack([np.asarray(row, dtype=np.float64) for row in coefficients], axis=0)
    mean = stacked.mean(axis=0)
    count = (np.abs(stacked) >= np.quantile(np.abs(stacked), 0.98, axis=1, keepdims=True)).sum(axis=0)
    order = np.argsort(-np.abs(mean))[: int(k)]
    return [
        {
            "layer": int(layer),
            "unit": int(index),
            "mean_coefficient": float(mean[index]),
            "sign": int(np.sign(mean[index])),
            "high_frequency": int(count[index]),
        }
        for index in order
    ]


def unit_direction_matrix(h: np.ndarray, gate_weight: np.ndarray, up_weight: np.ndarray) -> np.ndarray:
    """Columns are native SwiGLU unit input directions at reference state h."""
    h = np.asarray(h, dtype=np.float64)
    gate_weight = np.asarray(gate_weight, dtype=np.float64)
    up_weight = np.asarray(up_weight, dtype=np.float64)
    z = gate_weight @ h
    value = up_weight @ h
    derivative = silu_derivative(z)
    activation = silu(z)
    matrix = gate_weight.T * (derivative * value)[None, :] + up_weight.T * activation[None, :]
    norms = np.linalg.norm(matrix, axis=0)
    if not np.isfinite(norms).all() or (norms == 0).any():
        raise UnitDesignError("invalid unit direction matrix")
    return matrix / norms[None, :]


def omp_unit_vectors(
    gradient: np.ndarray,
    unit_matrix: np.ndarray,
    k_grid: Sequence[int],
    max_iter: int | None = None,
) -> Dict[str, Any]:
    """Greedy orthogonal matching pursuit of g in the native unit basis.

    Returns normalized vectors at each k, the selected unit indices, least-squares
    coefficients, and the reconstruction cosine.  This is a sparse coding of the
    mean gradient, not a causal decomposition.
    """
    gradient = np.asarray(gradient, dtype=np.float64)
    unit_matrix = np.asarray(unit_matrix, dtype=np.float64)
    if unit_matrix.shape[0] != gradient.shape[0]:
        raise UnitDesignError("shape mismatch between gradient and unit matrix")
    target = gradient / np.linalg.norm(gradient)
    max_k = max(int(k) for k in k_grid) if max_iter is None else int(max_iter)
    max_k = min(max_k, unit_matrix.shape[1], gradient.shape[0])
    selected: list = []
    residual = target.copy()
    vectors = {}
    records = {}
    for step in range(max_k):
        correlations = unit_matrix.T @ residual
        if selected:
            correlations[np.asarray(selected, dtype=np.int64)] = 0.0
        index = int(np.argmax(np.abs(correlations)))
        if abs(float(correlations[index])) < 1e-12:
            break
        selected.append(index)
        basis = unit_matrix[:, selected]
        coefficients, *_ = np.linalg.lstsq(basis, target, rcond=1e-8)
        reconstruction = basis @ coefficients
        residual = target - reconstruction
        current_k = step + 1
        if current_k in k_grid:
            norm = float(np.linalg.norm(reconstruction))
            vectors[current_k] = reconstruction / norm if norm > 0 else reconstruction
            records[current_k] = {
                "k": current_k,
                "selected": list(selected),
                "coefficients": [float(value) for value in coefficients],
                "reconstruction_cos": float(np.dot(reconstruction, target) / max(np.linalg.norm(reconstruction), 1e-12)),
                "residual_norm": float(np.linalg.norm(residual)),
            }
        if np.linalg.norm(residual) < 1e-9:
            break
    for k in k_grid:
        if k not in vectors:
            # fill remaining grid points with the last reconstruction
            vectors[k] = vectors[max(vectors)] if vectors else target.copy()
            records[k] = dict(records[max(records)]) if records else {"k": k, "selected": [], "coefficients": [], "reconstruction_cos": 0.0, "residual_norm": 1.0}
    return {"vectors": vectors, "records": records}
