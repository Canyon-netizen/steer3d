#!/usr/bin/env python3
"""Held-out transfer test for gradient-derived steering directions.

Split short AIME marker sites into calibration and held-out halves per marker.
Build a mean gradient direction on calibration sites, then evaluate it on
held-out sites of the same marker and of the other markers.  This separates
"a direction that works at the site you measured" from "a direction that
transfers".
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
    GradientError,
    compute_gradient,
    evaluate_direction,
    mean_direction,
    normalize,
    sparse_direction,
)

SCHEMA = "steer3d.steering_transfer/1"
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


def full_ids(site) -> np.ndarray:
    return np.concatenate([site["prompt"], site["ids"][: site["t"] + 1]]).astype(np.int64)


def aggregate_same_marker(sites, markers, direction_names):
    output = {}
    for marker in markers:
        rows = [site for site in sites if site["marker"] == marker]
        if not rows:
            continue
        summary = {}
        for name in direction_names:
            values = [site["directions"][name]["delta_logp"] for site in rows]
            summary[name] = {
                "mean_delta_logp": float(np.mean(values)),
                "improved_fraction": float(np.mean(np.array(values) > 0)),
                "n_sites": len(values),
            }
        oracle = [site["oracle"]["delta_logp"] for site in rows]
        summary["oracle_per_site_gradient"] = {
            "mean_delta_logp": float(np.mean(oracle)),
            "improved_fraction": float(np.mean(np.array(oracle) > 0)),
            "n_sites": len(oracle),
        }
        output[str(marker)] = summary
    return output


def aggregate_cross(rows, markers):
    output = {str(marker): {} for marker in markers}
    for row in rows:
        source = str(row["source"])
        target = str(row["target"])
        bucket = output.setdefault(source, {}).setdefault(target, [])
        bucket.append(float(row["delta_logp"]))
    for source, target_rows in output.items():
        for target, values in list(target_rows.items()):
            target_rows[target] = {
                "mean_delta_logp": float(np.mean(values)),
                "improved_fraction": float(np.mean(np.array(values) > 0)),
                "n_sites": len(values),
            }
    return output


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
    names = ["w", "minus_w", "g_mean", "g_sparse", "random", "oracle_per_site_gradient"]
    colors = {"w": "#fb7185", "minus_w": "#2dd4bf", "g_mean": "#60a5fa", "g_sparse": "#fbbf24", "random": "#94a3b8", "oracle_per_site_gradient": "#a78bfa"}
    labels = {"w": "w", "minus_w": "-w", "g_mean": "mean g", "g_sparse": "sparse g", "random": "random", "oracle_per_site_gradient": "oracle g"}

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)
    ax = axes[0]
    positions = np.arange(len(markers))
    width = 0.14
    for offset, name in enumerate(names):
        values = [data["same_marker"][marker][name]["mean_delta_logp"] for marker in markers]
        ax.bar(positions + (offset - 2.5) * width, values, width, label=labels[name], color=colors[name])
    ax.axhline(0, color="#334155", lw=1)
    ax.set_xticks(positions)
    ax.set_xticklabels(markers)
    ax.set_ylabel("mean delta log p(marker) on held-out sites")
    ax.set_title("same-marker held-out transfer")
    ax.legend(fontsize=8)

    ax = axes[1]
    matrix = np.full((len(markers), len(markers)), np.nan)
    for i, source in enumerate(markers):
        for j, target in enumerate(markers):
            cell = data["cross"].get(source, {}).get(target)
            if cell is not None:
                matrix[i, j] = cell["mean_delta_logp"]
    limit = min(1.5, max(0.01, float(np.nanmax(np.abs(matrix)))))
    image = ax.imshow(matrix, cmap="RdBu_r", vmin=-limit, vmax=limit)
    ax.set_xticks(range(len(markers)))
    ax.set_xticklabels(markers)
    ax.set_yticks(range(len(markers)))
    ax.set_yticklabels(markers)
    ax.set_xlabel("target marker")
    ax.set_ylabel("source mean gradient")
    ax.set_title("cross-marker transfer (mean g; color clipped at +/-%.1f)" % limit)
    for i in range(len(markers)):
        for j in range(len(markers)):
            if np.isfinite(matrix[i, j]):
                text_color = "#f8fafc" if abs(matrix[i, j]) > 0.55 * limit else "#0f172a"
                ax.text(j, i, "%+.3f" % matrix[i, j], ha="center", va="center", fontsize=9, color=text_color)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.02, label="delta log p")

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
    parser.add_argument("--out", type=Path, default=ROOT / "experiments/steering_transfer_v1/steering_transfer.json")
    parser.add_argument("--public", type=Path, default=ROOT / "frontend/public/latent/data/steering_transfer.json")
    parser.add_argument("--figure", type=Path, default=ROOT / "experiments/steering_transfer_v1/steering_transfer.png")
    parser.add_argument("--no-figure", action="store_true")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM

    vector = normalize(np.load(args.vector).astype(np.float32))
    digest = sha256_file(args.vector)
    if digest != EXPECTED_VECTOR_SHA:
        raise SystemExit("vector sha256 mismatch")
    markers = [int(item) for item in args.markers.split(",") if item.strip()]
    sites = select_sites(args.data_root, markers, args.max_prefix, args.per_marker)

    splits = {}
    for marker in markers:
        rows = sorted([site for site in sites if site["marker"] == marker], key=lambda site: site["n_prefix"])
        half = max(1, len(rows) // 2)
        splits[marker] = {"calibration": rows[:half], "heldout": rows[half:]}
        if len(rows[half:]) < 1:
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
            alpha = 0.1 * result["hidden_norm"]
            gradient_cache[(site["trajectory"], site["t"], marker)] = {
                "gradient": result["gradient"],
                "base_logp": result["base_logp"],
                "alpha": alpha,
                "n_prefix": len(ids),
                "tensor": tensor,
            }

    directions = {}
    for marker in markers:
        calib = [gradient_cache[(site["trajectory"], site["t"], marker)] for site in splits[marker]["calibration"]]
        g_mean = mean_direction([item["gradient"] for item in calib])
        directions[marker] = {
            "w": vector,
            "minus_w": -vector,
            "g_mean": g_mean,
            "g_sparse": sparse_direction(g_mean, 0.1),
            "random": random_direction,
        }

    results = []
    for marker in markers:
        for site in splits[marker]["heldout"]:
            cache = gradient_cache[(site["trajectory"], site["t"], marker)]
            row = {
                "trajectory": site["trajectory"],
                "problem": site["problem"],
                "mode": site["mode"],
                "t": site["t"],
                "marker": marker,
                "split": "heldout",
                "n_prefix": cache["n_prefix"],
                "alpha": cache["alpha"],
                "baseline_logp": cache["base_logp"],
                "directions": {},
                "oracle": None,
            }
            for name, direction in directions[marker].items():
                result = evaluate_direction(model, cache["tensor"], marker, direction, cache["alpha"], cache["base_logp"])
                row["directions"][name] = result
            oracle = evaluate_direction(model, cache["tensor"], marker, normalize(cache["gradient"]), cache["alpha"], cache["base_logp"])
            row["oracle"] = oracle
            results.append(row)

    # cross-marker: evaluate each source marker's g_mean on other markers' held-out sites
    cross_rows = []
    for source in markers:
        for target in markers:
            if source == target:
                continue
            for site in splits[target]["heldout"]:
                cache = gradient_cache[(site["trajectory"], site["t"], target)]
                result = evaluate_direction(model, cache["tensor"], target, directions[source]["g_mean"], cache["alpha"], cache["base_logp"])
                cross_rows.append({
                    "source": source,
                    "target": target,
                    "trajectory": site["trajectory"],
                    "t": site["t"],
                    "delta_logp": result["delta_logp"],
                })

    same_marker = aggregate_same_marker(results, markers, ["w", "minus_w", "g_mean", "g_sparse", "random"])
    cross = aggregate_cross(cross_rows, markers)
    data = {
        "schema": SCHEMA,
        "complete": True,
        "scope": "held-out transfer of gradient-derived directions on short AIME prefixes; calibration and held-out sites are disjoint per marker; cross cells evaluate a source marker's mean gradient on a target marker's held-out site",
        "model": {"name": args.model_dir.name, "injection_layer": 20, "dtype": "float32", "attention": "eager"},
        "vector": {"path": str(args.vector.resolve().relative_to(ROOT)), "sha256": digest},
        "alpha_rule": "0.1 * measured block-20 input L2 norm at the last prefix position",
        "splits": {
            str(marker): {
                "calibration": [{"trajectory": site["trajectory"], "t": site["t"], "n_prefix": site["n_prefix"]} for site in splits[marker]["calibration"]],
                "heldout": [{"trajectory": site["trajectory"], "t": site["t"], "n_prefix": site["n_prefix"]} for site in splits[marker]["heldout"]],
            }
            for marker in markers
        },
        "same_marker": same_marker,
        "cross": cross,
        "cross_rows": cross_rows,
        "sites": results,
        "guards": {
            "n_sites": len(results),
            "vector_sha_ok": True,
            "markers": markers,
            "calibration_heldout_disjoint": all(
                not ({site["trajectory"] + ":" + str(site["t"]) for site in splits[marker]["calibration"]} &
                     {site["trajectory"] + ":" + str(site["t"]) for site in splits[marker]["heldout"]})
                for marker in markers
            ),
        },
        "generated_by": "backend/examples/build_steering_transfer.py",
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
        item = same_marker[str(marker)]
        print("  marker %d: w %+.4f, g_mean %+.4f, g_sparse %+.4f, oracle %+.4f" % (
            marker, item["w"]["mean_delta_logp"], item["g_mean"]["mean_delta_logp"],
            item["g_sparse"]["mean_delta_logp"], item["oracle_per_site_gradient"]["mean_delta_logp"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

