#!/usr/bin/env bash
# Does the extraction layer change the behavioural effect?
#
# compare_extraction_layers.py showed the L8 and L24 versions of the
# confidence vector are near-orthogonal (cosine 0.395), so "the confidence
# direction" is not a single direction. This settles whether that matters
# behaviourally: injection is held fixed at L20 and only the layer the
# vector was READ OUT at varies, so any difference is attributable to the
# extraction rather than to where it lands.
#
# The zero-strength control is identical for every extraction layer (a
# zero vector is a zero vector), so it is run once per layer anyway to
# keep each run self-contained and to catch a broken vector directory.
#
# Usage (on a box with the model staged locally):
#     ./scripts/run_extraction_layer_experiment.sh /tmp/steer3d_vec_layers
set -uo pipefail

VEC_ROOT="${1:-/tmp/steer3d_vec_layers}"
MODEL="${MODEL:-/tmp/qwen3/master}"
PROFILES="${PROFILES:-/tmp/steerdata/layer_profiles.json}"
PROBLEMS="${PROBLEMS:-/tmp/problem_index.json}"
OUT="${OUT:-/tmp/iv_ext}"
LAYERS="${LAYERS:-8 14 20 24}"
INJECT_AT="${INJECT_AT:-20}"
PY="${PY:-$HOME/miniconda3/envs/steer3d/bin/python}"
REPO="${REPO:-$HOME/steer3d/backend}"

export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1

cd "$REPO" || { echo "no repo at $REPO"; exit 1; }

for L in $LAYERS; do
    d="$VEC_ROOT/L$L"
    if [[ ! -f "$d/confidence_up.npy" ]]; then
        echo "skip L$L — no vectors in $d" >&2
        continue
    fi
    echo "########## extracted at L$L, injected at L$INJECT_AT ##########"
    "$PY" -u examples/run_intervention.py \
        --model-path "$MODEL" \
        --vector-dir "$d" \
        --layer-profiles "$PROFILES" \
        --problems-file "$PROBLEMS" \
        --directions confidence_up \
        --sweep 0.0 0.2 \
        --layer "$INJECT_AT" \
        --max-new-tokens 60 \
        --out "${OUT}_L$L.json" || {
            echo "L$L FAILED" >&2
            continue
        }
    echo "  wrote ${OUT}_L$L.json"
done

echo "ALLDONE"
