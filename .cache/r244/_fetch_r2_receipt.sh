#!/bin/bash
# ⚖ 等 R2 落 `REG_RC` ⇒ ⇒ 取回收据 ＋ 打摘要（⛔ 不自己 kill 远端进程）
set -u
cd /Users/zhourui/code/steer3d || exit 2
EV=.cache/r244/_e24481
OUT=/dev/shm/s24480r/reg_24481b.txt

for i in $(seq 1 600); do
  if ssh zju-12 "grep -q 'REG_RC=' $OUT" 2>/dev/null; then break; fi
  sleep 20
done
ssh zju-12 "grep -q 'REG_RC=' $OUT" 2>/dev/null || { echo "⛔ R2 还没落 REG_RC"; exit 3; }

echo "=== R2 摘要 ==="
ssh zju-12 'grep -E "^n_exec_py=|^manifest_md5=|^manifest_diff_rc=|^added=|^removed=|^ledger_lines=|^ledger_md5=|^index_md5=|^host=" /dev/shm/s24480r/reg_24481b.txt; grep "小结：" /dev/shm/s24480r/reg_24481b.txt; grep "REG_RC=" /dev/shm/s24480r/reg_24481b.txt; echo "--- 红项 ---"; grep -E "^  \[BAD \]" /dev/shm/s24480r/reg_24481b.txt || echo "(无 BAD)"; echo -n "OK="; grep -c "^  \[OK \]" /dev/shm/s24480r/reg_24481b.txt; echo -n "SKIP="; grep -c "^  \[SKIP\]" /dev/shm/s24480r/reg_24481b.txt'

scp -q zju-12:/dev/shm/s24480r/reg_24481b.txt "$EV/reg_24481b.txt" || { echo "⛔ 取回 R2 收据失败"; exit 2; }
echo "=== R2 收据已取回 ==="
md5 -q "$EV/reg_24481b.txt"
wc -l < "$EV/reg_24481b.txt"
echo "DONE_R2_FETCH"
