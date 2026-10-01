#!/usr/bin/env bash
# Stage everything onto LOCAL disk.
#
# ~ is an NFS mount on this box. Loading a 1.5 GB model and importing torch
# (several GB of .so) over NFS put the first calibration run into D state
# for 3+ minutes before it printed a single line, with the GPU still at 0%.
# /var/tmp is local ext4 with ~480 GB free, so the fix is to stop paying
# NFS latency per import and per weight read.
set -euo pipefail

DST=/var/tmp/steer3d
mkdir -p "$DST"

echo "=== code ==="
mkdir -p "$DST/backend/examples/output"
cp -r ~/steer3d_run/backend/core "$DST/backend/core"
cp ~/steer3d_run/backend/examples/*.py "$DST/backend/examples/" 2>/dev/null || true
cp ~/steer3d_run/backend/examples/*.sh "$DST/backend/examples/" 2>/dev/null || true
cp -r ~/steer3d_run/backend/examples/output/. "$DST/backend/examples/output/" 2>/dev/null || true
rm -rf "$DST"/backend/*/__pycache__ "$DST"/backend/core/__pycache__ 2>/dev/null || true

echo "=== model (1.5 GB) ==="
mkdir -p "$DST/models/Qwen3-0.6B"
cp -r ~/models/Qwen3-0.6B/. "$DST/models/Qwen3-0.6B/"

echo "=== python env (torch is multi-GB) ==="
# Symlinking instead of copying would just point the imports back at NFS,
# which is the thing being fixed here.
cp -r ~/miniconda3/envs/steer3d "$DST/env"

echo "=== verify sizes ==="
du -sh "$DST"/models "$DST"/env "$DST"/backend 2>/dev/null
ls -l "$DST/models/Qwen3-0.6B/model.safetensors"
echo "STAGE OK"
