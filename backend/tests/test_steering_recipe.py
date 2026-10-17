"""Tests for the compiled recipe assembly."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.steering_recipe import RecipeError, assemble_recipe  # noqa: E402


def make_inputs():
    readout = {"best_layer": 17, "best_layer_mean_auc_cos": 0.73, "best_layer_orientation": 1}
    transfer = {
        "w": {"mean_delta_logp": 0.10, "n_sites": 2},
        "g_mean": {"mean_delta_logp": 0.65, "n_sites": 2},
        "g_sparse": {"mean_delta_logp": 0.61, "n_sites": 2},
        "oracle_per_site_gradient": {"mean_delta_logp": 0.67, "n_sites": 2},
    }
    window = {"direction": "sparse_g", "dose": 0.02, "mean_delta_logp": 0.26, "mean_kl": 0.07}
    files = {"w": "w.npy", "mean_g": "mean.npy", "sparse_g": "sparse.npy"}
    verification = {"n_sites": 2, "mean_delta_logp": 0.26, "mean_kl": 0.07, "sites": []}
    return readout, transfer, window, files, verification


def test_assemble_recipe_selects_file_and_copies_evidence():
    readout, transfer, window, files, verification = make_inputs()
    entry = assemble_recipe(7196, readout, transfer, window, files, verification, ["caveat"])
    assert entry["target_marker"] == 7196
    assert entry["compiled"]["direction"] == "sparse_g"
    assert entry["compiled"]["file"] == "sparse.npy"
    assert entry["compiled"]["expected_delta_logp"] == pytest.approx(0.26)
    assert entry["verification"]["mean_delta_logp"] == pytest.approx(0.26)
    assert entry["heldout_transfer"]["mean_g"] == pytest.approx(0.65)
    assert entry["caveats"] == ["caveat"]


def test_assemble_recipe_rejects_missing_window_or_file():
    readout, transfer, window, files, verification = make_inputs()
    with pytest.raises(RecipeError, match="direction/dose"):
        assemble_recipe(7196, readout, transfer, {"direction": None, "dose": None}, files, verification)
    with pytest.raises(RecipeError, match="no compiled file"):
        assemble_recipe(7196, readout, transfer, window, {"w": "w.npy"}, verification)

