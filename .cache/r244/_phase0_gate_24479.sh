#!/usr/bin/env bash
# =============================================================================
# _phase0_gate_24479.sh —— 244.79 固定剂量「合池判决层」Phase-0 闸门的**远端驱动**
#
# ⛔ 硬约束（必须遵守）：
#   · 解释器一律用 /home/zhourui/miniconda3/envs/easysteer/bin/python（⛔ 不用裸 python3）
#   · 一切输出写 /dev/shm/_phase0_24479/（tmpfs）⇒ ⛔ 不写 NFS、⛔ 不写 bpath
#   · ⛔ 零 GPU、⛔ 不跑跑批、⛔ 不 kill 任何进程、⛔ 不改 .cache/r244/ 下任何文件
#     （下面只是**读** dev 树，把需要的文件**复制**到 /dev/shm 的暂存树里）
#
# 暂存树布局（⛔ REPO 必须等于暂存树根，否则 ledger_cell_census 找不到
#   .cache/r244/_an.txt 与 .cache/mutbak/r204_noise_probe.py）：
#   $TREE/.cache/r244/     ← 统计机械 + 旧批读数 JSON + 两份旧批日志
#   $TREE/.cache/mutbak/   ← r227_kcurve.py（权威读数器）+ r204_noise_probe.py
#   $TREE/.cache/xcheck/   ← R6_RERUN_PREREG.md
# =============================================================================
set -uo pipefail

PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
ROOT=/dev/shm/_phase0_24479
TREE=$ROOT/tree
INC=$ROOT/incoming
DEV=/home/zhourui/steer3d/.cache/r244
BP=/home/zhourui/steer3d_bpath

say() { printf '%s\n' "$*"; }
die() { printf 'PRECOND_FAIL: %s\n' "$*" >&2; exit 2; }

say "=============================================================="
say "244.79 Phase-0 闸门驱动 ｜ $(date -Is)"
say "=============================================================="
say "解释器：$PY"
"$PY" -V || die "解释器跑不起来：$PY"
say "主机  ：$(hostname)"
say "负载  ：$(uptime)"
say ""

# ---------------------------------------------------------------- 前置
[ -x "$PY" ] || die "缺解释器 $PY"
for f in "$DEV/_k23_reader_r227_kcurve.py" "$DEV/fixed_dose_split_log.py" \
         "$BP/r244_warm_w.log" "$BP/r244_warm_w_status.txt" "$BP/warm_cells.txt"; do
  [ -f "$f" ] || die "缺输入 $f"
done
[ -f "$ROOT/_phase0_gate_24479.py" ] || die "缺闸门主脚本 $ROOT/_phase0_gate_24479.py"
[ -d "$INC/r244" ] || die "缺 incoming/r244（先把依赖模块 scp 上来）"
[ -d "$INC/mutbak" ] || die "缺 incoming/mutbak"

# ---------------------------------------------------------------- 搭暂存树
mkdir -p "$TREE/.cache/r244" "$TREE/.cache/mutbak" "$TREE/.cache/xcheck" || die "建暂存树失败"

# (a) dev 树里**已有**的原件（⛔ 只读复制，不改原件）—— 这三个就是被检对象
cp -f "$DEV/fixed_dose_split_log.py"   "$TREE/.cache/r244/"
cp -f "$DEV/dose_confound_audit.py"    "$TREE/.cache/r244/"
cp -f "$DEV/dose_layer_audit.py"       "$TREE/.cache/r244/"
# (b) 权威读数器（md5 必须是 1e31c78ed8f88a61099d2b7fd89665d5）⇒ 放两个角色
cp -f "$DEV/_k23_reader_r227_kcurve.py" "$TREE/.cache/mutbak/r227_kcurve.py"
# (c) incoming（本地 scp 上来、dev 树上没有的那些模块与旧批读数）
cp -f "$INC"/r244/*.py      "$TREE/.cache/r244/" 2>/dev/null || true
cp -f "$INC"/r244/_an.txt   "$TREE/.cache/r244/" 2>/dev/null || true
cp -f "$INC"/r244/_ra.txt   "$TREE/.cache/r244/" 2>/dev/null || true
cp -f "$INC"/r244/w_new.log   "$TREE/.cache/r244/" 2>/dev/null || true
cp -f "$INC"/r244/rand_new.log "$TREE/.cache/r244/" 2>/dev/null || true
cp -f "$INC"/mutbak/*.py    "$TREE/.cache/mutbak/" 2>/dev/null || true
# (d) 账本（⛔ 只读复制）
cp -f /home/zhourui/steer3d/.cache/xcheck/R6_RERUN_PREREG.md "$TREE/.cache/xcheck/" 2>/dev/null || true

say "---- 暂存树 md5 清单 ----"
( cd "$TREE/.cache/r244"  && md5sum ./*.py ./_an.txt ./_ra.txt ./*.log 2>/dev/null )
( cd "$TREE/.cache/mutbak" && md5sum ./*.py 2>/dev/null )
say ""

# ---------------------------------------------------------------- 跑闸门
say "---- 跑闸门（零 GPU、纯 CPU）----"
"$PY" "$ROOT/_phase0_gate_24479.py" \
    --gate all --selftest \
    --outdir "$ROOT" --tree "$TREE" --dev "$DEV" --bpath "$BP"
RC=$?
say ""
say "闸门退出码：$RC"
say "收据："
( cd "$ROOT" && ls -la g0_1.out g0_2.out g0_3.out selftest.out summary.json 2>&1 )
exit $RC
