"""Steering vector registry and residual-stream intervention.

This module is the backend half of the intervention story. It has two jobs:

1. **Registry** — load the `.npy` vectors produced by
   ``examples/compute_steering_vectors.py`` and hand them out by name
   (with metadata: which layer they were extracted at, how many
   samples backed them, what their validation looked like).

2. **Intervention** — given a direction name, a strength and a layer,
   return the vector to add to the residual stream, rescaled to that
   layer. ``inject`` is the callback the WebSocket server hands to
   ``runner.stream()``; the runner adds whatever it returns to the
   residual stream before each forward.

The key detail for interpretability: a steering vector is only
meaningful relative to the *scale of the residual stream* at the layer
where it is applied. Injecting a unit-norm vector at full strength
would be an enormous perturbation. So `scaled` multiplies by the
measured RMS norm of the hidden states at that layer, which keeps
"strength = 0.1" meaning roughly "move the state 10% of its own
magnitude", independent of the layer.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np


DEFAULT_VECTOR_DIR = Path(__file__).resolve().parent.parent / "examples" / "output" / "steering_vectors"


# Directions offered in the UI. Each maps to a `.npy` in the registry
# plus a human-readable label; the frontend mirrors these ids.
PRESET_DIRECTIONS: List[dict] = [
    {"id": "confidence_up", "label": "Confidence ↑",
     "hint": "lower entropy, firmer answers"},
    {"id": "confidence_down", "label": "Confidence ↓",
     "hint": "raise entropy, explore more"},
    {"id": "reasoning_deep", "label": "Deep reasoning",
     "hint": "push toward late-chain states"},
    {"id": "reasoning_shallow", "label": "Quick answer",
     "hint": "push toward early setup states"},
    {"id": "caution", "label": "Cautious",
     "hint": "the verify-your-work state"},
    {"id": "creativity", "label": "Creative",
     "hint": "the <think> scratchpad state"},
]


class SteeringRegistry:
    """Loads steering vectors from disk once and serves them by name."""

    def __init__(self, vector_dir: Optional[Path] = None):
        self.vector_dir = Path(vector_dir) if vector_dir else DEFAULT_VECTOR_DIR
        self._vectors: Dict[str, np.ndarray] = {}
        self._meta: Dict[str, dict] = {}
        self._rms: Dict[int, float] = {}     # layer -> RMS hidden-state norm
        self._lock = threading.Lock()
        self.loaded = False
        self.load_error: Optional[str] = None

    # -- loading ---------------------------------------------------------

    def load(self) -> bool:
        """Read every ``<name>.npy`` + ``steering_vectors.json`` in the dir.

        Returns True if at least one vector was loaded. Never raises —
        a missing registry should degrade the feature, not the server.
        """
        with self._lock:
            self._vectors.clear()
            self._meta.clear()
            self.loaded = False
            self.load_error = None

        meta_path = self.vector_dir / "steering_vectors.json"
        if not self.vector_dir.is_dir():
            self.load_error = f"vector dir not found: {self.vector_dir}"
            return False

        meta: Dict[str, dict] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except Exception as e:
                self.load_error = f"could not parse {meta_path.name}: {e}"

        found = 0
        for name, info in meta.items():
            npy = self.vector_dir / f"{name}.npy"
            if not npy.exists():
                continue
            try:
                v = np.load(npy).astype(np.float32).reshape(-1)
                if not np.all(np.isfinite(v)):
                    continue
                self._vectors[name] = v / (np.linalg.norm(v) + 1e-8)
                self._meta[name] = info
                found += 1
            except Exception:
                continue

        # If the JSON is missing or stale, still pick up any loose .npy files
        # so a hand-placed vector works without re-running the extractor.
        if found == 0:
            for npy in sorted(self.vector_dir.glob("*.npy")):
                name = npy.stem
                try:
                    v = np.load(npy).astype(np.float32).reshape(-1)
                    if np.all(np.isfinite(v)):
                        self._vectors[name] = v / (np.linalg.norm(v) + 1e-8)
                        self._meta.setdefault(name, {"layer": None})
                        found += 1
                except Exception:
                    continue

        self.loaded = found > 0
        if not self.loaded and self.load_error is None:
            self.load_error = f"no usable vectors in {self.vector_dir}"
        return self.loaded

    def load_layer_scales(self, profiles_path: Optional[Path] = None) -> int:
        """Seed the per-layer RMS scale from a measured profile file.

        ``measure_layers.py`` records ``mean_norm`` per layer — the
        average ‖h‖ over real trajectories. Feeding those in is what
        makes the UI's strength slider mean "a fraction of the state it
        is perturbing" instead of an arbitrary number. Without this,
        every injection through the web UI is mis-scaled by two or more
        orders of magnitude, silently.

        Returns the number of layers calibrated.
        """
        if profiles_path is None:
            profiles_path = (
                self.vector_dir.parent / "layer_profiles.json"
            )
        profiles_path = Path(profiles_path)
        if not profiles_path.exists():
            return 0
        try:
            data = json.loads(profiles_path.read_text())
        except Exception:
            return 0

        n = 0
        for entry in data.get("layers", []):
            layer = entry.get("layer")
            norm = entry.get("mean_norm")
            if layer is None or norm is None:
                continue
            # ‖h‖, not ‖h‖/√d — the injection is a full-space vector and
            # has to be compared against the full-space state norm.
            self.set_layer_rms(int(layer), float(norm))
            n += 1
        return n

    # -- accessors -------------------------------------------------------

    @property
    def names(self) -> List[str]:
        return sorted(self._vectors.keys())

    def has(self, name: str) -> bool:
        return name in self._vectors

    def meta(self, name: str) -> dict:
        return dict(self._meta.get(name, {}))

    def unit_vector(self, name: str) -> Optional[np.ndarray]:
        v = self._vectors.get(name)
        return None if v is None else v.copy()

    def dimension(self) -> int:
        for v in self._vectors.values():
            return int(v.shape[0])
        return 0

    def set_layer_rms(self, layer: int, rms: float) -> None:
        """Record the typical hidden-state magnitude at `layer`."""
        if rms > 0 and np.isfinite(rms):
            self._rms[int(layer)] = float(rms)

    def layer_rms(self, layer: int, default: float = 1.0) -> float:
        return self._rms.get(int(layer), default)

    def has_rms(self, layer: int) -> bool:
        return int(layer) in self._rms

    def calibrated_layers(self) -> List[int]:
        return sorted(self._rms)

    # -- intervention ----------------------------------------------------

    def scaled(self, name: str, strength: float, layer: int) -> Optional[np.ndarray]:
        """The vector to add to the residual stream, scaled for `layer`.

        ``strength`` is expressed as a fraction of the residual stream's
        own RMS norm at that layer, so 0.1 is "a 10% perturbation"
        regardless of which layer you are steering.

        That only holds if the layer's RMS is actually known. When it
        is not, we fall back to ``1.0`` and the caller is expected to
        check :meth:`has_rms` before telling the user what the slider
        means — a strength of 0.1 against a real RMS of ~100 is a
        perturbation three orders of magnitude weaker than the label
        suggests, and silently so.
        """
        v = self._vectors.get(name)
        if v is None:
            return None
        return (v * (float(strength) * self.layer_rms(layer))).astype(np.float32)

    def describe(self) -> List[dict]:
        """A JSON-serialisable summary for the frontend's direction picker."""
        out = []
        for p in PRESET_DIRECTIONS:
            name = p["id"]
            if name not in self._vectors:
                continue
            info = self._meta.get(name, {})
            out.append({
                **p,
                "layer": info.get("layer"),
                "validation": info.get("validation", {}),
                "n_positive": info.get("n_positive"),
                "n_negative": info.get("n_negative"),
            })
        return out

    def calibration(self) -> dict:
        """Whether the strength slider is calibrated, and for which layers.

        The frontend uses this to decide whether it can honestly label
        the strength as a percentage of the residual stream.
        """
        layers = self.calibrated_layers()
        return {
            "calibrated": bool(layers),
            "layers": layers,
            "layer_rms": {str(l): round(self._rms[l], 3) for l in layers},
        }


# ---------------------------------------------------------------------------
# Session-level intervention controller
# ---------------------------------------------------------------------------


class InterventionController:
    """Holds the *currently active* steering for one WebSocket session.

    A session can have several interventions layered on top of each
    other (the UI lets you stack them); each is a named direction with
    a strength and a layer. `callback` returns the sum of all active
    vectors, or None when nothing is active.

    Interventions are recorded so the UI can show a history and revert
    individual entries without restarting the stream.
    """

    def __init__(self, registry: SteeringRegistry):
        self.registry = registry
        self._active: Dict[int, dict] = {}
        self._next_id = 1
        self._lock = threading.Lock()
        self._cache: Optional[np.ndarray] = None
        self._cache_dirty = True

    # -- mutation --------------------------------------------------------

    def add(self, direction: str, strength: float, layer: int) -> dict:
        """Register an active intervention; returns its record."""
        if not self.registry.has(direction):
            raise KeyError(f"unknown steering direction: {direction}")
        strength = max(0.0, float(strength))
        with self._lock:
            iv_id = self._next_id
            self._next_id += 1
            rec = {
                "id": iv_id,
                "direction": direction,
                "strength": strength,
                "layer": int(layer),
                "active": True,
            }
            self._active[iv_id] = rec
            self._cache_dirty = True
        return rec

    def revert(self, intervention_id: int) -> bool:
        with self._lock:
            if intervention_id in self._active:
                del self._active[intervention_id]
                self._cache_dirty = True
                return True
        return False

    def clear(self) -> int:
        with self._lock:
            n = len(self._active)
            self._active.clear()
            self._cache_dirty = True
            return n

    def active(self) -> List[dict]:
        with self._lock:
            return [dict(r) for r in self._active.values()]

    # -- readout ---------------------------------------------------------

    def is_active(self) -> bool:
        with self._lock:
            return bool(self._active)

    def combined(self) -> Optional[np.ndarray]:
        """Sum of all active vectors, or None if nothing is active.

        Cached because the runner calls this once per generated token.
        """
        with self._lock:
            if not self._active:
                return None
            if not self._cache_dirty and self._cache is not None:
                return self._cache.copy()

            total: Optional[np.ndarray] = None
            for rec in self._active.values():
                v = self.registry.scaled(rec["direction"], rec["strength"], rec["layer"])
                if v is None:
                    continue
                total = v if total is None else total + v
            self._cache = total
            self._cache_dirty = False
            return None if total is None else total.copy()

    def make_callback(self) -> Callable[[int, str], Optional[np.ndarray]]:
        """The `inject_vector(step_id, token)` callable for runner.stream().

        The runner ignores the step/token arguments here because the
        intervention is constant across the stream — but the signature
        matches so a future version can make it token-conditional
        without touching the server.
        """

        def inject_vector(step_id: int, token: str) -> Optional[np.ndarray]:
            return self.combined()

        return inject_vector


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_REGISTRY: Optional[SteeringRegistry] = None


def get_registry() -> SteeringRegistry:
    """Lazily load the shared registry on first use."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SteeringRegistry()
        _REGISTRY.load()
        # Calibrate the strength scale so "0.1" means 10% of the state
        # it perturbs. Best-effort: a missing profile degrades to the
        # old uncalibrated behaviour, and the UI is told via
        # `describe()` so it can say so.
        _REGISTRY.load_layer_scales()
    return _REGISTRY
