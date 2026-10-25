#!/usr/bin/env bash
# =============================================================================
# _run_24489_verify.sh —— 244.89「保守读法换置信水平」的**验证链**（远端驱动，零 GPU）
#
# ⚖ 顺序（⛔ 有依赖，别换）：
#   ① 第一条实现的自检（Phase-0 G0-1..G0-9：合成夹具，⛔ 不依赖真数据）
#   ② 第一条实现（真数据：**只读**账本的 244.81 / 244.88 段，⛔ 不重跑日志、⛔ 零 GPU）
#   ③ 它的变异台                                ← 证明每条判据**能红**（含判决形态）
#   ④ 跨实现互证（**Fraction/Decimal** 路线 vs 被检实现的 float 路线）← 两条独立实现逐项比
#   ⑤ 预登记 ↔ 实现 的机械对账（口径真相源 = 预登记）
#
# ⛔ 硬约束：
#   · 解释器一律 easysteer（⛔ 不用裸 python3）
#   · **只读**账本；所有中间产物写 /dev/shm（⛔ 不写 NFS、⛔ 不改账本）
#   · ⛔ 零 GPU、⛔ 不跑批、⛔ 不 kill 任何进程、⛔ 不改任何预登记/读数器/探针
#   · ⛔ 不删任何已有文件（⇒ 上一轮的收据保留 ⇒ 可对照）
#
# ⚖⚖⚖ **账本依赖**：本轮的**每一个输入**都从**账本 244.81 段**（改判数、区间、基准）
#   解析，**跨轮锚**从**账本 244.88 段**（上一轮印的 9 格 + R1/R2/R3/R6）解析
#   ⇒ ⇒ 账本里必须**已经有**这两段 ⇒ ⇒ ⛔ 没有 ⇒ 直接 PRECOND_FAIL
#   （⛔ 绝不用代码里的字面值兜底）
#
# ⚖⚖⚖ **banner 里的变异条数是「现算」的**（⛔ 不写死）
#   ⇒ ⇒ 244.88 的第 ⑨ 条缺陷就是「banner 印 34、真实 35」⇒ ⇒ **本轮从结构上堵死**：
#   改台架就必然改 banner，不存在「过期计数」这种可能。
# =============================================================================
set -uo pipefail

PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
DEV=${DEV:-/home/zhourui/steer3d/.cache/r244}
REPO=${REPO:-/home/zhourui/steer3d}
LEDGER=${LEDGER:-$REPO/.cache/xcheck/R6_RERUN_PREREG.md}
LEDGER_DIR=${LEDGER_DIR:-$(dirname "$LEDGER")}
PREREG=${PREREG:-$LEDGER_DIR/R6_CONFIDENCE_LEVEL_PREREG.md}
OUT=${OUT:-/dev/shm/_null_24489}
mkdir -p "$OUT"

echo "=============================================================="
echo "244.89 验证链 ｜ $(date -Is) ｜ host=$(hostname)"
echo "=============================================================="
"$PY" -V || { echo "PRECOND_FAIL: 解释器跑不起来"; exit 2; }
echo "nproc=$(nproc)  load=$(cut -d' ' -f1-3 /proc/loadavg)"
echo "DEV=$DEV"

echo ""
echo "---- 前置：账本里必须有 244.81 与 244.88 段（全部输入与跨轮锚的出处）----"
if ! grep -q '^## 修订 244\.81 ' "$LEDGER" 2>/dev/null; then
  echo "PRECOND_FAIL: 账本 $LEDGER 里没有「## 修订 244.81」段 ⇒ 输入无处可读 ⇒ 中止"
  exit 2
fi
if ! grep -q '^## 修订 244\.88 ' "$LEDGER" 2>/dev/null; then
  echo "PRECOND_FAIL: 账本 $LEDGER 里没有「## 修订 244.88」段 ⇒ 跨轮锚无处可读 ⇒ 中止"
  exit 2
fi
echo "ledger_lines=$(wc -l < "$LEDGER")  ledger_md5=$(md5sum "$LEDGER" | cut -d' ' -f1)"
grep -n '^## 修订 244\.8[18] ' "$LEDGER" | head -2

echo ""
echo "---- 前置：预登记必须在（口径真相源）----"
if [ ! -f "$PREREG" ]; then
  echo "PRECOND_FAIL: 预登记 $PREREG 不存在 ⇒ 口径真相源缺失 ⇒ 中止"
  exit 2
fi
echo "prereg=$PREREG  prereg_md5=$(md5sum "$PREREG" | cut -d' ' -f1)"

echo ""
echo "---- 被检字节 ----"
md5sum "$DEV/confidence_level_audit.py" \
       "$DEV/mut_confidence_level_audit.py" \
       "$DEV/_cross_check_24489.py" \
       "$DEV/_spec_crosscheck_24489.py" 2>&1
md5sum "$DEV/_run_24489_verify.sh" \
       "$PREREG" 2>&1

# ⚖⚖⚖ 变异条数**现算**（⛔ 不写死 ⇒ ⇒ 不可能有「过期计数」）
MUT_N=$(grep -cE '^ +\("(MU|ML)[0-9]+",' "$DEV/mut_confidence_level_audit.py")
echo "mut_count(from_source)=$MUT_N"

echo ""
echo "==== ① 第一条实现的自检（Phase-0 G0-1..G0-9）===="
R24489_TMPDIR="$OUT/selftest_tmp" "$PY" "$DEV/confidence_level_audit.py" --selftest 2>&1 | tee "$OUT/selftest.out"
SELFTEST_RC=${PIPESTATUS[0]}
echo "SELFTEST_RC=$SELFTEST_RC"

echo ""
echo "==== ② 第一条实现（真数据：⛔ 只读账本、⛔ 零 GPU、⛔ 不重跑任何日志）===="
R24489_TMPDIR="$OUT/selftest_tmp" "$PY" "$DEV/confidence_level_audit.py" \
    --data --ledger "$LEDGER" 2>&1 | tee "$OUT/de.out"
DE_RC=${PIPESTATUS[0]}
echo "DE_RC=$DE_RC"

echo ""
echo "==== ③ 变异台（$MUT_N 条；条数现算，⛔ 不写死）===="
R244_LEDGER="$LEDGER" "$PY" "$DEV/mut_confidence_level_audit.py" 2>&1 | tee "$OUT/mut.out"
MUT_RC=${PIPESTATUS[0]}
echo "MUT_RC=$MUT_RC"

echo ""
echo "==== ④ 跨实现互证（Fraction/Decimal 路线 vs 被检实现的 float 路线；⛔ 27 格**逐格**对比）===="
R244_LEDGER="$LEDGER" R244_DE_OUT="$OUT/de.out" "$PY" "$DEV/_cross_check_24489.py" 2>&1 | tee "$OUT/cross.out"
CROSS_RC=${PIPESTATUS[0]}
echo "CROSS_RC=$CROSS_RC"

echo ""
echo "==== ⑤ 预登记 ↔ 实现 的机械对账（口径真相源 = 预登记）===="
R244_PREREG="$PREREG" R244_LEDGER="$LEDGER" "$PY" "$DEV/_spec_crosscheck_24489.py" 2>&1 | tee "$OUT/spec.out"
SPEC_RC=${PIPESTATUS[0]}
echo "SPEC_RC=$SPEC_RC"

echo ""
echo "==== 收据 ===="
{
  echo "=== 244.89 保守读法换置信水平 验证链 收据 ==="
  echo "host=$(hostname)  date=$(date '+%F %T')"
  echo "DEV=$DEV"
  echo "MUT_N=$MUT_N"
  echo "SELFTEST_RC=$SELFTEST_RC  DE_RC=$DE_RC  MUT_RC=$MUT_RC  CROSS_RC=$CROSS_RC  SPEC_RC=$SPEC_RC"
  echo "--- 被检字节 md5 ---"
  md5sum "$DEV/confidence_level_audit.py" \
         "$DEV/mut_confidence_level_audit.py" \
         "$DEV/_cross_check_24489.py" \
         "$DEV/_spec_crosscheck_24489.py"
  echo "--- 口径与驱动字节 md5 ---"
  md5sum "$DEV/_run_24489_verify.sh" \
         "$PREREG"
  echo "--- 账本（被读的那份）---"
  echo "ledger_lines=$(wc -l < "$LEDGER")  ledger_md5=$(md5sum "$LEDGER" | cut -d' ' -f1)"
  echo "--- 收据文件 md5 ---"
  md5sum "$OUT/selftest.out" "$OUT/de.out" "$OUT/mut.out" "$OUT/cross.out" "$OUT/spec.out"
} > "$OUT/receipt.txt"
cat "$OUT/receipt.txt"

echo ""
echo "=== 验证链跑完 ==="
