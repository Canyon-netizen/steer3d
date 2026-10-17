"""Model-level gradient helpers for steering-vector construction.

The pure helpers (normalize / mean_direction / sparse_direction) are testable
without a model.  compute_gradient and evaluate_direction are thin wrappers
around the actual HF model and the project's native_forward.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

import numpy as np


class GradientError(ValueError):
    """Raised when a gradient input is malformed."""


def normalize(vector: Any) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float64).reshape(-1)
    if not np.isfinite(array).all():
        raise GradientError("vector contains non-finite values")
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        raise GradientError("cannot normalize a zero vector")
    return array / norm


def mean_direction(gradients: Sequence[Any]) -> np.ndarray:
    """Normalize each gradient, average, then normalize the mean."""
    if not gradients:
        raise GradientError("no gradients to average")
    normalized = [normalize(gradient) for gradient in gradients]
    return normalize(np.mean(np.stack(normalized, axis=0), axis=0))


def sparse_direction(direction: Any, keep_fraction: float = 0.1) -> np.ndarray:
    """Keep the top-|value| coordinates and renormalize."""
    array = np.asarray(direction, dtype=np.float64).reshape(-1)
    if not (0.0 < keep_fraction <= 1.0):
        raise GradientError("keep_fraction must be in (0, 1]")
    keep = max(1, int(round(len(array) * keep_fraction)))
    order = np.argsort(-np.abs(array), kind="stable")
    sparse = np.zeros_like(array)
    sparse[order[:keep]] = array[order[:keep]]
    return normalize(sparse)


def logprob(logits: Any, token_id: int) -> float:
    x = np.asarray(logits, dtype=np.float64).reshape(-1)
    if not np.isfinite(x).all():
        raise GradientError("logits contain non-finite values")
    if not 0 <= token_id < len(x):
        raise GradientError("token id out of range")
    return float(x[token_id] - np.logaddexp.reduce(x))


def compute_gradient(model, input_ids, marker: int, layer: int = 20) -> Dict[str, Any]:
    """Return d log p(marker) / d h_layer at the last prefix position."""
    import torch

    with torch.enable_grad():
        output = model(input_ids=input_ids, use_cache=False, output_hidden_states=True)
        target = torch.log_softmax(output.logits[0, -1].float(), dim=-1)[marker]
        hidden = output.hidden_states[layer]
        gradient = torch.autograd.grad(target, hidden)[0][0, -1].detach().float().numpy()
        base_logp = float(target.detach())
        hidden_norm = float(torch.linalg.norm(hidden[0, -1]).detach())
    del output
    return {"gradient": gradient, "base_logp": base_logp, "hidden_norm": hidden_norm}


def evaluate_direction(
    model,
    input_ids,
    marker: int,
    direction: Any,
    alpha: float,
    baseline_logp: float | None = None,
) -> Dict[str, float]:
    """Run one injection and return log p(marker) and its difference from zero injection."""
    from core.neuron_mediation import native_forward

    if baseline_logp is None:
        baseline = native_forward(model, input_ids, injection_layer=20, vector=None, alpha=0.0)
        baseline_logp = logprob(baseline["logits"], marker)
    injected = native_forward(model, input_ids, injection_layer=20, vector=direction, alpha=alpha)
    injected_logp = logprob(injected["logits"], marker)
    return {
        "logp": injected_logp,
        "delta_logp": injected_logp - baseline_logp,
        "baseline_logp": baseline_logp,
        "probability": float(np.exp(injected_logp)),
    }
