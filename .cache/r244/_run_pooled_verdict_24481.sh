#!/bin/bash
# =============================================================================
# _run_pooled_verdict_24481.sh —— **固定剂量「合池判决层」的判决流水线**（244.81）
#
# ⚖ 数据流（每一跳都有真源，⛔ 读数器一个字都不改）：
#   bpath 的跑批日志（一趟，3 个 pos_frac 混着）
#     └─ 拆分器 `fixed_dose_split_log.py`（按 pos_frac 拆三份）
#          └─ 权威读数器 `r227_kcurve.py`（由分析器内部调用）
#               └─ `fixed_dose_pooled_verdict_audit.py`（合池 ⇒ 判决面板）
#
# ⛔ 硬约束：
#   · 解释器一律 easysteer（⛔ 不用裸 python3）
#   · **只读** bpath；所有中间产物写 /dev/shm（⛔ 不写 NFS、⛔ 不改 bpath）
#   · ⛔ 零 GPU、⛔ 不跑批、⛔ 不 kill 任何进程、⛔ 不改任何预登记/读数器/探针
#   · ⚖ 收据必须记：被检字节的 md5 ＋ 批次进度 ＋ 面板全文
# =============================================================================
set -uo pipefail

PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
DEV=/home/zhourui/steer3d/.cache/r244
XC=/home/zhourui/steer3d/.cache/xcheck
BP=/home/zhourui/steer3d_bpath
OUT=${OUT:-/dev/shm/_pooled_24481}
WORK=$OUT/work
PANEL=$OUT/verdict_panel.txt
RECEIPT=$OUT/receipt.txt

mkdir -p "$OUT" "$WORK"

echo "=============================================================="
echo "244.81 合池判决流水线 ｜ $(date -Is) ｜ host=$(hostname)"
echo "=============================================================="
"$PY" -V || { echo "PRECOND_FAIL: 解释器跑不起来"; exit 2; }

# ---- 被检字节（收据里必须逐位对上）
{
echo "=== 字节 ==="
md5sum "$DEV/fixed_dose_pooled_verdict_audit.py" \
       "$DEV/fixed_dose_split_log.py" \
       "$DEV/mut_fixed_dose_pooled_verdict_audit.py" \
       "$XC/R6_FIXED_DOSE_POOLED_VERDICT_PREREG.md" \
       "$XC/R6_FIXED_DOSE_VARIANT_PREREG.md" \
       "$DEV/_k23_reader_r227_kcurve.py" \
       "$BP/warm_cells_fixed_dose.tsv" 2>&1
echo "=== 批次输入 ==="
ls -la "$BP"/r244_warm_fd_*.log "$BP"/r244_warm_fd_*_status.txt 2>&1
} > "$RECEIPT"

# ---- ① 跑批进度（⛔ 从收据算，⛔ 不手估）
{
echo ""
echo "=== 跑批进度 ==="
bash "$DEV/_batch_progress_24479.sh" 2>&1
echo ""
} >> "$RECEIPT"

# ---- ② 前置闸：两臂必须**跑满**（⛔ 半批数据不许进判决）
#     ⚖ 判据：日志里的 `### END` 数 == 状态文件的行数 == 清单行数（168）
EXPECT=168
pre_fail=0
for arm in w rand; do
  LOG=$BP/r244_warm_fd_${arm}.log
  ST=$BP/r244_warm_fd_${arm}_status.txt
  # ⚠ `grep -c` 计数为 0 时退出码是 1 ⇒ ⛔ 别写 `|| echo 0`（会多打一个 0 ⇒ 变成两行）
  n_end=$(grep -c "^### END" "$LOG" 2>/dev/null || true)
  n_body=$(grep -c -v "^ALLDONE" "$ST" 2>/dev/null || true)
  n_alldone=$(grep -c "^ALLDONE" "$ST" 2>/dev/null || true)
  if [ "$n_end" != "$EXPECT" ] || [ "$n_body" != "$EXPECT" ] || [ "$n_alldone" != "1" ]; then
    echo "⛔ 臂 $arm 没跑满：### END=$n_end ｜ status 行=$n_body ｜ ALLDONE=${n_alldone}（期望各 ${EXPECT} / ${EXPECT} / 1）"
    pre_fail=1
  else
    echo "OK   臂 $arm 跑满：### END=$n_end ｜ status 行=$n_body ｜ ALLDONE=$n_alldone"
  fi
done
if [ "$pre_fail" != "0" ]; then
  echo "⛔ **前置不过 ⇒ 不出判决**（⛔ 半批数据长得像判决 ⇒ 这里必须拦住）"
  exit 9
fi

# ---- ③ 两臂各拆三份（⛔ 输出只写 /dev/shm）
for arm in w rand; do
  echo ""
  echo "=== 拆分 $arm 臂 ==="
  "$PY" "$DEV/fixed_dose_split_log.py" \
      --log "$BP/r244_warm_fd_${arm}.log" \
      --status "$BP/r244_warm_fd_${arm}_status.txt" \
      --cells "$BP/warm_cells_fixed_dose.tsv" \
      --nmap-prefix "$BP/n_eff_map" \
      --outdir "$WORK/$arm" 2>&1 | tee "$OUT/split_${arm}.out"
  echo "SPLIT_${arm}_RC=${PIPESTATUS[0]}"
done

# ---- ④ 合池分析器（⛔ 面板只写到 /dev/shm）
echo ""
echo "=== 合池分析器 ==="
ARMS=$(cat <<JSON
{"w":[{"log":"$WORK/w/pf025.log","status":"$WORK/w/pf025_status.txt"},
      {"log":"$WORK/w/pf050.log","status":"$WORK/w/pf050_status.txt"},
      {"log":"$WORK/w/pf075.log","status":"$WORK/w/pf075_status.txt"}],
 "rand":[{"log":"$WORK/rand/pf025.log","status":"$WORK/rand/pf025_status.txt"},
      {"log":"$WORK/rand/pf050.log","status":"$WORK/rand/pf050_status.txt"},
      {"log":"$WORK/rand/pf075.log","status":"$WORK/rand/pf075_status.txt"}]}
JSON
)
"$PY" "$DEV/fixed_dose_pooled_verdict_audit.py" --arms "$ARMS" --out "$PANEL" 2>&1 | tee "$OUT/audit.out"
echo "AUDIT_RC=${PIPESTATUS[0]}"

{
echo ""
echo "=== 面板全文 ==="
cat "$PANEL" 2>/dev/null
echo ""
echo "=== done ==="
} >> "$RECEIPT"
cp "$OUT/audit.out" "$OUT/audit_stdout.txt" 2>/dev/null
echo ""
echo "收据：$RECEIPT"
echo "面板：$PANEL"
