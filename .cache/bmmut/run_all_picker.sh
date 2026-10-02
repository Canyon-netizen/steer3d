#!/bin/bash
# 串行跑完所有变异判据。必须串行：run_mut_picker.py 每次都改
# frontend/lib/ws-endpoint.ts 并重新 `next build`，两个进程并行会
# 互相覆盖对方的 build 产物，于是"变异没生效"和"判据有牙齿"就再也
# 分不开了。
cd /Users/zhourui/code/steer3d || exit 1
PY=.cache/venv3d/bin/python
for m in "$@"; do
  echo "########## $m ##########"
  $PY .cache/bmmut/run_mut_picker.py "$m" 2>&1 | grep -E "^\s+\[|^===|RESULT|ABORT|TIMEOUT"
  echo ""
done
echo "########## ALL DONE ##########"
