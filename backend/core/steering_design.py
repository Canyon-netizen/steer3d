"""Build a steering-vector design guide from measured artifacts.

This module reads only artifacts that already exist on disk (no model forward
passes).  It turns them into a single report that answers, for a fixed vector:

  * what the vector is readable for (static readout);
  * what its injection actually does (dose / direction / wording);
  * which layers carry the effect and which layers compensate it
    (group-level block / restore against matched random groups);
  * which units were selected and what is *not* measured about them;
  * what to try next, with the evidence attached to each recommendation.

The report is deliberately descriptive.  It does not claim a control recipe:
per-unit causal alignment and a solved control direction are listed under
'unmeasured'.  The point is to make the design decision explicit and
falsifiable, not to dress a small-n result as a law.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Mapping, Optional

SCHEMA = "steer3d.steering_design/1"
LAYERS = list(range(20, 28))
PRIMARY_STRENGTH = "0.1"
RANDOM_GROUPS = (0, 1, 2, 3)

# A layer is called supporting / compensating only when both the block and the
# restore effect point the same way and the mean exceeds this floor.
EFFECT_FLOOR = 0.02


class DesignError(ValueError):
    """Raised when an input artifact cannot support a design claim."""


# ---------------------------------------------------------------------------
# small validation helpers
# ---------------------------------------------------------------------------

def _require(obj: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in obj:
        raise DesignError("%s: missing required field %r" % (where, key))
    return obj[key]


def _finite(value: Any, where: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise DesignError("%s: expected a number, got %r" % (where, value))
    if not math.isfinite(out):
        raise DesignError("%s: expected a finite number, got %r" % (where, value))
    return out


def _mean(summary: Mapping[str, Any], where: str) -> float:
    if not isinstance(summary, Mapping):
        raise DesignError("%s: expected a mapping" % where)
    return _finite(_require(summary, "mean", where), where + ".mean")


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DesignError("input artifact not found: %s" % path)
    except json.JSONDecodeError as exc:
        raise DesignError("input artifact is not valid JSON: %s (%s)" % (path, exc))


# ---------------------------------------------------------------------------
# layer strategy
# ---------------------------------------------------------------------------

def build_layer_table(summary: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Per-layer block / restore effects against the four random groups.

    Sign convention (from the neuron-mediation report):
      block   = score(+v) - score(+v with these units restored to baseline)
      restore = score(baseline with these units set to +v) - score(baseline)

    compensation = (block + restore) / 2 is positive when the units push
    *against* the vector's net effect; support = -compensation.
    """
    mediation = _require(summary, "mediation", "summary")
    if not isinstance(mediation, Mapping):
        raise DesignError("summary.mediation: expected a mapping")
    response = _require(summary, "response", "summary")
    try:
        net_effect = _mean(response["w+"][PRIMARY_STRENGTH], "response.w+." + PRIMARY_STRENGTH)
    except KeyError:
        raise DesignError("summary.response.w+ is missing the primary dose %r" % PRIMARY_STRENGTH)

    random_block = [_mean(mediation["random%d_block" % i], "mediation.random%d_block" % i) for i in RANDOM_GROUPS]
    random_restore = [_mean(mediation["random%d_restore" % i], "mediation.random%d_restore" % i) for i in RANDOM_GROUPS]
    random_comp = [(b + r) / 2.0 for b, r in zip(random_block, random_restore)]
    random_median_abs = median(sorted(abs(x) for x in random_comp))

    rows: List[Dict[str, Any]] = []
    for layer in LAYERS:
        block_key = "layer%d_block" % layer
        restore_key = "layer%d_restore" % layer
        if block_key not in mediation or restore_key not in mediation:
            raise DesignError("summary.mediation: missing %s / %s" % (block_key, restore_key))
        block = _mean(mediation[block_key], "mediation." + block_key)
        restore = _mean(mediation[restore_key], "mediation." + restore_key)
        compensation = (block + restore) / 2.0
        support = -compensation
        same_sign = _sign(block) != 0 and _sign(block) == _sign(restore)
        if compensation >= EFFECT_FLOOR and same_sign:
            action = "compensating"
        elif compensation <= -EFFECT_FLOOR and same_sign:
            action = "supporting"
        else:
            action = "weak"
        rank = 1 + sum(1 for x in random_comp if abs(x) > abs(compensation))
        rows.append({
            "layer": layer,
            "block_mean": block,
            "restore_mean": restore,
            "compensation": compensation,
            "support": support,
            "action": action,
            "same_sign": same_sign,
            "beyond_random_median": abs(compensation) > random_median_abs,
            "random_rank": rank,
            "random_compensations": list(random_comp),
            "random_median_abs": random_median_abs,
            "n_random_groups": len(random_comp),
            "block_per_problem": dict(_require(mediation[block_key], "per_problem", "mediation." + block_key)),
            "restore_per_problem": dict(_require(mediation[restore_key], "per_problem", "mediation." + restore_key)),
            "n_problems": int(_require(mediation[block_key], "n_problems", "mediation." + block_key)),
            "net_effect_primary": net_effect,
        })
    return rows


# ---------------------------------------------------------------------------
# dose / wording / transfer
# ---------------------------------------------------------------------------

def _dose_rows(summary: Mapping[str, Any], sign: str) -> List[Dict[str, Any]]:
    response = _require(summary, "response", "summary")
    if sign not in response or not isinstance(response[sign], Mapping):
        raise DesignError("summary.response.%s: missing or not a mapping" % sign)
    rows = []
    for dose in sorted(response[sign], key=lambda d: float(d)):
        block = response[sign][dose]
        rows.append({
            "dose": _finite(dose, "response.%s dose" % sign),
            "mean": _mean(block, "response.%s.%s" % (sign, dose)),
            "min": _finite(_require(block, "min", "response.%s.%s" % (sign, dose)), "response.%s.%s.min" % (sign, dose)),
            "max": _finite(_require(block, "max", "response.%s.%s" % (sign, dose)), "response.%s.%s.max" % (sign, dose)),
            "n_problems": int(_require(block, "n_problems", "response.%s.%s" % (sign, dose))),
        })
    return rows


def build_dose_table(summary: Mapping[str, Any]) -> Dict[str, Any]:
    random_primary = _mean(_require(summary["response"], "random_primary", "response"), "response.random_primary")
    return {
        "w+": _dose_rows(summary, "w+"),
        "w-": _dose_rows(summary, "w-"),
        "random_primary": random_primary,
        "note": "dose is a fraction of the measured block-input L2 norm at the injection position",
    }


def build_factorial(summary: Mapping[str, Any]) -> Dict[str, Any]:
    factorial = _require(summary, "factorial", "summary")
    out = {}
    for name, block in factorial.items():
        out[name] = {
            "mean": _mean(block, "factorial." + name),
            "min": _finite(_require(block, "min", "factorial." + name), "factorial.%s.min" % name),
            "max": _finite(_require(block, "max", "factorial." + name), "factorial.%s.max" % name),
            "n_problems": int(_require(block, "n_problems", "factorial." + name)),
        }
    return out


def build_transfer(summary: Mapping[str, Any]) -> Dict[str, Any]:
    transfer = _require(summary, "transfer", "summary")
    out = {}
    for name, block in transfer.items():
        if name == "transfer_source_audit":
            out[name] = dict(block) if isinstance(block, Mapping) else block
            continue
        out[name] = {
            "mean": _mean(block, "transfer." + name),
            "min": _finite(_require(block, "min", "transfer." + name), "transfer.%s.min" % name),
            "max": _finite(_require(block, "max", "transfer." + name), "transfer.%s.max" % name),
            "n_problems": int(_require(block, "n_problems", "transfer." + name)),
        }
    return out
# ---------------------------------------------------------------------------
# readout channels
# ---------------------------------------------------------------------------

def build_readout(bpath: Mapping[str, Any], axis_readouts: Mapping[str, Any], logit_lens: Mapping[str, Any]) -> Dict[str, Any]:
    static = _require(bpath, "readability_static", "bpath")
    per_id = _require(static, "per_id", "bpath.readability_static")
    markers = []
    for marker_id, row in per_id.items():
        markers.append({
            "id": int(marker_id),
            "dot": _finite(_require(row, "dot", "readability_static.per_id.%s" % marker_id), "readability_static.per_id.%s.dot" % marker_id),
            "freq": int(_require(row, "freq", "readability_static.per_id.%s" % marker_id)),
            "share": _finite(_require(row, "share", "readability_static.per_id.%s" % marker_id), "readability_static.per_id.%s.share" % marker_id),
        })
    markers.sort(key=lambda r: -r["freq"])

    axes = {}
    for name, axis in _require(axis_readouts, "axes", "axis_readouts").items():
        at0 = axis.get("at_delta0", {}) if isinstance(axis, Mapping) else {}
        per_layer = at0.get("per_layer", {}) if isinstance(at0, Mapping) else {}
        layers = {}
        for layer, cell in per_layer.items():
            layers[str(layer)] = {
                "cos": _finite(cell.get("cos"), "axis_readouts.axes.%s.%s.cos" % (name, layer)),
                "control_cos": _finite(cell.get("control_cos"), "axis_readouts.axes.%s.%s.control_cos" % (name, layer)),
                "beats_control": bool(cell.get("beats_control")),
            }
        axes[name] = {
            "label": axis.get("label"),
            "status": axis.get("status"),
            "n_layers_beating_control": int(at0.get("n_layers_beating_control", 0)),
            "n_layers": int(at0.get("n_layers", len(layers))),
            "per_layer": layers,
        }

    lens = _require(logit_lens, "per_layer_mean_p_final", "logit_lens")
    values = [_finite(v, "logit_lens.per_layer_mean_p_final") for v in _require(lens, "values", "logit_lens.per_layer_mean_p_final")]
    layer_scan = bpath.get("layer_profile", {}) if isinstance(bpath, Mapping) else {}
    scan_rows = []
    for row in layer_scan.get("rows", []):
        scan_rows.append({
            "traj": row.get("traj"),
            "mode": row.get("mode"),
            "t": row.get("t"),
            "alpha": _finite(row.get("alpha"), "layer_profile.rows.alpha"),
            "w_dot_hhat": _finite(row.get("w_dot_hhat"), "layer_profile.rows.w_dot_hhat"),
            "pred_marker_lse": _finite(row.get("pred_marker_lse"), "layer_profile.rows.pred_marker_lse"),
            "calibration_ratio": _finite(row.get("calibration_ratio"), "layer_profile.rows.calibration_ratio"),
            "by_layer": dict(row.get("by_layer", {})),
        })

    return {
        "marker": {
            "arith_mean": _finite(_require(static, "arith_mean", "readability_static"), "readability_static.arith_mean"),
            "freq_weighted": _finite(_require(static, "freq_weighted", "readability_static"), "readability_static.freq_weighted"),
            "n_ids_positive": int(_require(static, "n_ids_positive", "readability_static")),
            "n_ids": int(_require(static, "n_ids", "readability_static")),
            "freq_total": int(_require(static, "freq_total", "readability_static")),
            "per_id": markers,
        },
        "axes": axes,
        "logit_lens": {
            "per_layer_mean_p_final": values,
            "n_steps": int(_require(lens, "n_steps", "logit_lens.per_layer_mean_p_final")),
        },
        "layer_scan": {
            "headline": layer_scan.get("headline"),
            "calibration": layer_scan.get("calibration"),
            "retracted": layer_scan.get("retracted"),
            "rows": scan_rows,
        },
    }


# ---------------------------------------------------------------------------
# unit table
# ---------------------------------------------------------------------------

def build_units(mediation: Mapping[str, Any]) -> Dict[str, Any]:
    selection = _require(mediation, "selection", "mediation")
    units = _require(selection, "units", "mediation.selection")
    if not isinstance(units, list) or not units:
        raise DesignError("mediation.selection.units: expected a nonempty list")
    per_layer = []
    for layer in LAYERS:
        rows = [u for u in units if int(u.get("layer", -1)) == layer]
        if not rows:
            raise DesignError("mediation.selection.units: no selected units for layer %d" % layer)
        scores = [_finite(u.get("score"), "selection.units.score") for u in rows]
        magnitudes = [_finite(u.get("baseline_magnitude"), "selection.units.baseline_magnitude") for u in rows]
        norms = [_finite(u.get("column_norm"), "selection.units.column_norm") for u in rows]
        top = sorted(rows, key=lambda u: -_finite(u.get("score"), "selection.units.score"))[:8]
        per_layer.append({
            "layer": layer,
            "n": len(rows),
            "score_mean": sum(scores) / len(scores),
            "score_min": min(scores),
            "score_max": max(scores),
            "baseline_magnitude_mean": sum(magnitudes) / len(magnitudes),
            "column_norm_mean": sum(norms) / len(norms),
            "top_units": [{
                "unit": int(u["unit"]),
                "score": _finite(u["score"], "selection.units.score"),
                "baseline_magnitude": _finite(u["baseline_magnitude"], "selection.units.baseline_magnitude"),
                "column_norm": _finite(u["column_norm"], "selection.units.column_norm"),
            } for u in top],
        })
    return {
        "n_selected": len(units),
        "per_layer": per_layer,
        "caveat": "selection ranks units by measured response times write norm. Per-unit causal effect is NOT measured; block/restore is a group-level test. Do not label an individual unit as a mechanism from this table.",
    }

# ---------------------------------------------------------------------------
# readout atlas summary
# ---------------------------------------------------------------------------

def _fmt_opt(value: Any) -> str:
    return "None" if value is None else "%.4f" % float(value)


def build_readout_atlas_summary(atlas: Mapping[str, Any]) -> Dict[str, Any]:
    aggregate = _require(atlas, "aggregate", "readout_atlas")
    layers = _require(aggregate, "layers", "readout_atlas.aggregate")
    if not isinstance(layers, list) or not layers:
        raise DesignError("readout_atlas.aggregate.layers: expected a nonempty list")
    best_layer = aggregate.get("best_layer")
    best_row = next((row for row in layers if int(row.get("layer", -1)) == int(best_layer)), None) if best_layer is not None else None
    if best_row is None:
        raise DesignError("readout_atlas: best_layer not found in aggregate.layers")
    summarized = []
    for row in layers:
        summarized.append({
            "layer": int(row["layer"]),
            "mean_auc_cos": _opt_float(row.get("mean_auc_cos"), "readout_atlas.layers.mean_auc_cos"),
            "mean_auc_cos_oriented": _opt_float(row.get("mean_auc_cos_oriented"), "readout_atlas.layers.mean_auc_cos_oriented"),
            "mean_auc_norm": _opt_float(row.get("mean_auc_norm"), "readout_atlas.layers.mean_auc_norm"),
            "mean_auc_proj_resid": _opt_float(row.get("mean_auc_proj_resid"), "readout_atlas.layers.mean_auc_proj_resid"),
            "n_trajectories_with_both_classes": int(row.get("n_trajectories_with_both_classes", 0)),
        })
    per_marker_summary = {}
    for marker, item in (atlas.get("per_marker") or {}).items():
        per_marker_summary[str(marker)] = {
            "n_occurrences": int(item.get("n_occurrences", 0)),
            "n_trajectories": int(item.get("n_trajectories", 0)),
            "best_layer": item.get("best_layer"),
            "best_layer_mean_auc_cos": _opt_float(item.get("best_layer_mean_auc_cos"), "readout_atlas.per_marker.best_layer_mean_auc_cos"),
            "best_layer_mean_auc_cos_oriented": _opt_float(item.get("best_layer_mean_auc_cos_oriented"), "readout_atlas.per_marker.best_layer_mean_auc_cos_oriented"),
            "best_layer_orientation": item.get("best_layer_orientation"),
        }
    return {
        "best_layer": int(best_layer),
        "best_layer_mean_auc_cos": _opt_float(best_row.get("mean_auc_cos"), "readout_atlas.best.mean_auc_cos"),
        "best_layer_mean_auc_cos_oriented": _opt_float(best_row.get("mean_auc_cos_oriented"), "readout_atlas.best.mean_auc_cos_oriented"),
        "best_layer_mean_auc_norm": _opt_float(best_row.get("mean_auc_norm"), "readout_atlas.best.mean_auc_norm"),
        "best_layer_mean_auc_proj_resid": _opt_float(best_row.get("mean_auc_proj_resid"), "readout_atlas.best.mean_auc_proj_resid"),
        "best_layer_orientation": best_row.get("cos_orientation"),
        "n_trajectories": int(aggregate.get("n_trajectories", 0)),
        "n_marker_total": int(aggregate.get("n_marker_total", 0)),
        "n_trajectories_with_orientation": int(best_row.get("n_trajectories_with_orientation", 0)),
        "n_trajectories_negative_orientation": int(best_row.get("n_trajectories_negative_orientation", 0)),
        "chance_level": 0.5,
        "layers": summarized,
        "per_marker": per_marker_summary,
        "scope": atlas.get("scope"),
    }


def _opt_float(value: Any, where: str) -> Optional[float]:
    if value is None:
        return None
    return _finite(value, where)




def build_construction_summary(construction: Mapping[str, Any]) -> Dict[str, Any]:
    sites = _require(construction, "sites", "construction")
    aggregate = _require(construction, "aggregate", "construction")
    if not isinstance(sites, list) or not sites:
        raise DesignError("construction.sites: expected a nonempty list")
    by_marker = {}
    for marker, item in aggregate.items():
        candidates = _require(item, "candidates", "construction.aggregate." + str(marker))
        by_marker[str(marker)] = {
            "n_sites": int(item.get("n_sites", 0)),
            "best_candidate": item.get("best_candidate"),
            "candidates": {
                name: {
                    "mean_delta_logp": _finite(value.get("mean_delta_logp"), "construction.aggregate.%s.%s.mean_delta_logp" % (marker, name)),
                    "improved_fraction": _finite(value.get("improved_fraction"), "construction.aggregate.%s.%s.improved_fraction" % (marker, name)),
                }
                for name, value in candidates.items()
            },
        }
    per_site = []
    for site in sites:
        per_site.append({
            "trajectory": site.get("trajectory"),
            "marker": int(site["marker"]),
            "n_prefix": int(site["n_prefix"]),
            "baseline_logp": _finite(site.get("baseline_logp"), "construction.sites.baseline_logp"),
            "candidates": {
                name: _finite(value.get("delta_logp"), "construction.sites.%s.%s.delta_logp" % (site.get("trajectory"), name))
                for name, value in _require(site, "candidates", "construction.sites").items()
            },
        })
    return {
        "n_sites": len(sites),
        "by_marker": by_marker,
        "per_site": per_site,
        "alpha_rule": construction.get("alpha_rule"),
        "scope": construction.get("scope"),
    }




def build_transfer_summary(transfer: Mapping[str, Any]) -> Dict[str, Any]:
    sites = _require(transfer, "sites", "transfer")
    same = _require(transfer, "same_marker", "transfer")
    by_marker = {}
    for marker, item in same.items():
        by_marker[str(marker)] = {
            name: {
                "mean_delta_logp": _finite(value.get("mean_delta_logp"), "transfer.same_marker.%s.%s" % (marker, name)),
                "improved_fraction": _finite(value.get("improved_fraction"), "transfer.same_marker.%s.%s" % (marker, name)),
                "n_sites": int(value.get("n_sites", 0)),
            }
            for name, value in item.items()
        }
    cross = {}
    for source, target_rows in (transfer.get("cross") or {}).items():
        cross[str(source)] = {
            str(target): {
                "mean_delta_logp": _finite(value.get("mean_delta_logp"), "transfer.cross.%s.%s" % (source, target)),
                "improved_fraction": _finite(value.get("improved_fraction"), "transfer.cross.%s.%s" % (source, target)),
                "n_sites": int(value.get("n_sites", 0)),
            }
            for target, value in target_rows.items()
        }
    return {
        "n_sites": len(sites),
        "by_marker": by_marker,
        "cross": cross,
        "alpha_rule": transfer.get("alpha_rule"),
        "scope": transfer.get("scope"),
    }




def build_sweep_summary(steering_sweep: Mapping[str, Any]) -> Dict[str, Any]:
    aggregate = _require(steering_sweep, "aggregate", "steering_sweep")
    useful = _require(steering_sweep, "useful_window", "steering_sweep")
    by_marker = {}
    for marker, item in aggregate.items():
        directions = {}
        for name, rows in _require(item, "directions", "steering_sweep.aggregate.%s" % marker).items():
            directions[str(name)] = [
                {
                    "dose": _finite(row.get("dose"), "steering_sweep.aggregate.%s.%s.dose" % (marker, name)),
                    "mean_delta_logp": _finite(row.get("mean_delta_logp"), "steering_sweep.aggregate.%s.%s.mean_delta_logp" % (marker, name)),
                    "mean_kl": _finite(row.get("mean_kl"), "steering_sweep.aggregate.%s.%s.mean_kl" % (marker, name)),
                    "mean_delta_entropy": _finite(row.get("mean_delta_entropy"), "steering_sweep.aggregate.%s.%s.mean_delta_entropy" % (marker, name)),
                    "mean_delta_other_marker_mass": _finite(row.get("mean_delta_other_marker_mass"), "steering_sweep.aggregate.%s.%s.mean_delta_other_marker_mass" % (marker, name)),
                    "improved_fraction": _finite(row.get("improved_fraction"), "steering_sweep.aggregate.%s.%s.improved_fraction" % (marker, name)),
                    "n_sites": int(row.get("n_sites", 0)),
                }
                for row in rows
            ]
        by_marker[str(marker)] = {
            "directions": directions,
            "useful_window": dict(useful.get(marker, {})) if isinstance(useful.get(marker), Mapping) else {},
        }
    return {
        "n_sites": int(steering_sweep.get("guards", {}).get("n_sites", len(steering_sweep.get("sites", [])))),
        "by_marker": by_marker,
        "doses": [float(dose) for dose in steering_sweep.get("doses", [])],
        "kl_threshold": _finite(steering_sweep.get("kl_threshold"), "steering_sweep.kl_threshold"),
        "scope": steering_sweep.get("scope"),
    }




def build_recipe_summary(recipe: Mapping[str, Any]) -> Dict[str, Any]:
    markers = _require(recipe, "markers", "steering_recipe")
    if not isinstance(markers, Mapping) or not markers:
        raise DesignError("steering_recipe.markers: expected a nonempty mapping")
    output = {}
    for marker, entry in markers.items():
        compiled = _require(entry, "compiled", "steering_recipe.markers.%s" % marker)
        verification = _require(entry, "verification", "steering_recipe.markers.%s" % marker)
        output[str(marker)] = {
            "readout": dict(entry.get("readout", {})),
            "heldout_transfer": dict(entry.get("heldout_transfer", {})),
            "compiled": {
                "direction": compiled.get("direction"),
                "dose": _finite(compiled.get("dose"), "steering_recipe.markers.%s.compiled.dose" % marker),
                "file": compiled.get("file"),
                "public_url": compiled.get("public_url"),
                "expected_delta_logp": _finite(compiled.get("expected_delta_logp"), "steering_recipe.markers.%s.compiled.expected_delta_logp" % marker),
                "expected_kl": _finite(compiled.get("expected_kl"), "steering_recipe.markers.%s.compiled.expected_kl" % marker),
            },
            "verification": {
                "n_sites": int(verification.get("n_sites", 0)),
                "mean_delta_logp": _finite(verification.get("mean_delta_logp"), "steering_recipe.markers.%s.verification.mean_delta_logp" % marker),
                "mean_kl": _finite(verification.get("mean_kl"), "steering_recipe.markers.%s.verification.mean_kl" % marker),
                "sites": list(verification.get("sites", [])),
            },
            "caveats": list(entry.get("caveats", [])),
        }
    return {
        "n_markers": len(output),
        "markers": output,
        "source_hashes": dict(recipe.get("source_hashes", {})),
        "scope": recipe.get("scope"),
    }


# ---------------------------------------------------------------------------
# recommendations
# ---------------------------------------------------------------------------

def build_recommendations(report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    layers = report["layers"]
    dose = report["dose"]
    factorial = report["factorial"]
    readout = report["readout"]
    lens = readout["logit_lens"]["per_layer_mean_p_final"]
    markers = readout["marker"]["per_id"]
    by_layer = {row["layer"]: row for row in layers}
    layer20 = by_layer[20]
    layer25 = by_layer[25]
    net = by_layer[20]["net_effect_primary"]
    primary_plus = [r for r in dose["w+"] if abs(r["dose"] - 0.1) < 1e-9][0]
    primary_minus = [r for r in dose["w-"] if abs(r["dose"] - 0.1) < 1e-9][0]
    recs: List[Dict[str, Any]] = []

    recs.append({
        "priority": "high",
        "action": "define_target",
        "layer": None,
        "reason": "The vector is readable for the marker set but its measured causal effect is on multiplication correctness, and that effect is negative at the primary dose. Designing from w·U alone would optimise the wrong readout.",
        "evidence": [
            "freq-weighted w·U = %+.5f, %d/%d marker ids positive" % (readout["marker"]["freq_weighted"], readout["marker"]["n_ids_positive"], readout["marker"]["n_ids"]),
            "+v primary effect on correctness score = %+.5f" % net,
        ],
        "confidence": "measured",
    })

    recs.append({
        "priority": "high",
        "action": "avoid_positive_injection",
        "layer": 20,
        "reason": "Block-20 units move with the vector's net (negative) effect: restoring them during +v lowers the score further, and restoring them into baseline lowers it too. Injecting +v at this layer pushes the measured readout the wrong way for a correctness target.",
        "evidence": [
            "block %+.5f, restore %+.5f, support %+.5f" % (layer20["block_mean"], layer20["restore_mean"], layer20["support"]),
            "net +v effect at dose 0.1 = %+.5f" % net,
        ],
        "confidence": "measured",
    })

    recs.append({
        "priority": "high",
        "action": "test_compensator_removal",
        "layer": 25,
        "reason": "Block-25 units oppose the vector's net effect: restoring them during +v raises the score, and restoring them into baseline also raises it. This is the first layer to test for removal / sign flip before building a new direction.",
        "evidence": [
            "block %+.5f, restore %+.5f, compensation %+.5f" % (layer25["block_mean"], layer25["restore_mean"], layer25["compensation"]),
            "same-sign block/restore = %s; random rank %d/%d" % (layer25["same_sign"], layer25["random_rank"], layer25["n_random_groups"] + 1),
        ],
        "confidence": "descriptive",
    })

    weak_layers = [row["layer"] for row in layers if row["action"] == "weak"]
    if weak_layers:
        recs.append({
            "priority": "low",
            "action": "do_not_use_as_lever",
            "layer": None,
            "reason": "These layers have no layer-specific block/restore effect above the floor; do not present them as a mechanism without new measurements.",
            "evidence": ["weak layers: %s" % ", ".join(str(x) for x in weak_layers)],
            "confidence": "measured",
        })

    recs.append({
        "priority": "high",
        "action": "choose_direction_by_sign",
        "layer": None,
        "reason": "The effect reverses with the sign of the injected direction and grows with dose. For a correctness target the current +v is the wrong sign at the primary dose; -v is positive at every tested dose.",
        "evidence": [
            "w+ primary %+.5f; w- primary %+.5f; random primary %+.5f" % (
                primary_plus["mean"], primary_minus["mean"], dose["random_primary"]),
            "w+ at dose %s: %+.5f; w- at dose %s: %+.5f" % (
                dose["w+"][0]["dose"], dose["w+"][0]["mean"], dose["w-"][0]["dose"], dose["w-"][0]["mean"]),
        ],
        "confidence": "measured",
    })

    recs.append({
        "priority": "medium",
        "action": "condition_on_wording",
        "layer": None,
        "reason": "The sign of the effect depends on wording and equation truth. Fix the target wording before comparing vectors or doses.",
        "evidence": [
            "correct/neutral %+.5f; correct/self-check %+.5f; incorrect/neutral %+.5f; incorrect/self-check %+.5f" % (
                factorial["True_neutral"]["mean"], factorial["True_self_check_phrase"]["mean"],
                factorial["False_neutral"]["mean"], factorial["False_self_check_phrase"]["mean"],
            )
        ],
        "confidence": "measured",
    })

    dominant = markers[0] if markers else None
    if dominant is not None:
        recs.append({
            "priority": "high",
            "action": "do_not_treat_marker_set_as_one_concept",
            "layer": None,
            "reason": "Readout is positive for all markers, but the injection effect depends on which marker token is present. The dominant marker is suppressed by +w in the original marker-steering report, so the set average is not a single control target.",
            "evidence": [
                "dominant marker id %d: w·U %+.5f, share %.3f" % (dominant["id"], dominant["dot"], dominant["share"]),
                "marker-steering report: +w suppresses the dominant marker while raising the others",
            ],
            "confidence": "measured",
        })

    atlas = report.get("readout_atlas")
    if atlas:
        recs.append({
            "priority": "high",
            "action": "do_not_use_cos_h_w_as_positive_readout",
            "layer": atlas.get("best_layer"),
            "reason": "The hidden-state atlas finds its best marker separation at layer %s, but the orientation is negative: marker next-token positions have LOWER cos(h,w) (raw AUC %.4f; oriented AUC %.4f). This holds in %s/%s trajectories with both classes. The static w·U readout therefore does not transfer to a positive state-space projection; do not select layers or units by w·h." % (
                atlas.get("best_layer"),
                atlas.get("best_layer_mean_auc_cos") or float("nan"),
                atlas.get("best_layer_mean_auc_cos_oriented") or float("nan"),
                atlas.get("n_trajectories_negative_orientation"),
                atlas.get("n_trajectories_with_orientation"),
            ),
            "evidence": [
                "best layer %s: raw cos AUC %s, oriented cos AUC %s, orientation %s" % (
                    atlas.get("best_layer"),
                    _fmt_opt(atlas.get("best_layer_mean_auc_cos")),
                    _fmt_opt(atlas.get("best_layer_mean_auc_cos_oriented")),
                    atlas.get("best_layer_orientation"),
                ),
                "norm control AUC %s; residualised raw AUC %s" % (
                    _fmt_opt(atlas.get("best_layer_mean_auc_norm")),
                    _fmt_opt(atlas.get("best_layer_mean_auc_proj_resid")),
                ),
                "n_marker=%s, n_trajectories=%s" % (
                    atlas.get("n_marker_total"), atlas.get("n_trajectories")),
            ],
            "confidence": "descriptive",
        })
        per_marker = atlas.get("per_marker") or {}
        if per_marker:
            ordered = sorted(per_marker.items(), key=lambda item: -int(item[1].get("n_occurrences", 0)))
            reliable = [(str(marker), item) for marker, item in ordered if int(item.get("n_occurrences", 0)) >= 10]
            if not reliable:
                reliable = [(str(marker), item) for marker, item in ordered]
            positive = [(marker, item) for marker, item in reliable if item.get("best_layer_orientation") == 1]
            negative = [(marker, item) for marker, item in reliable if item.get("best_layer_orientation") == -1]
            positive_ids = [marker for marker, _ in positive]
            negative_ids = [marker for marker, _ in negative]
            top_positive = max(positive, key=lambda pair: pair[1].get("best_layer_mean_auc_cos") or -1.0) if positive else None
            top_negative = min(negative, key=lambda pair: pair[1].get("best_layer_mean_auc_cos") or 2.0) if negative else None
            if top_positive is not None and top_negative is not None:
                reason = "Per-marker readout resolves the set-level anti-alignment: marker %s (n=%s) is positively oriented at layer %s (raw cos AUC %s), while marker %s is the strongest negative (n=%s, layer %s, raw cos AUC %s). The set-level AUC hides this sign split. A single direction/sign cannot positively read all seven; pick the target marker and build its own direction and layer." % (
                    top_positive[0], top_positive[1].get("n_occurrences"), top_positive[1].get("best_layer"),
                    _fmt_opt(top_positive[1].get("best_layer_mean_auc_cos")),
                    top_negative[0], top_negative[1].get("n_occurrences"), top_negative[1].get("best_layer"),
                    _fmt_opt(top_negative[1].get("best_layer_mean_auc_cos")),
                )
            else:
                reason = "Per-marker readout resolves the set-level anti-alignment: positive markers are %s, negative markers are %s. A single direction/sign cannot positively read all seven; pick the target marker and build its own direction and layer." % (
                    ", ".join(positive_ids) or "none", ", ".join(negative_ids) or "none")
            recs.append({
                "priority": "high",
                "action": "split_marker_directions_by_sign",
                "layer": None,
                "reason": reason,
                "evidence": [
                    "marker %s: n=%s, best layer %s, raw cos AUC %s, orientation %s" % (
                        marker, item.get("n_occurrences"), item.get("best_layer"),
                        _fmt_opt(item.get("best_layer_mean_auc_cos")), item.get("best_layer_orientation"))
                    for marker, item in ordered
                ],
                "confidence": "descriptive",
            })
            small = [str(marker) for marker, item in ordered if int(item.get("n_occurrences", 0)) < 10]
            if small:
                recs.append({
                    "priority": "low",
                    "action": "do_not_adjudicate_small_n_markers",
                    "layer": None,
                    "reason": "These markers have fewer than 10 occurrences in the 30-trajectory atlas; their per-marker AUC is not adjudicable and must not be used to choose a direction.",
                    "evidence": ["small-n markers: %s" % ", ".join(small)],
                    "confidence": "measured",
                })
        else:
            recs.append({
                "priority": "medium",
                "action": "check_per_marker_sign_before_flipping",
                "layer": atlas.get("best_layer"),
                "reason": "The atlas treats the seven marker ids as one label. Split the label per marker and re-measure before choosing a direction.",
                "evidence": ["per-marker AUC not present in the atlas summary"],
                "confidence": "descriptive",
            })

    construction = report.get("construction")
    if construction:
        by_marker = construction.get("by_marker") or {}
        evidence = []
        for marker in sorted(by_marker):
            item = by_marker[marker]
            candidates = item.get("candidates", {})
            gradient = candidates.get("gradient", {})
            original = candidates.get("w", {})
            evidence.append("marker %s: mean delta w %+.5f (improved %.2f), gradient %+.5f (improved %.2f), n=%s" % (
                marker,
                original.get("mean_delta_logp", float("nan")),
                original.get("improved_fraction", float("nan")),
                gradient.get("mean_delta_logp", float("nan")),
                gradient.get("improved_fraction", float("nan")),
                item.get("n_sites"),
            ))
        recs.append({
            "priority": "high",
            "action": "use_gradient_direction_as_constructive_baseline",
            "layer": 20,
            "reason": "On %d short AIME prefixes, the normalized local gradient g = d log p(marker) / d h at layer 20 improved the target on every site and was the best candidate for all tested markers; w was negative for 7196 and weaker for 10061/6771, and w+g matched g. Use g as the constructive baseline, then audit native units." % construction.get("n_sites", 0),
            "evidence": evidence,
            "confidence": "measured",
        })
        recs.append({
            "priority": "medium",
            "action": "treat_unit_decomposition_as_diagnostic",
            "layer": None,
            "reason": "The per-unit decomposition is first-order and its sum-to-measured ratio varies across sites; the quadrants are useful for diagnosing carriers vs compensators, but they are not a validated mediation percentage, and naive removal of write-direction components failed in the prototype.",
            "evidence": [
                "see experiments/steering_construction_v1/steering_construction.json decomposition.ratio",
                "gradient is a white-box local direction; it is not a semantically named steering vector",
            ],
            "confidence": "descriptive",
        })

    steering_transfer = report.get("steering_transfer")
    if steering_transfer:
        by_marker = steering_transfer.get("by_marker") or {}
        evidence = []
        for marker in sorted(by_marker):
            item = by_marker[marker]
            evidence.append("marker %s: w %+.5f, mean g %+.5f, sparse g %+.5f, oracle %+.5f (held-out n=%s)" % (
                marker,
                item.get("w", {}).get("mean_delta_logp", float("nan")),
                item.get("g_mean", {}).get("mean_delta_logp", float("nan")),
                item.get("g_sparse", {}).get("mean_delta_logp", float("nan")),
                item.get("oracle_per_site_gradient", {}).get("mean_delta_logp", float("nan")),
                item.get("g_mean", {}).get("n_sites"),
            ))
        cross = steering_transfer.get("cross") or {}
        source_7196 = cross.get("7196", {})
        source_10061 = cross.get("10061", {})
        if source_7196 and source_10061:
            evidence.append("cross: 7196 mean g on 10061 %+.5f, on 6771 %+.5f; 10061 mean g on 7196 %+.5f" % (
                source_7196.get("10061", {}).get("mean_delta_logp", float("nan")),
                source_7196.get("6771", {}).get("mean_delta_logp", float("nan")),
                source_10061.get("7196", {}).get("mean_delta_logp", float("nan")),
            ))
        recs.append({
            "priority": "high",
            "action": "use_per_marker_mean_gradient_on_heldout",
            "layer": 20,
            "reason": "A mean gradient built on calibration sites per marker improved held-out f on all tested markers and retained most of the per-site oracle effect; w was much weaker (and negative for 7196). The cross matrix shows the 7196 direction is negative for other markers while 10061/6771 directions are positive for all, so at least 7196 needs its own direction. Use per-marker mean g as the construct, with sparse g as the interpretable variant.",
            "evidence": evidence,
            "confidence": "measured",
        })
        recs.append({
            "priority": "medium",
            "action": "sparse_direction_retains_effect",
            "layer": None,
            "reason": "Keeping only the top 10% of mean-gradient coordinates (sparse g) retained 78-100% of the held-out effect in this probe. It is a candidate for a more interpretable direction, but it is still a white-box local average, not a semantic vector.",
            "evidence": [
                "see experiments/steering_transfer_v1/steering_transfer.json same_marker.*.g_sparse",
            ],
            "confidence": "descriptive",
        })

    steering_sweep = report.get("steering_sweep")
    if steering_sweep:
        by_marker = steering_sweep.get("by_marker") or {}
        evidence = []
        for marker in sorted(by_marker):
            item = by_marker[marker]
            window = item.get("useful_window", {})
            directions = item.get("directions", {})
            def at(direction, dose):
                return next((row for row in directions.get(direction, []) if abs(float(row["dose"]) - dose) < 1e-9), None)
            mean_05 = at("mean_g", 0.05)
            sparse_05 = at("sparse_g", 0.05)
            evidence.append("marker %s: useful %s @ %s (df %+.4f, KL %s); at dose 0.05 mean g KL %s vs sparse g KL %s" % (
                marker, window.get("direction"), window.get("dose"),
                window.get("mean_delta_logp", float("nan")), _fmt_opt(window.get("mean_kl")),
                _fmt_opt(mean_05.get("mean_kl")) if mean_05 else "None",
                _fmt_opt(sparse_05.get("mean_kl")) if sparse_05 else "None",
            ))
        recs.append({
            "priority": "high",
            "action": "choose_direction_and_dose_by_kl_frontier",
            "layer": 20,
            "reason": "The sweep makes the effect/side-effect tradeoff explicit: mean g reaches the largest delta log p but with large KL and entropy drop; sparse g has lower KL at the same dose; w is safest but weaker. Under a mean-KL budget of %s the useful windows differ by marker, so do not use one direction/dose for all markers. Pick the window per marker, then verify side effects on more sites." % steering_sweep.get("kl_threshold"),
            "evidence": evidence,
            "confidence": "measured",
        })
        recs.append({
            "priority": "medium",
            "action": "sparse_g_reduces_side_effect",
            "layer": None,
            "reason": "At the same dose, sparse g (top 10% of mean-gradient coordinates) gives a lower global KL than dense mean g while retaining most of the target effect. It is a candidate for a more interpretable, lower-side-effect direction, but still a local white-box average.",
            "evidence": [
                "see experiments/steering_sweep_v1/steering_sweep.json aggregate.*.directions.mean_g / sparse_g",
            ],
            "confidence": "descriptive",
        })

    steering_recipe = report.get("steering_recipe")
    if steering_recipe:
        by_marker = steering_recipe.get("markers") or {}
        evidence = []
        for marker in sorted(by_marker):
            entry = by_marker[marker]
            compiled = entry.get("compiled", {})
            verification = entry.get("verification", {})
            evidence.append("marker %s: %s @ dose %s -> %s; verified mean delta %+.4f, mean KL %s (n=%s)" % (
                marker, compiled.get("direction"), compiled.get("dose"), compiled.get("file"),
                verification.get("mean_delta_logp", float("nan")), _fmt_opt(verification.get("mean_kl")),
                verification.get("n_sites"),
            ))
        recs.append({
            "priority": "high",
            "action": "compiled_recipe_available",
            "layer": 20,
            "reason": "One compiled .npy vector per marker is available, with the direction/dose chosen from the KL-budgeted sweep and a held-out verification. Treat it as a reproducible starting point: the verification reuses the transfer/sweep held-out sites, not a third independent split, and the files are local white-box directions rather than semantic production vectors.",
            "evidence": evidence,
            "confidence": "measured",
        })

    axes = readout["axes"]
    confidence_axis = axes.get("confidence", {})
    if confidence_axis:
        recs.append({
            "priority": "medium",
            "action": "do_not_use_readout_axis_blindly",
            "layer": None,
            "reason": "The only readout axis that beats the position control is confidence, and it is marked tautological (its target is a restatement of top-1 probability). There is no specific, non-circular readout axis to steer by yet.",
            "evidence": [
                "confidence axis: status=%s, layers beating control %d/%d" % (
                    confidence_axis.get("status"), confidence_axis.get("n_layers_beating_control"), confidence_axis.get("n_layers")),
            ],
            "confidence": "measured",
        })

    if len(lens) >= 2:
        early = lens[18] if len(lens) > 18 else lens[0]
        recs.append({
            "priority": "medium",
            "action": "prefer_late_layers_for_answer",
            "layer": None,
            "reason": "The final token only becomes linearly decodable late: mean p_final is near zero through the early layers and rises sharply after block 18. Early-layer injections must be verified with the readout atlas before being called answer-steering.",
            "evidence": [
                "mean p_final layer 0 %.5f -> layer 18 %.5f -> layer %d %.5f" % (lens[0], early, len(lens) - 1, lens[-1]),
                "logit-lens steps = %d" % readout["logit_lens"]["n_steps"],
            ],
            "confidence": "measured",
        })

    recs.append({
        "priority": "high",
        "action": "replicate_before_building",
        "layer": None,
        "reason": "All layer/unit effects above are from six held-out multiplication problems, one model, one vector, and are descriptive. Treat them as hypotheses for the next measurement, not as a construction recipe.",
        "evidence": [
            "n_evaluation_problems = 6; single model; single vector; per-unit causal alignment not measured",
        ],
        "confidence": "measured",
    })

    return recs


UNMEASURED = [
    "per-unit causal alignment: gradient of the target readout with respect to each unit product, dotted with its write direction",
    "control direction: solve C v = a for a requested high-level effect instead of reusing a readout direction",
    "token-composition-matched control: swap the marker token at a fixed position and re-measure",
    "second model and second vector: external validity of the layer/compensation pattern",
    "closed-loop controller: recompute the direction per generated token instead of one fixed injection",
    "marker-specific steering vector: one direction per marker instead of a frequency-weighted set average",
]

WARNINGS = [
    "This report is descriptive, not a validated construction recipe. The measured label means the number exists in the source artifact, not that the effect is statistically significant.",
    "Readout (w·U on the marker set) and causal effect (correctness score on held-out multiplication problems) are different targets; do not treat one as evidence for the other.",
    "Block/restore effects are group-level. The unit table is a response ranking, not a causal ranking.",
    "The marker-steering artifact reports selfcheck_passed=false (one Q3 check had no criterion); its readout numbers are usable but its verdict block is not a clean pass.",
]


# ---------------------------------------------------------------------------
# whole report
# ---------------------------------------------------------------------------

def build_report(
    summary: Mapping[str, Any],
    bpath: Mapping[str, Any],
    axis_readouts: Mapping[str, Any],
    logit_lens: Mapping[str, Any],
    mediation: Mapping[str, Any],
    *,
    source_paths: Optional[Mapping[str, str]] = None,
    source_hashes: Optional[Mapping[str, str]] = None,
    readout_atlas: Optional[Mapping[str, Any]] = None,
    construction: Optional[Mapping[str, Any]] = None,
    steering_transfer: Optional[Mapping[str, Any]] = None,
    steering_sweep: Optional[Mapping[str, Any]] = None,
    steering_recipe: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    layers = build_layer_table(summary)
    dose = build_dose_table(summary)
    factorial = build_factorial(summary)
    transfer = build_transfer(summary)
    readout = build_readout(bpath, axis_readouts, logit_lens)
    units = build_units(mediation)
    atlas_summary = build_readout_atlas_summary(readout_atlas) if readout_atlas is not None else None
    construction_summary = build_construction_summary(construction) if construction is not None else None
    steering_transfer_summary = build_transfer_summary(steering_transfer) if steering_transfer is not None else None
    steering_sweep_summary = build_sweep_summary(steering_sweep) if steering_sweep is not None else None
    steering_recipe_summary = build_recipe_summary(steering_recipe) if steering_recipe is not None else None
    if not summary.get("complete") or not mediation.get("complete"):
        raise DesignError("source artifacts report complete != true")
    if not bpath.get("readability_static"):
        raise DesignError("bpath artifact has no readability_static block")
    doses = sorted(float(d) for d in _require(summary["response"], "w+", "response"))

    report: Dict[str, Any] = {
        "schema": SCHEMA,
        "complete": True,
        "scope": "descriptive design guide from existing Qwen3-1.7B artifacts; no new model forward passes",
        "source_paths": dict(source_paths or {}),
        "source_hashes": dict(source_hashes or {}),
        "vector": {
            "arm": bpath.get("arm"),
            "injection_block": 20,
            "doses": doses,
            "primary_strength": float(PRIMARY_STRENGTH),
            "baseline": dict(summary["baseline"]),
        },
        "layers": layers,
        "dose": dose,
        "factorial": factorial,
        "transfer": transfer,
        "readout": readout,
        "readout_atlas": atlas_summary,
        "construction": construction_summary,
        "steering_transfer": steering_transfer_summary,
        "steering_sweep": steering_sweep_summary,
        "steering_recipe": steering_recipe_summary,
        "units": units,
        "recommendations": [],
        "unmeasured": list(UNMEASURED),
        "warnings": list(WARNINGS),
    }
    if atlas_summary:
        report["warnings"].append(
            "The readout atlas keeps per-marker rows: best layers and orientations differ across markers (see readout_atlas.per_marker). The set-level AUC must not be used to choose one layer/sign, and small-n markers are not adjudicable."
        )
    if construction_summary:
        report["warnings"].append(
            "The construction probe is a local white-box measurement on short AIME prefixes: it compares candidate directions at one alpha, not a general recipe. The first-order unit decomposition is a diagnostic, not a validated mediation percentage."
        )
    if steering_transfer_summary:
        report["warnings"].append(
            "The held-out transfer has two calibration and two held-out sites per marker; the split is by prefix length, so length/position confounding is possible. Treat the transfer numbers as descriptive, not as a validated recipe."
        )
    if steering_sweep_summary:
        report["warnings"].append(
            "The alpha sweep has six held-out sites and a single model; KL/entropy are global side effects. High doses can be off-manifold, and the useful window is a descriptive choice under a chosen KL budget."
        )
    if steering_recipe_summary:
        report["warnings"].append(
            "The compiled recipe verifies on the same held-out sites used by the transfer/sweep, not on a third independent split. The .npy files are local candidate directions, not a validated production steering vector."
        )
    report["recommendations"] = build_recommendations(report)
    report["headline"] = (
        "Readout is positive for all %d marker ids, but the measured +v effect on correctness is "
        "%+.5f at the primary dose. Block 20 supports that negative effect; block 25 compensates it. "
        "The current vector is a readout direction, not a validated control direction."
    ) % (report["readout"]["marker"]["n_ids"], report["layers"][0]["net_effect_primary"])
    if atlas_summary:
        report["headline"] += " Hidden-state atlas: best layer %d, raw cos AUC %.4f, orientation %s (w·h is anti-aligned with marker positions)." % (
            atlas_summary["best_layer"],
            atlas_summary["best_layer_mean_auc_cos"] if atlas_summary["best_layer_mean_auc_cos"] is not None else float("nan"),
            atlas_summary["best_layer_orientation"],
        )
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = []
    lines.append("# Steering design guide (%s)" % report["schema"])
    lines.append("")
    lines.append(report["headline"])
    lines.append("")
    lines.append("> This is a **descriptive** guide built from existing artifacts. It does not rerun the model.")
    lines.append("")
    lines.append("## Layer strategy")
    lines.append("")
    lines.append("| layer | block | restore | support | compensation | same-sign block/restore | action | random rank |")
    lines.append("|---:|---:|---:|---:|---:|---|---|---:|")
    def same_sign(values, mean):
        sign = 1 if mean >= 0 else -1
        same = sum(1 for value in values.values() if (1 if value >= 0 else -1) == sign)
        return str(same) + "/" + str(len(values))
    for row in report["layers"]:
        lines.append("| %d | %+.5f | %+.5f | %+.5f | %+.5f | %s / %s | %s | %d/%d |" % (
            row["layer"], row["block_mean"], row["restore_mean"], row["support"],
            row["compensation"], same_sign(row["block_per_problem"], row["block_mean"]),
            same_sign(row["restore_per_problem"], row["restore_mean"]),
            row["action"], row["random_rank"], row["n_random_groups"] + 1))
    lines.append("")
    lines.append("## Dose / direction")
    lines.append("")
    lines.append("| dose | w+ | w- |")
    lines.append("|---:|---:|---:|")
    w_plus = {row["dose"]: row["mean"] for row in report["dose"]["w+"]}
    w_minus = {row["dose"]: row["mean"] for row in report["dose"]["w-"]}
    for dose in sorted(w_plus):
        lines.append("| %s | %+.5f | %+.5f |" % (dose, w_plus[dose], w_minus.get(dose, float("nan"))))
    lines.append("")
    lines.append("random primary: %+.5f" % report["dose"]["random_primary"])
    lines.append("")
    atlas = report.get("readout_atlas")
    if atlas:
        lines.append("## Hidden-state readout atlas")
        lines.append("")
        lines.append("- best layer: **%s**" % atlas["best_layer"])
        lines.append("- raw cos AUC: %s; oriented cos AUC: %s; orientation: %s" % (
            _fmt_opt(atlas.get("best_layer_mean_auc_cos")),
            _fmt_opt(atlas.get("best_layer_mean_auc_cos_oriented")),
            atlas.get("best_layer_orientation"),
        ))
        lines.append("- norm control AUC: %s; residualised raw AUC: %s" % (
            _fmt_opt(atlas.get("best_layer_mean_auc_norm")),
            _fmt_opt(atlas.get("best_layer_mean_auc_proj_resid")),
        ))
        lines.append("- %s markers / %s trajectories; negative orientation in %s/%s trajectories with both classes" % (
            atlas.get("n_marker_total"), atlas.get("n_trajectories"),
            atlas.get("n_trajectories_negative_orientation"), atlas.get("n_trajectories_with_orientation"),
        ))
        lines.append("- chance level: %.1f; this is descriptive, not a significance test" % atlas.get("chance_level", 0.5))
        per_marker = atlas.get("per_marker") or {}
        if per_marker:
            lines.append("")
            lines.append("| marker | n | best layer | raw cos AUC | orientation |")
            lines.append("|---|---:|---:|---:|---:|")
            for marker, item in sorted(per_marker.items(), key=lambda pair: -int(pair[1].get("n_occurrences", 0))):
                lines.append("| %s | %s | %s | %s | %s |" % (
                    marker, item.get("n_occurrences"), item.get("best_layer"),
                    _fmt_opt(item.get("best_layer_mean_auc_cos")), item.get("best_layer_orientation")))
        lines.append("")
    construction = report.get("construction")
    if construction:
        lines.append("## Construction probe")
        lines.append("")
        lines.append("- %d sites; alpha rule: %s" % (construction.get("n_sites", 0), construction.get("alpha_rule")))
        lines.append("")
        lines.append("| marker | n | mean delta w | mean delta g | mean delta w+g | best |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for marker, item in sorted(construction.get("by_marker", {}).items()):
            candidates = item.get("candidates", {})
            def value(name):
                return candidates.get(name, {}).get("mean_delta_logp")
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                marker, item.get("n_sites"),
                _fmt_opt(value("w")), _fmt_opt(value("gradient")), _fmt_opt(value("w_plus_gradient")),
                item.get("best_candidate")))
        lines.append("")
    transfer_result = report.get("steering_transfer")
    if transfer_result:
        lines.append("## Held-out transfer")
        lines.append("")
        lines.append("| marker | w | mean g | sparse g | oracle g |")
        lines.append("|---|---:|---:|---:|---:|")
        for marker, item in sorted(transfer_result.get("by_marker", {}).items()):
            lines.append("| %s | %s | %s | %s | %s |" % (
                marker,
                _fmt_opt(item.get("w", {}).get("mean_delta_logp")),
                _fmt_opt(item.get("g_mean", {}).get("mean_delta_logp")),
                _fmt_opt(item.get("g_sparse", {}).get("mean_delta_logp")),
                _fmt_opt(item.get("oracle_per_site_gradient", {}).get("mean_delta_logp")),
            ))
        cross = transfer_result.get("cross", {})
        if cross:
            lines.append("")
            lines.append("Cross-marker mean-g transfer (source row -> target column):")
            for source, target_rows in sorted(cross.items()):
                lines.append("- %s -> %s" % (source, ", ".join("%s %s" % (target, _fmt_opt(value.get("mean_delta_logp"))) for target, value in sorted(target_rows.items()))))
        lines.append("")
    sweep_result = report.get("steering_sweep")
    if sweep_result:
        lines.append("## Alpha / side-effect sweep")
        lines.append("")
        lines.append("| marker | useful direction | dose | mean delta | mean KL |")
        lines.append("|---|---|---:|---:|---:|")
        for marker, item in sorted(sweep_result.get("by_marker", {}).items()):
            window = item.get("useful_window", {})
            lines.append("| %s | %s | %s | %s | %s |" % (
                marker, window.get("direction"), window.get("dose"),
                _fmt_opt(window.get("mean_delta_logp")), _fmt_opt(window.get("mean_kl")),
            ))
        lines.append("")
    recipe_result = report.get("steering_recipe")
    if recipe_result:
        lines.append("## Compiled recipe")
        lines.append("")
        lines.append("| marker | direction | dose | expected delta | expected KL | verified delta | verified KL | file |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---|")
        for marker, entry in sorted(recipe_result.get("markers", {}).items()):
            compiled = entry.get("compiled", {})
            verification = entry.get("verification", {})
            lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                marker, compiled.get("direction"), compiled.get("dose"),
                _fmt_opt(compiled.get("expected_delta_logp")), _fmt_opt(compiled.get("expected_kl")),
                _fmt_opt(verification.get("mean_delta_logp")), _fmt_opt(verification.get("mean_kl")),
                compiled.get("file"),
            ))
        lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    for rec in report["recommendations"]:
        layer = "layer %s" % rec["layer"] if rec["layer"] is not None else "global"
        lines.append("- **[%s] %s** (%s, %s): %s" % (rec["priority"], rec["action"], layer, rec["confidence"], rec["reason"]))
        for ev in rec["evidence"]:
            lines.append("  - %s" % ev)
    lines.append("")
    lines.append("## Unmeasured")
    lines.append("")
    for item in report["unmeasured"]:
        lines.append("- %s" % item)
    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    for item in report["warnings"]:
        lines.append("- %s" % item)
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    for name in sorted(report.get("source_paths", {})):
        lines.append("- %s: %s" % (name, report["source_paths"][name]))
        digest = report.get("source_hashes", {}).get(name)
        if digest:
            lines.append("  - sha256 %s" % digest)
    lines.append("")
    return chr(10).join(lines) + chr(10)

