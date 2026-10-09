#!/bin/sh
# think 剂量扫描（臂 B）：执行预登记修订 11 §11.6 第 1 步 / §11.7。
#
# 剂量阶梯与 D1-D4 判据**一个字不改**，直接用 dose_sweep.py 里早已写死的那份
# （写于发现层错位之前，先于任何臂 B 结果存在）。
#
# 要回答：think 上 +w 是「小剂量也不升」（D2 方向问题），
#        还是「大剂量转负、小剂量其实正常」（D1 量纲问题）。
B=/home/zhourui/steer3d_bpath
P=/home/zhourui/miniconda3/envs/easysteer/bin/python
export CUDA_VISIBLE_DEVICES=GPU-2f39bcda-a2b4-0090-ef0a-cbee082cac9e

cd $B
rm -f dose_B.done

# 2 条 think（p00/p01）+ 2 条 no_think（p00/p01）作 D4 要求的正控
$P -u dose_sweep.py \
   --npz-dir $B/gen_b2/aime --sidecar-dir $B/gen_b2/aime \
   --w $B/w_L19_m0.npy --gap 231.978 --n-pos 2 \
   --tids aime__aime25__p00__think,aime__aime25__p01__think,aime__aime25__p00__no_think,aime__aime25__p01__no_think \
   --out $B/dose_sweep_B.json

echo ALLDONE > dose_B.done
echo "剂量扫描完成"