#!/bin/bash
cd /Users/zhourui/code/steer3d || exit 1
PY=.cache/venv3d/bin/python
for m in "$@"; do
  echo "########## $m ##########"
  $PY .cache/bmmut/run_mut_outcome.py "$m" 2>&1 \
    | grep -E "^\s+\[|^===|RESULT|ABORT|frontend|build failed"
  echo ""
done
echo "########## ALL DONE ##########"
