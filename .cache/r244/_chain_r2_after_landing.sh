#!/bin/bash
# ⚖ 等「落账完成」⇒ ⇒ **立刻**启动 R2（用落账后的账本跑全回归）
#   ⇒ ⇒ 验「本次提交里那份字节」（R1 验的是落账**前**的账本）
set -u
cd /Users/zhourui/code/steer3d || exit 2
LED=.cache/xcheck/R6_RERUN_PREREG.md
BASE=41248

echo "=== 等落账完成（账本行数 > ${BASE}）==="
for i in $(seq 1 900); do
  n=$(wc -l < "$LED" 2>/dev/null || echo 0)
  if [ "$n" -gt "${BASE}" ]; then
    echo "✅ 落账完成：账本 $n 行（基线 ${BASE}）｜ md5 $(md5 -q "$LED")"
    break
  fi
  sleep 15
done
n=$(wc -l < "$LED" 2>/dev/null || echo 0)
[ "$n" -gt "${BASE}" ] || { echo "⛔ 落账没发生 ⇒ 不启动 R2"; exit 3; }

echo "=== 启动 R2 ==="
bash .cache/r244/_run_r2_24481.sh
echo "DONE_R2_CHAIN"
