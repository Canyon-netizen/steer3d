#!/usr/bin/env python3
"""Interpretable unit-basis steering design with a calibration-only rule.

For each marker:
  1. calibration sites -> h at block-20 input and g = d log p / d h;
  2. native SwiGLU unit input directions u_i = d a_i / d h at layer 20;
  3. c_i = g . u_i; v_k = normalize(sum_{top-k} c_i u_i), averaged over sites;
  4. choose k on calibration at a safe dose: smallest k reaching 90% of the
     best calibration delta, with KL <= 0.1;
  5. choose the largest calibration dose with mean KL <= 0.1 for that k;
  6. report the held-out design curve and the selected recipe.

The selection uses calibration only; held-out is a verification readout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.steering_gradient import mean_direction, normalize, sparse_direction  # noqa: E402
from core.steering_sweep import marker_summary  # noqa: E402
from core.unit_design import (  # noqa: E402
    blend_vectors,
    omp_unit_vectors,
    unit_activations,
    unit_coefficients,
    unit_direction_matrix,
)
from core.neuron_mediation import native_forward  # noqa: E402

SCHEMA = "steer3d.unit_design/1"
DEFAULT_VECTOR = ROOT / ".cache/bpath/results_B/w_L19_m0.npy"
K_GRID = [1, 2, 5, 10, 20, 50, 100, 200, 500]
LOW_DOSE = 0.02
DOSES = [0.02, 0.05, 0.1]
KL_BUDGET = 0.1
EFFECT_FRACTION = 0.9


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_sites(data_root: Path, markers, max_prefix: int, per_marker: int):
    sites = []
    for path in sorted(data_root.glob("*.npz")):
        with np.load(path) as data:
            ids = data["token_ids"]
            prompt = data["prompt_token_ids"]
        for t in range(len(ids) - 1):
            marker = int(ids[t + 1])
            if marker not in markers:
                continue
            n_prefix = int(len(prompt) + t + 1)
            if n_prefix > max_prefix:
                continue
            sites.append({
                "trajectory": path.stem,
                "problem": path.stem.replace("aime__", "").replace("__think", "").replace("__no_think", ""),
                "mode": "think" if path.stem.endswith("__think") else "no_think",
                "t": int(t),
                "marker": marker,
                "n_prefix": n_prefix,
                "prompt": prompt,
                "ids": ids,
            })
    chosen = []
    for marker in markers:
        rows = sorted([site for site in sites if site["marker"] == marker], key=lambda site: site["n_prefix"])
        taken = []
        seen = set()
        for row in rows:
            if row["trajectory"] in seen:
                continue
            taken.append(row)
            seen.add(row["trajectory"])
            if len(taken) >= per_marker:
                break
        if len(taken) < per_marker:
            for row in rows:
                if row not in taken:
                    taken.append(row)
                if len(taken) >= per_marker:
                    break
        chosen.extend(taken)
    return chosen


def full_ids(site) -> np.ndarray:
    return np.concatenate([site["prompt"], site["ids"][: site["t"] + 1]]).astype(np.int64)


def summarize(rows):
    return {
        "n_sites": len(rows),
        "mean_delta_logp": float(np.mean([row["delta_logp"] for row in rows])),
        "improved_fraction": float(np.mean([row["delta_logp"] > 0 for row in rows])),
        "mean_kl": float(np.mean([row["kl"] for row in rows])),
        "mean_delta_entropy": float(np.mean([row["delta_entropy"] for row in rows])),
        "mean_delta_other_marker_mass": float(np.mean([row["delta_other_marker_mass"] for row in rows])),
    }


def coefficient_mass(coefficients, k):
    values = []
    for row in coefficients:
        ordered = np.sort(np.abs(row))[::-1]
        total = float(ordered.sum())
        values.append(float(ordered[: int(k)].sum() / total) if total else 0.0)
    return float(np.mean(values))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "datasets/aime_qwen3_1p7b_32k_fp32/aime")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "datasets/models/Qwen3-1.7B")
    parser.add_argument("--vector", type=Path, default=DEFAULT_VECTOR)
    parser.add_argument("--markers", default="7196,10061,6771")
    parser.add_argument("--per-marker", type=int, default=4)
    parser.add_argument("--split-mode", choices=["interleave", "length"], default="interleave",
                        help="interleave balances prefix length between calibration and held-out")
    parser.add_argument("--max-prefix", type=int, default=400)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--layer", type=int, default=20)
    parser.add_argument("--sweep", type=Path, default=ROOT / "experiments/steering_sweep_v1/steering_sweep.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments/unit_design_v1")
    parser.add_argument("--out", type=Path, default=ROOT / "experiments/unit_design_v1/unit_design.json")
    parser.add_argument("--public", type=Path, default=ROOT / "frontend/public/latent/data/unit_design.json")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM

    sweep = json.loads(args.sweep.read_text(encoding="utf-8"))
    vector = normalize(np.load(args.vector).astype(np.float32))
    vector_sha = sha256_file(args.vector)
    markers = [int(item) for item in args.markers.split(",") if item.strip()]
    sites = select_sites(args.data_root, markers, args.max_prefix, args.per_marker)
    splits = {}
    for marker in markers:
        rows = sorted([site for site in sites if site["marker"] == marker], key=lambda site: site["n_prefix"])
        if args.split_mode == "interleave":
            calibration = [row for index, row in enumerate(rows) if index % 2 == 0]
            heldout = [row for index, row in enumerate(rows) if index % 2 == 1]
        else:
            half = max(1, len(rows) // 2)
            calibration, heldout = rows[:half], rows[half:]
        if not calibration or not heldout:
            raise SystemExit("marker %d has an empty split" % marker)
        splits[marker] = {"calibration": calibration, "heldout": heldout}

    torch.set_num_threads(args.threads)
    model = AutoModelForCausalLM.from_pretrained(
        str(args.model_dir), dtype=torch.float32, local_files_only=True, attn_implementation="eager")
    model.eval()
    layer = args.layer
    gate_weight = model.model.layers[layer].mlp.gate_proj.weight.detach().float().numpy().astype(np.float64)
    up_weight = model.model.layers[layer].mlp.up_proj.weight.detach().float().numpy().astype(np.float64)

    entries = {}
    source_hashes = {"vector": vector_sha, "sweep": sha256_file(args.sweep)}
    for marker in markers:
        calibration = splits[marker]["calibration"]
        heldout = splits[marker]["heldout"]
        gradients, hidden_states, coefficients = [], [], []
        for site in calibration:
            ids = full_ids(site)
            tensor = torch.tensor(ids.reshape(1, -1), dtype=torch.long)
            out = model(input_ids=tensor, use_cache=False, output_hidden_states=True)
            target = torch.log_softmax(out.logits[0, -1].float(), dim=-1)[marker]
            grad = torch.autograd.grad(target, out.hidden_states[layer])[0][0, -1].detach().float().numpy()
            h = out.hidden_states[layer][0, -1].detach().float().numpy()
            gradients.append(normalize(grad))
            hidden_states.append(h)
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                _activation, z, value = unit_activations(h, gate_weight, up_weight)
                c = unit_coefficients(grad, z, value, gate_weight, up_weight)
            if not np.isfinite(c).all():
                raise SystemExit("nonfinite unit coefficients")
            coefficients.append(c)
            del out
        mean_g = mean_direction(gradients)
        # Native unit basis at a reference calibration state; greedy sparse coding
        # (OMP) of the validated mean gradient.  This is the design algorithm:
        # basis = unit input directions, atoms = units, coefficients = least squares.
        h_ref = np.mean(np.stack(hidden_states, axis=0), axis=0)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            unit_matrix = unit_direction_matrix(h_ref, gate_weight, up_weight)
            omp = omp_unit_vectors(mean_g, unit_matrix, K_GRID)
        unit_vectors = omp["vectors"]
        records = omp["records"]
        cos_to_mean_g = {k: float(np.dot(unit_vectors[k], mean_g)) for k in K_GRID}
        reconstruction_cos = {k: float(records[k]["reconstruction_cos"]) for k in K_GRID}

        def evaluate(site_list, direction, doses):
            rows = []
            for site in site_list:
                ids = full_ids(site)
                tensor = torch.tensor(ids.reshape(1, -1), dtype=torch.long)
                baseline = native_forward(model, tensor, injection_layer=layer, vector=None, alpha=0.0, collect=False)
                base_logits = baseline["logits"]
                base_summary = marker_summary(base_logits, base_logits, marker, markers)
                input_norm = float(baseline["input_norm"])
                for dose in doses:
                    injected = native_forward(
                        model, tensor, injection_layer=layer, vector=direction,
                        alpha=dose * input_norm, collect=False)
                    summary = marker_summary(base_logits, injected["logits"], marker, markers)
                    rows.append({
                        "trajectory": site["trajectory"], "t": site["t"], "n_prefix": site["n_prefix"],
                        "dose": float(dose),
                        "delta_logp": summary["target_logp"] - base_summary["target_logp"],
                        "kl": summary["kl"],
                        "delta_entropy": summary["entropy"] - base_summary["entropy"],
                        "delta_other_marker_mass": summary["other_marker_mass"] - base_summary["other_marker_mass"],
                    })
            return rows

        # calibration selection at a safe dose
        cal_low = {}
        for k in K_GRID:
            rows = evaluate(calibration, unit_vectors[k], [LOW_DOSE])
            cal_low[k] = summarize(rows)
        best_delta = max(item["mean_delta_logp"] for item in cal_low.values())
        if best_delta < 0.02:
            selected_k = 1000
            selection_status = "flat calibration (best delta < 0.02); fallback k=1000"
        else:
            selected_k = next(
                (k for k in K_GRID if cal_low[k]["mean_delta_logp"] >= EFFECT_FRACTION * best_delta and cal_low[k]["mean_kl"] <= KL_BUDGET),
                K_GRID[-1],
            )
            selection_status = "calibration 90%% effect saturation"
        cal_selected_rows = evaluate(calibration, unit_vectors[selected_k], DOSES)
        by_dose = {dose: summarize([row for row in cal_selected_rows if abs(row["dose"] - dose) < 1e-9]) for dose in DOSES}
        safe_doses = [dose for dose in DOSES if by_dose[dose]["mean_kl"] <= KL_BUDGET]
        selected_dose = max(safe_doses) if safe_doses else min(DOSES)

        # Hybrid design: start from the selected unit vector and add back a
        # fraction of the dense mean gradient.  lambda=0 is unit-only, 1 is mean g.
        lambda_grid = [0.0, 0.25, 0.5, 0.75, 1.0]
        hybrid_cal_low = {}
        for lam in lambda_grid:
            hybrid_cal_low[str(lam)] = summarize(evaluate(calibration, blend_vectors(unit_vectors[selected_k], mean_g, lam), [LOW_DOSE]))
        reference = hybrid_cal_low["1.0"]
        selected_lambda = next(
            (lam for lam in lambda_grid if hybrid_cal_low[str(lam)]["mean_delta_logp"] >= EFFECT_FRACTION * reference["mean_delta_logp"] and hybrid_cal_low[str(lam)]["mean_kl"] <= KL_BUDGET),
            1.0,
        )
        hybrid_vector = blend_vectors(unit_vectors[selected_k], mean_g, selected_lambda)
        hybrid_cal_rows = evaluate(calibration, hybrid_vector, DOSES)
        hybrid_by_dose = {dose: summarize([row for row in hybrid_cal_rows if abs(row["dose"] - dose) < 1e-9]) for dose in DOSES}
        hybrid_safe = [dose for dose in DOSES if hybrid_by_dose[dose]["mean_kl"] <= KL_BUDGET]
        hybrid_dose = max(hybrid_safe) if hybrid_safe else min(DOSES)
        hybrid_held_rows = evaluate(heldout, hybrid_vector, [hybrid_dose])
        hybrid_metrics = summarize(hybrid_held_rows)
        hybrid_curve = {str(lam): summarize(evaluate(heldout, blend_vectors(unit_vectors[selected_k], mean_g, lam), [LOW_DOSE])) for lam in lambda_grid}
        hybrid = {
            "lambda_grid": lambda_grid,
            "selected_lambda": float(selected_lambda),
            "selected_dose": float(hybrid_dose),
            "rule": "calibration: smallest lambda reaching 90%% of mean-g delta at dose %.2f, KL<=%.2f; then largest dose with calibration KL<=%.2f" % (LOW_DOSE, KL_BUDGET, KL_BUDGET),
            "calibration_low": hybrid_cal_low,
            "calibration": hybrid_by_dose,
            "heldout_curve_at_0.02": hybrid_curve,
            "heldout": hybrid_metrics,
        }

        # held-out curve at two doses, plus baselines and the selected recipe
        curve = []
        for k in K_GRID:
            curve.append({
                "k": k,
                "cos_to_mean_g": cos_to_mean_g[k],
                "reconstruction_cos": reconstruction_cos[k],
                "rows": {
                    "0.02": summarize(evaluate(heldout, unit_vectors[k], [0.02])),
                    "0.1": summarize(evaluate(heldout, unit_vectors[k], [0.1])),
                },
            })
        baselines = {}
        for name, direction in (("w", vector), ("mean_g", mean_g), ("sparse_g", sparse_direction(mean_g, 0.1))):
            baselines[name] = {
                "0.02": summarize(evaluate(heldout, direction, [0.02])),
                "0.1": summarize(evaluate(heldout, direction, [0.1])),
            }
        selected_rows = evaluate(heldout, unit_vectors[selected_k], [selected_dose])
        selected_metrics = summarize(selected_rows)
        selected = {
            "k": int(selected_k),
            "dose": float(selected_dose),
            "cos_to_mean_g": cos_to_mean_g[selected_k],
            "reconstruction_cos": reconstruction_cos[selected_k],
            "rule": "calibration: 90%% of best delta at dose %.2f, KL<=%.2f; then largest dose with calibration KL<=%.2f" % (LOW_DOSE, KL_BUDGET, KL_BUDGET),
            "selection_status": selection_status,
            "calibration": by_dose,
            "heldout": selected_metrics,
        }
        entries[str(marker)] = {
            "target_marker": marker,
            "layer": layer,
            "n_calibration": len(calibration),
            "n_heldout": len(heldout),
            "cos_to_mean_g": cos_to_mean_g,
            "reconstruction_cos": reconstruction_cos,
            "calibration_low": cal_low,
            "curve": curve,
            "baselines": baselines,
            "top_units": [
                {"layer": layer, "unit": int(unit), "coefficient": float(coef)}
                for unit, coef in zip(records[selected_k]["selected"], records[selected_k]["coefficients"])
            ][:12],
            "selected": selected,
            "hybrid": hybrid,
            "selected_sites": selected_rows,
        }
        print("[unit] marker %d: k=%d dose=%.2f calibration Δ %+.4f/KL %.4f; held-out Δ %+.4f/KL %.4f; recon_cos(k)=%.3f" % (
            marker, selected_k, selected_dose,
            by_dose[selected_dose]["mean_delta_logp"], by_dose[selected_dose]["mean_kl"],
            selected_metrics["mean_delta_logp"], selected_metrics["mean_kl"], reconstruction_cos[selected_k]))
        print("[hybrid] marker %d: lambda=%.2f dose=%.2f held-out Δ %+.4f/KL %.4f" % (
            marker, selected_lambda, hybrid_dose, hybrid_metrics["mean_delta_logp"], hybrid_metrics["mean_kl"]))

    data = {
        "schema": SCHEMA,
        "complete": True,
        "scope": "local first-order unit-basis construction at the block-20 input; calibration-only selection; held-out verification; no semantic/causal claim",
        "model": {"name": args.model_dir.name, "injection_layer": layer, "dtype": "float32", "attention": "eager"},
        "vector": {"path": str(args.vector.resolve().relative_to(ROOT)), "sha256": vector_sha},
        "k_grid": K_GRID,
        "doses": DOSES,
        "split_mode": args.split_mode,
        "kl_budget": KL_BUDGET,
        "effect_fraction": EFFECT_FRACTION,
        "markers": entries,
        "source_hashes": source_hashes,
        "guards": {
            "n_markers": len(entries),
            "vector_sha_ok": vector_sha == sha256_file(args.vector),
            "selection_uses_calibration_only": True,
            "all_heldout_finite": all(np.isfinite(entry["selected"]["heldout"]["mean_delta_logp"]) for entry in entries.values()),
        },
        "generated_by": "backend/examples/build_unit_design.py",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    args.public.parent.mkdir(parents=True, exist_ok=True)
    args.public.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print("[ok] unit design:", args.out)
    print("[ok] public:", args.public)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

