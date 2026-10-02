#!/bin/bash
# 串行跑完逐层链的所有变异。必须串行：每次都重新 `next build`，
# 两个进程并行会互相覆盖 build 产物，于是"变异没生效"和"判据有牙齿"
# 就再也分不开了。
cd /Users/zhourui/code/steer3d || exit 1
PY=.cache/venv3d/bin/python
for m in "$@"; do
  echo "########## $m ##########"
  $PY .cache/bmmut/run_mut_derivation.py "$m" 2>&1 \
    | grep -E "^\s+\[|^===|RESULT|ABORT|TIMEOUT|frontend"
  echo ""
done
echo "########## ALL DONE ##########"
