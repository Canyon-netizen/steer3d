#!/bin/bash
# One sequential pass: baseline, then each mutation, then revert. No overlap --
# an earlier run of this had two sweeps racing for the same backup file and
# one of them reverted a tree the other was still mutating.
set -u
cd /Users/zhourui/code/steer3d
OUT=.cache/cottext/sweep_report.txt
: > "$OUT"
run() { node .cache/cottext/verify_cottext.mjs 2>&1; }
{
echo "=== 基线（无变异）==="
run | grep -E "^  FAIL|^(ALL PASS|FAIL [0-9]+/)"
for M in M1 M2 M3 M4 M5 M6 M7 M8; do
  echo
  echo "=== $M ==="
  bash .cache/cottext/mutate_cottext.sh apply-$M 2>&1 | head -1
  run > .cache/cottext/m_$M.txt
  grep -E "^  FAIL" .cache/cottext/m_$M.txt | sed 's/^/  /'
  grep -E "^(ALL PASS|FAIL [0-9]+/)" .cache/cottext/m_$M.txt | sed 's/^/  => /'
  bash .cache/cottext/mutate_cottext.sh revert 2>&1 | head -1
done
echo
echo "=== 收尾：文件是否回到干净状态 ==="
bash .cache/cottext/mutate_cottext.sh status
} >> "$OUT" 2>&1
echo "done -> $OUT"
