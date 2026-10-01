#!/usr/bin/env bash
# Run one shard of the 24-problem x 4-condition sweep, checkpointing per problem.
#
# Why a wrapper instead of one run_intervention.py invocation: that script writes
# its results once, at the very end. A 16-run shard takes hours; if it dies at
# run 15 everything is lost. Here each problem is its own invocation and its
# results are appended to a JSONL immediately, so a crash costs at most one
# problem.
#
# Usage: shard.sh <gpu> <shard_idx> <n_shards> <model_dir> <base_dir>

set -u
GPU=$1
IDX=$2
NSHARD=$3
MODEL=$4
BASE=$5

REPO=$HOME/steer3d
OUT=$BASE/out32k
mkdir -p "$OUT"

export CUDA_VISIBLE_DEVICES=$GPU
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

SLICE=$BASE/slice_${IDX}.json
JOURNAL="$OUT/shard_${IDX}.jsonl"
# Create up front so `wc -l` below never hits a missing file.
: > "$JOURNAL"

echo "shard $IDX/$NSHARD on GPU$GPU  model=$MODEL  start $(date +%T)"
HELPER=$BASE/sweep_helpers.py
python3 "$HELPER" slice_helper "$BASE/problem_index_24.json" "$SLICE" "$IDX" "$NSHARD" \
  || { echo "FATAL: slice build failed"; exit 1; }

# Iterate only this shard's own problems, read from the slice file. Hardcoding
# the full id list here is what let shard 1 try to run a problem it did not own.
IDS=$(python3 -c "import json,sys; print(' '.join(r['id'] for r in json.load(open(sys.argv[1]))))" "$SLICE")
echo "  problems: $IDS"

for PID in $IDS; do
  ONE=$BASE/one_${IDX}_${PID}.json
  python3 "$HELPER" one_helper "$SLICE" "$ONE" "$PID" \
    || { echo "  !! $PID not in slice, skipping"; continue; }

  TMP=$OUT/.tmp_${IDX}_${PID}.json
  echo "--- $PID  start $(date +%T) ---"
  # Keep a long tail: `tail -3` once hid the frames that said *what* was
  # importing torchaudio, which is exactly the part needed to debug it.
  ( cd "$REPO/backend/examples" && python3 -u run_intervention.py \
      --problems-file "$ONE" --limit 1 \
      --directions confidence_up confidence_down --sweep 0.0 0.2 \
      --layer 20 --layer-rms 865.77 \
      --max-new-tokens 32000 \
      --model-path "$MODEL" --vector-dir "$BASE/vectors" \
      --device cuda:0 --out "$TMP" 2>&1 | grep -v "Loading weights" | tail -25 )

  if [ -s "$TMP" ]; then
    python3 "$HELPER" append_helper "$TMP" "$JOURNAL" "$IDX" "$GPU" \
      && echo "  journalled; journal now has $(wc -l < "$JOURNAL") lines"
  else
    echo "  !! $PID produced no output; moving on"
  fi
done

echo "SHARD_${IDX}_DONE $(date +%T)  lines=$(wc -l < "$JOURNAL")"
