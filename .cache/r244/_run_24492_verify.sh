#!/usr/bin/env bash
# ⚖⚖⚖ _run_24492_verify.sh —— 244.92 的**验证链**（远端 zju-53）
#   ⛔ 零 GPU、⛔ 零跑批、⛔ 不重解析原始跑批日志、⛔ 只读账本/页面（⛔ 不写远端 docs/）
#   ⇒ 产出：selftest / before / after / mut / cross / spec 六个 .out ＋ receipt.txt
set -u

REPO=${R244_REPO:-/home/zhourui/steer3d}
PY=${R244_PY:-/home/zhourui/miniconda3/envs/easysteer/bin/python}
OUT=${R244_OUT:-/dev/shm/_e24492}
PAGE_BEFORE=${R244_PAGE_BEFORE:-/dev/shm/_page_24492_before.md}
PAGE_AFTER=${R244_PAGE_AFTER:-/dev/shm/_page_24492_after.md}
LEDGER=$REPO/.cache/xcheck/R6_RERUN_PREREG.md
CONF_PREREG=$REPO/.cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md
DOC_PREREG=$REPO/.cache/xcheck/R6_DOC_CONSISTENCY_PREREG.md
RECEIPT=${R244_RECEIPT:-/dev/shm/_e24489b/de.out}

mkdir -p "$OUT"
cd "$REPO" || exit 9

rc_sel=0; rc_before=0; rc_after=0; rc_mut=0; rc_cross=0; rc_spec=0

"$PY" .cache/r244/doc_consistency_audit.py --selftest > "$OUT/selftest.out" 2>&1
rc_sel=$?

# ⚖ **改前**：过期页面 ⇒ ⇒ **必须红**（rc ≠ 0）
"$PY" .cache/r244/doc_consistency_audit.py --data --page "$PAGE_BEFORE" \
    --ledger "$LEDGER" --prereg "$CONF_PREREG" > "$OUT/before.out" 2>&1
rc_before=$?

# ⚖ **改后**：对齐后的页面 ⇒ ⇒ **必须绿**（rc = 0）
"$PY" .cache/r244/doc_consistency_audit.py --data --page "$PAGE_AFTER" \
    --ledger "$LEDGER" --prereg "$CONF_PREREG" > "$OUT/after.out" 2>&1
rc_after=$?

R244_LEDGER="$LEDGER" R244_PREREG="$CONF_PREREG" R244_PAGE="$PAGE_AFTER" \
    "$PY" .cache/r244/mut_doc_consistency_audit.py > "$OUT/mut.out" 2>&1
rc_mut=$?

R244_LEDGER="$LEDGER" R244_PREREG="$CONF_PREREG" R244_PAGE="$PAGE_AFTER" \
    R244_RECEIPT="$RECEIPT" \
    "$PY" .cache/r244/_cross_check_24492.py > "$OUT/cross.out" 2>&1
rc_cross=$?

R244_PREREG="$DOC_PREREG" R244_CONF_PREREG="$CONF_PREREG" R244_LEDGER="$LEDGER" \
    R244_PAGE="$PAGE_AFTER" R244_IMPL=.cache/r244/doc_consistency_audit.py \
    R244_MUT=.cache/r244/mut_doc_consistency_audit.py \
    R244_DRIVER=.cache/r244/_run_24492_verify.sh \
    "$PY" .cache/r244/_spec_crosscheck_24492.py > "$OUT/spec.out" 2>&1
rc_spec=$?

{
  echo "===== RECEIPT 244.92 ====="
  echo "rc: selftest=$rc_sel before=$rc_before after=$rc_after mut=$rc_mut cross=$rc_cross spec=$rc_spec"
  echo "--- 六个输出 ---"
  for f in selftest before after mut cross spec; do
    md5sum "$OUT/$f.out" | awk -v n="$f.out" '{print $1"  "n}'
  done
  echo "--- 被检件 ---"
  for f in .cache/r244/doc_consistency_audit.py .cache/r244/mut_doc_consistency_audit.py \
           .cache/r244/_cross_check_24492.py .cache/r244/_spec_crosscheck_24492.py \
           .cache/r244/_run_24492_verify.sh .cache/xcheck/R6_DOC_CONSISTENCY_PREREG.md \
           .cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md .cache/xcheck/R6_RERUN_PREREG.md; do
    md5sum "$f"
  done
  echo "--- 页面 ---"
  md5sum "$PAGE_BEFORE" "$PAGE_AFTER"
  echo "--- 收据（244.89 的 de.out，三方对账的第一环）---"
  md5sum "$RECEIPT" 2>/dev/null || echo "（收据缺失）"
  echo "VERIFY_RC=0"
} > "$OUT/receipt.txt" 2>&1

# ⚖ **判据**：「改前必须红」＋「其余五个必须绿」
if [ "$rc_sel" -eq 0 ] && [ "$rc_before" -ne 0 ] && [ "$rc_after" -eq 0 ] \
   && [ "$rc_mut" -eq 0 ] && [ "$rc_cross" -eq 0 ] && [ "$rc_spec" -eq 0 ]; then
  echo "VERIFY_RC=0"
  exit 0
fi
echo "VERIFY_RC=1"
exit 1
