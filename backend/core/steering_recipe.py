"""Assemble a per-marker steering recipe from measured artifacts.

This module is pure: it combines readout / transfer / sweep / compiled-file
metadata into one entry.  The model runner lives in the example script.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


class RecipeError(ValueError):
    """Raised when a recipe cannot be assembled."""


def _require(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise RecipeError("%s: missing %r" % (where, key))
    return mapping[key]


def assemble_recipe(
    marker: int,
    readout: Mapping[str, Any],
    transfer: Mapping[str, Any],
    sweep_window: Mapping[str, Any],
    files: Mapping[str, str],
    verification: Mapping[str, Any],
    caveats: Optional[list] = None,
) -> Dict[str, Any]:
    direction = sweep_window.get("direction")
    dose = sweep_window.get("dose")
    if direction is None or dose is None:
        raise RecipeError("marker %d: useful window has no direction/dose" % marker)
    if direction not in files:
        raise RecipeError("marker %d: no compiled file for direction %r" % (marker, direction))
    expected_delta = sweep_window.get("mean_delta_logp")
    expected_kl = sweep_window.get("mean_kl")
    if expected_delta is None or expected_kl is None:
        raise RecipeError("marker %d: useful window has no delta/KL" % marker)
    return {
        "target_marker": int(marker),
        "readout": {
            "best_layer": readout.get("best_layer"),
            "raw_cos_auc": readout.get("best_layer_mean_auc_cos"),
            "orientation": readout.get("best_layer_orientation"),
        },
        "heldout_transfer": {
            "w": transfer.get("w", {}).get("mean_delta_logp"),
            "mean_g": transfer.get("g_mean", {}).get("mean_delta_logp"),
            "sparse_g": transfer.get("g_sparse", {}).get("mean_delta_logp"),
            "oracle": transfer.get("oracle_per_site_gradient", {}).get("mean_delta_logp"),
            "n_sites": transfer.get("g_mean", {}).get("n_sites"),
        },
        "compiled": {
            "direction": str(direction),
            "dose": float(dose),
            "file": files[str(direction)],
            "expected_delta_logp": float(expected_delta),
            "expected_kl": float(expected_kl),
        },
        "verification": dict(verification),
        "caveats": list(caveats or []),
    }
