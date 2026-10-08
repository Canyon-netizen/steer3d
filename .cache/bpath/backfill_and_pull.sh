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
# --verify 现在是**真的会拦**的对齐闸门：把 gen 段按 R-1 的偏移（消费前）
# 对齐后再比，相对差 > 0.10 就拒写；旧版那套错位口径会读到 ~1.1 却照样写入。
set -u
ROOT=/home/zhourui/steer3d_bpath
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
MODEL=/home/zhourui/.cache/huggingface/models/Qwen--Qwen3-1.7B/snapshots/master
GEN="${1:?用法: bash backfill_and_pull.sh <gen_tag>  例如 gen_b2}"

# ⚠ 远端 /home/zhourui/steer3d 的 git 与本地完全分叉，那个工作树里有**别人未提交的
#   改动**，绝不能就地修改。远端自带的那份 backfill_prompt_hidden.py 是**未修复**的
#   （错位比对 + 闸门不拦），所以要用本地修好的版本，显式 scp 到 bf_fixed/。
#   被测对象必须与本地仓库那份一致，见 backfill_gate_teeth.py 的自检 0。
LOCAL_BF="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/backend/examples/backfill_prompt_hidden.py"
echo "[bf] 本地修好的版本: $LOCAL_BF"
ssh zju-53 "mkdir -p $ROOT/bf_fixed"
scp -q "$LOCAL_BF" "zju-53:$ROOT/bf_fixed/backfill_prompt_hidden.py"
BF="$ROOT/bf_fixed/backfill_prompt_hidden.py"

echo "[bf] 阶段 0：闸门牙齿自检（证明 --verify 会咬，不是只会打印）"
ssh zju-53 "cd $ROOT && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/zhourui/steer3d/backend $PY backfill_gate_teeth.py 2>&1 | grep -v 'Loading weights' | tail -8"

echo
echo "[bf] 阶段 1：小样本验证 --verify --limit 2"
PYTHONDONTWRITEBYTECODE=1 "$PY" "$BF" \
  --root "$ROOT/$GEN/aime" \
  --model-path "$MODEL" \
  --dtype bfloat16 \
  --verify --limit 2 2>&1 | tail -25

echo
echo "[bf] 阶段 2：全量回填（带对齐闸门）"
PYTHONDONTWRITEBYTECODE=1 nohup "$PY" "$BF" \
  --root "$ROOT/$GEN/aime" \
  --model-path "$MODEL" \
  --dtype bfloat16 \
  --verify \
  > "$ROOT/backfill_${GEN}.log" 2>&1 &
echo "[bf] pid=$!  log=$ROOT/backfill_${GEN}.log"
echo "[bf] 跟踪: ssh zju-53 'tail -5 $ROOT/backfill_${GEN}.log'"
echo "[bf] 完成标准: 摘要行 reject=0 且 ok 数 == 轨迹数；出现 reject 必须查原因再回填"