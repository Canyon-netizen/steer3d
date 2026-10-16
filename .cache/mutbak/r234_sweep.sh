#!/bin/bash
# 修订 234：**加独立问题数**（修订 229 §229.8 ③ —— 修订 232 做完 ①②，剩这一条）。
#
# ⚖⚖ 为什么必须加**问题**而不是加轨迹：
#   `think` / `no_think` 同属**一个问题** ⇒ 符号检验的独立单位是问题。
#   全同向时精确双尾 p = 2/2^n ⇒ n=4 给 0.125、n=5 给 **0.0625（仍 > 0.05）**、
#   n=6 才给 0.03125。⚖⚠ 修订 229 §229.8 ③ 写的「n≥5 才可能到 0.05」**差一格**，
#   ⚖ 本笔按 **n≥6** 规划。
#
# ⚖⚖⚖ 纳入规则（**跑之前定死**，⛔ 不是跑完挑）：
#   「两条轨迹的 n_eff 都落在 [380, 6000] 的问题，**全部纳入**，不抽样。」
#   ⚖ 带的下界 380 覆盖旧的 p05__no_think(385)，上界 6000 覆盖旧的最大 3786。
#   ⚖ 为什么要有带：旧两问题的 n_eff 是 490–3786；⛔ 不设带地取「前 5 个」
#   会拉到 5960–16717（最长的一条差 4.4 倍）⇒ 长度成为混杂因子。
#   ⚖ 为什么是 380–6000 而不是更窄：⚠ **实测两条都在 [400,4000] 的只有 4 个问题，
#   ⚖ 其中 2 个已测** ⇒ 严格匹配只能再加 2 个（n=4，p=0.125，**不够**）。
#   ⚖ 6000 是「能一次纳入足够问题数的最窄上界」内可用的宽法。
#   ⚖ 结果：新纳入 **5 个**问题（p02/p05/p07/p18/p24），合计 **7 个问题** ⇒ n=7，
#   ⚖ 全同向时 p = 0.015625。
#
# ⚖ 阶梯必须与修订 229/232 **逐项同一套**：k = n_eff/{1024,256,64,16,4,2} 整除、丢 ≤0。
# ⚖ 验过：这套公式算出的旧四条 n_eff = 1762/490/3786/1141，⚖ **与账本逐个吻合**。
#
# ⚖⚠ `>>` 追加而不是重开：同一个日志里 40（已验）+ 76（新）= 116 格，
# ⚖ `### BEGIN` 与状态行**逐格 1:1 且同序** ⇒ 读数器五道交叉校验原样成立。
# ⚖⛔ 绝不手工拼接两份日志 —— 拼接正是「rc=1 把后续行错位一格」那种错的来源。
#
# ⚖⚠ 一次对照只改一个变量：探针、剂量、pos_frac、臂、GPU 与 r227/r232 逐项相同，
# ⚖ ⛔ **唯一变的是「测哪些格」**。
# ⚖ 探针 `r226_probe.py` 未改（md5 4afc93be…），⛔ 不许覆盖。
set -u
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
B=/home/zhourui/steer3d_bpath
C="--cell --npz-dir $B/gen_b2_max32768/aime --sidecar-dir $B/gen_b2_max32768/aime --labels $B/r182_1015_003713_label.json --w /tmp/w_p2a.npy --gap 113.47440338134766 --pos-frac 0.5 --n-steps 60 --alpha-max 120 --band 60 --gpu-uuid 2828f5ba-f9ea-5e83-d270-4cb229dce027 --arm rand --inject-nested"
LOG=$B/r227_sweep.log          # ⚖ 追加进**同一个**日志
ST=$B/r227_status.txt          # ⚖ 追加进**同一个**状态文件
: >> "$LOG"; : >> "$ST"

# ⚖ 每格都记 `n_eff`，读数器拿它与读数自报的 `P+t` 互证（第五道校验）。
# ⚖ 下面的 n_eff 由远端按 P=(extra).prompt_tokens、t=max(1,int(n_gen*0.5)) 算出，
# ⚖ ⛔ 不是「整条序列长度」（修订 226 踩过的坑）。
run_k() {   # $1=tid  $2=n_eff  $3=k
  echo "### BEGIN $1 n_eff=$2  $(date +%T)" >> "$LOG"
  $PY $B/r226_probe.py $C --tid "$1" --inject-scope k --inject-n-sites "$3" >> "$LOG" 2>&1
  echo "$1 k=$3 rc=$?" >> "$ST"
}

run_sc() {  # $1=tid  $2=n_eff  $3=all|single
  echo "### BEGIN $1 n_eff=$2 $3  $(date +%T)" >> "$LOG"
  if [ "$3" = "all" ]; then
    $PY $B/r226_probe.py $C --tid "$1" --inject-scope all >> "$LOG" 2>&1
  else
    $PY $B/r226_probe.py $C --tid "$1" --inject-scope single >> "$LOG" 2>&1
  fi
  echo "$1 $3 rc=$?" >> "$ST"
}

# ⚖⚖ 阶梯表：`问题:think_n_eff:think_k…:no_think_n_eff:no_think_k…`
# ⚖ n_eff 与 k 全部由远端脚本从数据算出后**抄进这里**，⛔ 不手填、不猜。
SPECS="
aime__aime25__p02:4161:4,16,65,260,1040,2080:758:2,11,47,189,379
aime__aime25__p05:1878:1,7,29,117,469,939:385:1,6,24,96,192
aime__aime25__p07:3200:3,12,50,200,800,1600:2210:2,8,34,138,552,1105
aime__aime25__p18:5320:5,20,83,332,1330,2660:1156:1,4,18,72,289,578
aime__aime25__p24:3956:3,15,61,247,989,1978:617:2,9,38,154,308
"

for SPEC in $SPECS; do
  PROB=${SPEC%%:*}
  # ⚖⚠ 用 IFS=':' 切 5 段：**变量名必须互不相同**。
  # ⚖   第一版写成 `_ TNEFF TK _ NNEFF NK`（7 个变量名接 6 段）⇒ 第二个 `_`
  # ⚖   把 NNEFF 顶成了 k 串，⛔ no_think 的 n_eff 会变成 "2,11,47,189,379"。
  # ⚖   ⛔ 这是 bash 特有的坑：不会报错，只会安静地量错东西。
  IFS=':' read -r _prob TNEFF TK NNEFF NK <<< "$SPEC"
  if [ "$_prob" != "$PROB" ]; then echo "⛔ SPEC 解析错位：$SPEC" >&2; exit 9; fi
  echo "== $PROB  think n_eff=$TNEFF k=[$TK]   no_think n_eff=$NNEFF k=[$NK]"
  for K in ${TK//,/ }; do run_k "${PROB}__think"  "$TNEFF" "$K"; done
  for K in ${NK//,/ }; do run_k "${PROB}__no_think" "$NNEFF" "$K"; done
  # ⚖ `all` 是 `k_hi→all` 的终点，`single` 是「位置身份」那一列的另一半
  # （修订 229 §229.3：single 与 k=1 位点身份不同）⇒ 两条轨迹都要补。
  run_sc "${PROB}__think"     "$TNEFF" all
  run_sc "${PROB}__think"     "$TNEFF" single
  run_sc "${PROB}__no_think"  "$NNEFF" all
  run_sc "${PROB}__no_think"  "$NNEFF" single
done
echo "ALLDONE $(date +%T)" >> "$ST"
