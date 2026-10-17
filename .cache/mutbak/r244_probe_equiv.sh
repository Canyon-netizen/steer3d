#!/bin/bash
# 修订 244 的 Phase-0：验**新旧探针在显式传参下读数逐位一致**。
#
# ⚠⚠⚠ 为什么必须先验这一条：
#   `rand` 臂那 137 格是**旧探针** `r226_probe.py` 跑的（修订 232/234/235），
#   `w` 臂要用**新探针** `r241_probe.py`（修订 241 改了它的 `--inject-scope` 默认值）。
#   ⚖⇒ 不验这一条，`w` 与 `rand` 之间就**不止 `--arm` 一个变量**变了，
#   ⚖⚠ 那就不是「一次对照只改一个变量」，而是**两个**。
#   ⚗ 本脚本**不验**就不能发 w 臂跑批。
#
# ⚠⚠⚠⚠ 三条硬要求（每一条都是被本轮的错误做法逼出来的）：
#   ① **先看 rc**：rc=2 是 argparse 错误，⛔ 那一刻产物是空的
#   ② **先断言非空**：两个**空文件**逐字节相同是**假绿**
#      （本轮第一版就栽在这：`cmp -s` 比两个 0 B 文件返回成功）
#   ③ **用脚本文件，不用内联**：本轮第三版内联写 `$C` 在远端没展开，
#      报的是「required arguments are missing」
set -u
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
B=/home/zhourui/steer3d_bpath
GPU_UUID=${1:?用法: r244_probe_equiv.sh <GPU-UUID>}
export CUDA_VISIBLE_DEVICES=GPU-$GPU_UUID
LOG=$B/r244_equiv.log
ST=$B/r244_equiv_status.txt
: > "$LOG"; : > "$ST"
echo "PINNED GPU=$GPU_UUID  $(date +%T)" >> "$ST"

C="--cell --npz-dir $B/gen_b2_max32768/aime --sidecar-dir $B/gen_b2_max32768/aime --labels $B/r182_1015_003713_label.json --w /tmp/w_p2a.npy --gap 113.47440338134766 --pos-frac 0.5 --n-steps 60 --alpha-max 120 --band 60 --gpu-uuid $GPU_UUID --arm w --inject-nested"

TID=aime__aime25__p00__think
# ⚖ 一次对照只改一个变量：**唯一差别是探针文件名**，
# ⚖ 其余（tid / scope k / n-sites / arm / 全部扫描参数）逐字相同。
echo "=== BEGIN old  $(date +%T)" >> "$LOG"
$PY $B/r226_probe.py $C --tid "$TID" --inject-scope k --inject-n-sites 1 --dump-raw /tmp/eqvA >> "$LOG" 2>&1
rc_old=$?
echo "old rc=$rc_old" >> "$ST"
echo "=== END   old  $(date +%T)  rc=$rc_old" >> "$LOG"

echo "=== BEGIN new  $(date +%T)" >> "$LOG"
$PY $B/r241_probe.py $C --tid "$TID" --inject-scope k --inject-n-sites 1 --dump-raw /tmp/eqvB >> "$LOG" 2>&1
rc_new=$?
echo "new rc=$rc_new" >> "$ST"
echo "=== END   new  $(date +%T)  rc=$rc_new" >> "$LOG"

# ⚖⚠ **两条闸**：rc 必须是 0，且产物**非空**。
# ⚖⚗ 少了第 2 条，本轮第一版就是拿两个空文件宣布「逐字节相同」。
echo "old_files=$(find /tmp/eqvA -type f 2>/dev/null | wc -l) new_files=$(find /tmp/eqvB -type f 2>/dev/null | wc -l)" >> "$ST"
diff -r /tmp/eqvA /tmp/eqvB > /tmp/eqv_diff.txt 2>&1
echo "diff_rc=$?  diff_bytes=$(wc -c < /tmp/eqv_diff.txt)" >> "$ST"
echo "ALLDONE $(date +%T)" >> "$ST"
