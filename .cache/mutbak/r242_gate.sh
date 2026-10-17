#!/bin/bash
# 修订 242 的 Phase-0 闸门：⛔ 验证**全量分支**（非 smoke）当前能跑通并落盘。
#
# ⚠⚠⚠ 为什么必须先过这一关：
#   `r6_rerun.py` 的**全量落盘路径从未在真实数据上跑过** ——
#   远端唯一那份带 rows 的全量产物（r6_dryrun_rows.json，10-09）
#   早于 --inject-scope（修订 219）与 dose_source（修订 239/240），
#   ⚖⚗ 所以「修订 240 补的那条路径在非 smoke 下到底通不通」**没人验过**。
#   ⛔ 直接发 274 格全量 ⇒ 第一个崩就白等几小时。
#
# ⛔ 闸门**不许事后放宽**。不过 ⇒ 不发全量。
set -u
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
B=/home/zhourui/steer3d_bpath
# ⚠⚠ 空卡在共享机器上**会漂**：10:45 是 GPU 0 空，10:55 变成 GPU 1 空。
# ⚖ ⇒ UUID **在启动时再钉一次**，⛔ 不写死在账本/脚本里当常量。
GPU_UUID=${1:?用法: r242_gate.sh <GPU-UUID>}
export CUDA_VISIBLE_DEVICES=GPU-$GPU_UUID
LOG=$B/r242_gate.log
ST=$B/r242_gate_status.txt
: > "$LOG"; : > "$ST"
echo "PINNED GPU=$GPU_UUID  $(date +%T)" >> "$ST"
echo "PINNED GPU=$GPU_UUID" >> "$LOG"

run() {
  nm=$1; shift
  echo "=== BEGIN $nm  $(date +%T)" >> "$LOG"
  $PY "$@" >> "$LOG" 2>&1
  rc=$?
  echo "$nm rc=$rc" >> "$ST"
  echo "=== END   $nm  $(date +%T)  rc=$rc" >> "$LOG"
}

# ⚖ 走**全量**分支（⛔ 不带 --smoke），⛔ 只放 3 条轨迹把规模压到最小。
# ⚖ 口径 = single（P6 主口径，修订 228）。
run gate3 $B/r6_rerun_r240.py --npz-dir $B/gen_b2_max32768/aime --sidecar-dir $B/gen_b2_max32768/aime --labels $B/r182_1015_003713_label.json --w /tmp/w_p2a.npy --w-meta /tmp/w_p2a.npy.json --limit-traj 3 --inject-scope single --out /tmp/r242_gate.json
echo "ALLDONE $(date +%T)" >> "$ST"
