#!/bin/sh
set -u
TASK_DIR=/home/zhourui/steer3d_bpath
TASK_PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
cd "$TASK_DIR" || exit 2
"$TASK_PY" -u bpath_norm_transport.py \
  --model /home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master \
  --root "$TASK_DIR" --out "$TASK_DIR/bpath_norm_B.json" \
  --gpu-uuid GPU-0400dad8-3492-7afc-612e-1c89040cb688
task_status=$?
printf '%s\n' "$task_status" > "$TASK_DIR/norm_B.exit"
exit "$task_status"
