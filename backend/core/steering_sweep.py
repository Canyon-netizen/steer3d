"""Pure metrics for the alpha / side-effect sweep."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

import numpy as np


class SweepError(ValueError):
    """Raised when sweep inputs are malformed."""


def log_softmax(logits: Any) -> np.ndarray:
    x = np.asarray(logits, dtype=np.float64).reshape(-1)
    if not np.isfinite(x).all():
        raise SweepError("logits contain non-finite values")
    shifted = x - np.max(x)
    return shifted - np.logaddexp.reduce(shifted)


def entropy(logits: Any) -> float:
    logp = log_softmax(logits)
    p = np.exp(logp)
    return float(-np.sum(p * logp))


def kl_divergence(base_logits: Any, injected_logits: Any) -> float:
    logp_base = log_softmax(base_logits)
    logp_injected = log_softmax(injected_logits)
    p_base = np.exp(logp_base)
    return float(np.sum(p_base * (logp_base - logp_injected)))


def logprob(logits: Any, token_id: int) -> float:
    logp = log_softmax(logits)
    if not 0 <= token_id < len(logp):
        raise SweepError("token id out of range")
    return float(logp[token_id])


def marker_summary(
    base_logits: Any,
    injected_logits: Any,
    target: int,
    other_markers: Sequence[int],
) -> Dict[str, float]:
    """Target/side-effect metrics for one injection."""
    base = np.asarray(base_logits, dtype=np.float64).reshape(-1)
    injected = np.asarray(injected_logits, dtype=np.float64).reshape(-1)
    if base.shape != injected.shape:
        raise SweepError("base and injected logits must have the same shape")
    p_base = np.exp(log_softmax(base))
    p_injected = np.exp(log_softmax(injected))
    others = [int(marker) for marker in other_markers if int(marker) != int(target)]
    return {
        "target_logp": logprob(injected, target),
        "target_probability": float(p_injected[target]),
        "other_marker_mass": float(p_injected[others].sum()),
        "kl": kl_divergence(base, injected),
        "entropy": entropy(injected),
        "top1_id": int(np.argmax(injected)),
    }


def aggregate_sweep(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-(marker, direction, dose) means and improved fractions."""
    if not rows:
        raise SweepError("no rows to aggregate")
    groups: Dict[str, Dict[str, Dict[str, List[Mapping[str, Any]]]]] = {}
    for row in rows:
        marker = str(row["marker"])
        direction = str(row["direction"])
        dose = float(row["dose"])
        groups.setdefault(marker, {}).setdefault(direction, {}).setdefault(str(dose), []).append(row)

    output: Dict[str, Any] = {}
    for marker, directions in groups.items():
        output[marker] = {"directions": {}}
        for direction, doses in directions.items():
            dose_rows = []
            for dose in sorted(doses, key=float):
                items = doses[dose]
                delta = np.asarray([float(item["delta_logp"]) for item in items], dtype=float)
                kl = np.asarray([float(item["kl"]) for item in items], dtype=float)
                delta_entropy = np.asarray([float(item["delta_entropy"]) for item in items], dtype=float)
                delta_other = np.asarray([float(item["delta_other_marker_mass"]) for item in items], dtype=float)
                dose_rows.append({
                    "dose": float(dose),
                    "n_sites": len(items),
                    "mean_delta_logp": float(delta.mean()),
                    "improved_fraction": float(np.mean(delta > 0)),
                    "mean_kl": float(kl.mean()),
                    "mean_delta_entropy": float(delta_entropy.mean()),
                    "mean_delta_other_marker_mass": float(delta_other.mean()),
                })
            output[marker]["directions"][direction] = dose_rows
    return output
