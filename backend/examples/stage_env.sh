#!/usr/bin/env bash
# Stage the python env onto local ext4.
#
# One `tar` pipe for the whole env. Earlier versions tried to cherry-pick
# packages and were worse on every axis: `cp -r` does three NFS round trips
# per file across ~40k small files, and the filtered tar raced against a
# stale concurrent run that `rm -rf`'d the destination mid-flight (the
# receiving tar's "无法 mkdir lib" was that, not a tar bug).
#
# The env is ~10 GB and /var/tmp has ~480 GB free, so there is no reason to
# be clever here. `flock` is what actually prevents a second concurrent
# run from deleting the destination out from under the first.
set -euo pipefail

SRC=$HOME/miniconda3/envs/steer3d
DST=/var/tmp/steer3d/env
LOCK=/var/tmp/stage_env.lock

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "another staging run holds $LOCK — refusing to run a second copy"
  exit 1
fi

echo "=== source size ==="
du -sh "$SRC"

rm -rf "$DST"
mkdir -p "$DST"

echo "=== tar stream $(date +%H:%M:%S) ==="
tar -C "$SRC" -cf - . | tar -C "$DST" -xf -
echo "=== extracted $(date +%H:%M:%S) ==="

du -sh "$DST"
ls "$DST/bin/python" >/dev/null || { echo "NO INTERPRETER"; exit 1; }

echo "=== import test ==="
"$DST/bin/python" - <<'PY'
import time
t = time.time(); import torch; t1 = time.time()
import transformers; t2 = time.time()
import numpy; t3 = time.time()
print(f"  torch        {t1-t:6.1f}s  v{torch.__version__}  cuda={torch.cuda.is_available()}")
print(f"  transformers {t2-t1:6.1f}s  v{transformers.__version__}")
print(f"  numpy        {t3-t2:6.1f}s  v{numpy.__version__}")
if torch.cuda.is_available():
    print(f"  device: {torch.cuda.get_device_name(0)}")
PY
echo "ENV OK"
