#!/usr/bin/env bash
# _run_24497_verify.sh —— 244.97 判决链驱动（远端 zju-53，零 GPU、零跑批）
# ⚖ 每一步的**期望返回码是写死的** ⇒ ⇒ 任何一步红了/歪了 ⇒ ⇒ 整条链红。
# ⚖ 收据落在 ${OUT}（默认 /dev/shm/_e24497）⇒ ⇒ ⛔ 不入库。
#
# ⚖⚖⚖ **口径真相源**：`.cache/xcheck/R6_DOSE_CURVE_PREREG.md`（244.97 签，先于实现；含 §8 追加更正）
set -u
cd /home/zhourui/steer3d

PY=${PY:-/home/zhourui/miniconda3/envs/easysteer/bin/python}
OUT=${OUT:-/dev/shm/_e24497}
LEDGER=.cache/xcheck/R6_RERUN_PREREG.md
PAGE_AFTER=.cache/r244/_page_24497.md
PAGE_BEFORE=.cache/r244/_page_24497_before.md
CHECKER=.cache/r244/doc_dose_curve_audit.py
BENCH=.cache/r244/mut_doc_dose_curve_audit.py
CROSS=.cache/r244/_cross_check_24497.py
SPEC=.cache/r244/_spec_crosscheck_24497.py
PREREG=.cache/xcheck/R6_DOSE_CURVE_PREREG.md
DRIVER=.cache/r244/_run_24497_verify.sh
MUT_WORK=${MUT_WORK:-/dev/shm/_mut24497}
# ⚖ 变异台的三个输入**显式导出**（⛔ 不依赖它自己的默认值）
export MUT_WORK
export MUT_LEDGER="${LEDGER}"
export MUT_PAGE="${PAGE_AFTER}"

mkdir -p "${OUT}"
FAIL=0

run_step () {
  # run_step <名字> <期望返回码> <命令...>
  local name=$1
  local want=$2
  shift 2
  local log="${OUT}/${name}.out"
  "$@" > "${log}" 2>&1
  local rc=$?
  local mark="OK"
  if [ "${rc}" != "${want}" ]; then
    mark="MISMATCH"
    FAIL=1
  fi
  echo "[${mark}] ${name}：rc=${rc}（期望 ${want}）｜ 收据 ${log}"
  return 0
}

echo "=== 244.97 判决链（改前 ⇒ 改后）==="
echo "账本 ${LEDGER}"
echo "收据目录 ${OUT}"
echo ""

run_step selftest 0 "${PY}" "${CHECKER}" --selftest
# ⚖ 改前页面**预期判红**（预登记 §2 末尾：D1 ⇒ E3；D2 ⇒ E4）⇒ ⇒ 返回码 1
run_step data_before 1 "${PY}" "${CHECKER}" --data --page "${PAGE_BEFORE}" --ledger "${LEDGER}"
run_step data_after 0 "${PY}" "${CHECKER}" --data --page "${PAGE_AFTER}" --ledger "${LEDGER}"
run_step mut 0 "${PY}" "${BENCH}"
run_step cross 0 "${PY}" "${CROSS}" --main "${OUT}/data_after.out" --page "${PAGE_AFTER}" --ledger "${LEDGER}"
run_step cross_selftest 0 "${PY}" "${CROSS}" --selftest --main "${OUT}/data_after.out" \
  --page "${PAGE_AFTER}" --ledger "${LEDGER}"
run_step spec 0 "${PY}" "${SPEC}" --prereg "${PREREG}" \
  --checker "${CHECKER}" --bench "${BENCH}" --cross "${CROSS}" \
  --mut-out "${OUT}/mut.out" \
  --page-before "${PAGE_BEFORE}" --page-after "${PAGE_AFTER}" --ledger "${LEDGER}" \
  --main-before "${OUT}/data_before.out" --main-after "${OUT}/data_after.out"

echo ""
echo "===== KEY_SUMMARY ====="
grep -hE "^(VERDICT|CHECKS_RED|N_CHECKS|CHECK_E[0-9]|N_[A-Z_]+|MUT_[A-Z_]+|CROSS_[A-Z_]+|SPEC_[A-Z_]+|SELFTEST_[A-Z]+)=" \
  "${OUT}"/*.out 2>/dev/null | sort -u
echo "===== END_KEY_SUMMARY ====="

# ⚖⚖⚖ **收据锚字节指纹**（远端现算）⇒ ⇒ 提交后双回读拿它跟**本地现算**逐位对
{
  echo "=== 244.97 收据 ==="
  date -u '+RUN_UTC=%Y-%m-%dT%H:%M:%SZ'
  echo "--- 输入与被检文件的 md5（远端现算）---"
  md5sum "${LEDGER}" "${PAGE_AFTER}" "${PAGE_BEFORE}" "${CHECKER}" "${BENCH}" "${CROSS}" "${SPEC}" "${PREREG}" "${DRIVER}"
  echo "--- 收据文件的 md5（远端现算）---"
  md5sum "${OUT}"/*.out
  echo "=== END ==="
} > "${OUT}/receipt.txt"
echo ""
echo "--- 收据锚字节指纹 ---"
cat "${OUT}/receipt.txt"
echo ""
echo "VERIFY_RC=${FAIL}"
exit "${FAIL}"
