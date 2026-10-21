#!/bin/sh
set -eu
TASK_ROOT=${2:-/home/zhourui/steer3d_circuit_20261017}
GPU_UUID=${1:?Pass an idle GPU UUID}
cd "$TASK_ROOT"
if test -e results/run.pid || test -e results/circuit_landscape.json; then
  echo 'Refusing duplicate launch.'
  exit 6
fi
setsid sh run_remote.sh "$GPU_UUID" "$TASK_ROOT" > results/run.log 2>&1 < /dev/null &
task_pid=$!
printf '%s\n' "$task_pid" > results/run.pid
printf 'launched pid=%s gpu=%s root=%s\n' "$task_pid" "$GPU_UUID" "$TASK_ROOT"
