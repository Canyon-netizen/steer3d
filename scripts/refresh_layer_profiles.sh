#!/usr/bin/env bash
# Regenerate the measured layer profiles and publish them to the
# frontend, so every claim the UI makes about a layer traces back to a
# number computed from the trajectories.
#
# Usage:  ./scripts/refresh_layer_profiles.sh [data-root]
set -euo pipefail

cd "$(dirname "$0")/.."
DATA_ROOT="${1:-datasets/aime_qwen3_1p7b_16k_fp16/aime}"
OUT=backend/examples/output/layer_profiles.json

echo "→ profiling $DATA_ROOT"
python3 backend/examples/measure_layers.py \
    --data-root "$DATA_ROOT" \
    --out "$OUT"

mkdir -p frontend/public
cp "$OUT" frontend/public/layer_profiles.json
echo "→ published to frontend/public/layer_profiles.json"
