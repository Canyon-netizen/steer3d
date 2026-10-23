#!/bin/bash
# ⚖ 244.81 的**第二轮**远端全回归（R2）：验**追加 244.80 ＋ 244.81 两段之后**的账本
#
# ⚖⚠⚖⚖ **为什么要多跑这一轮**：
#   R1（`_run_24481_reg_shm.sh`）跑的时候账本还是 244.79 那版（41 248 行）
#   ⇒ ⇒ 它验的是**工具**字节（已最终）⇒ ⇒ 但**账本字节**随后会变
#   ⇒ ⇒ 「证据 ↔ 最终版字节」这条闸，对**账本**这一半还没过
#   ⇒ ⇒ 所以追加之后**再跑一轮** ⇒ ⇒ 这次跑的账本 = **本次提交里的那份**。
#
# ⚖⚠ **只读 NFS、只写 tmpfs**：账本/索引从 DEV 拷进树，跑完回执留在树里。
#   ⛔ 不碰 bpath、⛔ 不起 GPU、⛔ 不改任何被测文件。
set -u
ROOT=${ROOT:-/dev/shm/s24480r}
DEV=${DEV:-/home/zhourui/steer3d}
R244=$ROOT/.cache/r244
OUT=$ROOT/reg_24481b.txt
MAN_NEW=$ROOT/_md5_exec_24481b.txt
MAN_PREV=$ROOT/_md5_exec_24481.txt
DIFF=$ROOT/manifest_diff_24481b.txt
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
# ⚖ 期望的账本 md5（**由调用方从本地作者树算好后传进来**）⇒ ⇒ 杜绝「同步错版本」
EXPECT_LEDGER_MD5=${EXPECT_LEDGER_MD5:-}

[ -d "$ROOT" ] || { echo "⛔ 树不存在：$ROOT" >&2; exit 2; }
[ -f "$MAN_PREV" ] || { echo "⛔ 缺上一轮清单：$MAN_PREV" >&2; exit 2; }

# ---- 1) 同步账本 ＋ 索引（⛔ 这两个是本轮**唯一**会变的输入）
cp "$DEV/.cache/xcheck/R6_RERUN_PREREG.md" "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" || exit 2
cp "$DEV/.cache/xcheck/R6_RERUN_INDEX.md" "$ROOT/.cache/xcheck/R6_RERUN_INDEX.md" || exit 2

# ⚖⚖⚖ 账本**逐位对账**：DEV 的账本必须等于调用方给的期望 md5
#   ⇒ ⇒ 否则就是「同步了另一个版本」⇒ ⇒ ⛔ 硬停（244.81 那次就是这么出的事故）
LED_MD5=$(md5sum "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d' ' -f1)
DEV_MD5=$(md5sum "$DEV/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d' ' -f1)
if [ -n "$EXPECT_LEDGER_MD5" ] && [ "$LED_MD5" != "$EXPECT_LEDGER_MD5" ]; then
  echo "⛔ 账本 md5 不符：树=$LED_MD5 DEV=$DEV_MD5 期望=$EXPECT_LEDGER_MD5 ⇒ ⛔ 硬停" >&2
  exit 3
fi
if [ "$LED_MD5" != "$DEV_MD5" ]; then
  echo "⛔ 树里的账本与 DEV 不一致 ⇒ ⛔ 硬停" >&2; exit 3
fi
echo "sync_ok: 账本 md5=${LED_MD5}（= 调用方给的期望值）"

# ⚖ 执行集文件：R2 **一个字节都不该变** ⇒ ⇒ 逐位对账 DEV↔树（对 R1 那 5 个变更文件）
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

# ---- 3) 清单 diff：**对 R1 的清单**（⛔ 不是对 244.80 的）
#   ⇒ R2 不该改任何执行集文件 ⇒ ⇒ 期望 **added=0 / removed=0**
# ⚠⚠⚠ 这里**必须**用 awk 而不是 `grep -c ... || echo 0`：
#   `grep -c` 在**无匹配**时**照样打印 0** 并返回**非 0** ⇒ `|| echo 0` 会**再补一个 0**
#   ⇒ 变量变成两行「0」⇒ 收据头被撑出两行游离的「0」。
#   ⚠ 而且它**只在「没有差异」时触发** —— 恰恰是最该干净的那一种情况。
diff "$MAN_PREV" "$MAN_NEW" > "$DIFF"
man_diff_rc=$?
man_added=$(awk '/^>/{n++} END{print n+0}' "$DIFF")
man_removed=$(awk '/^</{n++} END{print n+0}' "$DIFF")

{
echo "=== 远端全回归 R2（244.81 **落账后**的账本 —— 验本次提交里的那份字节）==="
echo "host=$(hostname)  date=$(date '+%F %T')  root=$ROOT"
echo "python=$($PY -V 2>&1)  nproc=$(nproc)  load=$(cat /proc/loadavg | cut -d' ' -f1-3)"
echo "fs=$(df -T $ROOT | tail -1)"
echo "n_exec_py=$(wc -l < "$MAN_NEW")  md5_manifest=$MAN_NEW  manifest_md5=$(md5sum "$MAN_NEW" | cut -d' ' -f1)"
echo "manifest_diff_rc=$man_diff_rc  added=$man_added  removed=$man_removed  (对 R1 清单 ⇒ 期望 0/0)"
echo "--- 清单 diff（对 R1）---"
cat "$DIFF"
echo "--- 账本（= 追加 244.80 ＋ 244.81 两段之后的那份）---"
echo "ledger_lines=$(wc -l < "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md")  ledger_md5=$(md5sum "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d' ' -f1)"
echo "index_lines=$(wc -l < "$ROOT/.cache/xcheck/R6_RERUN_INDEX.md")  index_md5=$(md5sum "$ROOT/.cache/xcheck/R6_RERUN_INDEX.md" | cut -d' ' -f1)"
echo "--- 本轮变更过的执行集文件（md5 逐位对上）---"
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
