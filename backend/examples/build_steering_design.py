#!/usr/bin/env python3
"""Build the steering design guide from existing measurement artifacts.

No model forward passes.  The report is written to
experiments/steering_design_v1/ and, for the web page, copied to
frontend/public/latent/data/steering_design.json.

Usage:
  python3 backend/examples/build_steering_design.py
  python3 backend/examples/build_steering_design.py --out /tmp/design.json --no-public
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.steering_design import (  # noqa: E402
    DesignError,
    build_report,
    load_json,
    render_markdown,
    sha256_file,
)

DEFAULTS = {
    "summary": ROOT / "experiments/neuron_mediation_v1/results/summary.json",
    "mediation": ROOT / "experiments/neuron_mediation_v1/results/native_mediation_v1.json",
    "bpath": ROOT / "frontend/public/latent/data/bpath_marker_steering.json",
    "axis": ROOT / "frontend/public/latent/data/axis_readouts.json",
    "lens": ROOT / "frontend/public/latent/data/logit_lens.json",
    "atlas": ROOT / "experiments/readout_atlas_v1/readout_atlas.json",
    "construction": ROOT / "experiments/steering_construction_v1/steering_construction.json",
    "steering_transfer": ROOT / "experiments/steering_transfer_v1/steering_transfer.json",
    "steering_sweep": ROOT / "experiments/steering_sweep_v1/steering_sweep.json",
    "steering_recipe": ROOT / "experiments/steering_recipe_v1/steering_recipe.json",
    "out": ROOT / "experiments/steering_design_v1/steering_design.json",
    "markdown": ROOT / "experiments/steering_design_v1/README.md",
    "public": ROOT / "frontend/public/latent/data/steering_design.json",
    "figure": ROOT / "experiments/steering_design_v1/steering_design.png",
}


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in DEFAULTS.items():
        parser.add_argument("--" + name, type=Path, default=default)
    parser.add_argument("--no-public", action="store_true", help="skip the frontend copy")
    parser.add_argument("--no-figure", action="store_true", help="skip the static PNG summary")
    parser.add_argument("--no-atlas", action="store_true", help="skip the hidden-state readout atlas")
    parser.add_argument("--no-construction", action="store_true", help="skip the construction probe")
    parser.add_argument("--no-steering-transfer", action="store_true", help="skip the held-out transfer")
    parser.add_argument("--no-steering-sweep", action="store_true", help="skip the alpha/side-effect sweep")
    parser.add_argument("--no-steering-recipe", action="store_true", help="skip the compiled recipe")
    args = parser.parse_args()

    paths = {name: args.__dict__[name] for name in ("summary", "mediation", "bpath", "axis", "lens")}
    try:
        sources = {name: load_json(path) for name, path in paths.items()}
    except DesignError as exc:
        print("[error] %s" % exc, file=sys.stderr)
        return 2

    hashes = {name: sha256_file(path) for name, path in paths.items()}
    source_paths = {name: rel(path) for name, path in paths.items()}

    atlas = None
    if not args.no_atlas:
        if args.atlas.exists():
            try:
                atlas = load_json(args.atlas)
            except DesignError as exc:
                print("[error] %s" % exc, file=sys.stderr)
                return 2
            hashes["atlas"] = sha256_file(args.atlas)
            source_paths["atlas"] = rel(args.atlas)
        else:
            print("[warn] atlas not found, continuing without it: %s" % rel(args.atlas), file=sys.stderr)

    construction = None
    if not args.no_construction:
        if args.construction.exists():
            try:
                construction = load_json(args.construction)
            except DesignError as exc:
                print("[error] %s" % exc, file=sys.stderr)
                return 2
            hashes["construction"] = sha256_file(args.construction)
            source_paths["construction"] = rel(args.construction)
        else:
            print("[warn] construction probe not found, continuing without it: %s" % rel(args.construction), file=sys.stderr)

    steering_transfer = None
    if not args.no_steering_transfer:
        if args.steering_transfer.exists():
            try:
                steering_transfer = load_json(args.steering_transfer)
            except DesignError as exc:
                print("[error] %s" % exc, file=sys.stderr)
                return 2
            hashes["steering_transfer"] = sha256_file(args.steering_transfer)
            source_paths["steering_transfer"] = rel(args.steering_transfer)
        else:
            print("[warn] steering transfer not found, continuing without it: %s" % rel(args.steering_transfer), file=sys.stderr)

    steering_sweep = None
    if not args.no_steering_sweep:
        if args.steering_sweep.exists():
            try:
                steering_sweep = load_json(args.steering_sweep)
            except DesignError as exc:
                print("[error] %s" % exc, file=sys.stderr)
                return 2
            hashes["steering_sweep"] = sha256_file(args.steering_sweep)
            source_paths["steering_sweep"] = rel(args.steering_sweep)
        else:
            print("[warn] steering sweep not found, continuing without it: %s" % rel(args.steering_sweep), file=sys.stderr)

    steering_recipe = None
    if not args.no_steering_recipe:
        if args.steering_recipe.exists():
            try:
                steering_recipe = load_json(args.steering_recipe)
            except DesignError as exc:
                print("[error] %s" % exc, file=sys.stderr)
                return 2
            hashes["steering_recipe"] = sha256_file(args.steering_recipe)
            source_paths["steering_recipe"] = rel(args.steering_recipe)
        else:
            print("[warn] steering recipe not found, continuing without it: %s" % rel(args.steering_recipe), file=sys.stderr)

    try:
        report = build_report(
            sources["summary"], sources["bpath"], sources["axis"], sources["lens"], sources["mediation"],
            source_paths=source_paths, source_hashes=hashes, readout_atlas=atlas, construction=construction,
            steering_transfer=steering_transfer, steering_sweep=steering_sweep, steering_recipe=steering_recipe,
        )
    except DesignError as exc:
        print("[error] %s" % exc, file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    if not args.no_public:
        args.public.parent.mkdir(parents=True, exist_ok=True)
        args.public.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")

    if not args.no_figure:
        try:
            from core.steering_design_figure import render_figure
            render_figure(report, args.figure)
            print("[ok] figure: %s" % rel(args.figure))
        except ImportError as exc:
            print("[warn] figure skipped: %s" % exc, file=sys.stderr)

    print("[ok] report: %s" % rel(args.out))
    print("[ok] markdown: %s" % rel(args.markdown))
    if not args.no_public:
        print("[ok] public: %s" % rel(args.public))
    if report.get("steering_recipe"):
        summary = report["steering_recipe"]
        print("[recipe] %d compiled markers: %s" % (
            summary["n_markers"], ", ".join("%s=%s@%s" % (marker, entry["compiled"].get("direction"), entry["compiled"].get("dose")) for marker, entry in sorted(summary["markers"].items()))))
    if report.get("steering_sweep"):
        summary = report["steering_sweep"]
        print("[sweep] %d held-out sites; useful windows %s" % (
            summary["n_sites"], ", ".join("%s=%s@%s" % (marker, item.get("useful_window", {}).get("direction"), item.get("useful_window", {}).get("dose")) for marker, item in sorted(summary["by_marker"].items()))))
    if report.get("steering_transfer"):
        summary = report["steering_transfer"]
        print("[transfer] %d held-out sites; markers %s" % (summary["n_sites"], ", ".join(sorted(summary["by_marker"]))))
    if report.get("construction"):
        summary = report["construction"]
        print("[construction] %d sites; markers %s" % (summary["n_sites"], ", ".join(sorted(summary["by_marker"]))))
    if report.get("readout_atlas"):
        summary = report["readout_atlas"]
        print("[atlas] best layer %s: raw cos AUC %s, oriented %s, orientation %s" % (
            summary["best_layer"], summary.get("best_layer_mean_auc_cos"),
            summary.get("best_layer_mean_auc_cos_oriented"), summary.get("best_layer_orientation")))
    print("[headline] %s" % report["headline"])
    print("[recommendations] %d" % len(report["recommendations"]))
    for rec in report["recommendations"]:
        layer = "layer %s" % rec["layer"] if rec["layer"] is not None else "global"
        print("  - [%s] %s (%s): %s" % (rec["priority"], rec["action"], layer, rec["confidence"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

