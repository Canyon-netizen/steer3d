#!/bin/bash
# B 路生成后的回填与回传。
#
# 为什么要回填：采集脚本存出来的 npz 只有 6 个键
#   hidden_states / last_hidden / token_ids / attention_mask / topk_logits / topk_indices
# 而干预分析（R-1 的位置定位）依赖的 prompt_hidden_states / prompt_last_hidden /
# prompt_token_ids 在**另一个数组**里 —— 现有 48 条是靠 backfill_prompt_hidden.py
# 事后补上的（sidecar 里 extra.prompt_backfilled = true，schema_version 1.1）。
# 不补 => 新数据坐标系和旧数据对不上，下游全部失效。
#
# 落盘 dtype 由脚本自动跟随轨迹侧车里的 stored_dtype（本次生成用了 float16）。
# 脚本没有 --store-dtype 参数，不要传。
#
# 回填脚本内部硬编码 CUDA_DEVICE_ORDER=PCI_BUS_ID + CUDA_VISIBLE_DEVICES=7
# （= CVD 7 = nvidia-smi index 3），且无条件覆盖环境变量 ⇒ 不改脚本，按它设计跑。
# --verify 是内建的对齐闸门：重跑前向并比对 gen 位置末层残差与已存的 last_hidden，
# 差异 > 5e-2 就拒写。这一步必须开。
set -u
ROOT=/home/zhourui/steer3d_bpath
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
BF=/home/zhourui/steer3d/backend/examples/backfill_prompt_hidden.py
MODEL=/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master
GEN="${1:?用法: bash backfill_and_pull.sh <gen_tag>  例如 gen_b1}"

echo "[bf] 阶段 1：小样本验证 --verify --limit 2（对齐闸门）"
PYTHONDONTWRITEBYTECODE=1 "$PY" "$BF" \
  --root "$ROOT/$GEN/aime" \
  --model-path "$MODEL" \
  --dtype bfloat16 \
  --verify --limit 2 2>&1 | tail -25

echo
echo "[bf] 阶段 2：全量回填（带 --verify）"
PYTHONDONTWRITEBYTECODE=1 nohup "$PY" "$BF" \
  --root "$ROOT/$GEN/aime" \
  --model-path "$MODEL" \
  --dtype bfloat16 \
  --verify \
  > "$ROOT/backfill_${GEN}.log" 2>&1 &
echo "[bf] pid=$!  log=$ROOT/backfill_${GEN}.log"
echo "[bf] 跟踪: ssh zju-53 'tail -5 $ROOT/backfill_${GEN}.log'"