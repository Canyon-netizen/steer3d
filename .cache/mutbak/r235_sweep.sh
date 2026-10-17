#!/bin/bash
# 修订 235：**给新问题补 3/4 与 7/8 两档** —— 消掉「尾段没法分步」。
#
# ⚖⚖⚖ **事前声明（重要，跑之前写死）**：
#   `jitter`（相邻档差的 **max**）是**极值**统计量，⚖ **档数越多它只会越大**。
#   ⚖ 本笔给 10 条新轨迹**各加 2 档** ⇒ ⚠ **它们的 max 地板会上升**
#   ⚖ ⇒ ⚠⚠ **max 尺对这些曲线的判决只会更偏「噪声主导」，不可能变少**。
#   ⚖ 这是**修正**（极值统计量本就该随步数增长，⛔ 不增长才是伪影），
#   ⚖ 但 ⚗ **正因为它会让结论往一个方向动，才必须先写下来** ——
#   ⚖⛔ 事后补一句「我提前知道会这样」不算数。
#   ⚖ `drift_khi_all` **不会变**（k_hi 是 ≤50% 的那一档，⛔ 不受本笔影响）。
#
# ⚖ 为什么要补：
#   实测 117 格后，14 条曲线里**只有 4 条**（旧的 p00/p03）尾段有 3–4 点，
#   ⚖ 新问题普遍只有 2 点，其中 **3 条只有 1 个点** ⇒ 读数器报
#   ⚖ 「⛔ 尾段只有 1 个点，没法分步」。
#   ⚖ 根因：三条曲线的 n_eff 为**奇数**，⚖ `n_eff/2` 整除后落在尾段判据之外
#   ⚖ （`p02__think` n_eff=4161、k=2080 ⇒ `2×2080=4160 >= 4161` **不成立**）。
#   ⚖⇒ 补 3/4 与 7/8 让尾段变成 3–4 点，与旧问题可比。
#
# ⚖ **顺带**把阶梯档数跨度从 **5–9 收到 7–9**（⛔ 仍非均匀：修订 232 给
# ⚖ `p03__think` 多补的 k=1 使它是 9 档，⛔ 数据不能删 ⇒ 不追求完全一致）。
#
# ⚖ 阶梯位置：`n_eff*3//4` 与 `n_eff*7//8`（整数除法，与修订 232 同口径）。
# ⚖ ⚠ 已逐条查过：**20 个 k 与已有档无一重复**。
#
# ⚖ 一次对照只改一个变量：探针、剂量、pos_frac、臂、GPU 与前几轮**逐项相同**，
# ⚖ ⛔ **唯一变的是「测哪些格」**。⛔ 不许调剂量 / pos_offset / 注入层（修订 222）。
set -u
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
B=/home/zhourui/steer3d_bpath
C="--cell --npz-dir $B/gen_b2_max32768/aime --sidecar-dir $B/gen_b2_max32768/aime --labels $B/r182_1015_003713_label.json --w /tmp/w_p2a.npy --gap 113.47440338134766 --pos-frac 0.5 --n-steps 60 --alpha-max 120 --band 60 --gpu-uuid 2828f5ba-f9ea-5e83-d270-4cb229dce027 --arm rand --inject-nested"
LOG=$B/r227_sweep.log          # ⚖ 追加进**同一个**日志
ST=$B/r227_status.txt          # ⚖ 追加进**同一个**状态文件
: >> "$LOG"; : >> "$ST"

# ⚖ 补档表：`问题:think_n_eff:think补的k…:no_think_n_eff:no_think补的k…`
# ⚖ n_eff 取自上一轮真读数（读数器自报 P+t，已与 BEGIN 互证），
# ⚖ 补的 k = n_eff*3//4 与 n_eff*7//8，⚠ 逐条查过与已有档**无一重复**。
SPECS="
aime__aime25__p02:4161:3120,3640:758:568,663
aime__aime25__p05:1878:1408,1643:385:288,336
aime__aime25__p07:3200:2400,2800:2210:1657,1933
aime__aime25__p18:5320:3990,4655:1156:867,1011
aime__aime25__p24:3956:2967,3461:617:462,539
"

# ⚖⚠ 变量名必须互不相同（修订 234 第一版踩过：7 个变量名接 6 段，
# ⚖ 第二个 `_` 把 NNEFF 顶成了 k 串，⚖ bash 只会安静地量错东西）。
for SPEC in $SPECS; do
  PROB=${SPEC%%:*}
  IFS=':' read -r _p TNEFF TK NNEFF NK <<< "$SPEC"
  if [ "$_p" != "$PROB" ]; then echo "⛔ SPEC 解析错位：$SPEC" >&2; exit 9; fi
  echo "== $PROB  think n_eff=$TNEFF k=[$TK]   no_think n_eff=$NNEFF k=[$NK]"
  for K in ${TK//,/ }; do
    echo "### BEGIN ${PROB}__think n_eff=$TNEFF  $(date +%T)" >> "$LOG"
    $PY $B/r226_probe.py $C --tid "${PROB}__think" --inject-scope k --inject-n-sites "$K" >> "$LOG" 2>&1
    echo "${PROB}__think k=$K rc=$?" >> "$ST"
  done
  for K in ${NK//,/ }; do
    echo "### BEGIN ${PROB}__no_think n_eff=$NNEFF  $(date +%T)" >> "$LOG"
    $PY $B/r226_probe.py $C --tid "${PROB}__no_think" --inject-scope k --inject-n-sites "$K" >> "$LOG" 2>&1
    echo "${PROB}__no_think k=$K rc=$?" >> "$ST"
  done
done
echo "ALLDONE $(date +%T)" >> "$ST"
