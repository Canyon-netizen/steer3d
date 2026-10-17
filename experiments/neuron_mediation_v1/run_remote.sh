#!/bin/sh
set -u
TASK_ROOT=${2:-/home/zhourui/steer3d_neuron_20261017}
TASK_PY=/tmp/easysteer_env_local/bin/python
GPU_UUID=${1:?Pass the idle GPU UUID}
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
export PYTHONUNBUFFERED=1
cd "$TASK_ROOT" || exit 2
"$TASK_PY" -u backend/examples/run_neuron_mediation.py \
  --model /home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master \
  --vector "$TASK_ROOT/w_L19_m0.npy" \
  --protocol "$TASK_ROOT/experiments/neuron_mediation_v1/protocol.json" \
  --out "$TASK_ROOT/results/native_mediation_v1.json" \
  --gpu-uuid "$GPU_UUID" \
  --aime-root /home/zhourui/steer3d_bpath/gen_b2/aime \
  --r6-source "$TASK_ROOT/original_r6.py"
task_exit=$?
printf '%s\n' "$task_exit" > "$TASK_ROOT/results/run.exit"
exit "$task_exit"
