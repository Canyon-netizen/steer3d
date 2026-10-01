#!/bin/bash
# Strength-matched 0.6B run.
#
# Why: at the same nominal strength=0.2, Qwen3-0.6B's relative residual shift at
# the divergence step is 0.406-0.612 (median ~0.48) against Qwen3-1.7B's
# 0.242-0.400 (median ~0.32). Same number, ~1.5x the actual perturbation, so
# any flip-rate comparison between the two models is confounded by how hard
# each was pushed. This run lowers the strength until the *measured* relative
# shift lands on 1.7B's, making the cross-model comparison strength-matched.
#
# 0.2 * 0.32/0.48 = 0.133
cd /var/tmp/steer3d/backend/examples || exit 1
PY=~/miniconda3/envs/steer3d/bin/python

echo "=== strength-matched 0.6B paired collection, strength=0.13 ==="
date
# GPU 3 had another workload on it; 6 was idle and 0.6B needs ~1.2GB.
export CUDA_VISIBLE_DEVICES=6
$PY run_paired_steering.py \
  --model-path /var/tmp/steer3d/models/Qwen3-0.6B \
  --problems output/problem_index.json \
  --limit 6 --max-new-tokens 128 \
  --layers 4,12,20,26,28 --layer 20 \
  --direction confidence_up --strength 0.13 \
  --vectors-dir /var/tmp/steer3d/steer_0p6b \
  --layer-profiles /var/tmp/steer3d/layer_profiles_0p6b.json \
  --outdir output/paired_0p6b_matched
echo "PAIRED_EXIT=$?"
date
