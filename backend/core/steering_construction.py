"""Pure helpers for the steering-construction probe.

The probe asks: for a fixed hidden-state prefix and a target readout f
(log p of a marker token), which local direction increases f, and which native
units carry or oppose that change?  Model forward/backward lives in the example
script; these helpers stay testable without a model.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np


class ConstructionError(ValueError):
    """Raised when the probe inputs are malformed."""


def normalize(vector: Any) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float64).reshape(-1)
    if not np.isfinite(array).all():
        raise ConstructionError("vector contains non-finite values")
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        raise ConstructionError("cannot normalize a zero vector")
    return array / norm


def blend(vector: Any, gradient: Any, weight: float) -> np.ndarray:
    """Normalize vector + weight * gradient."""
    v = np.asarray(vector, dtype=np.float64).reshape(-1)
    g = np.asarray(gradient, dtype=np.float64).reshape(-1)
    if v.shape != g.shape:
        raise ConstructionError("vector and gradient must have the same shape")
    if not np.isfinite(weight):
        raise ConstructionError("weight must be finite")
    return normalize(v + weight * g)


def quadrant_counts(
    response: Any,
    contribution: Any,
    high_threshold: Optional[float] = None,
) -> Dict[str, int]:
    """Split units by response (high/low) and contribution sign.

    carrier: high response, positive contribution
    compensator: high response, negative contribution
    silent: low response, positive contribution
    neutral: low response, non-positive contribution
    """
    r = np.asarray(response, dtype=float).reshape(-1)
    c = np.asarray(contribution, dtype=float).reshape(-1)
    if r.shape != c.shape:
        raise ConstructionError("response and contribution must have the same shape")
    if not (np.isfinite(r).all() and np.isfinite(c).all()):
        raise ConstructionError("response/contribution contain non-finite values")
    threshold = float(np.median(r)) if high_threshold is None else float(high_threshold)
    high = r >= threshold
    positive = c > 0
    return {
        "carrier": int(np.sum(high & positive)),
        "compensator": int(np.sum(high & ~positive & (c < 0))),
        "silent": int(np.sum(~high & positive)),
        "neutral": int(np.sum(~high & ~positive)),
        "threshold": threshold,
    }


def top_by(values: Any, k: int, sign: int = 1) -> List[int]:
    """Indices of the k largest sign*values, restricted to that sign."""
    if k < 1:
        raise ConstructionError("k must be positive")
    array = np.asarray(values, dtype=float).reshape(-1)
    if not np.isfinite(array).all():
        raise ConstructionError("values contain non-finite values")
    if sign > 0:
        candidates = np.nonzero(array > 0)[0]
        order = candidates[np.argsort(-array[candidates], kind="stable")]
    elif sign < 0:
        candidates = np.nonzero(array < 0)[0]
        order = candidates[np.argsort(array[candidates], kind="stable")]
    else:
        raise ConstructionError("sign must be +1 or -1")
    return [int(index) for index in order[:k]]


def aggregate_candidates(sites: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Mean delta and improved fraction per candidate, grouped by marker."""
    if not sites:
        raise ConstructionError("no sites to aggregate")
    candidate_names = list(sites[0]["candidates"].keys())
    by_marker: Dict[str, Dict[str, Any]] = {}
    for site in sites:
        marker = str(site["marker"])
        entry = by_marker.setdefault(marker, {"n_sites": 0, "candidates": {name: [] for name in candidate_names}})
        entry["n_sites"] += 1
        for name in candidate_names:
            delta = float(site["candidates"][name]["delta_logp"])
            if not np.isfinite(delta):
                raise ConstructionError("candidate delta is not finite")
            entry["candidates"][name].append(delta)
    output: Dict[str, Any] = {}
    for marker, entry in by_marker.items():
        summary = {}
        for name, values in entry["candidates"].items():
            array = np.asarray(values, dtype=float)
            summary[name] = {
                "mean_delta_logp": float(array.mean()),
                "improved_fraction": float(np.mean(array > 0)),
                "n_sites": int(len(array)),
            }
        best = max(summary, key=lambda name: summary[name]["mean_delta_logp"])
        output[marker] = {
            "n_sites": entry["n_sites"],
            "candidates": summary,
            "best_candidate": best,
        }
    return output
