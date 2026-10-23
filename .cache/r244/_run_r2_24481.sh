#!/bin/bash
# ⚖ **R2**：用**落账之后**的账本再跑一轮远端全回归 ⇒ ⇒ 验「本次提交里那份字节」
#
# ⚖⚖⚖ 为什么必须有 R2（不是走过场）：
#   R1 跑的时候账本还是 244.79 那版（41 248 行）⇒ ⇒ 它验的是**工具**字节（已最终）
#   ⇒ ⇒ 但 244.80 ＋ 244.81 两段追加后**账本字节变了** ⇒ ⇒ 「证据 ↔ 最终版字节」这条闸
#        对**账本**这一半还没过 ⇒ ⇒ 所以追加之后**再跑一轮**。
#
# ⚖ 同步方向：**本地作者树 → 远端 DEV → tmpfs 树**（⛔ 不是反着来）
#   （244.81 那次的事故正是「DEV→树」把新字节盖回旧的 ⇒ ⇒ 现在每步都有逐位对账断言）
set -u
cd /Users/zhourui/code/steer3d || exit 2
EV=.cache/r244/_e24481
DEV=zju-12:/home/zhourui/steer3d
TREE=/dev/shm/s24480r
OUT=$TREE/reg_24481b.txt

# ⚖⚖⚖ **幂等锁**（`mkdir` 原子）⇒ ⇒ 两个链条同时触发也**只会有一个** R2
#   ⇒ ⇒ 否则两个 harness 会同时往同一棵树/同一个收据文件里写 ⇒ ⇒ 证据混血
if ! mkdir .cache/r244/_r2_lock 2>/dev/null; then
  echo "⛔ 已有 R2 在跑（锁存在）⇒ 不重复启动"
  exit 7
fi
echo "R2 锁已取得"

LED=.cache/xcheck/R6_RERUN_PREREG.md
IDX=.cache/xcheck/R6_RERUN_INDEX.md
LED_MD5=$(md5 -q "$LED")
echo "本地账本 md5 = $LED_MD5 ｜ 行数 = $(wc -l < "$LED")"

echo "=== 1) 同步账本 + 索引 + R2 脚本到远端 DEV ==="
scp -q "$LED" "$DEV/.cache/xcheck/R6_RERUN_PREREG.md" || { echo "⛔ 账本同步失败"; exit 2; }
scp -q "$IDX" "$DEV/.cache/xcheck/R6_RERUN_INDEX.md" || { echo "⛔ 索引同步失败"; exit 2; }
scp -q .cache/r244/_run_24481b_reg_shm.sh "$DEV/.cache/r244/" || { echo "⛔ R2 脚本同步失败"; exit 2; }
echo "✅ 已同步"

echo "=== 2) 逐位对账（远端 DEV 的账本必须等于本地那份）==="
REM_MD5=$(ssh zju-12 "md5sum /home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md | cut -d' ' -f1")
echo "远端 DEV 账本 md5 = $REM_MD5"
[ "$REM_MD5" = "$LED_MD5" ] || { echo "⛔ 远端账本与本地不一致 ⇒ 硬停"; exit 3; }
echo "✅ 逐位一致"

echo "=== 3) 启动 R2 ==="
ssh zju-12 "EXPECT_LEDGER_MD5=$LED_MD5 bash /home/zhourui/steer3d/.cache/r244/_run_24481b_reg_shm.sh > /dev/shm/s24480r/reg_24481b_launch.log 2>&1" &
LAUNCH_PID=$!
echo "R2 已在 zju-12 启动（本地 ssh pid=${LAUNCH_PID}）"

echo "=== 4) 等 R2 落 REG_RC ==="
for i in $(seq 1 240); do
  if ssh zju-12 "grep -q 'REG_RC=' $OUT" 2>/dev/null; then break; fi
  sleep 20
done
ssh zju-12 "grep -q 'REG_RC=' $OUT" 2>/dev/null || { echo "⛔ R2 还没落 REG_RC"; exit 4; }

echo "=== R2 摘要 ==="
ssh zju-12 'grep -E "^n_exec_py=|^ledger_lines=|^manifest_md5=|^manifest_diff_rc=|^added=|^removed=|^host=" /dev/shm/s24480r/reg_24481b.txt; grep "小结：" /dev/shm/s24480r/reg_24481b.txt; grep "REG_RC=" /dev/shm/s24480r/reg_24481b.txt; echo "--- 红项 ---"; grep -E "^  \[BAD \]" /dev/shm/s24480r/reg_24481b.txt || echo "(无 BAD)"; echo -n "OK="; grep -c "^  \[OK \]" /dev/shm/s24480r/reg_24481b.txt; echo -n "SKIP="; grep -c "^  \[SKIP\]" /dev/shm/s24480r/reg_24481b.txt'

scp -q zju-12:/dev/shm/s24480r/reg_24481b.txt "$EV/reg_24481b.txt" || { echo "⛔ 取回 R2 收据失败"; exit 2; }
echo "=== R2 收据已取回 ==="
md5 -q "$EV/reg_24481b.txt"
echo "DONE_R2"
