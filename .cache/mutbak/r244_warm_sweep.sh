#!/bin/bash
# 修订 244：`w` 臂跑批（141→137 格）。⚖ 与 rand 臂之间**只差 `--arm`**。
#
# ⚠⚠⚠ 发这批之前必须先过的 Phase-0（已过，见账本 §244.1）：
#   新探针 `r241_probe.py` 与旧探针 `r226_probe.py` 在**显式传 --inject-scope** 时
#   读数**逐字节相同**（diff_bytes=0）。
#   ⚖⇒ 不验这条，w 与 rand 之间就不止一个变量变了。
#   ⚖ ⚗ 本轮第一版没验就差点发，且两次栽在「假绿」上（见 §244.2）。
#
# ⚠⚠⚠ 三条纪律（每条都是本轮用教训换来的）：
#   ① **格清单从文件读**（由 r227_status.txt 机器解析生成，137 行），
#      ⛔ 不手打 —— 修订 232 的纪律：绝不手工拼接。
#   ② **新日志**：r244_warm.log / r244_warm_status.txt，⛔ 不追加进 r227_*。
#   ③ **脚本文件 + GPU UUID 作启动参数**：远端跑批一律不内联
#      （本轮第三版内联 $C 在远端没展开，报「required arguments are missing」）。
set -u
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
B=/home/zhourui/steer3d_bpath
GPU_UUID=${1:?用法: r244_warm_sweep.sh <GPU-UUID>}
CELLS=${2:-$B/warm_cells.txt}
export CUDA_VISIBLE_DEVICES=GPU-$GPU_UUID
LOG=$B/r244_warm.log
ST=$B/r244_warm_status.txt
: > "$LOG"; : > "$ST"
# ⚠⚠⚠ 修订 244.1：**状态文件的契约是「每格一行 + ALLDONE」**。
# ⚖ `r227_kcurve.parse_status` 遇到读不出 rc 的行会 **HardFail**，
# ⚖ 而那道守卫是**对的** ⇒ ⛔ **不许为了让它绿而去放宽读数器**，
# ⚖ ⚗ 那是「事后把红改成绿」。⇒ 改**生产者**。
# ⚖ 第一版我在 $ST 里写了 `PINNED GPU=…` 头行 ⇒ 读数器当场 HardFail。
# ⚖⇒ PINNED / ABORT / 一切非格行，**只许进 $LOG**。
echo "PINNED GPU=$GPU_UUID  CELLS=$CELLS  $(date +%T)" >> "$LOG"

# ⛔ 格数闸：清单不是 137 行 ⇒ 中止，别跑半份。
N=$(grep -c . "$CELLS" 2>/dev/null || echo 0)
if [ "$N" -ne 137 ]; then
  echo "ABORT 格数=$N ≠ 137（清单可能没传对）" >> "$LOG"
  echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
  echo "ALLDONE $(date +%T)" >> "$ST"
  exit 9
fi

# ⚖⚠ 扫描参数与 rand 臂**逐字相同**（修订 238 的 K23 会查一致性）。
# ⚖ 唯一改动：--arm rand → --arm w。
C="--cell --npz-dir $B/gen_b2_max32768/aime --sidecar-dir $B/gen_b2_max32768/aime --labels $B/r182_1015_003713_label.json --w /tmp/w_p2a.npy --gap 113.47440338134766 --pos-frac 0.5 --n-steps 60 --alpha-max 120 --band 60 --gpu-uuid $GPU_UUID --arm w --inject-nested"

i=0
while IFS=$'\t' read -r TID KIND VAL; do
  [ -n "$TID" ] || continue
  i=$((i+1))
  if [ "$KIND" = "k" ]; then
    SCOPE_ARGS="--inject-scope k --inject-n-sites $VAL"
  else
    SCOPE_ARGS="--inject-scope $VAL"
  fi
  # ⚠⚠⚠ 修订 244.1 修复：**tid 必须是 `### BEGIN` 后的第一个 token**。
  # ⚖ `r227_kcurve.BEGIN_RE` 契约是
  #     ^###\s+BEGIN\s+(?P<tid>\S+)(?P<rest>.*?)\s\s+(?P<time>\d\d:\d\d:\d\d)\s*$
  # ⚖ 第一版把 `[i/n]` 印在 tid **之前** ⇒ 读数器把 `[1/137]` 当 tid，
  # ⚖    立刻 HardFail「第 1 格 tid 对不上」。
  # ⚖⇒ 序号移到 **rest 内**（读数器 `rest` 不解析它，无害），
  # ⚖   同时保留「第几格」的可见性。END 行同理，读数器不解析 END。
  # ⚖⚗ 本脚本已产出过 2026-10-17 那份日志（用了旧的错写法）；
  # ⚖  本次只改**未来**跑批的写法，⛔ 不去改已落盘的产物
  #    （改产物会让「脚本说的」与「产物是的」不一致）。
  echo "### BEGIN $TID [$i/137] $SCOPE_ARGS  $(date +%T)" >> "$LOG"
  $PY $B/r241_probe.py $C --tid "$TID" $SCOPE_ARGS >> "$LOG" 2>&1
  rc=$?
  # ⚖ 状态行与 r227_status.txt 同形，便于读数器对账
  if [ "$KIND" = "k" ]; then
    echo "$TID k=$VAL rc=$rc" >> "$ST"
  else
    echo "$TID scope=$VAL rc=$rc" >> "$ST"
  fi
  echo "### END   [$i/137] $TID rc=$rc  $(date +%T)" >> "$LOG"
done < "$CELLS"
echo "SWEEPDONE cells=$i  $(date +%T)" >> "$LOG"
echo "ALLDONE $(date +%T)" >> "$ST"
