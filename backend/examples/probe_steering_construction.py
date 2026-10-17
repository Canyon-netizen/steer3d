#!/usr/bin/env python3
"""Probe constructive directions for a marker target from hidden-state gradients.

For a few short AIME prefixes, take a marker token as the target f = log p(marker)
at the next position.  Then compare:
  * the stored steering vector w
  * -w
  * the local gradient g = d f / d h at the injection layer
  * w + g (normalized)
  * random
and decompose g through every native SwiGLU unit (layer 20-27) into a
response r_i and a first-order contribution c_i.  This is a local, white-box
probe, not a general construction recipe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.steering_construction import (  # noqa: E402
    ConstructionError,
    aggregate_candidates,
    blend,
    normalize,
    quadrant_counts,
    top_by,
)
from core.neuron_mediation import native_forward  # noqa: E402

SCHEMA = "steer3d.steering_construction/1"
LAYERS = list(range(20, 28))
DEFAULT_VECTOR = ROOT / ".cache/bpath/results_B/w_L19_m0.npy"
EXPECTED_VECTOR_SHA = "6ef6df33e2cb22d647594d7d9f0b371e7bec8c9a0cd25741095b7fe26a890c16"


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


def logprob(logits: np.ndarray, token_id: int) -> float:
    x = np.asarray(logits, dtype=np.float64)
    return float(x[token_id] - np.logaddexp.reduce(x))


def evaluate(model, x, marker: int, vector, alpha: float):
    result = native_forward(model, x, injection_layer=20, vector=vector, alpha=alpha)
    return logprob(result["logits"], marker), result


def probe_site(model, site, vector, random_direction, threads: int):
    import torch

    full = np.concatenate([site["prompt"], site["ids"][: site["t"] + 1]]).astype(np.int64)
    x = torch.tensor(full.reshape(1, -1), dtype=torch.long)
    marker = int(site["marker"])

    base_logp, base = evaluate(model, x, marker, None, 0.0)
    alpha = 0.1 * float(base["input_norm"])

    out = model(input_ids=x, use_cache=False, output_hidden_states=True)
    target = torch.log_softmax(out.logits[0, -1].float(), dim=-1)[marker]
    hidden = [out.hidden_states[layer] for layer in LAYERS]
    grads = torch.autograd.grad(target, hidden)
    gradient = grads[0][0, -1].detach().float().numpy()
    gradient = normalize(gradient)
    del out

    plus_logp, plus = evaluate(model, x, marker, vector, alpha)
    baseline_products = base["states"]
    plus_products = plus["states"]

    candidates = {
        "w": vector,
        "minus_w": -vector,
        "gradient": gradient,
        "w_plus_gradient": blend(vector, gradient, 1.0),
        "w_minus_gradient": blend(vector, gradient, -1.0),
        "random": random_direction,
    }
    candidate_results = {}
    for name, direction in candidates.items():
        value, _result = evaluate(model, x, marker, direction, alpha)
        candidate_results[name] = {
            "logp": value,
            "delta_logp": value - base_logp,
            "probability": float(np.exp(value)),
        }

    layer_rows = []
    all_response = []
    all_contribution = []
    all_unit = []
    for index, layer in enumerate(LAYERS):
        weight = model.model.layers[layer].mlp.down_proj.weight.detach().float().numpy()
        g = grads[index][0, -1].detach().float().numpy()
        s = weight.astype(np.float64).T @ np.asarray(g, dtype=np.float64)
        delta_a = plus_products[layer]["product"] - baseline_products[layer]["product"]
        column_norm = np.linalg.norm(weight.astype(np.float64), axis=0)
        response = np.abs(delta_a) * column_norm
        contribution = s * delta_a
        all_response.append(response)
        all_contribution.append(contribution)
        all_unit.append((layer, weight))
        layer_rows.append({
            "layer": layer,
            "sum_contribution": float(contribution.sum()),
            "positive_units": int((contribution > 0).sum()),
            "negative_units": int((contribution < 0).sum()),
            "response_max": float(response.max()),
            "top_carrier_ids": top_by(contribution, 6, +1),
            "top_compensator_ids": top_by(contribution, 6, -1),
        })

    response = np.concatenate(all_response)
    contribution = np.concatenate(all_contribution)
    sample_indices = np.linspace(0, len(response) - 1, min(400, len(response))).astype(int)
    scatter = [
        {"response": float(response[index]), "contribution": float(contribution[index])}
        for index in sample_indices
    ]
    quadrants = quadrant_counts(response, contribution, high_threshold=float(np.quantile(response, 0.9)))
    sum_c = float(contribution.sum())
    measured_delta_w = candidate_results["w"]["delta_logp"]

    global_offsets = []
    offset = 0
    for layer in LAYERS:
        global_offsets.append((offset, offset + 6144, layer))
        offset += 6144

    def describe(global_index: int):
        for start, end, layer in global_offsets:
            if start <= global_index < end:
                unit = global_index - start
                weight = model.model.layers[layer].mlp.down_proj.weight.detach().float().numpy()
                response_value = float(np.abs(plus_products[layer]["product"][unit] - baseline_products[layer]["product"][unit]) * np.linalg.norm(weight[:, unit]))
                contribution_value = float(contribution[global_index])
                return {"layer": layer, "unit": int(unit), "response": response_value, "contribution": contribution_value}
        raise ConstructionError("global unit index out of range")

    top_carriers = [describe(index) for index in top_by(contribution, 8, +1)]
    top_compensators = [describe(index) for index in top_by(contribution, 8, -1)]

    return {
        "trajectory": site["trajectory"],
        "problem": site["problem"],
        "mode": site["mode"],
        "t": site["t"],
        "marker": marker,
        "n_prefix": int(len(full)),
        "alpha": alpha,
        "baseline_logp": base_logp,
        "candidates": candidate_results,
        "gradient": {
            "layer": 20,
            "norm": float(np.linalg.norm(gradient)),
            "cos_with_w": float(np.dot(gradient, vector)),
        },
        "scatter": scatter,
        "decomposition": {
            "sum_contribution": sum_c,
            "measured_delta_w": measured_delta_w,
            "ratio": sum_c / measured_delta_w if measured_delta_w != 0 else None,
            "quadrants": quadrants,
            "layers": layer_rows,
            "top_carriers": top_carriers,
            "top_compensators": top_compensators,
        },
    }


def render_figure(data: dict, out_path: Path) -> Path:
    root = Path(__file__).resolve().parents[2]
    cache = root / ".cache/mpl"
    cache.mkdir(parents=True, exist_ok=True)
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sites = data["sites"]
    names = ["w", "minus_w", "gradient", "w_plus_gradient", "random"]
    colors = {"w": "#fb7185", "minus_w": "#2dd4bf", "gradient": "#60a5fa", "w_plus_gradient": "#fbbf24", "random": "#94a3b8"}
    fig, axes = plt.subplots(1, 3, figsize=(19, 5.5), constrained_layout=True)

    ax = axes[0]
    positions = np.arange(len(sites))
    width = 0.16
    for offset, name in enumerate(names):
        values = [site["candidates"][name]["delta_logp"] for site in sites]
        ax.bar(positions + (offset - 2) * width, values, width, label=name, color=colors[name])
    ax.axhline(0, color="#334155", lw=1)
    ax.set_xticks(positions)
    ax.set_xticklabels([str(site["marker"]) + " L" + str(site["n_prefix"]) for site in sites], rotation=45, fontsize=8)
    ax.set_ylabel("delta log p(marker)")
    ax.set_title("candidate directions per site")
    ax.legend(fontsize=8)

    ax = axes[1]
    site = sites[0]
    scatter = data.get("scatter", [])
    if scatter:
        r = np.asarray([point["response"] for point in scatter], dtype=float)
        c = np.asarray([point["contribution"] for point in scatter], dtype=float)
        colors_scatter = ["#2dd4bf" if value > 0 else "#fb7185" for value in c]
        ax.scatter(r, c, s=4, c=colors_scatter, alpha=0.5)
        ax.set_xscale("log")
    ax.axhline(0, color="#334155", lw=1)
    ax.set_xlabel("response |delta a| * ||d_i|| (log)")
    ax.set_ylabel("causal contribution c_i")
    ax.set_title("unit quadrants for " + str(site["marker"]))

    ax = axes[2]
    aggregate = data["aggregate"]
    markers = list(aggregate.keys())
    positions = np.arange(len(markers))
    for offset, name in enumerate(["w", "minus_w", "gradient", "w_plus_gradient"]):
        values = [aggregate[marker]["candidates"][name]["mean_delta_logp"] for marker in markers]
        ax.bar(positions + (offset - 1.5) * 0.18, values, 0.18, label=name, color=colors[name])
    ax.axhline(0, color="#334155", lw=1)
    ax.set_xticks(positions)
    ax.set_xticklabels(markers)
    ax.set_ylabel("mean delta log p(marker)")
    ax.set_title("aggregate by marker")
    ax.legend(fontsize=8)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "datasets/aime_qwen3_1p7b_32k_fp32/aime")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "datasets/models/Qwen3-1.7B")
    parser.add_argument("--vector", type=Path, default=DEFAULT_VECTOR)
    parser.add_argument("--markers", default="7196,10061,6771")
    parser.add_argument("--per-marker", type=int, default=2)
    parser.add_argument("--max-prefix", type=int, default=400)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20261017)
    parser.add_argument("--out", type=Path, default=ROOT / "experiments/steering_construction_v1/steering_construction.json")
    parser.add_argument("--public", type=Path, default=ROOT / "frontend/public/latent/data/steering_construction.json")
    parser.add_argument("--figure", type=Path, default=ROOT / "experiments/steering_construction_v1/steering_construction.png")
    parser.add_argument("--no-figure", action="store_true")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM

    vector = np.load(args.vector).astype(np.float32)
    if vector.shape != (2048,) or not np.isfinite(vector).all():
        raise SystemExit("invalid vector")
    if abs(float(np.linalg.norm(vector)) - 1.0) > 1e-4:
        vector = vector / np.linalg.norm(vector)
    digest = sha256_file(args.vector)
    if digest != EXPECTED_VECTOR_SHA:
        raise SystemExit("vector sha256 mismatch")

    markers = [int(item) for item in args.markers.split(",") if item.strip()]
    sites = select_sites(args.data_root, markers, args.max_prefix, args.per_marker)
    if len(sites) < 4:
        raise SystemExit("need at least 4 sites, got %d" % len(sites))

    torch.set_num_threads(args.threads)
    model = AutoModelForCausalLM.from_pretrained(
        str(args.model_dir), dtype=torch.float32, local_files_only=True, attn_implementation="eager")
    model.eval()
    rng = np.random.default_rng(args.seed)
    random_direction = normalize(rng.standard_normal(2048).astype(np.float32))

    results = []
    scatter = []
    for site in sites:
        print("[site] %s marker=%d t=%d prefix=%d" % (site["trajectory"], site["marker"], site["t"], site["n_prefix"]), flush=True)
        row = probe_site(model, site, vector, random_direction, args.threads)
        results.append(row)
    scatter = results[0].pop("scatter", [])
    for row in results[1:]:
        row.pop("scatter", None)
    aggregate = aggregate_candidates(results)

    data = {
        "schema": SCHEMA,
        "complete": True,
        "scope": "local white-box probe on short AIME prefixes; f = log p(marker next-token); candidate directions are evaluated at the same alpha = 0.1 * block-20 input norm",
        "model": {"name": args.model_dir.name, "injection_layer": 20, "dtype": "float32", "attention": "eager"},
        "vector": {"path": str(args.vector.resolve().relative_to(ROOT)), "sha256": digest},
        "alpha_rule": "0.1 * measured block-20 input L2 norm at the last prefix position",
        "sites": results,
        "scatter": scatter,
        "aggregate": aggregate,
        "guards": {
            "n_sites": len(results),
            "vector_sha_ok": True,
            "all_finite": all(np.isfinite(site["baseline_logp"]) for site in results),
            "min_prefix": min(site["n_prefix"] for site in results),
            "max_prefix": max(site["n_prefix"] for site in results),
        },
        "generated_by": "backend/examples/probe_steering_construction.py",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    args.public.parent.mkdir(parents=True, exist_ok=True)
    args.public.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    if not args.no_figure:
        render_figure(data, args.figure)

    print("[ok] report: %s" % args.out)
    print("[ok] public: %s" % args.public)
    for marker, item in aggregate.items():
        print("  marker %s: best %s mean delta %.5f" % (marker, item["best_candidate"], item["candidates"][item["best_candidate"]]["mean_delta_logp"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

