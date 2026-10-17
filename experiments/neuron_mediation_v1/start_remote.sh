#!/bin/sh
set -eu
TASK_ROOT=${2:-/home/zhourui/steer3d_neuron_20261017}
GPU_UUID=${1:?Pass the idle GPU UUID}
cd "$TASK_ROOT"
if test -e results/run.pid || test -e results/native_mediation_v1.json; then
  printf '%s\n' 'Existing run handle or result; refusing duplicate launch.'
  exit 6
fi
setsid sh scripts/run_remote.sh "$GPU_UUID" "$TASK_ROOT" > results/run.log 2>&1 < /dev/null &
task_pid=$!
printf '%s\n' "$task_pid" > results/run.pid
printf 'launched pid=%s gpu=%s\n' "$task_pid" "$GPU_UUID"
