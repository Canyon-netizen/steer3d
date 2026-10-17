"""Tests for the steering design guide.

The guide is a pure transformation of measured artifacts.  These tests pin the
sign convention, the failure modes (missing / non-finite inputs) and the
serialisability of the report; they do not touch a model.
"""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.steering_design import (  # noqa: E402
    DesignError,
    build_layer_table,
    build_report,
    build_units,
    render_markdown,
)


def summary_block(mean, per_problem=None, n=2):
    return {"mean": mean, "min": mean - 0.01, "max": mean + 0.01,
            "n_problems": n, "per_problem": per_problem or {"m%d" % i: mean for i in range(n)}}


def make_summary():
    response = {
        "w+": {"0.02": summary_block(-0.01), "0.1": summary_block(-0.06), "0.25": summary_block(-0.16)},
        "w-": {"0.02": summary_block(0.01), "0.1": summary_block(0.10), "0.25": summary_block(0.30)},
        "random_primary": summary_block(-0.02),
    }
    mediation = {
        "joint_block": summary_block(0.048), "joint_restore": summary_block(0.045),
        "random0_block": summary_block(-0.13), "random0_restore": summary_block(-0.16),
        "random1_block": summary_block(-0.007), "random1_restore": summary_block(-0.014),
        "random2_block": summary_block(-0.022), "random2_restore": summary_block(-0.024),
        "random3_block": summary_block(-0.009), "random3_restore": summary_block(-0.003),
    }
    block = {20: -0.05, 21: 0.035, 22: -0.008, 23: 0.006, 24: 0.026, 25: 0.082, 26: -0.009, 27: -0.007}
    restore = {20: -0.045, 21: 0.037, 22: -0.007, 23: 0.010, 24: 0.028, 25: 0.089, 26: -0.012, 27: -0.008}
    for layer in range(20, 28):
        mediation["layer%d_block" % layer] = summary_block(block[layer])
        mediation["layer%d_restore" % layer] = summary_block(restore[layer])
    factorial = {
        "True_neutral": summary_block(0.106), "True_self_check_phrase": summary_block(-0.260),
        "False_neutral": summary_block(-0.135), "False_self_check_phrase": summary_block(0.023),
    }
    transfer = {
        "total": summary_block(0.122), "minus_total": summary_block(-0.217),
        "raw_marker_lse_delta": summary_block(0.388),
        "block": summary_block(0.011), "restore": summary_block(0.018),
    }
    for i in range(4):
        transfer["random%d_block" % i] = summary_block(0.001 * i)
        transfer["random%d_restore" % i] = summary_block(-0.001 * i)
    transfer["transfer_source_audit"] = {"n_trajectories": 12, "n_measured_sites": 18}
    return {
        "complete": True,
        "response": response,
        "mediation": mediation,
        "factorial": factorial,
        "transfer": transfer,
        "baseline": {"p_correct": 0.67, "argmax_correct": 16, "argmax_outside": 0,
                     "mean_answer_set_coverage": 0.9999},
    }


def make_bpath():
    return {
        "arm": "B_L19_m0(H[t])",
        "readability_static": {
            "arith_mean": 0.18, "freq_weighted": 0.184, "n_ids_positive": 2, "n_ids": 2,
            "freq_total": 100,
            "per_id": {
                "7196": {"dot": 0.179, "freq": 60, "share": 0.6},
                "13824": {"dot": 0.184, "freq": 40, "share": 0.4},
            },
        },
        "layer_profile": {
            "headline": "test",
            "calibration": "test",
            "retracted": "test",
            "rows": [{"traj": "t0", "mode": "think", "t": 10, "alpha": 1.0,
                      "w_dot_hhat": 0.01, "pred_marker_lse": 2.0, "calibration_ratio": 0.99,
                      "by_layer": {"-1": 2.0, "20": 0.5}}],
        },
    }


def make_axis():
    return {"axes": {
        "confidence": {"label": "high confidence", "status": "tautological",
                       "at_delta0": {"n_layers_beating_control": 1, "n_layers": 1,
                                     "per_layer": {"12": {"cos": 0.41, "control_cos": 0.003, "beats_control": True}}}},
        "caution": {"label": "caution", "status": "shared_readout",
                    "at_delta0": {"n_layers_beating_control": 1, "n_layers": 1,
                                  "per_layer": {"12": {"cos": 0.31, "control_cos": 0.018, "beats_control": True}}}},
    }}


def make_lens():
    return {"per_layer_mean_p_final": {"values": [0.0002] * 18 + [0.13, 0.22, 0.35, 0.57, 0.70, 0.73, 0.80, 0.87, 0.89, 0.94],
                                        "n_steps": 100}}


def make_mediation():
    units = []
    for layer in range(20, 28):
        units.append({"layer": layer, "unit": 1, "score": float(layer),
                      "baseline_magnitude": 1.0, "column_norm": 0.5})
    return {"complete": True, "selection": {"units": units}}


def make_report():
    return build_report(make_summary(), make_bpath(), make_axis(), make_lens(), make_mediation())


def test_layer_table_flags_supporting_and_compensating():
    rows = {r["layer"]: r for r in build_layer_table(make_summary())}
    assert rows[20]["action"] == "supporting"
    assert rows[20]["support"] > 0
    assert rows[25]["action"] == "compensating"
    assert rows[25]["compensation"] > 0
    assert rows[22]["action"] == "weak"
    assert rows[25]["random_compensations"]
    assert rows[25]["random_median_abs"] > 0


def test_layer_table_requires_every_layer():
    summary = make_summary()
    del summary["mediation"]["layer25_block"]
    with pytest.raises(DesignError, match="layer25_block"):
        build_layer_table(summary)


def test_nonfinite_input_is_rejected():
    summary = make_summary()
    summary["mediation"]["random0_block"]["mean"] = float("nan")
    with pytest.raises(DesignError, match="finite"):
        build_layer_table(summary)


def test_build_units_requires_one_unit_per_layer():
    mediation = make_mediation()
    mediation["selection"]["units"] = [u for u in mediation["selection"]["units"] if u["layer"] != 27]
    with pytest.raises(DesignError, match="layer 27"):
        build_units(mediation)


def test_report_is_serialisable_and_has_recommendations():
    report = make_report()
    assert report["schema"] == "steer3d.steering_design/1"
    assert report["complete"] is True
    actions = {r["action"] for r in report["recommendations"]}
    assert {"define_target", "avoid_positive_injection", "test_compensator_removal"} <= actions
    assert report["unmeasured"]
    assert report["units"]["n_selected"] == 8
    text = json.dumps(report, ensure_ascii=False, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text


def test_all_floats_are_finite():
    def walk(value):
        if isinstance(value, float):
            assert math.isfinite(value), value
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(make_report())


def test_markdown_contains_layer_table_and_unmeasured():
    text = render_markdown(make_report())
    assert "| 20 |" in text
    assert "## Unmeasured" in text
    assert "test_compensator_removal" in text
    assert "## Provenance" in text




def make_atlas():
    layers = []
    for layer in range(28):
        layers.append({
            "layer": layer,
            "mean_auc_cos": 0.2 if layer == 21 else 0.5,
            "mean_auc_cos_oriented": 0.8 if layer == 21 else 0.5,
            "mean_auc_norm": 0.56,
            "mean_auc_proj_resid": 0.19,
            "n_trajectories_with_both_classes": 24,
            "cos_orientation": -1 if layer == 21 else 1,
            "n_trajectories_with_orientation": 24,
            "n_trajectories_negative_orientation": 24,
        })
    def marker(n, layer, auc, orientation):
        return {
            "n_occurrences": n, "n_trajectories": 9, "best_layer": layer,
            "best_layer_mean_auc_cos": auc,
            "best_layer_mean_auc_cos_oriented": max(auc, 1 - auc),
            "best_layer_orientation": orientation, "layers": [],
        }
    return {
        "aggregate": {
            "best_layer": 21,
            "layers": layers,
            "n_trajectories": 30,
            "n_marker_total": 384,
            "chance_level": 0.5,
        },
        "per_marker": {
            "7196": marker(105, 17, 0.7305, 1),
            "6771": marker(119, 27, 0.1453, -1),
            "80022": marker(4, 9, 0.0197, -1),
        },
        "scope": "synthetic atlas for tests",
    }


def test_report_integrates_readout_atlas():
    report = build_report(
        make_summary(), make_bpath(), make_axis(), make_lens(), make_mediation(),
        readout_atlas=make_atlas(),
    )
    atlas = report["readout_atlas"]
    assert atlas["best_layer"] == 21
    assert atlas["best_layer_orientation"] == -1
    assert atlas["n_trajectories_with_orientation"] == 24
    actions = {rec["action"] for rec in report["recommendations"]}
    assert "do_not_use_cos_h_w_as_positive_readout" in actions
    assert "split_marker_directions_by_sign" in actions
    assert "do_not_adjudicate_small_n_markers" in actions
    assert any("per-marker rows" in warning for warning in report["warnings"])
    assert report["readout_atlas"]["per_marker"]["7196"]["best_layer_orientation"] == 1
    text = render_markdown(report)
    assert "## Hidden-state readout atlas" in text




def make_construction():
    sites = [
        {
            "trajectory": "t0", "marker": 7196, "n_prefix": 140, "baseline_logp": -0.02,
            "candidates": {
                "w": {"delta_logp": -0.02},
                "gradient": {"delta_logp": 0.02},
                "w_plus_gradient": {"delta_logp": 0.02},
                "random": {"delta_logp": 0.0},
            },
        },
        {
            "trajectory": "t1", "marker": 10061, "n_prefix": 176, "baseline_logp": -0.61,
            "candidates": {
                "w": {"delta_logp": 0.18},
                "gradient": {"delta_logp": 0.60},
                "w_plus_gradient": {"delta_logp": 0.58},
                "random": {"delta_logp": 0.01},
            },
        },
    ]
    aggregate = {
        "7196": {
            "n_sites": 1,
            "best_candidate": "gradient",
            "candidates": {
                "w": {"mean_delta_logp": -0.02, "improved_fraction": 0.0},
                "gradient": {"mean_delta_logp": 0.02, "improved_fraction": 1.0},
            },
        },
        "10061": {
            "n_sites": 1,
            "best_candidate": "gradient",
            "candidates": {
                "w": {"mean_delta_logp": 0.18, "improved_fraction": 1.0},
                "gradient": {"mean_delta_logp": 0.60, "improved_fraction": 1.0},
            },
        },
    }
    return {"sites": sites, "aggregate": aggregate, "alpha_rule": "0.1 * input norm", "scope": "synthetic"}


def test_report_integrates_construction_probe():
    report = build_report(
        make_summary(), make_bpath(), make_axis(), make_lens(), make_mediation(),
        construction=make_construction(),
    )
    assert report["construction"]["n_sites"] == 2
    assert report["construction"]["by_marker"]["7196"]["n_sites"] == 1
    actions = {rec["action"] for rec in report["recommendations"]}
    assert "use_gradient_direction_as_constructive_baseline" in actions
    assert "treat_unit_decomposition_as_diagnostic" in actions
    assert any("construction probe is a local" in warning for warning in report["warnings"])
    text = render_markdown(report)
    assert "## Construction probe" in text




def make_transfer():
    def cell(value):
        return {"mean_delta_logp": value, "improved_fraction": 1.0, "n_sites": 2}

    return {
        "sites": [
            {"trajectory": "t0", "marker": 7196, "n_prefix": 140},
            {"trajectory": "t1", "marker": 10061, "n_prefix": 176},
        ],
        "same_marker": {
            "7196": {
                "w": cell(0.10), "g_mean": cell(0.65), "g_sparse": cell(0.61),
                "random": cell(0.03), "oracle_per_site_gradient": cell(0.67),
            },
            "10061": {
                "w": cell(0.02), "g_mean": cell(0.44), "g_sparse": cell(0.38),
                "random": cell(-0.03), "oracle_per_site_gradient": cell(0.47),
            },
        },
        "cross": {
            "7196": {"10061": cell(-0.45)},
            "10061": {"7196": cell(0.31)},
        },
        "alpha_rule": "0.1 * input norm",
        "scope": "synthetic",
    }


def test_report_integrates_heldout_transfer():
    report = build_report(
        make_summary(), make_bpath(), make_axis(), make_lens(), make_mediation(),
        steering_transfer=make_transfer(),
    )
    assert report["steering_transfer"]["by_marker"]["7196"]["g_mean"]["mean_delta_logp"] == pytest.approx(0.65)
    assert report["steering_transfer"]["cross"]["7196"]["10061"]["mean_delta_logp"] == pytest.approx(-0.45)
    actions = {rec["action"] for rec in report["recommendations"]}
    assert "use_per_marker_mean_gradient_on_heldout" in actions
    assert "sparse_direction_retains_effect" in actions
    assert any("held-out transfer" in warning for warning in report["warnings"])
    text = render_markdown(report)
    assert "## Held-out transfer" in text




def make_sweep():
    def cell(dose, delta, kl):
        return {
            "dose": dose, "mean_delta_logp": delta, "mean_kl": kl,
            "mean_delta_entropy": -0.1, "mean_delta_other_marker_mass": 0.0,
            "improved_fraction": 1.0, "n_sites": 2,
        }
    window = {
        "direction": "sparse_g", "dose": 0.05,
        "mean_delta_logp": 0.28, "mean_kl": 0.2, "kl_threshold": 0.1,
    }
    return {
        "aggregate": {
            "7196": {
                "directions": {
                    "w": [cell(0.05, 0.10, 0.03)],
                    "mean_g": [cell(0.05, 0.30, 0.50)],
                    "sparse_g": [cell(0.05, 0.28, 0.20)],
                },
                "useful_window": window,
            }
        },
        "useful_window": {"7196": window},
        "doses": [0.05],
        "kl_threshold": 0.1,
        "guards": {"n_sites": 2, "n_markers": 1},
        "sites": [{"marker": 7196, "direction": "sparse_g", "dose": 0.05}],
        "scope": "synthetic",
    }


def test_report_integrates_sweep():
    report = build_report(
        make_summary(), make_bpath(), make_axis(), make_lens(), make_mediation(),
        steering_sweep=make_sweep(),
    )
    assert report["steering_sweep"]["by_marker"]["7196"]["useful_window"]["direction"] == "sparse_g"
    actions = {rec["action"] for rec in report["recommendations"]}
    assert "choose_direction_and_dose_by_kl_frontier" in actions
    assert "sparse_g_reduces_side_effect" in actions
    assert any("alpha sweep" in warning for warning in report["warnings"])
    text = render_markdown(report)
    assert "## Alpha / side-effect sweep" in text




def make_recipe():
    return {
        "markers": {
            "7196": {
                "target_marker": 7196,
                "readout": {"best_layer": 17, "best_layer_mean_auc_cos": 0.73, "best_layer_orientation": 1},
                "heldout_transfer": {"w": 0.10, "g_mean": 0.65, "g_sparse": 0.61, "oracle": 0.67, "n_sites": 2},
                "compiled": {
                    "direction": "sparse_g", "dose": 0.02, "file": "experiments/vectors/7196_sparse_g.npy",
                    "public_url": "/latent/data/steering_recipes/7196_sparse_g.npy",
                    "expected_delta_logp": 0.26, "expected_kl": 0.07,
                },
                "verification": {"n_sites": 2, "mean_delta_logp": 0.26, "mean_kl": 0.07, "sites": []},
                "caveats": ["local"],
            }
        },
        "source_hashes": {},
        "scope": "synthetic",
    }


def test_report_integrates_compiled_recipe():
    report = build_report(
        make_summary(), make_bpath(), make_axis(), make_lens(), make_mediation(),
        steering_recipe=make_recipe(),
    )
    assert report["steering_recipe"]["n_markers"] == 1
    assert report["steering_recipe"]["markers"]["7196"]["compiled"]["direction"] == "sparse_g"
    actions = {rec["action"] for rec in report["recommendations"]}
    assert "compiled_recipe_available" in actions
    assert any("compiled recipe" in warning for warning in report["warnings"])
    text = render_markdown(report)
    assert "## Compiled recipe" in text

