#!/bin/bash
# 修订 244.8 —— 242 的 274 格（137 x {w, rand}）串行双臂启动器。
#
# 为什么串行而不是两臂各占一张卡：发批那一刻只有 GPU 0 满足 <3 GB 且 util<5%。
# ⚖ 两臂**必须**在同一批机器条件上跑，这一点反而比并发更好 ——
# ⚖   历史形态是「rand 是过去某一轮的产物、w 是今天跑的」（限定 3），
# ⚖   本次把 rand 拉到现在与 w 同批跑，**顺带解掉了那个时间混淆**。
#
# ⚖ 硬条件（逐条来自账本）：
#   ① 两臂之间**只差 --arm**（用同一个脚本 + ARM 参数，⛔ 不复制第二份脚本）
#   ② BEGIN 行带 n_eff=，来源是跑批前独立算出的映射表（⛔ 不回填读数）
#   ③ 格数闸 137，映射表闸 非空，两闸任一不过 ⇒ exit 9 且不产出半份
#   ④ GPU UUID 由调用者在启动那一刻传入，本脚本不猜、不探测
set -u
B=/home/zhourui/steer3d_bpath
UUID=${1:?用法: run274.sh <GPU-UUID>}
CELLS=$B/warm_cells.txt
NMAP=$B/n_eff_map.tsv
LAUNCH=$B/r244_run274_launch.log

if [ ! -s "$CELLS" ]; then
  echo "PRECOND_FAIL 格清单缺失: $CELLS" | tee -a "$LAUNCH"
  exit 2
fi
if [ ! -s "$NMAP" ]; then
  echo "PRECOND_FAIL n_eff 映射表缺失: $NMAP" | tee -a "$LAUNCH"
  exit 2
fi

echo "LAUNCH start uuid=$UUID cells=$(grep -c . "$CELLS") nmap_md5=$(md5sum "$NMAP" | cut -d' ' -f1)  $(date +%T)" >> "$LAUNCH"

# ---- 臂 1: w ----
bash "$B/r244_warm_sweep.sh" "$UUID" "$CELLS" "$NMAP" 137 _w w
RC_W=$?
echo "ARM_W_DONE rc=$RC_W  $(date +%T)" >> "$LAUNCH"
if [ "$RC_W" -ne 0 ]; then
  # ⛔ 臂 1 非零 ⇒ **不发臂 2**。两臂只差 --arm，一臂残了就无法比较，
  # ⚖   跑完 274 格再发现没法配对，比只跑 137 格更浪费。
  echo "HALT 臂 w 非零（rc=$RC_W），不发 rand 臂" >> "$LAUNCH"
  exit "$RC_W"
fi

# ---- 臂 2: rand ----
bash "$B/r244_warm_sweep.sh" "$UUID" "$CELLS" "$NMAP" 137 _rand rand
RC_R=$?
echo "ARM_RAND_DONE rc=$RC_R  $(date +%T)" >> "$LAUNCH"
echo "ALLDONE274 $(date +%T)" >> "$LAUNCH"
exit "$RC_R"
