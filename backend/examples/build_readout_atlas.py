#!/usr/bin/env python3
"""Build a hidden-state readout atlas for a steering vector.

Reads the stored float32 hidden states (no model forward pass), projects every
layer/token onto the vector, labels whether the NEXT token is a marker, and
writes per-layer rank AUC / effect sizes plus a few per-token series for the
web page.

Usage (use the venv with numpy/transformers, or any python with numpy):
  .cache/venv_steer/bin/python backend/examples/build_readout_atlas.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.readout_atlas import (  # noqa: E402
    aggregate_layers,
    aggregate_marker_layers,
    best_layer as pick_best_layer,
    layer_stats,
)

SCHEMA = "steer3d.readout_atlas/1"
MARKERS = [13824, 14190, 6771, 10061, 7196, 88190, 80022]
EXPECTED_VECTOR_SHA = "6ef6df33e2cb22d647594d7d9f0b371e7bec8c9a0cd25741095b7fe26a890c16"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_vector(path: Path, expected_sha: str) -> np.ndarray:
    vector = np.load(path).astype(np.float32)
    if vector.shape != (2048,):
        raise SystemExit("vector shape is %r, expected (2048,)" % (vector.shape,))
    if not np.isfinite(vector).all():
        raise SystemExit("vector contains non-finite values")
    norm = float(np.linalg.norm(vector))
    if abs(norm - 1.0) > 1e-4:
        vector = vector / norm
    digest = sha256_file(path)
    if expected_sha and digest != expected_sha:
        raise SystemExit("vector sha256 mismatch: %s != %s" % (digest, expected_sha))
    return vector


def parse_meta(path: Path) -> dict:
    stem = path.stem
    mode = "think" if stem.endswith("__think") else "no_think" if stem.endswith("__no_think") else "unknown"
    problem = stem[len("aime__"):] if stem.startswith("aime__") else stem
    problem = re.sub(r"__(think|no_think)$", "", problem)
    return {"id": stem, "problem": problem, "mode": mode}


def rank_auc_safe(proj: np.ndarray, labels: np.ndarray) -> float:
    from core.readout_atlas import rank_auc
    value = rank_auc(proj, labels)
    return float("nan") if value is None else value


def aggregate_series(proj, cos, norm, labels):
    return layer_stats(proj, cos, norm, labels)


def decode_tokens(tokenizer, ids):
    if tokenizer is None:
        return None
    texts = []
    for token_id in ids:
        try:
            text = tokenizer.decode([int(token_id)])
        except Exception:
            text = str(int(token_id))
        if len(text) > 16:
            text = text[:16]
        texts.append(text)
    return texts


def render_figure(atlas: dict, out_path: Path) -> Path:
    root = Path(__file__).resolve().parents[2]
    cache = root / ".cache/mpl"
    cache.mkdir(parents=True, exist_ok=True)
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    layers = atlas["aggregate"]["layers"]
    fig, axes = plt.subplots(1, 3, figsize=(20, 5.5), gridspec_kw={"width_ratios": [1, 2.4, 1.2]}, constrained_layout=True)
    ax = axes[0]
    xs = [row["layer"] for row in layers]

    def series(key):
        return [row[key] if row.get(key) is not None else float("nan") for row in layers]

    ax.plot(xs, series("mean_auc_cos"), "o-", color="#60a5fa", label="cos raw")
    ax.plot(xs, series("mean_auc_cos_oriented"), "o--", color="#f59e0b", label="cos oriented")
    ax.plot(xs, series("mean_auc_norm"), ":", color="#94a3b8", label="norm control")
    best = atlas["aggregate"]["best_layer"]
    if best is not None:
        ax.axvline(best, color="#fbbf24", ls="--", lw=1)
        ax.text(best + 0.3, 0.4, " best " + str(best), color="#b45309", fontsize=9)
    ax.axhline(0.5, color="#334155", lw=1, ls=":")
    ax.set_xlabel("layer")
    ax.set_ylabel("mean rank AUC (marker next-token)")
    ax.set_title("cos(h,w): raw / oriented / norm-control")
    ax.set_ylim(0.15, 0.85)
    ax.legend(fontsize=8)

    ax = axes[1]
    series = atlas["series"][0]
    cos = np.asarray(series["cos"], dtype=float).T  # layers x tokens
    n_tokens = cos.shape[1]
    stride = max(1, n_tokens // 600)
    pooled = cos[:, ::stride]
    im = ax.imshow(pooled, aspect="auto", origin="lower", cmap="RdBu_r", vmin=-0.25, vmax=0.25)
    marker_positions = [p // stride for p in series["marker_positions"] if p // stride < pooled.shape[1]]
    for position in marker_positions:
        ax.axvline(position, color="#111827", lw=0.5, alpha=0.7)
    ax.set_xlabel("token (downsampled; black ticks = marker next-token)")
    ax.set_ylabel("layer")
    ax.set_title("cos(h, w) for " + series["id"])
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01, label="cosine")

    ax = axes[2]
    per_marker = atlas.get("per_marker", {})
    items = sorted(per_marker.items(), key=lambda pair: -int(pair[1].get("n_occurrences", 0)))
    labels = [str(marker) + " (n=" + str(item.get("n_occurrences", 0)) + ")" for marker, item in items]
    values = [item.get("best_layer_mean_auc_cos") if item.get("best_layer_mean_auc_cos") is not None else float("nan") for _, item in items]
    colors = ["#2dd4bf" if item.get("best_layer_orientation") == 1 else "#fb7185" for _, item in items]
    positions = np.arange(len(items))
    ax.barh(positions, values, color=colors)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.axvline(0.5, color="#334155", lw=1, ls=":")
    ax.set_xlim(0.0, 1.0)
    ax.invert_yaxis()
    ax.set_xlabel("best-layer raw cos AUC")
    ax.set_title("per-marker: signs differ")

    fig.suptitle("Hidden-state readout atlas: best layer " + str(best) + "; per-marker signs differ", fontsize=12)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "datasets/aime_qwen3_1p7b_32k_fp32/aime")
    parser.add_argument("--vector", type=Path, default=ROOT / ".cache/bpath/results_B/w_L19_m0.npy")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "datasets/models/Qwen3-1.7B")
    parser.add_argument("--out", type=Path, default=ROOT / "experiments/readout_atlas_v1/readout_atlas.json")
    parser.add_argument("--public", type=Path, default=ROOT / "frontend/public/latent/data/readout_atlas.json")
    parser.add_argument("--figure", type=Path, default=ROOT / "experiments/readout_atlas_v1/readout_atlas.png")
    parser.add_argument("--series", default="", help="comma-separated trajectory ids for the heatmap")
    parser.add_argument("--series-count", type=int, default=3)
    parser.add_argument("--max-series-tokens", type=int, default=2200)
    parser.add_argument("--max-trajectories", type=int, default=0, help="0 = all")
    parser.add_argument("--expected-vector-sha", default=EXPECTED_VECTOR_SHA)
    parser.add_argument("--no-figure", action="store_true")
    parser.add_argument("--no-tokenizer", action="store_true")
    args = parser.parse_args()

    paths = sorted(args.data_root.glob("*.npz"))
    if args.max_trajectories > 0:
        paths = paths[: args.max_trajectories]
    if not paths:
        raise SystemExit("no .npz trajectories under %s" % args.data_root)
    vector = load_vector(args.vector, args.expected_vector_sha)

    config = json.loads((args.model_dir / "config.json").read_text(encoding="utf-8"))
    n_layers = int(config["num_hidden_layers"])
    d_model = int(config["hidden_size"])

    # Pass 1: cheap marker count / length from token_ids only.
    inventory = []
    for path in paths:
        with np.load(path) as data:
            ids = data["token_ids"]
            labels = np.isin(ids[1:], MARKERS)
            inventory.append({"path": path, "meta": parse_meta(path), "T": int(len(ids)),
                              "n_marker": int(labels.sum())})
    by_id = {row["meta"]["id"]: row for row in inventory}

    wanted = [item.strip() for item in args.series.split(",") if item.strip()]
    if wanted:
        series_ids = [item for item in wanted if item in by_id]
    else:
        candidates = [row for row in inventory if row["n_marker"] >= 5 and row["T"] <= args.max_series_tokens]
        candidates.sort(key=lambda row: (-row["n_marker"], row["T"]))
        series_ids = [row["meta"]["id"] for row in candidates[: args.series_count]]
        if not series_ids:
            fallback = sorted(inventory, key=lambda row: -row["n_marker"])
            series_ids = [row["meta"]["id"] for row in fallback[: args.series_count]]
    series_ids = list(dict.fromkeys(series_ids))

    tokenizer = None
    if not args.no_tokenizer:
        try:
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
        except Exception:
            tokenizer = None

    per_trajectory = []
    per_marker_traj = {marker: [] for marker in MARKERS}
    series = []
    n_marker_total = 0
    for row in inventory:
        path = row["path"]
        with np.load(path) as data:
            hidden = data["hidden_states"]
            ids = data["token_ids"]
            files = set(data.files)
            top1 = data["topk_indices"][:-1, 0] if "topk_indices" in files else None
            n_prompt = int(len(data["prompt_token_ids"])) if "prompt_token_ids" in files else None
        if hidden.ndim != 3 or hidden.shape[1] != n_layers or hidden.shape[2] != d_model:
            raise SystemExit("unexpected hidden_states shape in %s: %r" % (path, hidden.shape))
        proj = np.einsum("tld,d->tl", hidden, vector)
        norm = np.linalg.norm(hidden, axis=2)
        cos = proj / np.where(norm > 0, norm, 1.0)
        if not (np.isfinite(proj).all() and np.isfinite(cos).all()):
            raise SystemExit("non-finite projection in %s" % path)
        labels = np.isin(ids[1:], MARKERS)
        proj = proj[:-1]
        cos = cos[:-1]
        norm = norm[:-1]
        stats = aggregate_series(proj, cos, norm, labels)
        per_trajectory.append(stats)
        n_marker_total += int(labels.sum())
        next_ids = ids[1:]
        for marker in MARKERS:
            marker_labels = (next_ids == marker)
            marker_count = int(marker_labels.sum())
            if marker_count == 0 or marker_count == len(marker_labels):
                continue
            per_marker_traj[marker].append(layer_stats(proj, cos, norm, marker_labels))
        if row["meta"]["id"] in series_ids:
            tokens = decode_tokens(tokenizer, ids[:-1])
            series.append({
                "id": row["meta"]["id"],
                "problem": row["meta"]["problem"],
                "mode": row["meta"]["mode"],
                "T": int(len(ids)),
                "n_prompt_tokens": n_prompt,
                "n_marker": int(labels.sum()),
                "tokens": tokens,
                "token_ids": [int(x) for x in ids[:-1]],
                "top1_ids": [int(x) for x in top1] if top1 is not None else None,
                "marker_mask": [int(x) for x in labels],
                "marker_positions": [int(x) for x in np.nonzero(labels)[0]],
                "proj": np.round(proj, 2).tolist(),
                "cos": np.round(cos, 3).tolist(),
                "norm": np.round(norm, 2).tolist(),
            })
        del hidden, proj, norm, cos, ids, top1

    aggregate = aggregate_layers(per_trajectory)
    per_marker = aggregate_marker_layers(per_marker_traj, MARKERS)
    best = pick_best_layer(aggregate)
    best_row = next((row for row in aggregate if row["layer"] == best), None)
    best_value = best_row.get("mean_auc_cos_oriented") if best_row else None
    if best is None or best_row is None or best_value is None:
        raise SystemExit("no layer has a defined marker AUC")
    if len(per_trajectory) < 5:
        raise SystemExit("need at least 5 trajectories, got %d" % len(per_trajectory))

    atlas = {
        "schema": SCHEMA,
        "complete": True,
        "scope": "stored float32 hidden states; primary score = cos(h,w) (scale-free), secondary = w.h; label = next generated token is one of 7 marker ids; rank AUC is descriptive, not causal; norm AUC is a confound control",
        "vector": {
            "path": str(args.vector.resolve().relative_to(ROOT)),
            "sha256": args.expected_vector_sha,
            "extraction_layer": 19,
            "injection_block": 20,
            "norm": float(np.linalg.norm(vector)),
        },
        "model": {"name": args.model_dir.name, "n_layers": n_layers, "d_model": d_model},
        "marker_ids": MARKERS,
        "aggregate": {
            "layers": aggregate,
            "best_layer": best,
            "best_layer_mean_auc_proj": best_row.get("mean_auc"),
            "best_layer_mean_auc_cos": best_row.get("mean_auc_cos"),
            "best_layer_mean_auc_cos_oriented": best_value,
            "best_layer_mean_auc_norm": best_row.get("mean_auc_norm"),
            "best_layer_mean_auc_proj_resid": best_row.get("mean_auc_proj_resid"),
            "best_layer_orientation": best_row.get("cos_orientation"),
            "n_trajectories_with_orientation": best_row.get("n_trajectories_with_orientation"),
            "n_trajectories_negative_orientation": best_row.get("n_trajectories_negative_orientation"),
            "chance_level": 0.5,
            "n_trajectories": len(per_trajectory),
            "n_marker_total": n_marker_total,
            "n_positions_total": int(sum(row[0]["n_total"] for row in per_trajectory)),
        },
        "per_marker": per_marker,
        "trajectories": [
            {"id": row["meta"]["id"], "problem": row["meta"]["problem"], "mode": row["meta"]["mode"],
             "T": row["T"], "n_marker": row["n_marker"]}
            for row in inventory
        ],
        "series": series,
        "guards": {
            "vector_sha_ok": True,
            "trajectories_loaded": len(per_trajectory),
            "marker_occurrences": n_marker_total,
            "best_layer_finite": bool(np.isfinite(best_value)),
            "max_abs_cos": float(max(np.abs(np.asarray(item["cos"])).max() for item in series)) if series else None,
            "series_count": len(series),
            "per_marker_markers_with_data": sum(1 for item in per_marker.values() if item["n_occurrences"] > 0),
        },
        "generated_by": "backend/examples/build_readout_atlas.py",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(atlas, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    args.public.parent.mkdir(parents=True, exist_ok=True)
    args.public.write_text(json.dumps(atlas, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")

    if not args.no_figure:
        render_figure(atlas, args.figure)

    print("[ok] atlas: %s" % args.out)
    print("[ok] public: %s" % args.public)
    print("[ok] series: %s" % ", ".join(series_ids))
    for marker in MARKERS:
        item = per_marker[str(marker)]
        print("  marker %s: n=%s, best layer %s, raw cos AUC %s, orientation %s" % (
            marker, item["n_occurrences"], item["best_layer"],
            "%.4f" % item["best_layer_mean_auc_cos"] if item["best_layer_mean_auc_cos"] is not None else "None",
            item["best_layer_orientation"]))
    print("[best] layer %d oriented cos AUC %.4f (raw cos %s, proj %s, norm %s; neg-orient traj %s/%s; n_marker=%d, n_traj=%d)" % (
        best, best_value,
        "%.4f" % best_row["mean_auc_cos"] if best_row.get("mean_auc_cos") is not None else "None",
        "%.4f" % best_row["mean_auc"] if best_row.get("mean_auc") is not None else "None",
        "%.4f" % best_row["mean_auc_norm"] if best_row.get("mean_auc_norm") is not None else "None",
        best_row.get("n_trajectories_negative_orientation"), best_row.get("n_trajectories_with_orientation"),
        n_marker_total, len(per_trajectory)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

