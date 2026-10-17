#!/usr/bin/env python3
"""Compile one steering-vector recipe per marker and verify the saved file.

The recipe combines:
  * readout atlas (which layer reads the marker)
  * held-out transfer (mean g / sparse g vs w)
  * alpha/side-effect sweep (useful direction/dose under a KL budget)
  * a compiled .npy direction and one held-out verification run

The output is a recipe, not a claim that this is the only or best vector.
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

from core.steering_gradient import compute_gradient, mean_direction, normalize, sparse_direction  # noqa: E402
from core.steering_recipe import RecipeError, assemble_recipe  # noqa: E402
from core.steering_sweep import marker_summary  # noqa: E402
from core.neuron_mediation import native_forward  # noqa: E402

SCHEMA = "steer3d.steering_recipe/1"
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
    parser.add_argument("--atlas", type=Path, default=ROOT / "experiments/readout_atlas_v1/readout_atlas.json")
    parser.add_argument("--transfer", type=Path, default=ROOT / "experiments/steering_transfer_v1/steering_transfer.json")
    parser.add_argument("--sweep", type=Path, default=ROOT / "experiments/steering_sweep_v1/steering_sweep.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments/steering_recipe_v1")
    parser.add_argument("--public-dir", type=Path, default=ROOT / "frontend/public/latent/data/steering_recipes")
    parser.add_argument("--out", type=Path, default=ROOT / "experiments/steering_recipe_v1/steering_recipe.json")
    parser.add_argument("--public", type=Path, default=ROOT / "frontend/public/latent/data/steering_recipe.json")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM

    for name, path in (("atlas", args.atlas), ("transfer", args.transfer), ("sweep", args.sweep)):
        if not path.exists():
            raise SystemExit("%s artifact not found: %s" % (name, path))
    atlas = json.loads(args.atlas.read_text(encoding="utf-8"))
    transfer = json.loads(args.transfer.read_text(encoding="utf-8"))
    sweep = json.loads(args.sweep.read_text(encoding="utf-8"))

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
        if not splits[marker]["heldout"]:
            raise SystemExit("marker %d has no held-out site" % marker)

    torch.set_num_threads(args.threads)
    model = AutoModelForCausalLM.from_pretrained(
        str(args.model_dir), dtype=torch.float32, local_files_only=True, attn_implementation="eager")
    model.eval()
    rng = np.random.default_rng(args.seed)
    random_direction = normalize(rng.standard_normal(2048).astype(np.float32))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "vectors").mkdir(parents=True, exist_ok=True)
    args.public_dir.mkdir(parents=True, exist_ok=True)

    recipes = {}
    source_hashes = {
        "atlas": sha256_file(args.atlas),
        "transfer": sha256_file(args.transfer),
        "sweep": sha256_file(args.sweep),
        "vector": digest,
    }
    for marker in markers:
        calibration = splits[marker]["calibration"]
        gradients = []
        for site in calibration:
            ids = full_ids(site)
            tensor = torch.tensor(ids.reshape(1, -1), dtype=torch.long)
            result = compute_gradient(model, tensor, marker=marker, layer=20)
            gradients.append(result["gradient"])
        mean_g = mean_direction(gradients)
        directions = {
            "w": vector,
            "minus_w": -vector,
            "mean_g": mean_g,
            "sparse_g": sparse_direction(mean_g, 0.1),
            "random": random_direction,
        }
        files = {}
        for name, direction in directions.items():
            path = args.out_dir / "vectors" / ("%d_%s.npy" % (marker, name))
            np.save(path, np.asarray(direction, dtype=np.float32))
            public_path = args.public_dir / path.name
            np.save(public_path, np.asarray(direction, dtype=np.float32))
            files[name] = str(path.resolve().relative_to(ROOT))

        window = sweep["useful_window"][str(marker)]
        chosen_direction = window["direction"]
        chosen_dose = float(window["dose"])
        if chosen_direction not in directions:
            raise SystemExit("useful direction %r has no compiled vector" % chosen_direction)

        # verify the saved chosen direction on all held-out sites of this marker
        verification_rows = []
        for held in splits[marker]["heldout"]:
            ids = full_ids(held)
            tensor = torch.tensor(ids.reshape(1, -1), dtype=torch.long)
            baseline = native_forward(model, tensor, injection_layer=20, vector=None, alpha=0.0)
            alpha = chosen_dose * float(baseline["input_norm"])
            injected = native_forward(model, tensor, injection_layer=20, vector=directions[chosen_direction], alpha=alpha)
            base_summary = marker_summary(baseline["logits"], baseline["logits"], marker, markers)
            summary = marker_summary(baseline["logits"], injected["logits"], marker, markers)
            verification_rows.append({
                "trajectory": held["trajectory"],
                "t": held["t"],
                "n_prefix": held["n_prefix"],
                "dose": chosen_dose,
                "alpha": alpha,
                "delta_logp": summary["target_logp"] - base_summary["target_logp"],
                "kl": summary["kl"],
                "target_probability": summary["target_probability"],
                "other_marker_mass": summary["other_marker_mass"],
            })
        verification = {
            "n_sites": len(verification_rows),
            "mean_delta_logp": float(np.mean([row["delta_logp"] for row in verification_rows])),
            "mean_kl": float(np.mean([row["kl"] for row in verification_rows])),
            "sites": verification_rows,
        }

        readout = atlas["per_marker"][str(marker)]
        transfer_entry = transfer["same_marker"][str(marker)]
        caveats = [
            "local white-box recipe on short AIME prefixes; single model, layer 20, one alpha grid",
            "held-out verification uses the same two held-out sites per marker as the transfer; it is not an independent third split",
            "mean g / sparse g are numerical directions, not semantic vectors; high doses can be off-manifold",
            "the useful window is chosen by a mean-KL budget, not by correctness on a downstream task",
        ]
        try:
            entry = assemble_recipe(marker, readout, transfer_entry, window, files, verification, caveats)
        except RecipeError as exc:
            raise SystemExit(str(exc))
        entry["compiled"]["public_url"] = "/latent/data/steering_recipes/" + Path(files[chosen_direction]).name
        entry["compiled"]["file_sha256"] = sha256_file(ROOT / files[chosen_direction])
        entry["compiled"]["norm"] = float(np.linalg.norm(directions[chosen_direction]))
        recipes[str(marker)] = entry
        print("[recipe] marker %d: %s @ dose %.2f, verification mean delta %+.4f KL %.4f (n=%d)" % (
            marker, chosen_direction, chosen_dose, verification["mean_delta_logp"], verification["mean_kl"], verification["n_sites"]))

    data = {
        "schema": SCHEMA,
        "complete": True,
        "scope": "compiled per-marker recipes combining readout atlas, held-out transfer, alpha/KL sweep, and one held-out verification run",
        "model": {"name": args.model_dir.name, "injection_layer": 20, "dtype": "float32", "attention": "eager"},
        "vector": {"path": str(args.vector.resolve().relative_to(ROOT)), "sha256": digest},
        "alpha_rule": "dose * measured block-20 input L2 norm at the last prefix position",
        "markers": recipes,
        "source_hashes": source_hashes,
        "guards": {
            "n_markers": len(recipes),
            "vector_sha_ok": True,
            "all_files_exist": all((ROOT / entry["compiled"]["file"]).exists() for entry in recipes.values()),
            "verification_finite": all(np.isfinite(entry["verification"]["mean_delta_logp"]) for entry in recipes.values()),
        },
        "generated_by": "backend/examples/compile_steering_recipe.py",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    args.public.parent.mkdir(parents=True, exist_ok=True)
    args.public.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print("[ok] recipe: %s" % args.out)
    print("[ok] public: %s" % args.public)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

