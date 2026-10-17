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
GPU_UUID=${1:?用法: r244_warm_sweep.sh <GPU-UUID> <cells-file> <n-eff-map>}
CELLS=${2:-$B/warm_cells.txt}
NMAP=${3:-$B/n_eff_map.tsv}
# ⚖ 单一真源：--pos-frac 只从这里出。⚗ 之前它硬编码在 $C 里，而 n_eff 映射表
# ⚖   是用另一处的 0.5 生成的 —— 两处不一致时，t 会静默错且没有任何守卫会响。
POS_FRAC=0.5
# ⚖ 修订 244.8：格数闸与日志名参数化，**默认值不变**。
# ⚖⚗ 存在的唯一理由：新 BEGIN 格式（带 n_eff=）要先过 1 格端到端烟测，
# ⚖   而原来的硬编码 137 会让烟测当场 exit 9。默认值仍是 137，
# ⚖   且实际期望值与 TAG 都进 $LOG ⇒ 事后可核对当时按哪个闸跑的。
# ⚖ ⛔ 不接受「把闸放宽到能跑」这种用法：那是事后把红改成绿。
EXPECT_CELLS=${4:-137}
TAG=${5:-}
# ⚖ 修订 244.8：臂作为参数，⛔ 不另写一份 rand 版脚本。
# ⚖⚗ 242 的硬条件是「两臂之间只差 --arm」—— 复制脚本就会引入第二个可能漂的变量。
ARM=${6:-w}
LOG=$B/r244_warm${TAG}.log
ST=$B/r244_warm${TAG}_status.txt
export CUDA_VISIBLE_DEVICES=GPU-$GPU_UUID
: > "$LOG"; : > "$ST"
# ⚠⚠⚠ 修订 244.1：**状态文件的契约是「每格一行 + ALLDONE」**。
# ⚖ `r227_kcurve.parse_status` 遇到读不出 rc 的行会 **HardFail**，
# ⚖ 而那道守卫是**对的** ⇒ ⛔ **不许为了让它绿而去放宽读数器**，
# ⚖ ⚗ 那是「事后把红改成绿」。⇒ 改**生产者**。
# ⚖ 第一版我在 $ST 里写了 `PINNED GPU=…` 头行 ⇒ 读数器当场 HardFail。
# ⚖⇒ PINNED / ABORT / 一切非格行，**只许进 $LOG**。
echo "PINNED GPU=$GPU_UUID  CELLS=$CELLS  NMAP=$NMAP  POS_FRAC=$POS_FRAC  EXPECT_CELLS=$EXPECT_CELLS  TAG=${TAG:-none}  ARM=$ARM  $(date +%T)" >> "$LOG"

# ⚠⚠⚠ 修订 244.8：n_eff 映射表闸。⛔ 表不存在 / 为空 / pos_frac 不符 ⇒ 中止整批。
# ⚖ 理由：244.5 记录的缺陷是「BEGIN 无独立 n_eff ⇒ 读数器退回同源回退」。
# ⚖⚗ 本闸是那道死结的另一端：⛔ 不许「表没有就照跑」。
if [ ! -s "$NMAP" ]; then
  echo "ABORT n_eff 映射表缺失或为空：$NMAP" >> "$LOG"
  echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
  echo "ALLDONE $(date +%T)" >> "$ST"
  exit 9
fi
MAP_ROWS=$(($(wc -l < "$NMAP") - 1))
MAP_MD5=$(md5sum "$NMAP" | cut -d' ' -f1)
echo "NMAP rows=$MAP_ROWS md5=$MAP_MD5  $(date +%T)" >> "$LOG"

# ⛔ 格数闸：清单不是 137 行 ⇒ 中止，别跑半份。
N=$(grep -c . "$CELLS" 2>/dev/null || echo 0)
if [ "$N" -ne "$EXPECT_CELLS" ]; then
  echo "ABORT 格数=$N ≠ EXPECT_CELLS=$EXPECT_CELLS（清单可能没传对）" >> "$LOG"
  echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
  echo "ALLDONE $(date +%T)" >> "$ST"
  exit 9
fi

# ⚖⚠ 扫描参数与 rand 臂**逐字相同**（修订 238 的 K23 会查一致性）。
# ⚖ 唯一改动：--arm rand → --arm w。
C="--cell --npz-dir $B/gen_b2_max32768/aime --sidecar-dir $B/gen_b2_max32768/aime --labels $B/r182_1015_003713_label.json --w /tmp/w_p2a.npy --gap 113.47440338134766 --pos-frac $POS_FRAC --n-steps 60 --alpha-max 120 --band 60 --gpu-uuid $GPU_UUID --arm $ARM --inject-nested"

i=0
while IFS=$'\t' read -r TID KIND VAL; do
  [ -n "$TID" ] || continue
  i=$((i+1))
  if [ "$KIND" = "k" ]; then
    SCOPE_ARGS="--inject-scope k --inject-n-sites $VAL"
  else
    SCOPE_ARGS="--inject-scope $VAL"
  fi
  # ⚠⚠⚠ 修订 244.8：BEGIN 行现在带 `n_eff=`，来源是**跑批之前**独立算出的
  # ⚖   P = len(tokenizer(chat_template_input))  ← 重编码，不读侧车自报字段
  # ⚖   t = max(1, int(len(npz token_ids) * pos_frac))
  # ⚖⇒ 读数器 `b["n_eff"] != pt_sum`（r227_kcurve.py:214）**第一次变成可红的**：
  # ⚖   BEGIN 的独立值 vs 探针自报的 P+t，两者不一致就 HardFail。
  # ⚖ ⛔ 244.5 判 r232 那种「从上一轮读数回填」为恒绿守卫并明令不许用。
  # ⚖ ⚗ 若此处查不到 tid ⇒ **中止整批**，⛔ 绝不回退成「不写 n_eff=」——
  # ⚖    静默缺字段会让读数器退回同源回退路径，那正是 244.5 记录的缺陷。
  NEFF=$(awk -F'\t' -v t="$TID" '$1==t {print $6; found=1} END{if(!found) exit 1}' "$NMAP")
  if [ -z "$NEFF" ]; then
    echo "ABORT 第 $i 格 tid=$TID 不在 n_eff 映射表里 ⇒ 拒绝跑无独立来源的批" >> "$LOG"
    echo "ALLDONE $(date +%T) ABORTED" >> "$LOG"
    echo "ALLDONE $(date +%T)" >> "$ST"
    exit 9
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
  echo "### BEGIN $TID [$i/$EXPECT_CELLS] n_eff=$NEFF $SCOPE_ARGS  $(date +%T)" >> "$LOG"
  $PY $B/r241_probe.py $C --tid "$TID" $SCOPE_ARGS >> "$LOG" 2>&1
  rc=$?
  # ⚖ 状态行与 r227_status.txt 同形，便于读数器对账
  if [ "$KIND" = "k" ]; then
    echo "$TID k=$VAL rc=$rc" >> "$ST"
  else
    echo "$TID scope=$VAL rc=$rc" >> "$ST"
  fi
  echo "### END   [$i/$EXPECT_CELLS] $TID rc=$rc  $(date +%T)" >> "$LOG"
done < "$CELLS"
echo "SWEEPDONE cells=$i  $(date +%T)" >> "$LOG"
echo "ALLDONE $(date +%T)" >> "$ST"
