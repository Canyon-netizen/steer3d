#!/bin/bash
# ⚖ 244.81 的远端全回归（tmpfs 工作副本，⛔ 不碰 NFS / conda / HF 快照）
#   ⚖⚠ 树 = **244.80 那棵**（/dev/shm/s24480r）**＋ 本轮变更的执行集文件**
#      · 新增 2 个（verify_pooled_verdict_indep.py / mut_verify_pooled_verdict_indep.py）
#      · 变更 3 个（fixed_dose_pooled_verdict_audit.py / mut_fixed_dose_pooled_verdict_audit.py
#                  / probe_compat_check.py）
#      ⇒ ⇒ 都不以 `_` 开头 ⇒ **全部进执行集** ⇒ 必须重跑
#   ⚖⚠ 账本同步**当前**版本（41 248 行，含 244.79 段）
#      ⇒ ⇒ 读账本的那几个工具这次看到的是**最新**账本
#   ⚖⚠ 清单 diff **必须逐条能解释**：新增 2 行 ＋ 变更 3 行（各一增一删）
set -u
ROOT=${ROOT:-/dev/shm/s24480r}
DEV=${DEV:-/home/zhourui/steer3d}
R244=$ROOT/.cache/r244
OUT=$ROOT/reg_24481.txt
MAN_NEW=$ROOT/_md5_exec_24481.txt
MAN_OLD=$ROOT/_md5_exec_24480.txt
DIFF=$ROOT/manifest_diff_24481.txt
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python

[ -d "$ROOT" ] || { echo "⛔ 树不存在：$ROOT" >&2; exit 2; }
[ -f "$MAN_OLD" ] || { echo "⛔ 缺上一轮清单：$MAN_OLD" >&2; exit 2; }

# ---- 1) 同步本轮新增/更新的文件
#     ⚖⚠ DEV 树在某些机器上**不全**（如 zju-12 的 DEV 只有 35 个 .py）
#     ⇒ ⇒ 优先从 DEV 拿；**拿不到就用树里已同步的那份**（⇒ 收据里的 md5 才是准的）
for f in fixed_dose_pooled_verdict_audit.py mut_fixed_dose_pooled_verdict_audit.py \
         verify_pooled_verdict_indep.py mut_verify_pooled_verdict_indep.py \
         probe_compat_check.py; do
  if [ -f "$DEV/.cache/r244/$f" ]; then
    cp "$DEV/.cache/r244/$f" "$R244/" || { echo "⛔ 覆盖失败 $f" >&2; exit 2; }
  elif [ ! -f "$R244/$f" ]; then
    echo "⛔ 缺 ${f}（DEV 与树里都没有）" >&2; exit 2
  else
    echo "⚠ $f 不在 DEV ⇒ 用树里已同步的那份"
  fi
done
cp "$DEV/.cache/xcheck/R6_RERUN_PREREG.md" "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" || exit 2
cp "$DEV/.cache/xcheck/R6_RERUN_INDEX.md" "$ROOT/.cache/xcheck/R6_RERUN_INDEX.md" || exit 2
cp "$DEV/.cache/xcheck/R6_FIXED_DOSE_POOLED_VERDICT_PREREG.md" \
   "$ROOT/.cache/xcheck/R6_FIXED_DOSE_POOLED_VERDICT_PREREG.md" || exit 2
cp "$DEV/.cache/xcheck/R6_FIXED_DOSE_VARIANT_PREREG.md" \
   "$ROOT/.cache/xcheck/R6_FIXED_DOSE_VARIANT_PREREG.md" || exit 2

# ⚖⚖⚖ 同步后的**逐位对账**（244.81 补）：这一步是为了防一类真事故 ——
#   244.81 第一次跑这轮回归时，DEV 里存着**旧字节**（`mut_verify_pooled_verdict_indep.py`
#   少了 `PRECOND_FAIL` 那句）⇒ ⇒ 「DEV → 树」把新字节**盖回旧的** ⇒ ⇒
#   ⇒ 回归测的不是最终版字节 ⇒ ⇒ 且那个台架会因缺远端产物报**假红**。
#   ⇒ ⇒ 现在**同步完立刻逐位对账**：DEV 与树不一致 ⇒ ⛔ 硬停。
for f in fixed_dose_pooled_verdict_audit.py mut_fixed_dose_pooled_verdict_audit.py \
         verify_pooled_verdict_indep.py mut_verify_pooled_verdict_indep.py \
         probe_compat_check.py; do
  if [ -f "$DEV/.cache/r244/$f" ]; then
    a=$(md5sum "$DEV/.cache/r244/$f" | cut -d' ' -f1)
    b=$(md5sum "$R244/$f" | cut -d' ' -f1)
    [ "$a" = "$b" ] || { echo "⛔ DEV 与树的 $f **不一致**（DEV=${a} 树=${b}）⇒ ⛔ 硬停" >&2; exit 3; }
  fi
done
echo "sync_ok: DEV 与树的 5 个文件逐位一致"

cd "$ROOT" || exit 2

# ---- 2) 执行集清单（规则与前几轮同：`.cache/r244` 下不以 `_` 开头的 .py）
find "$R244" -type f -name '*.py' ! -path '*/__pycache__/*' -printf '%P\n' \
  | grep -v '^_' | LC_ALL=C sort \
  | while read -r f; do
      printf '%s  %s\n' "$(md5sum "$R244/$f" | cut -d' ' -f1)" "$f"
    done > "$MAN_NEW"

# ---- 3) 清单 diff（新增 2 行 ＋ 变更 3 行 ⇒ 各一增一删）
diff "$MAN_OLD" "$MAN_NEW" > "$DIFF"
man_diff_rc=$?
man_added=$(grep -c '^>' "$DIFF" 2>/dev/null || echo 0)
man_removed=$(grep -c '^<' "$DIFF" 2>/dev/null || echo 0)

{
echo "=== 远端全回归（244.81：**判决那一轮** —— 合池分析器补印 V3/V4 分布 ＋ 独立重算器，tmpfs 工作副本）==="
echo "host=$(hostname)  date=$(date '+%F %T')  root=$ROOT"
echo "python=$($PY -V 2>&1)  nproc=$(nproc)  load=$(cat /proc/loadavg | cut -d' ' -f1-3)"
echo "fs=$(df -T $ROOT | tail -1)"
echo "n_exec_py=$(wc -l < "$MAN_NEW")  md5_manifest=$MAN_NEW  manifest_md5=$(md5sum "$MAN_NEW" | cut -d' ' -f1)"
echo "manifest_diff_rc=$man_diff_rc  added=$man_added  removed=$man_removed"
echo "--- 清单 diff（新增 2 行 ＋ 变更 3 行 ⇒ 每一行都要能解释）---"
cat "$DIFF"
echo "--- 账本 ---"
echo "ledger_lines=$(wc -l < "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md")  ledger_md5=$(md5sum "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d' ' -f1)"
echo "--- 本轮新增/更新的文件（md5 逐位对上）---"
for f in fixed_dose_pooled_verdict_audit.py mut_fixed_dose_pooled_verdict_audit.py \
         verify_pooled_verdict_indep.py mut_verify_pooled_verdict_indep.py \
         probe_compat_check.py; do
  echo "md5_${f}=$(md5sum "$R244/$f" | cut -d' ' -f1)"
done
echo ""
} > "$OUT"

# ---- 4) 跑 harness
$PY -u "$R244/_reg_24457.py" >> "$OUT" 2>&1
rc=$?
{
echo ""
echo "REG_RC=$rc"
echo "=== done rc=$rc ==="
} >> "$OUT"
