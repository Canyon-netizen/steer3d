#!/bin/bash
# ⚖ 244.82 的**远端全回归（R3）**：验**追加 244.82 段之后**的账本 ＋ 本轮新增的执行集文件
#
# ⚖⚠⚖⚖ **R3 与 R2 的关系**
#   R1（`_run_24481_reg_shm.sh`）：账本 = 244.79 那版
#   R2（`_run_24481b_reg_shm.sh`）：账本 = 追加 244.80 ＋ 244.81 之后的那版
#   R3（本文件）：账本 = **追加 244.82 之后**的那版 ＝ **本次提交里的那份**
#   ⇒ ⇒ 清单 diff 对 **R2** ⇒ ⇒ 期望 **added=2 / removed=0**
#      （新增的两个执行集成员：`premise_independence_audit.py` ＋ 它的变异台；
#        ⛔ `_` 开头的（`_cross_check_24482.py` / `_append_24482.py` / `_run_24482_verify.sh`）
#        **不进**执行集）
#
# ⚖⚠ **只读 NFS、只写 tmpfs**：账本/索引/新文件从 DEV 拷进树，跑完回执留在树里。
#   ⛔ 不碰 bpath、⛔ 不起 GPU、⛔ 不改任何被测文件。
set -u
ROOT=${ROOT:-/dev/shm/s24480r}
DEV=${DEV:-/home/zhourui/steer3d}
R244=$ROOT/.cache/r244
OUT=$ROOT/reg_24482.txt
MAN_NEW=$ROOT/_md5_exec_24482.txt
MAN_PREV=$ROOT/_md5_exec_24481b.txt
DIFF=$ROOT/manifest_diff_24482.txt
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
# ⚖ 期望的账本 md5（**由调用方从本地作者树算好后传进来**）⇒ ⇒ 杜绝「同步错版本」
EXPECT_LEDGER_MD5=${EXPECT_LEDGER_MD5:-}
# ⚖ 本轮**新增**的执行集文件（必须逐位对账 DEV↔树）
NEW_FILES="premise_independence_audit.py mut_premise_independence_audit.py"

[ -d "$ROOT" ] || { echo "⛔ 树不存在：$ROOT" >&2; exit 2; }
[ -f "$MAN_PREV" ] || { echo "⛔ 缺上一轮清单：$MAN_PREV" >&2; exit 2; }

# ---- 1) 同步账本 ＋ 索引 ＋ 本轮新增的执行集文件
cp "$DEV/.cache/xcheck/R6_RERUN_PREREG.md" "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" || exit 2
cp "$DEV/.cache/xcheck/R6_RERUN_INDEX.md" "$ROOT/.cache/xcheck/R6_RERUN_INDEX.md" || exit 2
for f in $NEW_FILES; do
  cp "$DEV/.cache/r244/$f" "$R244/$f" || { echo "⛔ 同步 $f 失败" >&2; exit 2; }
done

# ⚖⚖⚖ 账本**逐位对账**：DEV 的账本必须等于调用方给的期望 md5
LED_MD5=$(md5sum "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d' ' -f1)
DEV_MD5=$(md5sum "$DEV/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d' ' -f1)
if [ -n "$EXPECT_LEDGER_MD5" ] && [ "$LED_MD5" != "$EXPECT_LEDGER_MD5" ]; then
  echo "⛔ 账本 md5 不符：树=${LED_MD5} DEV=${DEV_MD5} 期望=${EXPECT_LEDGER_MD5} ⇒ ⛔ 硬停" >&2
  exit 3
fi
if [ "$LED_MD5" != "$DEV_MD5" ]; then
  echo "⛔ 树里的账本与 DEV 不一致 ⇒ ⛔ 硬停" >&2; exit 3
fi
echo "sync_ok: 账本 md5=${LED_MD5}（= 调用方给的期望值）"

# ⚖ 本轮新增的执行集文件：DEV↔树**逐位对账**
for f in $NEW_FILES; do
  a=$(md5sum "$DEV/.cache/r244/$f" | cut -d' ' -f1)
  b=$(md5sum "$R244/$f" | cut -d' ' -f1)
  [ "${a}" = "${b}" ] || { echo "⛔ DEV 与树的 ${f} **不一致**（DEV=${a} 树=${b}）⇒ ⛔ 硬停" >&2; exit 3; }
done
echo "sync_ok: DEV 与树的 ${NEW_FILES} 逐位一致"

cd "$ROOT" || exit 2

# ---- 2) 执行集清单（规则与前几轮同：`.cache/r244` 下不以 `_` 开头的 .py）
find "$R244" -type f -name '*.py' ! -path '*/__pycache__/*' -printf '%P\n' \
  | grep -v '^_' | LC_ALL=C sort \
  | while read -r f; do
      printf '%s  %s\n' "$(md5sum "$R244/$f" | cut -d' ' -f1)" "$f"
    done > "$MAN_NEW"

# ---- 3) 清单 diff：**对 R2 的清单**
#   ⇒ R3 新增 2 个执行集成员 ⇒ ⇒ 期望 **added=2 / removed=0**
# ⚠⚠⚠ 这里**必须**用 awk 而不是 `grep -c ... || echo 0`：
#   `grep -c` 在**无匹配**时**照样打印 0** 并返回**非 0** ⇒ `|| echo 0` 会**再补一个 0**
#   ⇒ 变量变成两行「0」⇒ 收据头被撑出两行游离的「0」。
#   ⚠ 而且它**只在「没有差异」时触发** —— 恰恰是最该干净的那一种情况。
diff "$MAN_PREV" "$MAN_NEW" > "$DIFF"
man_diff_rc=$?
man_added=$(awk '/^>/{n++} END{print n+0}' "$DIFF")
man_removed=$(awk '/^</{n++} END{print n+0}' "$DIFF")

{
echo "=== 远端全回归 R3（244.82 **落账后**的账本 —— 验本次提交里的那份字节）==="
echo "host=$(hostname)  date=$(date '+%F %T')  root=$ROOT"
echo "python=$($PY -V 2>&1)  nproc=$(nproc)  load=$(cat /proc/loadavg | cut -d' ' -f1-3)"
echo "fs=$(df -T $ROOT | tail -1)"
echo "n_exec_py=$(wc -l < "$MAN_NEW")  md5_manifest=$MAN_NEW  manifest_md5=$(md5sum "$MAN_NEW" | cut -d' ' -f1)"
echo "manifest_diff_rc=$man_diff_rc  added=$man_added  removed=$man_removed  (对 R2 清单 ⇒ 期望 2/0)"
echo "--- 清单 diff（对 R2）---"
cat "$DIFF"
echo "--- 账本（= 追加 244.82 之后的那份）---"
echo "ledger_lines=$(wc -l < "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md")  ledger_md5=$(md5sum "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d' ' -f1)"
echo "index_lines=$(wc -l < "$ROOT/.cache/xcheck/R6_RERUN_INDEX.md")  index_md5=$(md5sum "$ROOT/.cache/xcheck/R6_RERUN_INDEX.md" | cut -d' ' -f1)"
echo "--- 本轮新增的执行集文件（md5 逐位对上）---"
for f in $NEW_FILES; do
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
