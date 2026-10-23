#!/bin/bash
# ⚖ R1 收尾 → 落账（只追加）→ 重建索引（一次性做完，⛔ 不碰同事的文件）
#
# ⚖⚖⚖ 纪律：
#   ① **只追加**：两个追加脚本各自带「围栏数不变 ＋ 旧前缀逐字节不变」的双重断言
#   ② **只带显式路径**：⛔ 不用 git add -A、⛔ 不加整个目录
#   ③ 顺序固定：先 244.80、后 244.81（账本只追加 ⇒ 顺序就是历史顺序）
set -u
cd /Users/zhourui/code/steer3d || exit 2
EV=.cache/r244/_e24481
REG=/dev/shm/s24480r/reg_24481.txt

# ---- 1) 等 R1 落 REG_RC（⛔ 不自己 kill 远端的进程）
for i in $(seq 1 900); do
  if ssh zju-12 "grep -q 'REG_RC=' $REG" 2>/dev/null; then break; fi
  sleep 20
done
ssh zju-12 "grep -q 'REG_RC=' $REG" 2>/dev/null || { echo "⛔ R1 还没落 REG_RC ⇒ 不落账"; exit 3; }

echo "=== R1 摘要 ==="
ssh zju-12 'grep -E "^n_exec_py=|^ledger_lines=|^manifest_md5=|^manifest_diff_rc=|^host=" /dev/shm/s24480r/reg_24481.txt; grep "小结：" /dev/shm/s24480r/reg_24481.txt; grep "REG_RC=" /dev/shm/s24480r/reg_24481.txt; echo "--- 红项 ---"; grep -E "^  \[BAD \]" /dev/shm/s24480r/reg_24481.txt || echo "(无 BAD)"; echo "--- OK/SKIP 计数 ---"; echo -n "OK="; grep -c "^  \[OK \]" /dev/shm/s24480r/reg_24481.txt; echo -n "SKIP="; grep -c "^  \[SKIP\]" /dev/shm/s24480r/reg_24481.txt'

# ---- 2) 取回收据
scp -q zju-12:/dev/shm/s24480r/reg_24481.txt "$EV/reg_24481.txt" || { echo "⛔ 取回收据失败"; exit 2; }
echo "=== 取回的收据 ==="
md5 -q "$EV/reg_24481.txt"
wc -l < "$EV/reg_24481.txt"

# ---- 3) 落账（先 244.80，后 244.81）
echo "=== 落账 244.80 ==="
python3 .cache/r244/_append_24480.py || { echo "⛔ 244.80 落账失败 ⇒ 停下"; exit 4; }
echo "=== 落账 244.81 ==="
python3 .cache/r244/_append_24481.py || { echo "⛔ 244.81 落账失败 ⇒ 停下"; exit 5; }

# ---- 4) 重建索引
echo "=== 重建索引 ==="
python3 .cache/mutbak/r100_build_index.py || { echo "⛔ 索引重建失败 ⇒ 停下"; exit 6; }

# ---- 5) 回读核对（围栏数 / 旧前缀 / 新增标题 / 索引命中）
echo "=== 回读核对 ==="
python3 .cache/r244/_verify_landing_24481.py
echo "DONE_24481_LANDING"
