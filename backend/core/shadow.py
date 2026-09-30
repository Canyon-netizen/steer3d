"""Counterfactual ("shadow") tracking for intervention experiments.

Why this exists
---------------
Injecting a steering vector and watching the trajectory move does not
tell you what the intervention *did*. The trajectory moves anyway —
every token changes the state. To attribute a change to the
intervention you need a counterfactual: the same computation run
without the vector, over the same inputs.

So every steered step runs **two** forward passes:

  * the **primary** stream, with the steering vector added at layer L;
  * the **shadow** stream, identical except the vector is absent.

Both consume the *same* token (teacher-forced from the primary
stream's own argmax). That is deliberate: it makes the comparison
well-posed. The shadow asks "given exactly this text, where would the
state have been?" — a pure question about representation. If instead
each stream fed its own argmax, any divergence would compound into a
different sentence and you could no longer tell a representational
change from a behavioural one.

What you get per step
---------------------
For every layer, the cosine between the primary and shadow residual
streams, and the L2 shift normalised by the shadow state's own norm.
Plotted over the sequence, that is the "how far did my intervention
push the internals, and how fast does it wash out downstream?"
curve — the single most useful readout in an activation-steering
experiment, and the one this project was missing.

Cost
----
Doubles the per-step forward cost and roughly doubles KV-cache
memory. Both are acceptable for a 1.7B model on a single card, and
both are avoidable: pass ``enabled=False`` to get the primary stream
only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class LayerShift:
    """Per-layer divergence between the steered and unsteered streams."""

    layer: int
    cosine: float          # cos(h_primary, h_shadow) at this layer
    shift: float           # ||h_primary - h_shadow||
    rel_shift: float       # shift / ||h_shadow|| — scale-free
    projection: float      # <h_shadow, v_hat> along the steering direction


@dataclass
class StepShadow:
    """One step's worth of primary-vs-shadow comparison."""

    step_id: int
    token: str
    layers: List[LayerShift] = field(default_factory=list)
    logit_cosine: float = 0.0        # agreement of the output distributions
    logit_kl: float = 0.0            # KL(shadow || primary) in nats
    token_match: bool = True         # did both streams argmax the same token?
    entropy_primary: float = 0.0
    entropy_shadow: float = 0.0


class ShadowTracker:
    """Accumulates primary-vs-shadow comparisons across a stream.

    Usage inside a decode loop::

        tracker = ShadowTracker(steer_vector=v, n_layers=28)
        # ... run both streams, get their per-layer hidden states ...
        step = tracker.compare(step_id, token, primary_hs, shadow_hs,
                               primary_logits, shadow_logits)
        tracker.steps.append(step)

    ``primary_hs`` and ``shadow_hs`` are sequences of length
    ``n_layers + 1`` (embedding output through final layer), each
    ``(d_model,)`` — the same layout as ``output.hidden_states``.
    """

    def __init__(
        self,
        steer_vector: Optional[np.ndarray],
        n_layers: int,
        enabled: bool = True,
        max_steps: Optional[int] = None,
    ):
        self.n_layers = n_layers
        self.enabled = enabled and steer_vector is not None
        self.max_steps = max_steps
        self.steps: List[StepShadow] = []

        if self.enabled:
            v = np.asarray(steer_vector, dtype=np.float32).reshape(-1)
            n = np.linalg.norm(v)
            self.unit = (v / n).astype(np.float32) if n > 1e-8 else v
            self.norm = float(n)
        else:
            self.unit = None
            self.norm = 0.0

    # ------------------------------------------------------------------

    def compare(
        self,
        step_id: int,
        token: str,
        primary_hs,
        shadow_hs,
        primary_logits: Optional[np.ndarray] = None,
        shadow_logits: Optional[np.ndarray] = None,
    ) -> Optional[StepShadow]:
        """Build one :class:`StepShadow` from this step's two streams.

        ``primary_hs`` / ``shadow_hs``: iterables of per-layer vectors
        (index 0 = embedding output, matching ``hidden_states``).
        Returns None when tracking is disabled or the step cap is hit.
        """
        if not self.enabled:
            return None
        if self.max_steps is not None and len(self.steps) >= self.max_steps:
            return None

        layers: List[LayerShift] = []
        for li, (p, s) in enumerate(zip(primary_hs, shadow_hs)):
            p = np.asarray(p, dtype=np.float32).reshape(-1)
            s = np.asarray(s, dtype=np.float32).reshape(-1)

            cos = float(
                np.clip(
                    np.dot(p, s) / (np.linalg.norm(p) * np.linalg.norm(s) + 1e-8),
                    -1.0, 1.0,
                )
            )
            shift = float(np.linalg.norm(p - s))
            s_norm = float(np.linalg.norm(s))
            rel = shift / (s_norm + 1e-8)
            proj = float(np.dot(s, self.unit))
            layers.append(LayerShift(
                # HF's `hidden_states` tuple is [embeddings, out(block0),
                # out(block1), …], so index i holds the output of block
                # i-1. A pre-hook on `layers[k]` alters that block's
                # *input*, which therefore first appears in index k+1 —
                # i.e. label k. Subtracting one is what puts the spike at
                # the layer you actually injected at.
                layer=li - 1,
                cosine=cos,
                shift=shift,
                rel_shift=rel,
                projection=proj,
            ))

        logit_cos, logit_kl, tok_match = 0.0, 0.0, True
        ent_p = ent_s = 0.0
        if primary_logits is not None and shadow_logits is not None:
            pl = np.asarray(primary_logits, dtype=np.float64).reshape(-1)
            sl = np.asarray(shadow_logits, dtype=np.float64).reshape(-1)
            logit_cos = float(
                np.dot(pl, sl) / (np.linalg.norm(pl) * np.linalg.norm(sl) + 1e-12)
            )
            ent_p = _entropy(pl)
            ent_s = _entropy(sl)
            logit_kl = _kl(sl, pl)
            tok_match = int(np.argmax(pl)) == int(np.argmax(sl))

        step = StepShadow(
            step_id=step_id,
            token=token,
            layers=layers,
            logit_cosine=logit_cos,
            logit_kl=logit_kl,
            token_match=tok_match,
            entropy_primary=ent_p,
            entropy_shadow=ent_s,
        )
        self.steps.append(step)
        return step

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def layer_curve(self) -> dict:
        """Mean cosine / rel-shift per layer, averaged over all steps.

        This is the "does the perturbation survive downstream?" curve.
        A drop back toward 1.0 means the model absorbed the injection;
        a flat curve near the injection layer means it is still riding
        the perturbation all the way to the logits.

        The returned arrays are aligned index-for-index with ``layer``:
        label -1 is the embedding output and label ``L`` is the output
        of block ``L-1`` — which is the residual stream entering block
        ``L``, i.e. where a vector injected at layer ``L`` first shows
        up. Both lists run in the same natural order so a consumer can
        zip them without off-by-one bookkeeping.
        """
        if not self.steps:
            return {}
        n = len(self.steps[0].layers)
        cos = [0.0] * n
        rel = [0.0] * n
        for st in self.steps:
            for i, ls in enumerate(st.layers):
                cos[i] += ls.cosine
                rel[i] += ls.rel_shift
        return {
            "layer": list(range(-1, n - 1)),   # -1 = embedding, 0.. = blocks
            "mean_cosine": [c / len(self.steps) for c in cos],
            "mean_rel_shift": [r / len(self.steps) for r in rel],
        }

    def summary(self) -> dict:
        """Aggregate stats for the intervention as a whole.

        Unusable steps (non-finite logits or states) are counted and
        excluded from the means rather than being allowed to poison
        every aggregate via np.mean's NaN propagation. ``n_bad_steps``
        is reported so a reader can tell a clean run from a partial one.
        """
        if not self.steps:
            return {"n_steps": 0}
        curve = self.layer_curve()

        good = [
            s for s in self.steps
            if np.isfinite(s.logit_kl) and np.isfinite(s.entropy_primary)
            and all(np.isfinite(ls.cosine) for ls in s.layers)
        ]
        n_bad = len(self.steps) - len(good)
        basis = good if good else self.steps

        divergences = [1.0 - ls.cosine for st in basis for ls in st.layers]

        def _safe_mean(vals):
            arr = np.asarray(vals, dtype=np.float64)
            arr = arr[np.isfinite(arr)]
            return float(arr.mean()) if arr.size else float("nan")

        return {
            "n_steps": len(self.steps),
            "n_bad_steps": n_bad,
            "steer_norm": self.norm,
            "token_agreement": (
                sum(1 for s in basis if s.token_match) / len(basis)
            ),
            "first_diverged_step": next(
                (s.step_id for s in self.steps if not s.token_match), None
            ),
            "mean_logit_kl": _safe_mean([s.logit_kl for s in basis]),
            "mean_entropy_primary": _safe_mean([s.entropy_primary for s in basis]),
            "mean_entropy_shadow": _safe_mean([s.entropy_shadow for s in basis]),
            "max_divergence": float(max(divergences)) if divergences else 0.0,
            "mean_divergence": float(np.mean(divergences)) if divergences else 0.0,
            "layer_curve": curve,
        }


# ---------------------------------------------------------------------------
# small numeric helpers
# ---------------------------------------------------------------------------


def _log_softmax(x: np.ndarray) -> np.ndarray:
    """Log-softmax that refuses to emit NaN from non-finite inputs.

    A single NaN in the logits used to flow straight into the summary
    aggregates, where ``np.mean`` and ``max`` turn one bad step into a
    silently wrong number for the whole run. Returning NaN explicitly
    is better than returning a plausible-looking finite value: the
    caller can see that the step was unusable.
    """
    x = np.asarray(x, dtype=np.float64)
    if not np.all(np.isfinite(x)):
        return np.full_like(x, np.nan)
    m = x.max()
    shifted = x - m
    # exp of a large negative underflows to 0, which is correct; the sum
    # is at least exp(0)=1 so it can never be zero.
    return shifted - np.log(np.exp(shifted).sum())


def _entropy(logits: np.ndarray) -> float:
    lp = _log_softmax(logits)
    if not np.all(np.isfinite(lp)):
        return float("nan")
    return float(-np.sum(np.exp(lp) * lp))


def _kl(p_logits: np.ndarray, q_logits: np.ndarray) -> float:
    """KL(p || q) in nats, from unnormalised logit vectors.

    Uses ``np.maximum`` rather than Python's ``max`` on purpose:
    ``max(0.0, nan)`` evaluates to ``0.0`` in Python, so a NaN would be
    laundered into a perfectly confident "these two distributions are
    identical" reading. KL is non-negative by construction, but the
    non-negativity clamp must not swallow a failed computation.
    """
    lp = _log_softmax(p_logits)
    lq = _log_softmax(q_logits)
    if not (np.all(np.isfinite(lp)) and np.all(np.isfinite(lq))):
        return float("nan")
    val = float(np.sum(np.exp(lp) * (lp - lq)))
    return float(np.maximum(0.0, val))
