#!/bin/bash
# ⚖ 244.87 的**远端全回归（R8）**：验**追加 244.87 段之后**的账本 ＋ 本轮新增的执行集文件
#
# ⚖⚖⚖⚖⚖ **R8 与前几轮的关系**
#   R6（`_run_24485_reg_shm.sh`）：账本 = 追加 244.85 之后的那版
#   R7（`_run_24486_reg_shm.sh`）：账本 = 追加 244.86 之后的那版 ＝ 244.86 那次提交里的那份
#   R8（本文件）：账本 = **追加 244.87 之后**的那版 ＝ **本次提交里的那份**
#   ⇒ ⇒ 清单 diff 对 **R7** ⇒ ⇒ 期望 **added=4 / removed=0**
#
# ⚖⚖⚖ **added 为什么是 4 而不是 2**（本轮**顺手补上的一个洞**）
#   ① `cmax_robustness_audit.py` ＋ `mut_cmax_robustness_audit.py`
#      —— 本轮的新实现 ＋ 它的变异台（⛔ `_` 开头的**不进**执行集）。
#   ② `fixed_dose_strata.py` ＋ `mut_fixed_dose_strata.py`
#      —— **R4–R7 的树里漏掉的两个已入库执行集成员**（来自 `0466c9b`）
#      ⇒ ⇒ 「全回归全绿」这句话**在这两个文件上从未成立过**
#      ⇒ ⇒ 本轮补进树 ⇒ ⇒ **R8 首次覆盖它们**（实测：变异台 14/14、自检 22/22）。
#
# ⚖⚠ **只读 NFS、只写 tmpfs**：账本/索引/新文件从 DEV 拷进树，跑完回执留在树里。
#   ⛔ 不碰 bpath、⛔ 不起 GPU、⛔ 不改任何被测文件。
set -u
ROOT=${ROOT:-/dev/shm/s24480r}
DEV=${DEV:-/home/zhourui/steer3d}
R244=$ROOT/.cache/r244
OUT=$ROOT/reg_24487.txt
MAN_NEW=$ROOT/_md5_exec_24487.txt
MAN_PREV=$ROOT/_md5_exec_24486.txt
DIFF=$ROOT/manifest_diff_24487.txt
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python
# ⚖ 期望的账本 md5（**由调用方从本地作者树算好后传进来**）⇒ ⇒ 杜绝「同步错版本」
EXPECT_LEDGER_MD5=${EXPECT_LEDGER_MD5:-}
# 本轮**新增**的执行集文件（必须逐位对账 DEV↔树）
NEW_FILES="cmax_robustness_audit.py mut_cmax_robustness_audit.py fixed_dose_strata.py mut_fixed_dose_strata.py"

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

# ---- 3) 清单 diff：**对 R7 的清单**
#   ⇒ R8 新增 4 个执行集成员 ⇒ ⇒ 期望 **added=4 / removed=0**
# ⚠⚠⚠ 这里**必须**用 awk 而不是 `grep -c ... || echo 0`：
#   `grep -c` 在**无匹配**时**照样打印 0** 并返回**非 0** ⇒ `|| echo 0` 会**再补一个 0**
diff "$MAN_PREV" "$MAN_NEW" > "$DIFF"
man_diff_rc=$?
man_added=$(awk '/^>/{n++} END{print n+0}' "$DIFF")
man_removed=$(awk '/^</{n++} END{print n+0}' "$DIFF")

{
echo "=== 远端全回归 R8（244.87 **落账后**的账本 —— 验本次提交里的那份字节）==="
echo "host=$(hostname)  date=$(date '+%F %T')  root=$ROOT"
echo "python=$($PY -V 2>&1)  nproc=$(nproc)  load=$(cat /proc/loadavg | cut -d' ' -f1-3)"
echo "fs=$(df -T $ROOT | tail -1)"
echo "n_exec_py=$(wc -l < "$MAN_NEW")  md5_manifest=$MAN_NEW  manifest_md5=$(md5sum "$MAN_NEW" | cut -d' ' -f1)"
echo "manifest_diff_rc=$man_diff_rc  added=$man_added  removed=$man_removed  (对 R7 清单 ⇒ 期望 4/0)"
echo "--- 清单 diff（对 R7）---"
cat "$DIFF"
echo "--- 账本（= 追加 244.87 之后的那份）---"
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

echo "R8 跑完：rc=$rc ｜ $OUT"
exit $rc
