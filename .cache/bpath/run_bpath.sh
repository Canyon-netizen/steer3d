#!/bin/bash
# B 路正式生成：远端 zju-53，只读调用仓库自带脚本，产物写到树外的新目录。
#
# 三条硬规矩（都是踩过的坑）：
#  1. PYTHONDONTWRITEBYTECODE=1 —— 不许在远端工作树里生成 __pycache__
#  2. 跑远端仓库里那份脚本本体（md5 已验与本地一致），不拷贝、不改远端
#  3. 日志名带批次标识；改参数重跑必须换新日志名（nohup 进程不随后台任务死）
#
# 用法: bash run_bpath.sh <max_new_tokens> <batch_tag> <device_cvd>
set -u
MAXNEW="${1:-8192}"
TAG="${2:-b1}"
DEV="${3:-cuda:2}"

ROOT=/home/zhourui/steer3d_bpath
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
COLLECT=/home/zhourui/steer3d/backend/examples/collect_qwen3_aime.py
MODEL=/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master

LOG="$ROOT/gen_${TAG}_max${MAXNEW}_${DEV//:/}.log"
OUT="$ROOT/gen_${TAG}"

echo "[run_bpath] MAXNEW=$MAXNEW TAG=$TAG DEV=$DEV"
echo "[run_bpath] LOG=$LOG"
echo "[run_bpath] OUT=$OUT/aime/"

# 启动前重新查一次卡（快照余量不是可用余量，但模型只要 3.4G，够用即可）
nvidia-smi --query-gpu=index,uuid,memory.used,memory.total,utilization.gpu \
  --format=csv,noheader | sed 's/^/[gpu] /'

mkdir -p "$OUT"
cd "$ROOT"
PYTHONDONTWRITEBYTECODE=1 nohup "$PY" "$COLLECT" \
  --model-path "$MODEL" \
  --device "$DEV" \
  --dtype bfloat16 \
  --max-new-tokens "$MAXNEW" \
  --max-context 16384 \
  --jsonl "$ROOT/problems_bpath60.jsonl" \
  --out-dir "$OUT" \
  --dataset aime \
  --store-dtype float16 \
  --seed 42 \
  > "$LOG" 2>&1 &

echo "[run_bpath] pid=$!"
echo "[run_bpath] 跟踪: ssh zju-53 'tr \"\\r\" \"\\n\" < $LOG | grep -v Loading | tail -20'"