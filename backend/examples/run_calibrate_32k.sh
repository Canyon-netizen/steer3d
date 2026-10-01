#!/usr/bin/env bash
# Phase 1 of the 32k study: how many tokens does Qwen3-0.6B need before it
# closes </think>? Nothing downstream can be sized without this number.
#
# Every path here is under /var/tmp (local ext4). The NFS-backed ~ made the
# first attempt sit in D state for 3+ minutes with the GPU at 0%.
set -euo pipefail

ROOT=/var/tmp/steer3d
cd "$ROOT/backend/examples"
PY="$ROOT/env/bin/python"
MODEL="$ROOT/models/Qwen3-0.6B"
OUT=output/longcal_06b.json
LOG=output/longcal_06b.log

# Extractor self-test first. A wrong answer regex produces a clean-looking
# "0/2 answers known" and would be read as a property of the model rather
# than of the harness.
"$PY" run_long_cot.py --self-test

echo "=== calibrate: ${1:-2} problem(s), 32768 token budget ==="
echo "=== $(date) ==="
"$PY" -u run_long_cot.py \
  --model-path "$MODEL" \
  --device cuda:0 \
  --problems-file output/problem_index.json \
  --limit "${1:-2}" \
  --mode calibrate \
  --max-new-tokens 32768 \
  --save-text \
  --out "$OUT" 2>&1 | tee "$LOG"

echo "=== DONE $(date) -> $OUT ==="
