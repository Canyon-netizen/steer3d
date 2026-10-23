#!/usr/bin/env bash
# =============================================================================
# _run_24481_verify.sh —— 244.81「判决那一轮」的**验证链**（远端驱动）
#
# ⚖ 顺序（⛔ 有依赖，别换）：
#   ① 分析器自检（V-P1…V-P19）        ← 补印 V3/V4 的分布之后必须重跑
#   ② 分析器变异台（21 条）            ← 新增 P21 ⇒ V-P19 必须能红
#   ③ 判决流水线（重出面板 + 收据）    ← 面板变了 ⇒ 收据的 md5 必须跟着变
#   ④ 独立重算器自检（已知答案）        ← ⛔ 不依赖真数据
#   ⑤ 独立重算器（真数据 vs 面板）      ← ⛔ 第二条独立实现
#   ⑥ 独立重算器的变异台（12 条）        ← 证明「重算 vs 面板」这条比对能红
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
OUT=${OUT:-/dev/shm/_verify_24481}
mkdir -p "$OUT"

echo "=============================================================="
echo "244.81 验证链 ｜ $(date -Is) ｜ host=$(hostname)"
echo "=============================================================="
"$PY" -V || { echo "PRECOND_FAIL: 解释器跑不起来"; exit 2; }
echo "nproc=$(nproc)  load=$(cut -d' ' -f1-3 /proc/loadavg)"
echo ""
echo "---- 被检字节 ----"
md5sum "$DEV/fixed_dose_pooled_verdict_audit.py" \
       "$DEV/mut_fixed_dose_pooled_verdict_audit.py" \
       "$DEV/verify_pooled_verdict_indep.py" \
       "$DEV/mut_verify_pooled_verdict_indep.py" \
       "$DEV/fixed_dose_split_log.py" \
       "$DEV/_k23_reader_r227_kcurve.py" 2>&1

echo ""
echo "==== ① 分析器自检（V-P1…V-P19）===="
"$PY" "$DEV/fixed_dose_pooled_verdict_audit.py" --selftest \
    --old-w-log   "$BP/r244_warm_w.log" \
    --old-w-status "$BP/r244_warm_w_status.txt" \
    --old-r-log   "$BP/r244_warm_rand.log" \
    --old-r-status "$BP/r244_warm_rand_status.txt" 2>&1 | tee "$OUT/selftest.out"
echo "SELFTEST_RC=${PIPESTATUS[0]}"

echo ""
echo "==== ② 分析器变异台（21 条）===="
"$PY" "$DEV/mut_fixed_dose_pooled_verdict_audit.py" 2>&1 | tee "$OUT/mut_analyzer.out"
echo "MUT_ANALYZER_RC=${PIPESTATUS[0]}"

echo ""
echo "==== ③ 判决流水线（重出面板 + 收据）===="
bash "$DEV/_run_pooled_verdict_24481.sh" 2>&1 | tail -40
echo "PIPELINE_RC=${PIPESTATUS[0]}"

echo ""
echo "==== ④ 独立重算器自检（已知答案）===="
"$PY" "$DEV/verify_pooled_verdict_indep.py" --selftest 2>&1 | tee "$OUT/indep_selftest.out"
echo "INDEP_SELFTEST_RC=${PIPESTATUS[0]}"

echo ""
echo "==== ⑤ 独立重算器（真数据 vs 面板）===="
"$PY" "$DEV/verify_pooled_verdict_indep.py" \
    --w-log   "$BP/r244_warm_fd_w.log" \
    --rand-log "$BP/r244_warm_fd_rand.log" \
    --panel   /dev/shm/_pooled_24481/verdict_panel.txt \
    --out "$OUT/indep_verify.out" 2>&1 | tail -70
echo "INDEP_VERIFY_RC=${PIPESTATUS[0]}"

echo ""
echo "==== ⑥ 独立重算器的变异台（12 条）===="
R244_PANEL=/dev/shm/_pooled_24481/verdict_panel.txt \
    "$PY" "$DEV/mut_verify_pooled_verdict_indep.py" 2>&1 | tee "$OUT/mut_indep.out"
echo "MUT_INDEP_RC=${PIPESTATUS[0]}"

echo ""
echo "=== 验证链跑完 ==="
