#!/bin/bash
# 修订 240 真机跑：让 `dose_source` **第一次**落进 smoke 批次的产物。
#
# ⚠⚠⚠ 为什么必须是 smoke 批次（这是本脚本存在的唯一理由）：
#   修订 240 查出 `r6_rerun.py` 的 **smoke 落盘路径不记 `dose_source`**，
#   而**口径差跑批全部是 smoke 批次** ⇒ 16 个历史载荷该字段全为 None
#   ⇒ `r220_scope_delta.py` 的三态守卫把它们全判成 `unknown`（拒绝归因）。
# ⚖⇒ 唯一能把「r220_smoke.sh 传了 --w-meta ⇒ 应该是 w_meta」这个
# ⚖   **从脚本推断**变成**产物读数**的办法，就是真跑一批。
#
# ⛔ 一次对照只改一个变量：两路**只有 `--inject-scope` 不同**
#    （w 向量、meta、npz、labels、轨迹数全部相同）。
#
# ⚠⚠⚠ **调用的是 `r6_rerun_r240.py`，⛔ 不是 `r6_rerun.py`。**
# ⚖⚗ 第一版这里写的是 `$B/r6_rerun.py` —— 远端**早就存在**一份旧版
# ⚖ （581 行、没有 `--inject-scope` / `--smoke-traj`），
# ⚖⚠ 两路 3 秒内 rc=2 全挂在 argparse 上。
# ⚖ ⚗ 教训：**推了新文件 ≠ 跑的是新文件**，⛔ 必须点名到具体文件名。
set -u
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
B=/home/zhourui/steer3d_bpath
# ⚠⚠ 空卡在 2026-10-17 10:45 从 GPU 1 换成了 GPU 0，⛔ 不要沿用旧 UUID。
export CUDA_VISIBLE_DEVICES=GPU-fae7a2e0-ea2a-fd9b-b776-63399a0d7401
C="--npz-dir $B/gen_b2_max32768/aime --sidecar-dir $B/gen_b2_max32768/aime --labels $B/r182_1015_003713_label.json --w /tmp/w_p2a.npy --w-meta /tmp/w_p2a.npy.json --smoke --smoke-traj 10"
LOG=$B/r240_smoke.log
ST=$B/r240_status.txt
: > "$LOG"; : > "$ST"
run() {
  nm=$1; shift
  echo "=== BEGIN $nm  $(date +%T)" >> "$LOG"
  $PY "$@" >> "$LOG" 2>&1
  rc=$?
  echo "$nm rc=$rc" >> "$ST"
  echo "=== END   $nm  $(date +%T)  rc=$rc" >> "$LOG"
}
run single $B/r6_rerun_r240.py $C --inject-scope single --out /tmp/r240_single.json
run all    $B/r6_rerun_r240.py $C --inject-scope all    --out /tmp/r240_all.json
echo "ALLDONE $(date +%T)" >> "$ST"
