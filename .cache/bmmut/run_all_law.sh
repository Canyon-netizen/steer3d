#!/bin/bash
# 变异总跑：每条都必须"精确命中"它声明的那条判据。
# 一条没打红 = 那条判据在那件事上没有牙齿，不是覆盖率差一点。
set -u
cd /Users/zhourui/code/steer3d
OUT=.cache/mutlaw/ALL.txt
# 目录要自己建：python 侧的 backup() 才建，而 shell 先截断文件 ——
# 目录不存在时 `: > "$OUT"` 直接失败，9 条变异会全部报成 BAD。
mkdir -p .cache/mutlaw
: > "$OUT"
ok=0; bad=0
for m in "$@"; do
  echo "################ $m" >> "$OUT"
  python3 .cache/bmmut/run_mut_law.py "$m" >> "$OUT" 2>&1
  if grep -q "RESULT $m OK" "$OUT"; then
    ok=$((ok+1)); echo "OK   $m"
  else
    bad=$((bad+1)); echo "BAD  $m"
  fi
done
echo "-----------------------------"
echo "hit=$ok missed=$bad"
grep -E "^RESULT|^####" "$OUT" | sed 's/^/  /'
[ "$bad" -eq 0 ]
