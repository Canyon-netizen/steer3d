#!/usr/bin/env bash
# =============================================================================
# _run_24483_verify.sh —— 244.83「剂量等值性」的**验证链**（远端驱动，零 GPU）
#
# ⚖ 顺序（⛔ 有依赖，别换）：
#   ① 第一条实现的自检（Phase-0 G0-1/G0-2：合成夹具 ①全绿 ②12 个缺陷逐个打红）
#      ← ⛔ 不依赖真数据
#   ② 第一条实现（真数据：bpath 原始日志 + 向量 + 跑批器 + 探针）
#   ③ 它的变异台（18 条）                      ← 证明每条判据**能红**
#   ④ 跨实现互证（纯 Python 路线 vs numpy 路线）← 19 条判据
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
OUT=${OUT:-/dev/shm/_de_24483}
mkdir -p "$OUT"

echo "=============================================================="
echo "244.83 验证链 ｜ $(date -Is) ｜ host=$(hostname)"
echo "=============================================================="
"$PY" -V || { echo "PRECOND_FAIL: 解释器跑不起来"; exit 2; }
echo "nproc=$(nproc)  load=$(cut -d' ' -f1-3 /proc/loadavg)"

echo ""
echo "---- 被检字节 ----"
md5sum "$DEV/dose_equivalence_audit.py" \
       "$DEV/mut_dose_equivalence_audit.py" \
       "$DEV/_cross_check_24483.py" 2>&1

echo ""
echo "---- bpath 产物 md5（被读的六件）----"
md5sum "$BP/r244_warm_fd_w.log" "$BP/r244_warm_fd_rand.log" \
       "$BP/r244_warm_sweep.sh" "$BP/r241_probe.py" \
       "$BP/w_p2a.npy" "$BP/warm_cells_fixed_dose.tsv" 2>&1

echo ""
echo "==== ① 第一条实现的自检（Phase-0 G0-1/G0-2）===="
"$PY" "$DEV/dose_equivalence_audit.py" --selftest 2>&1 | tee "$OUT/selftest.out"
SELFTEST_RC=${PIPESTATUS[0]}
echo "SELFTEST_RC=$SELFTEST_RC"

echo ""
echo "==== ② 第一条实现（真数据）===="
"$PY" "$DEV/dose_equivalence_audit.py" \
    --w-log   "$BP/r244_warm_fd_w.log" \
    --rand-log "$BP/r244_warm_fd_rand.log" \
    --runner  "$BP/r244_warm_sweep.sh" \
    --probe   "$BP/r241_probe.py" \
    --w-npy   "$BP/w_p2a.npy" \
    --cells   "$BP/warm_cells_fixed_dose.tsv" 2>&1 | tee "$OUT/de.out"
DE_RC=${PIPESTATUS[0]}
echo "DE_RC=$DE_RC"

echo ""
echo "==== ③ 变异台（18 条）===="
"$PY" "$DEV/mut_dose_equivalence_audit.py" 2>&1 | tee "$OUT/mut.out"
MUT_RC=${PIPESTATUS[0]}
echo "MUT_RC=$MUT_RC"

echo ""
echo "==== ④ 跨实现互证（纯 Python 路线 vs numpy 路线）===="
"$PY" "$DEV/_cross_check_24483.py" 2>&1 | tee "$OUT/cross.out"
CROSS_RC=${PIPESTATUS[0]}
echo "CROSS_RC=$CROSS_RC"

echo ""
echo "==== 收据 ===="
{
  echo "=== 244.83 剂量等值性验证链 收据 ==="
  echo "host=$(hostname)  date=$(date '+%F %T')"
  echo "SELFTEST_RC=$SELFTEST_RC  DE_RC=$DE_RC  MUT_RC=$MUT_RC  CROSS_RC=$CROSS_RC"
  echo "--- 被检字节 md5 ---"
  md5sum "$DEV/dose_equivalence_audit.py" \
         "$DEV/mut_dose_equivalence_audit.py" \
         "$DEV/_cross_check_24483.py"
  echo "--- bpath 产物 md5 ---"
  md5sum "$BP/r244_warm_fd_w.log" "$BP/r244_warm_fd_rand.log" \
         "$BP/r244_warm_sweep.sh" "$BP/r241_probe.py" \
         "$BP/w_p2a.npy" "$BP/warm_cells_fixed_dose.tsv"
  echo "--- 收据文件 md5 ---"
  md5sum "$OUT/selftest.out" "$OUT/de.out" "$OUT/mut.out" "$OUT/cross.out"
} > "$OUT/receipt.txt"
cat "$OUT/receipt.txt"

echo ""
echo "=== 验证链跑完 ==="
