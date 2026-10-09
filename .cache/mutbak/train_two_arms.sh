#!/bin/sh
# 两臂训练：修好层（NPZ_LAYER = LAYER-1 = 19）后，只差 token 位置。
# 臂 A pos_offset=-1 -> H[t-1]（注入点，修订 7 的推理）
# 臂 B pos_offset= 0 -> H[t]  （marker 自身，修订 10 §10.2 的实测）
# 选择规则见预登记修订 10 §10.4，用 w·U[marker] 相对随机基线的倍数，
# **不用 P9 的绿红来选**。
set -e
B=/home/zhourui/steer3d_bpath
P=/home/zhourui/miniconda3/envs/easysteer/bin/python
D=$B/gen_b2/aime
export CUDA_VISIBLE_DEVICES=GPU-2f39bcda-a2b4-0090-ef0a-cbee082cac9e

cd $B
rm -f train_L19.done

for OFF in -1 0; do
  TAG=$([ "$OFF" = "-1" ] && echo m1 || echo m0)
  echo "=== 臂 $TAG  pos_offset=$OFF ==="
  $P -u r6_rerun.py \
     --npz-dir $D --sidecar-dir $D \
     --labels $B/labels_full60.json \
     --out $B/r6_L19_${TAG}_rows.json \
     --pos-offset $OFF \
     --train-only \
     --w-out $B/w_L19_${TAG}.npy
done

echo ALLDONE > train_L19.done
echo "两臂训练完成"
