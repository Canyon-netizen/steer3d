#!/bin/bash
# ⚖ 244.79 的跑批进度收据（⛔ 只读；⛔ 输出到 /dev/shm）
#   ⇒ 落账时**从这份收据算节奏与 ETA**（⛔ 不许手估）
set -u
B=/home/zhourui/steer3d_bpath
OUT=/dev/shm/_batchprog_24479.out
{
echo "=== 244.79 跑批进度 ==="
date '+%F %T'
for a in w rand; do
  L=$B/r244_warm_fd_$a.log
  n=$(grep -c "^### END" $L 2>/dev/null | tr -d '\n' || true)
  first=$(grep "^### END" $L 2>/dev/null | head -1 | awk '{print $NF}')
  last=$(grep "^### END" $L 2>/dev/null | tail -1 | awk '{print $NF}')
  lasti=$(grep "^### END" $L 2>/dev/null | tail -1 | sed -E 's/.*\[([0-9]+)\/([0-9]+)\].*/\1 \2/')
  ab=$(grep -c "ABORT" $L 2>/dev/null | tr -d '\n' || true)
  rc0=$(grep -c "rc=0" $L 2>/dev/null | tr -d '\n' || true)
  echo "arm=$a cells_done=$n first_end=$first last_end=$last idx_tot=$lasti abort=$ab rc0=$rc0"
done
} > "$OUT"
cat "$OUT"
