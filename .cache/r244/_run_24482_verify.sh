#!/usr/bin/env bash
# =============================================================================
# _run_24482_verify.sh —— 244.82「前提独立性」的**验证链**（远端驱动，零 GPU）
#
# ⚖ 顺序（⛔ 有依赖，别换）：
#   ① 第二条实现的自检（Phase-0 G0-1/G0-2：DP vs 暴力枚举、t 分位数、二项、jackknife、
#      块键、平票夹具、Fisher 已知值）        ← ⛔ 不依赖真数据
#   ② 第二条实现（真数据：bpath 原始日志）      ← G0-3 自检闸在**这里**
#   ③ 它的变异台（13 条）                      ← 证明每条判据**能红**
#   ④ 跨实现互证（先导探查 vs 本实现）          ← 20 条判据
#
# ⛔ 硬约束：
#   · 解释器一律 easysteer（⛔ 不用裸 python3）
#   · **只读** bpath；所有中间产物写 /dev/shm（⛔ 不写 NFS、⛔ 不改 bpath）
#   · ⛔ 零 GPU、⛔ 不跑批、⛔ 不 kill 任何进程、⛔ 不改任何预登记/读数器/探针
#   · ⛔ 不删任何已有文件（⇒ 上一轮的收据保留 ⇒ 可对照）
# =============================================================================
set -uo pipefail

PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
DEV=/home/zhourui/steer3d/.cache/r244
BP=/home/zhourui/steer3d_bpath
OUT=${OUT:-/dev/shm/_pi_24482}
SCOUT=${SCOUT_OUT:-/dev/shm/_pooled_24481/scout_premise_indep_24481.out}
mkdir -p "$OUT"

echo "=============================================================="
echo "244.82 验证链 ｜ $(date -Is) ｜ host=$(hostname)"
echo "=============================================================="
"$PY" -V || { echo "PRECOND_FAIL: 解释器跑不起来"; exit 2; }
echo "nproc=$(nproc)  load=$(cut -d' ' -f1-3 /proc/loadavg)"

echo ""
echo "---- 被检字节 ----"
md5sum "$DEV/premise_independence_audit.py" \
       "$DEV/mut_premise_independence_audit.py" \
       "$DEV/_cross_check_24482.py" 2>&1

echo ""
echo "==== ① 第二条实现的自检（Phase-0 G0-1/G0-2）===="
"$PY" "$DEV/premise_independence_audit.py" --selftest 2>&1 | tee "$OUT/selftest.out"
echo "SELFTEST_RC=${PIPESTATUS[0]}"

echo ""
echo "==== ② 第二条实现（真数据：bpath 原始日志）===="
"$PY" "$DEV/premise_independence_audit.py" \
    --w-log   "$BP/r244_warm_fd_w.log" \
    --rand-log "$BP/r244_warm_fd_rand.log" 2>&1 | tee "$OUT/pi.out"
echo "PI_RC=${PIPESTATUS[0]}"

echo ""
echo "==== ③ 变异台（13 条）===="
"$PY" "$DEV/mut_premise_independence_audit.py" 2>&1 | tee "$OUT/mut.out"
echo "MUT_RC=${PIPESTATUS[0]}"

echo ""
echo "==== ④ 跨实现互证（先导探查 vs 本实现）===="
if [ ! -f "$SCOUT" ]; then
  echo "PRECOND_FAIL: 缺先导探查输出：$SCOUT ⇒ 这一轮**跑不动** ⇒ ⛔ **不是「判据红」**"
  exit 2
fi
"$PY" "$DEV/_cross_check_24482.py" "$SCOUT" "$OUT/pi.out" 2>&1 | tee "$OUT/cross.out"
echo "CROSS_RC=${PIPESTATUS[0]}"

echo ""
echo "=== 验证链跑完 ==="
