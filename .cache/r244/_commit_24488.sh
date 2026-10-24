#!/usr/bin/env bash
# =============================================================================
# _commit_24488.sh —— 244.88 的**提交**（⛔ 只带显式路径 ＋ 提交前逐条核对索引）
#
# ⚖⚖⚖ **纪律**
#   ① ⛔ **不用 `git add -A` / `git add .`** ⇒ ⇒ 只 `git add -f` **显式路径**
#      （`.cache/` 在 .gitignore 里 ⇒ ⇒ 新文件必须 `-f`；⛔ 但绝不用 `-A` 兜底）
#   ② ⛔ **提交前逐条核对 `git diff --cached --name-only`**
#      ⇒ ⇒ `git commit -F msg` 会提交**整个索引**（会把**别人已暂存**的文件一起带走）
#      ⇒ ⇒ 唯一的共同前提就是**核对**这一步
#   ③ ⛔ **不碰**工作区里同事的两处已跟踪改动（`backend/examples/build_circuit_landscape.py`、
#      `frontend/components/CircuitLandscape.tsx`）与那些未跟踪文件
#   ④ ⛔ 交接文件 `.cache/xcheck/HANDOFF_24488.md` **不入库**（按惯例）
#
# ⚖ **用法**：bash .cache/r244/_commit_24488.sh
# =============================================================================
set -uo pipefail

REPO=/Users/zhourui/code/steer3d
cd "$REPO" || exit 2

MSG=.cache/r244/_commit_msg_24488.txt

# ⚖⚖⚖ **本次提交的 15 条路径**（⛔ 与 `_post_commit_readback_24488.py` 的 WHITELIST 一致）
PATHS=(
  ".cache/r244/conservative_bound_audit.py"
  ".cache/r244/mut_conservative_bound_audit.py"
  ".cache/r244/_cross_check_24488.py"
  ".cache/r244/_spec_crosscheck_24488.py"
  ".cache/r244/_run_24488_verify.sh"
  ".cache/r244/_run_24488_reg_shm.sh"
  ".cache/r244/_append_24488.py"
  ".cache/r244/_commit_msg_24488.py"
  ".cache/r244/_make_handoff_24488.py"
  ".cache/r244/_gen_readback_24488.py"
  ".cache/r244/_post_commit_readback_24488.py"
  ".cache/r244/_commit_24488.sh"
  ".cache/xcheck/R6_CONSERVATIVE_BOUND_PREREG.md"
  ".cache/xcheck/R6_RERUN_PREREG.md"
  ".cache/xcheck/R6_RERUN_INDEX.md"
)

echo "════ 1) 生成提交信息 ════"
python3 .cache/r244/_commit_msg_24488.py || exit 3
[ -s "$MSG" ] || { echo "⛔ 提交信息是空的 ⇒ 中止"; exit 3; }
head -1 "$MSG"

echo ""
echo "════ 2) 核对工作区（⛔ 同事的改动必须原样还在）════"
git status --porcelain | grep -E "build_circuit_landscape|CircuitLandscape" \
  && echo "  （上面两处是同事的改动 ⇒ 本脚本**绝不**碰它们）"

echo ""
echo "════ 3) 只 add 显式路径（-f：.cache/ 在 .gitignore 里）════"
for p in "${PATHS[@]}"; do
  [ -f "$p" ] || { echo "⛔ 缺文件：$p ⇒ 中止"; exit 3; }
  git add -f "$p" || { echo "⛔ git add 失败：$p ⇒ 中止"; exit 3; }
done
echo "  已 add ${#PATHS[@]} 条显式路径"

echo ""
echo "════ 4) 逐条核对索引（⛔ 这一步是唯一的保险）════"
# ⚖⚖⚖ **纯内存比较**（⛔ 不用临时文件：⛔ 本机 /tmp 不可写 ⇒ ⇒ 写临时文件会**假红**）
GOT=$(git diff --cached --name-only | LC_ALL=C sort)
WANT=$(printf '%s\n' "${PATHS[@]}" | LC_ALL=C sort)
echo "  索引里现有 $(printf '%s\n' "$GOT" | grep -c .) 条："
printf '%s\n' "$GOT" | sed 's/^/    /'
if [ "$GOT" != "$WANT" ]; then
  echo ""
  echo "⛔ 索引里的路径 ≠ 期望的 ${#PATHS[@]} 条 ⇒ ⇒ **中止提交**"
  echo "   —— 差异（< 只有索引里有 / > 只有期望里有）："
  diff <(printf '%s\n' "$WANT") <(printf '%s\n' "$GOT") | sed 's/^/    /'
  echo "   （⛔ 绝不在有别人已暂存文件的情况下提交）"
  exit 4
fi
echo ""
echo "  ✅ 索引逐条核对通过：正好 ${#PATHS[@]} 条，与期望一致"

echo ""
echo "════ 5) 提交 ════"
git commit -F "$MSG" || { echo "⛔ commit 失败"; exit 5; }
echo ""
git log --oneline -1

echo ""
echo "════ 6) 提交后双回读（账本 ＋ 索引 ＋ 提交清单 ＋ R9 收据）════"
python3 .cache/r244/_post_commit_readback_24488.py
rc=$?
echo ""
if [ "$rc" -eq 0 ]; then
  echo "✅ 提交后双回读全绿"
else
  echo "⛔ 提交后双回读**有红项**（rc=$rc）⇒ ⇒ 查上面的清单"
fi
exit "$rc"
