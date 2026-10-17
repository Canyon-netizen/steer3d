#!/usr/bin/env python3
"""Alpha sweep and side-effect frontier for gradient-derived directions.

For held-out marker sites, sweep injection dose for w, -w, mean g, sparse g,
and random.  For every injection measure target log p(marker), KL to baseline,
entropy change, and the probability mass of the other markers.  The output is a
dose-response + side-effect table, not a single "best alpha".
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

from core.steering_gradient import (  # noqa: E402
    compute_gradient,
    mean_direction,
    normalize,
    sparse_direction,
)
from core.steering_sweep import aggregate_sweep, marker_summary  # noqa: E402
from core.neuron_mediation import native_forward  # noqa: E402

SCHEMA = "steer3d.steering_sweep/1"
DEFAULT_VECTOR = ROOT / ".cache/bpath/results_B/w_L19_m0.npy"
EXPECTED_VECTOR_SHA = "6ef6df33e2cb22d647594d7d9f0b371e7bec8c9a0cd25741095b7fe26a890c16"
DEFAULT_DOSES = [0.02, 0.05, 0.1, 0.2, 0.3, 0.5]


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


def render_figure(data: dict, out_path: Path) -> Path:
    root = Path(__file__).resolve().parents[2]
    cache = root / ".cache/mpl"
    cache.mkdir(parents=True, exist_ok=True)
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    markers = [str(marker) for marker in data["guards"]["markers"]]
    colors = {"w": "#fb7185", "minus_w": "#2dd4bf", "mean_g": "#60a5fa", "sparse_g": "#fbbf24", "random": "#94a3b8"}
    names = ["w", "minus_w", "mean_g", "sparse_g", "random"]
    plot_names = ["w", "mean_g", "sparse_g", "random"]
    fig, axes = plt.subplots(1, 3, figsize=(19, 5.5), constrained_layout=True)

    ax = axes[0]
    for direction in plot_names:
        rows = data["aggregate"][markers[0]]["directions"][direction]
        ax.plot([row["dose"] for row in rows], [row["mean_delta_logp"] for row in rows], "o-", color=colors[direction], label=direction)
    ax.axhline(0, color="#334155", lw=1)
    ax.set_xlabel("dose (fraction of input norm)")
    ax.set_ylabel("mean delta log p(marker)")
    ax.set_title("dose response: marker " + markers[0] + " (minus_w omitted)")
    ax.legend(fontsize=8)

    ax = axes[1]
    for marker in markers:
        rows = data["aggregate"][marker]["directions"]["mean_g"]
        ax.plot([row["dose"] for row in rows], [row["mean_kl"] for row in rows], "o-", label=marker)
    ax.set_xlabel("dose")
    ax.set_ylabel("mean KL(base || injected), log scale")
    ax.set_yscale("log")
    ax.set_title("side effect of mean g vs dose")
    ax.legend(fontsize=8)

    ax = axes[2]
    for direction in plot_names:
        for marker in markers:
            rows = data["aggregate"][marker]["directions"][direction]
            ax.scatter([max(row["mean_kl"], 1e-5) for row in rows], [row["mean_delta_logp"] for row in rows], color=colors[direction], s=18, alpha=0.7)
    ax.axhline(0, color="#334155", lw=1)
    ax.set_xscale("log")
    ax.set_xlabel("mean KL (log)")
    ax.set_ylabel("mean delta log p(marker)")
    ax.set_title("effect vs side effect (minus_w omitted)")
    for direction in plot_names:
        ax.scatter([], [], color=colors[direction], label=direction, s=18)
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
    parser.add_argument("--per-marker", type=int, default=4)
    parser.add_argument("--max-prefix", type=int, default=400)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20261017)
    parser.add_argument("--doses", default="0.02,0.05,0.1,0.2,0.3,0.5")
    parser.add_argument("--kl-threshold", type=float, default=0.1)
    parser.add_argument("--out", type=Path, default=ROOT / "experiments/steering_sweep_v1/steering_sweep.json")
    parser.add_argument("--public", type=Path, default=ROOT / "frontend/public/latent/data/steering_sweep.json")
    parser.add_argument("--figure", type=Path, default=ROOT / "experiments/steering_sweep_v1/steering_sweep.png")
    parser.add_argument("--no-figure", action="store_true")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM

    vector = normalize(np.load(args.vector).astype(np.float32))
    digest = sha256_file(args.vector)
    if digest != EXPECTED_VECTOR_SHA:
        raise SystemExit("vector sha256 mismatch")
    markers = [int(item) for item in args.markers.split(",") if item.strip()]
    other_markers = [marker for marker in markers]
    doses = [float(item) for item in args.doses.split(",") if item.strip()]
    sites = select_sites(args.data_root, markers, args.max_prefix, args.per_marker)

    splits = {}
    for marker in markers:
        rows = sorted([site for site in sites if site["marker"] == marker], key=lambda site: site["n_prefix"])
        half = max(1, len(rows) // 2)
        splits[marker] = {"calibration": rows[:half], "heldout": rows[half:]}
        if not splits[marker]["heldout"]:
            raise SystemExit("marker %d has no held-out site" % marker)

    torch.set_num_threads(args.threads)
    model = AutoModelForCausalLM.from_pretrained(
        str(args.model_dir), dtype=torch.float32, local_files_only=True, attn_implementation="eager")
    model.eval()
    rng = np.random.default_rng(args.seed)
    random_direction = normalize(rng.standard_normal(2048).astype(np.float32))

    gradient_cache = {}
    for marker in markers:
        for site in splits[marker]["calibration"] + splits[marker]["heldout"]:
            ids = full_ids(site)
            tensor = torch.tensor(ids.reshape(1, -1), dtype=torch.long)
            result = compute_gradient(model, tensor, marker=marker, layer=20)
            gradient_cache[(site["trajectory"], site["t"], marker)] = {
                "gradient": result["gradient"],
                "tensor": tensor,
                "base_logp": result["base_logp"],
                "alpha": 0.1 * result["hidden_norm"],
                "n_prefix": len(ids),
            }

    directions = {}
    for marker in markers:
        calib = [gradient_cache[(site["trajectory"], site["t"], marker)] for site in splits[marker]["calibration"]]
        mean_g = mean_direction([item["gradient"] for item in calib])
        directions[marker] = {
            "w": vector,
            "minus_w": -vector,
            "mean_g": mean_g,
            "sparse_g": sparse_direction(mean_g, 0.1),
            "random": random_direction,
        }

    rows = []
    for marker in markers:
        for site in splits[marker]["heldout"]:
            cache = gradient_cache[(site["trajectory"], site["t"], marker)]
            tensor = cache["tensor"]
            baseline = native_forward(model, tensor, injection_layer=20, vector=None, alpha=0.0)
            base_summary = marker_summary(baseline["logits"], baseline["logits"], marker, other_markers)
            input_norm = float(baseline["input_norm"])
            for direction_name, direction in directions[marker].items():
                for dose in doses:
                    alpha = dose * input_norm
                    injected = native_forward(model, tensor, injection_layer=20, vector=direction, alpha=alpha)
                    summary = marker_summary(baseline["logits"], injected["logits"], marker, other_markers)
                    rows.append({
                        "trajectory": site["trajectory"],
                        "problem": site["problem"],
                        "mode": site["mode"],
                        "t": site["t"],
                        "marker": marker,
                        "n_prefix": cache["n_prefix"],
                        "dose": dose,
                        "alpha": alpha,
                        "direction": direction_name,
                        "base_target_logp": base_summary["target_logp"],
                        "target_logp": summary["target_logp"],
                        "delta_logp": summary["target_logp"] - base_summary["target_logp"],
                        "target_probability": summary["target_probability"],
                        "other_marker_mass": summary["other_marker_mass"],
                        "delta_other_marker_mass": summary["other_marker_mass"] - base_summary["other_marker_mass"],
                        "kl": summary["kl"],
                        "entropy": summary["entropy"],
                        "base_entropy": base_summary["entropy"],
                        "delta_entropy": summary["entropy"] - base_summary["entropy"],
                        "top1_id": summary["top1_id"],
                    })

    aggregate = aggregate_sweep(rows)
    useful = {}
    for marker in markers:
        best = None
        for direction_name in directions[marker]:
            for row in aggregate[str(marker)]["directions"][direction_name]:
                if row["mean_kl"] <= args.kl_threshold:
                    candidate = (row["mean_delta_logp"], direction_name, row["dose"], row["mean_kl"])
                    if best is None or candidate[0] > best[0]:
                        best = candidate
        useful[str(marker)] = {
            "direction": best[1] if best else None,
            "dose": best[2] if best else None,
            "mean_delta_logp": best[0] if best else None,
            "mean_kl": best[3] if best else None,
            "kl_threshold": args.kl_threshold,
        }

    data = {
        "schema": SCHEMA,
        "complete": True,
        "scope": "alpha sweep and KL/entropy/other-marker side effects on held-out marker sites; calibration sites build mean g; doses are fractions of block-20 input norm",
        "model": {"name": args.model_dir.name, "injection_layer": 20, "dtype": "float32", "attention": "eager"},
        "vector": {"path": str(args.vector.resolve().relative_to(ROOT)), "sha256": digest},
        "markers": markers,
        "doses": doses,
        "kl_threshold": args.kl_threshold,
        "splits": {
            str(marker): {
                "calibration": [{"trajectory": site["trajectory"], "t": site["t"], "n_prefix": site["n_prefix"]} for site in splits[marker]["calibration"]],
                "heldout": [{"trajectory": site["trajectory"], "t": site["t"], "n_prefix": site["n_prefix"]} for site in splits[marker]["heldout"]],
            }
            for marker in markers
        },
        "aggregate": aggregate,
        "useful_window": useful,
        "sites": rows,
        "guards": {
            "n_sites": sum(len(splits[marker]["heldout"]) for marker in markers),
            "n_markers": len(markers),
            "n_rows": len(rows),
            "vector_sha_ok": True,
            "markers": markers,
            "doses": doses,
            "calibration_heldout_disjoint": all(
                not ({site["trajectory"] + ":" + str(site["t"]) for site in splits[marker]["calibration"]} &
                     {site["trajectory"] + ":" + str(site["t"]) for site in splits[marker]["heldout"]})
                for marker in markers
            ),
        },
        "generated_by": "backend/examples/build_steering_sweep.py",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    args.public.parent.mkdir(parents=True, exist_ok=True)
    args.public.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    if not args.no_figure:
        render_figure(data, args.figure)

    print("[ok] report: %s" % args.out)
    print("[ok] public: %s" % args.public)
    for marker in markers:
        window = useful[str(marker)]
        print("  marker %d: best within KL<=%.2f: %s at dose %s, delta %s" % (
            marker, args.kl_threshold, window["direction"], window["dose"], window["mean_delta_logp"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

