"""Steering vector extraction and application.

Implements a clean version of Contrastive Activation Addition (CAA)
following:
  Turner et al., "Activation Addition: Steering Language Models
  Without Optimization", 2023.
  Panickssery et al., "Steering Llama 2 via Contrastive Activation
  Addition", 2023.

The design keeps the model + hook interface abstract so we can
swap in nnsight, TransformerLens or a manual PyTorch hook without
touching the rest of the system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np


@dataclass
class SteeringVector:
    """A unit-norm direction in the residual-stream activation space."""

    name: str
    direction: np.ndarray  # shape (d_model,), unit-normed

    def scaled(self, alpha: float) -> np.ndarray:
        return self.direction * float(alpha)


# ---------------------------------------------------------------------------
# Step 1 — collect contrastive activations
# ---------------------------------------------------------------------------


def collect_residual_activations(
    run_with_text: Callable[[str], np.ndarray],
    positive_prompts: Sequence[str],
    negative_prompts: Sequence[str],
) -> np.ndarray:
    """Run each prompt through the model and return residual-stream
    activations at the last token position.

    The `run_with_text` callable is supplied by the host environment
    (model_runner.py). It must return a 1-D numpy vector of shape
    (d_model,) per call.

    Returns an array of shape (2 * N, d_model) where the first N
    rows are positive prompts and the last N rows are negative.
    """
    if len(positive_prompts) != len(negative_prompts):
        raise ValueError("positive and negative prompts must have the same length")
    pos = np.stack([run_with_text(p) for p in positive_prompts], axis=0)
    neg = np.stack([run_with_text(p) for p in negative_prompts], axis=0)
    return np.concatenate([pos, neg], axis=0)


def mean_difference_steering(
    pos_neg_activations: np.ndarray,
    n_pairs: int,
    normalize: bool = True,
) -> np.ndarray:
    """Compute the CAA steering vector from collected activations.

    pos_neg_activations shape: (2 * n_pairs, d_model)
    The first n_pairs rows are positive, the last n_pairs are negative.
    """
    pos = pos_neg_activations[:n_pairs]
    neg = pos_neg_activations[n_pairs:]
    v = pos.mean(axis=0) - neg.mean(axis=0)
    if normalize:
        norm = np.linalg.norm(v)
        if norm > 0:
            v = v / norm
    return v


def extract_all_presets(
    presets: Dict[str, Dict[str, str]],
    collect_fn: Callable[[str], np.ndarray],
    n_pairs_per_preset: int = 4,
) -> Dict[str, SteeringVector]:
    """Extract a SteeringVector for each preset at boot time.

    The prompts in each preset are repeated (with light paraphrasing
    by prefix variation in production) to give the contrastive estimate
    a stable direction.
    """
    out: Dict[str, SteeringVector] = {}
    for name, spec in presets.items():
        pos = [spec["positive"]] * n_pairs_per_preset
        neg = [spec["negative"]] * n_pairs_per_preset
        activations = collect_residual_activations(collect_fn, pos, neg)
        direction = mean_difference_steering(activations, n_pairs_per_preset)
        out[name] = SteeringVector(name=name, direction=direction)
    return out


# ---------------------------------------------------------------------------
# Step 2 — apply a steering vector at inference time
# ---------------------------------------------------------------------------


def make_additive_steer_hook(
    steering_vector: np.ndarray,
    alpha: float,
):
    """Return a forward-pre-hook that adds (alpha * steering_vector)
    to the residual stream at the target layer's input.
    """
    sv = np.asarray(steering_vector, dtype=np.float32)
    a = float(alpha)

    def hook(module, inputs):
        # inputs is a tuple; first element is the hidden state.
        x = inputs[0]
        # Add-onwards only for 3-D hidden states (T, B, d_model)
        if x.dim() == 3:
            new_x = x + a * sv.to(x.device).to(x.dtype)
            return (new_x,) + inputs[1:]
        return None

    return hook


# ---------------------------------------------------------------------------
# Step 3 — synthesize plausible steering vectors without a real model.
# Useful for the demo_synthetic backend so that the framework is
# runnable on a laptop without a GPU.
# ---------------------------------------------------------------------------


def synthetic_steering_vector(
    name: str,
    d_model: int = 4096,
    seed: int = 0,
) -> SteeringVector:
    """Build a deterministic fake steering vector keyed by `name`.

    Different names yield orthogonal-ish directions, which is enough
    to make the 3D paths diverge visibly in the visualization.
    """
    rng = np.random.default_rng(abs(hash(name)) % (2**32) + seed)
    v = rng.standard_normal(d_model).astype(np.float32)
    v = v / np.linalg.norm(v)
    return SteeringVector(name=name, direction=v)