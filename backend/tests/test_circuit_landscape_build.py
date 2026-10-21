"""Tests for the circuit-landscape browser payload + progress map.

The rules these tests defend, in the order they bite:

* the readout bands must **tile** [0,1] with no gap and no overlap — a site in
  the gap would silently get no label (docs/STEERING_LEDGER.md T4);
* the decision band and the floor band must never be aggregated together
  (assertion ⑪);
* the per-layer ledger must be the **32-site aggregate**, not site 0
  (prediction P9);
* the "cheapest next level" of a rung is the gate of the rung **above** it,
  never its own `needs` (framework §8.6, design error 3 — that off-by-one
  shipped once and every hint was one level late).
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "build_circuit_landscape", ROOT / "backend/examples/build_circuit_landscape.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


# ------------------------------------------------------------------- bands
def test_regime_bands_tile_the_unit_interval():
    """Every p in [0,1] gets exactly one band, and the boundaries are the
    documented ones (floor < 0.01, decision >= 0.05, ceiling > 0.95)."""
    assert build.regime_of(0.0) == "floor"
    assert build.regime_of(1e-9) == "floor"
    assert build.regime_of(build.FLOOR_P) == "transition"
    assert build.regime_of(build.DECISION_P) == "decision"
    assert build.regime_of(0.5) == "decision"
    assert build.regime_of(build.CEILING_P) == "decision"
    assert build.regime_of(0.99) == "ceiling"
    assert build.regime_of(1.0) == "ceiling"
    # no gap: everything is labelled
    for i in range(0, 1001):
        p = i / 1000.0
        assert build.regime_of(p) in {"floor", "transition", "decision", "ceiling"}


def test_only_the_decision_band_may_support_a_behavioural_claim():
    for regime in ("floor", "transition", "ceiling"):
        assert build.band_label(regime)
    assert build.band_label("decision") == "决策带"


# ------------------------------------------------------------------ fixtures
def make_site(index, baseline_lp, strength=0.1, d_plus=0.5, d_random=0.1):
    """A minimal site with the fields trim_site reads.

    `d_plus` is the plus arm's ΔlogP.  It is a parameter on purpose: the whole
    point of the band split is that the floor band moves in *nats* a lot more
    than the decision band, and a fixture where every site moves the same
    amount would make "the bands must not be mixed" vacuously true.
    """
    def arm(lp):
        return {
            "readout": {"marker_logprob": lp, "top_tokens": [
                {"id": 1, "text": " x", "probability": 0.5}]},
            "layers": {
                "20": {
                    "states": {"incoming": [0, 0, 0], "input": [0, 0, 0],
                               "after_attention": [0, 0, 0], "out": [0, 0, 0]},
                    "writes": {"attention": [1, 0, 0], "mlp": [0, 1, 0]},
                    "units": [{
                        "id": 7, "gate": 1.0, "value": 2.0, "raw_gate": 3.0,
                        "natural_product": 2.0, "product": 2.0, "baseline_product": 2.0,
                        "regime": "++", "patched": False, "in_frozen_group": False,
                        "write_norm": 2.0, "response_norm": 0.0,
                        "write": [1, 0, 0], "writer": [1, 0, 0],
                    }],
                    "remainder": [0, 0, 0],
                    "closure_l2": 1e-7, "closure_relative": 1e-9,
                    "displayed_native_units": 1, "total_native_units": 6144,
                },
            },
        }
    return {
        "trajectory": "t%d" % index, "t": index, "anchor": False,
        "prefix_sha256": "x", "n_prefix_tokens": 1, "next_token": "x",
        "context_before": "", "context_after": "", "alpha": 60.0,
        "arms": {
            "baseline": arm(baseline_lp),
            "plus": arm(baseline_lp + d_plus),
            "minus": arm(baseline_lp - d_plus),
            "random": arm(baseline_lp + d_random),
            "block": arm(baseline_lp + d_plus * 0.9),
            "restore": arm(baseline_lp + d_plus * 0.1),
        },
    }


# -------------------------------------------------------------------- trim
def test_trim_site_adds_the_readout_context():
    site = build.trim_site(make_site(0, math.log(0.7)), 0.1, 5)
    assert site["p_base"] == pytest.approx(0.7, rel=1e-4)
    assert site["regime"] == "decision"
    assert site["h_norm"] == pytest.approx(600.0, rel=1e-6)
    assert site["readout_delta"]["plus"] == pytest.approx(0.5, rel=1e-4)
    assert site["snr"] == pytest.approx(5.0, rel=1e-3)
    # fields the page does not render are dropped
    unit = site["arms"]["plus"]["layers"]["20"]["units"][0]
    assert "raw_gate" not in unit
    assert "writer" not in unit
    assert "closure_l2" not in site["arms"]["plus"]["layers"]["20"]


def test_trim_site_labels_a_tail_probability_as_floor():
    site = build.trim_site(make_site(0, -30.0), 0.1, 5)
    assert site["regime"] == "floor"
    assert site["p_base"] < build.FLOOR_P


# ----------------------------------------------------------------- summary
def test_summary_keeps_the_bands_apart():
    sites = [
        build.trim_site(make_site(0, math.log(0.7), d_plus=0.5), 0.1, 5),   # decision
        build.trim_site(make_site(1, math.log(0.5), d_plus=0.3), 0.1, 5),   # decision
        build.trim_site(make_site(2, -30.0, d_plus=2.0), 0.1, 5),           # floor
    ]
    summary = build.readout_summary(sites, 5)
    assert summary["decision"]["n_sites"] == 2
    assert summary["floor"]["n_sites"] == 1
    assert summary["all"]["n_sites"] == 3
    # the mixed number must NOT equal either band
    assert summary["all"]["arms"]["plus"]["mean"] != summary["decision"]["arms"]["plus"]["mean"]
    assert summary["all"]["arms"]["plus"]["mean"] != summary["floor"]["arms"]["plus"]["mean"]
    # the floor band is the one with the larger nats but the smaller probability
    assert summary["floor"]["arms"]["plus"]["mean"] > summary["decision"]["arms"]["plus"]["mean"]
    # and the mixed number sits between them, which is exactly why mixing lies
    assert (summary["decision"]["arms"]["plus"]["mean"]
            < summary["all"]["arms"]["plus"]["mean"]
            < summary["floor"]["arms"]["plus"]["mean"])


# ------------------------------------------------------------------ ledger
def test_ledger_aggregate_is_over_every_site_not_just_the_first():
    sites = [build.trim_site(make_site(i, -1.0), 0.1, 5) for i in range(3)]
    rows = build.ledger_aggregate(sites, [20], 5)
    assert len(rows) == 1
    row = rows[0]
    assert row["n_sites"] == 3
    assert row["space"] == "projected-3d"
    # attention write is [1,0,0] -> 1.0 ; mlp write is [0,1,0] -> 1.0
    assert row["attn_mean"] == pytest.approx(1.0)
    assert row["mlp_mean"] == pytest.approx(1.0)
    assert row["attn_share"] == pytest.approx(0.5)
    # the plus arm's writes are identical to baseline in the fixture, so no change
    assert row["dmlp_over_mlp"] == pytest.approx(0.0)


def test_ledger_aggregate_uses_true_norms_when_the_archive_is_available():
    sites = [build.trim_site(make_site(0, -1.0), 0.1, 5)]
    true = {(0, "baseline", 20): {"attn": [3.0, 0, 0], "mlp": [0, 4.0, 0]},
            (0, "plus", 20): {"attn": [3.0, 0, 0], "mlp": [0, 8.0, 0]}}
    row = build.ledger_aggregate(sites, [20], 5, true)[0]
    assert row["space"] == "true-2048"
    assert row["attn_mean"] == pytest.approx(3.0)
    assert row["mlp_mean"] == pytest.approx(4.0)
    assert row["dmlp_mean"] == pytest.approx(4.0)
    assert row["dmlp_over_mlp"] == pytest.approx(1.0)


# ------------------------------------------------------------- progress map
def test_next_level_is_the_gate_of_the_rung_above_not_of_this_one(tmp_path):
    ladder = {
        "ladder": [
            {"level": "L0", "claim": "a", "needs": "gate-L0", "state": "done", "here": "h0", "note": ""},
            {"level": "L1", "claim": "b", "needs": "gate-L1", "state": "done", "here": "h1", "note": ""},
            {"level": "L2", "claim": "c", "needs": "gate-L2", "state": "partial", "here": "h2", "note": ""},
            {"level": "L3", "claim": "d", "needs": "gate-L3", "state": "missing", "here": "h3", "note": ""},
        ],
        "max_level_claimed": "L2", "max_level_with_data": "L2", "why_two_numbers": "w",
    }
    path = tmp_path / "evidence_ladder.json"
    path.write_text(json.dumps(ladder), encoding="utf-8")
    evidence = {"guards": {"max_residual_closure_relative": 2.25e-07}, "sites": [],
                "arms": [], "ledger": {"per_layer": []}}
    prog = build.build_progress(evidence, {}, path, tmp_path, 1234, 5)
    rows = {r["level"]: r for r in prog["rows"]}
    # a done rung points at the gate of the first rung above it that is not done
    assert rows["L0"]["cells"]["向量"]["next"] == "gate-L2"
    assert rows["L1"]["cells"]["向量"]["next"] == "gate-L2"
    assert rows["L2"]["cells"]["向量"]["next"] == "gate-L3"
    # the rung's own gate is its own `needs`, never the next one
    assert rows["L2"]["cells"]["向量"]["gate"] == "gate-L2"
    assert rows["L2"]["needs"] == "gate-L2"


def test_progress_map_keeps_claimed_and_with_data_apart(tmp_path):
    ladder = {
        "ladder": [{"level": "L0", "claim": "a", "needs": "g", "state": "done", "here": "h", "note": ""}],
        "max_level_claimed": "L4", "max_level_with_data": "L6", "why_two_numbers": "keep apart",
    }
    path = tmp_path / "evidence_ladder.json"
    path.write_text(json.dumps(ladder), encoding="utf-8")
    evidence = {"guards": {"max_residual_closure_relative": 1e-7}, "sites": [],
                "arms": [], "ledger": {"per_layer": []}}
    prog = build.build_progress(evidence, {}, path, tmp_path, 1, 5)
    assert prog["ladder_max_level_claimed"] == "L4"
    assert prog["ladder_max_level_with_data"] == "L6"
    assert prog["ladder_max_level_claimed"] != prog["ladder_max_level_with_data"]


def test_progress_map_marks_the_gpu_stages_as_locked(tmp_path):
    evidence = {"guards": {"max_residual_closure_relative": 1e-7}, "sites": [],
                "arms": [], "ledger": {"per_layer": []}}
    prog = build.build_progress(evidence, {}, tmp_path / "missing.json", tmp_path, 1, 5)
    states = {s["id"]: s["state"] for s in prog["stages"]}
    assert states["S3"] == "locked"
    assert states["S5"] == "locked"
    assert states["S0"] == "pass"
    # the L2' row is this round's own contribution
    assert any(r["level"] == "L2′" for r in prog["rows"])


# ------------------------------------------------------------- end to end
SOURCE = ROOT / "experiments/circuit_landscape_v1/results/circuit_landscape.json"


@pytest.mark.skipif(not SOURCE.exists(), reason="raw circuit landscape artifact not present")
def test_built_payload_is_smaller_than_the_source_and_keeps_the_page_contract(tmp_path):
    import io
    import contextlib
    out = tmp_path / "circuit_landscape.json"
    prog = tmp_path / "steering_progress.json"
    # run the real builder, writing into a temp dir
    build.sys.argv = ["build_circuit_landscape.py", "--public", str(tmp_path)]
    with contextlib.redirect_stdout(io.StringIO()):
        assert build.main() == 0
    assert out.exists() and prog.exists()
    payload = out.read_text(encoding="utf-8")
    assert len(payload) < SOURCE.stat().st_size
    data = json.loads(payload)
    assert data["schema"] == "steer3d.circuit_landscape/1"
    for site in data["sites"]:
        assert "p_base" in site and "regime" in site
        assert site["regime"] in {"floor", "transition", "decision", "ceiling"}
        assert "readout_delta" in site and "snr" in site
    assert data["ledger"]["per_layer"]
    assert all(row["n_sites"] == len(data["sites"]) for row in data["ledger"]["per_layer"])
    assert data["readout_summary"]["decision"]["n_sites"] <= len(data["sites"])
    progress = json.loads(prog.read_text(encoding="utf-8"))
    assert progress["schema"] == "steer3d.steering_progress/1"
    assert len(progress["stages"]) == 6
    assert progress["rows"]
