#!/bin/sh
set -u
TASK_ROOT=${2:-/home/zhourui/steer3d_circuit_20261017}
GPU_UUID=${1:?Pass an idle GPU UUID}
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 PYTHONUNBUFFERED=1
cd "$TASK_ROOT" || exit 2
/tmp/easysteer_env_local/bin/python -u backend/examples/collect_circuit_landscape.py \
  --model /home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master \
  --vector "$TASK_ROOT/w_L19_m0.npy" \
  --source-root /home/zhourui/steer3d_bpath/gen_b2/aime \
  --mediation "$TASK_ROOT/native_mediation_v1.json" \
  --source-manifest "$TASK_ROOT/source_manifest.json" \
  --out "$TASK_ROOT/results/circuit_landscape.json" --gpu-uuid "$GPU_UUID"
task_exit=$?
printf '%s\n' "$task_exit" > results/run.exit
exit "$task_exit"
