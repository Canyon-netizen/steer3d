#!/bin/bash
# ⚖⚖⚖ 244.93 的**远端全回归（R12）**：验**追加 244.93 段之后**的账本 ＋ 本轮新增的执行集文件
#
# ⚖⚖⚖ **R12 与前几轮的关系**
#   R11（`_run_24492_reg_shm.sh`）：账本 = 追加 244.92 之后的那版
#   R12（本文件）：账本 = **追加 244.93 之后**的那版 ＝ **本次提交里的那份**
#   ⇒ ⇒ 清单 diff 对 **R11** ⇒ ⇒ 期望 **added=2 / removed=0**
#
# ⚖⚖⚖ **added 为什么是 2**（与 R11 同型）
#   ① `doc_dose_axis_audit.py`      —— 本轮的新实现（它带 `--selftest` ⇒ 进**自检族**）
#   ② `mut_doc_dose_axis_audit.py`  —— 它的变异台（进**变异台族**）
#   （`_cross_check_24493.py` / `_spec_crosscheck_24493.py` / `_append_24493.py` 带 `_` 前缀 ⇒ ⛔ 不进执行集）
#
# ⚖⚠ **只读 NFS、只写 tmpfs**：账本/索引/新文件/页面/预登记从 DEV 拷进树，跑完回执留在树里。
#   ⛔ 不碰 bpath、⛔ 不起 GPU、⛔ 不改任何被测文件。
#
# ⚖⚖⚖ **期望值一律手写在本文件里**（⛔ 不从被检对象/上一轮输出里推导）
#   ⇒ ⇒ 否则「期望」会跟着「实现」一起变 ⇒ ⇒ 恒绿 ⇒ ⇒ 没有闸门能抓。
#   ⚖ 本轮的期望**不是推出来的**，是**上一轮的 + 本轮新增的那几个**（手写）：
#     R11：n_exec=140 / 变异台 57/57 / 自检 54/54
#     R12：140 + 2 = 142 ｜ 57 + 1 = 58/58 ｜ 54 + 1 = 55/55
set -u

ROOT=${ROOT:-/dev/shm/s24480r}
DEV=${DEV:-/home/zhourui/steer3d}
R244=$ROOT/.cache/r244
OUT=$ROOT/reg_24493.txt
MAN_NEW=$ROOT/_md5_exec_24493.txt
MAN_PREV=$ROOT/_md5_exec_24492.txt
DIFF=$ROOT/manifest_diff_24493.txt
PY=/home/zhourui/miniconda3/envs/easysteer/bin/python

# ---- 手写的期望值（⛔ 不许现场算）----
EXPECT_LEDGER_MD5=${EXPECT_LEDGER_MD5:-8dd319628194740bf8df5e4d3eb3a923}
EXPECT_LEDGER_LINES=${EXPECT_LEDGER_LINES:-42608}
EXPECT_INDEX_MD5=${EXPECT_INDEX_MD5:-b65af171bef07d62c350c87b8897fd0c}
EXPECT_INDEX_LINES=${EXPECT_INDEX_LINES:-407}
EXPECT_ADDED=${EXPECT_ADDED:-2}
EXPECT_REMOVED=${EXPECT_REMOVED:-0}
EXPECT_N_EXEC=${EXPECT_N_EXEC:-142}
EXPECT_MUT_GREEN=${EXPECT_MUT_GREEN:-58}     # 变异台：全绿数（= 跑得动数）
EXPECT_MUT_TOTAL=${EXPECT_MUT_TOTAL:-58}
EXPECT_ST_GREEN=${EXPECT_ST_GREEN:-55}       # 自检：全绿数（= 跑得动数）
EXPECT_ST_TOTAL=${EXPECT_ST_TOTAL:-55}

# 本轮**新增**的执行集文件（必须逐位对账 DEV↔树）
NEW_FILES="doc_dose_axis_audit.py mut_doc_dose_axis_audit.py"

fail() { echo "⛔ $*" >&2; exit 3; }

[ -d "$ROOT" ] || fail "树不存在：$ROOT"
[ -f "$MAN_PREV" ] || fail "缺上一轮清单：$MAN_PREV"
[ -x "$PY" ] || fail "解释器不存在：$PY"

# ---- 1) 同步账本 ＋ 索引 ＋ 本轮新增的执行集文件 ＋（页面与预登记，供数据层对账）
cp "$DEV/.cache/xcheck/R6_RERUN_PREREG.md" "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" || exit 2
cp "$DEV/.cache/xcheck/R6_RERUN_INDEX.md"  "$ROOT/.cache/xcheck/R6_RERUN_INDEX.md"  || exit 2
cp "$DEV/.cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md" "$ROOT/.cache/xcheck/R6_CONFIDENCE_LEVEL_PREREG.md" || exit 2
cp "$DEV/.cache/xcheck/R6_DOSE_AXIS_DOC_PREREG.md" "$ROOT/.cache/xcheck/R6_DOSE_AXIS_DOC_PREREG.md" || exit 2
mkdir -p "$ROOT/docs"
cp "$DEV/.cache/r244/_page_24493.md" "$ROOT/docs/BPATH_VERDICT.md" || exit 2
cp "$DEV/.cache/r244/_page_24493.md" "$R244/_page_24493.md" || exit 2
for f in $NEW_FILES; do
  cp "$DEV/.cache/r244/$f" "$R244/$f" || fail "同步 $f 失败"
done

# ⚖⚖⚖ 账本**逐位对账**：DEV 的账本必须等于**手写的期望 md5**（杜绝「同步错版本」）
LED_MD5=$(md5sum "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d' ' -f1)
DEV_MD5=$(md5sum "$DEV/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d' ' -f1)
[ "$LED_MD5" = "$EXPECT_LEDGER_MD5" ] || fail "树里的账本 md5=${LED_MD5} ≠ 期望=${EXPECT_LEDGER_MD5} ⇒ ⛔ 硬停"
[ "$LED_MD5" = "$DEV_MD5" ] || fail "树里的账本(${LED_MD5}) 与 DEV(${DEV_MD5}) 不一致 ⇒ ⛔ 硬停"
LED_LINES=$(wc -l < "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md")
[ "$LED_LINES" = "$EXPECT_LEDGER_LINES" ] || fail "账本行数=${LED_LINES} ≠ 期望=${EXPECT_LEDGER_LINES} ⇒ ⛔ 硬停"
echo "sync_ok: 账本 md5=${LED_MD5} 行=${LED_LINES}（= 手写的期望值）"

# ⚖ 索引同样逐位对账
IDX_MD5=$(md5sum "$ROOT/.cache/xcheck/R6_RERUN_INDEX.md" | cut -d' ' -f1)
IDX_LINES=$(wc -l < "$ROOT/.cache/xcheck/R6_RERUN_INDEX.md")
[ "$IDX_MD5" = "$EXPECT_INDEX_MD5" ] || fail "索引 md5=${IDX_MD5} ≠ 期望=${EXPECT_INDEX_MD5} ⇒ ⛔ 硬停"
[ "$IDX_LINES" = "$EXPECT_INDEX_LINES" ] || fail "索引行数=${IDX_LINES} ≠ 期望=${EXPECT_INDEX_LINES} ⇒ ⛔ 硬停"
echo "sync_ok: 索引 md5=${IDX_MD5} 行=${IDX_LINES}（= 手写的期望值）"

# ⚖⚖⚖ 新字节的**特征**：账本里必须**恰好一处** 244.93 段（⇒ 验的是「追加后」那份，不是旧的）
N_2493=$(grep -c '^## 修订 244\.93 ' "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md")
[ "$N_2493" = "1" ] || fail "账本里「## 修订 244.93 」出现 ${N_2493} 次（期望 1）⇒ ⛔ 硬停"
echo "sync_ok: 账本里 244.93 段恰好 1 处（行 $(grep -n '^## 修订 244\.93 ' "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d: -f1)）"
N_2492=$(grep -c '^## 修订 244\.92 ' "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md")
[ "$N_2492" = "1" ] || fail "账本里「## 修订 244.92 」出现 ${N_2492} 次（期望 1）⇒ ⛔ 硬停"
echo "sync_ok: 账本里 244.92 段仍恰好 1 处（行 $(grep -n '^## 修订 244\.92 ' "$ROOT/.cache/xcheck/R6_RERUN_PREREG.md" | cut -d: -f1)）"

# ⚖ 本轮新增的执行集文件：DEV↔树**逐位对账**
for f in $NEW_FILES; do
  a=$(md5sum "$DEV/.cache/r244/$f" | cut -d' ' -f1)
  b=$(md5sum "$R244/$f" | cut -d' ' -f1)
  [ "$a" = "$b" ] || fail "DEV 与树的 ${f} **不一致**（DEV=${a} 树=${b}）⇒ ⛔ 硬停"
  echo "sync_ok: ${f} DEV↔树逐位一致（md5=${a}）"
done

cd "$ROOT" || exit 2

# ---- 2) 执行集清单（规则与前几轮同：`.cache/r244` 下不以 `_` 开头的 .py）
find "$R244" -type f -name '*.py' ! -path '*/__pycache__/*' -printf '%P\n' \
  | grep -v '^_' | LC_ALL=C sort \
  | while read -r f; do
      printf '%s  %s\n' "$(md5sum "$R244/$f" | cut -d' ' -f1)" "$f"
    done > "$MAN_NEW"

# ---- 3) 清单 diff：**对 R11 的清单** ⇒ ⇒ 期望 added=2 / removed=0
diff "$MAN_PREV" "$MAN_NEW" > "$DIFF"
man_diff_rc=$?
man_added=$(awk '/^>/{n++} END{print n+0}' "$DIFF")
man_removed=$(awk '/^</{n++} END{print n+0}' "$DIFF")
n_exec=$(wc -l < "$MAN_NEW")

[ "$man_added" = "$EXPECT_ADDED" ] || fail "清单 added=${man_added} ≠ 期望=${EXPECT_ADDED} ⇒ ⛔ 硬停"
[ "$man_removed" = "$EXPECT_REMOVED" ] || fail "清单 removed=${man_removed} ≠ 期望=${EXPECT_REMOVED} ⇒ ⛔ 硬停"
[ "$n_exec" = "$EXPECT_N_EXEC" ] || fail "执行集个数=${n_exec} ≠ 期望=${EXPECT_N_EXEC} ⇒ ⛔ 硬停"

{
  echo "=== 远端全回归 R12（244.93 **落账后**的账本 —— 验本次提交里的那份字节）==="
  echo "host=$(hostname)  date=$(date '+%F %T')  root=$ROOT"
  echo "python=$($PY -V 2>&1)  nproc=$(nproc)  load=$(cut -d' ' -f1-3 /proc/loadavg)"
  echo "n_exec_py=$n_exec  md5_manifest=$MAN_NEW  manifest_md5=$(md5sum "$MAN_NEW" | cut -d' ' -f1)"
  echo "manifest_diff_rc=$man_diff_rc  added=$man_added  removed=$man_removed  (对 R11 清单 ⇒ 期望 2/0)"
  echo "--- 清单 diff（对 R11）---"
  cat "$DIFF"
  echo "--- 账本（= 追加 244.93 之后的那份）---"
  echo "ledger_lines=$LED_LINES  ledger_md5=$LED_MD5"
  echo "index_lines=$IDX_LINES  index_md5=$IDX_MD5"
  echo "n_24493_section=$N_2493  n_24492_section=$N_2492"
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

# ---- 5) ⚖⚖⚖ 硬门：rc 必须 0、零 BAD、两个族的绿数必须等于手写的期望
BAD_N=$(grep -c '\[BAD\]' "$OUT")
SUMMARY=$(grep -E "小结：变异台" "$OUT" | tail -1)
MUT_G=$(printf '%s' "$SUMMARY" | sed -n 's/.*变异台 全绿 \([0-9]*\) \/ 跑得动 \([0-9]*\).*/\1/p')
MUT_R=$(printf '%s' "$SUMMARY" | sed -n 's/.*变异台 全绿 \([0-9]*\) \/ 跑得动 \([0-9]*\).*/\2/p')
ST_G=$(printf '%s' "$SUMMARY" | sed -n 's/.*自检 全绿 \([0-9]*\) \/ 跑得动 \([0-9]*\).*/\1/p')
ST_R=$(printf '%s' "$SUMMARY" | sed -n 's/.*自检 全绿 \([0-9]*\) \/ 跑得动 \([0-9]*\).*/\2/p')
{
  echo "--- R12 硬门 ---"
  echo "REG_RC=$rc  BAD_n=$BAD_N"
  echo "小结原文：$SUMMARY"
  echo "变异台 全绿=${MUT_G} 跑得动=${MUT_R} （期望 ${EXPECT_MUT_GREEN}/${EXPECT_MUT_TOTAL}）"
  echo "自检   全绿=${ST_G} 跑得动=${ST_R} （期望 ${EXPECT_ST_GREEN}/${EXPECT_ST_TOTAL}）"
} >> "$OUT"

GATE_RC=0
[ "$rc" = "0" ] || { echo "⛔ harness rc=${rc} ≠ 0" | tee -a "$OUT" >&2; GATE_RC=3; }
[ "$BAD_N" = "0" ] || { echo "⛔ 输出里有 ${BAD_N} 处 [BAD]" | tee -a "$OUT" >&2; GATE_RC=3; }
[ "$MUT_G" = "$EXPECT_MUT_GREEN" ] && [ "$MUT_R" = "$EXPECT_MUT_TOTAL" ] \
  || { echo "⛔ 变异台 ${MUT_G}/${MUT_R} ≠ 期望 ${EXPECT_MUT_GREEN}/${EXPECT_MUT_TOTAL}" | tee -a "$OUT" >&2; GATE_RC=3; }
[ "$ST_G" = "$EXPECT_ST_GREEN" ] && [ "$ST_R" = "$EXPECT_ST_TOTAL" ] \
  || { echo "⛔ 自检 ${ST_G}/${ST_R} ≠ 期望 ${EXPECT_ST_GREEN}/${EXPECT_ST_TOTAL}" | tee -a "$OUT" >&2; GATE_RC=3; }
echo "GATE_RC=$GATE_RC" >> "$OUT"

echo "R12 跑完：rc=$rc ｜ 硬门 rc=$GATE_RC ｜ $OUT"
[ "$GATE_RC" = "0" ] || exit "$GATE_RC"
exit $rc
