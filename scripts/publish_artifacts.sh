#!/usr/bin/env bash
# Publish the backend's generated artifacts into frontend/public/ so the
# UI can fetch them.
#
# The Next.js app serves static files from public/, while the analysis
# scripts write into backend/examples/output/. This copies the two the
# frontend reads — the measured layer profiles and any archived
# intervention experiments — across, and reports anything it skipped so
# a stale copy can't pass silently.
#
# Usage:  ./scripts/publish_artifacts.sh
set -euo pipefail

cd "$(dirname "$0")/.."

OUT=backend/examples/output
PUB=frontend/public
mkdir -p "$PUB/intervention"

# --- layer profiles (InterpretationPanel) ---
if [[ -f "$OUT/layer_profiles.json" ]]; then
    cp "$OUT/layer_profiles.json" "$PUB/layer_profiles.json"
    echo "→ layer_profiles.json  (measured $(python3 -c "
import json,sys
d=json.load(open('$OUT/layer_profiles.json'))
print(f\"{d['n_trajectories']} trajectories, {len(d['layers'])} layers\")
"))"
else
    echo "✗ $OUT/layer_profiles.json missing — run scripts/refresh_layer_profiles.sh" >&2
fi

# --- intervention experiments (ArchivedExperiments) ---
# The panel names specific files; copy whatever is present and say what
# did not make it, so the UI's "nothing archived yet" state is
# distinguishable from "the copy is stale".
shopt -s nullglob
found=0
for f in "$OUT"/intervention/*.json; do
    cp "$f" "$PUB/intervention/"
    found=$((found + 1))
done

if [[ $found -eq 0 ]]; then
    echo "! no intervention experiments in $OUT/intervention/" >&2
    echo "  run: python3 backend/examples/run_intervention.py --out $OUT/intervention/<name>.json" >&2
else
    echo "→ $found experiment file(s):"
    for f in "$PUB"/intervention/*.json; do
        echo "    $(basename "$f")"
    done
fi

# Warn about files the frontend references but that are not published.
for want in directions_L20_aime2023.json confidence_up_L20_sweep.json layer_scan_confidence_up.json; do
    [[ -f "$PUB/intervention/$want" ]] || echo "  (referenced by the UI but not yet produced: $want)"
done
