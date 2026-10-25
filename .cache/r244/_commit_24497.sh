#!/bin/bash
# ⚖⚖⚖ _commit_24497.sh —— 244.97 的**提交脚本**（⛔ 只带显式路径、⛔ 不用 git add -A / git add .）
#
# ⚖⚖⚖ **共享工作树纪律**（同事会在你工作期间提交 ⇒ ⇒ 提交前**必须**核对索引）：
#   ① **先**看索引（`git diff --cached --name-only`）⇒ ⇒ 若同事**已暂存**了东西 ⇒ ⇒ 记下来；
#   ② 只 `git add -f <显式路径>`（⛔ 不用 -A / .）；
#   ③ **逐条核对**索引 == 我要提交的路径集合 ⇒ ⇒ 不等 ⇒ ⇒ **改用路径限定提交**
#      （`git commit -F msg -- <路径>` ⇒ ⇒ 只提交我的路径，同事的暂存**原样留着**）；
#   ④ 提交后立刻 `git show --name-only` 回读 ⇒ ⇒ 核对这次提交**只带**白名单路径。
#
# ⚖⚠ **同事的未跟踪文件（40+）与 `backend/examples/build_circuit_landscape.py`、
#   `frontend/components/CircuitLandscape.tsx` 一律不碰、不提交。**
set -u

cd /Users/zhourui/code/steer3d || exit 9
MSG=.cache/r244/_msg_24497.txt

FILES=".cache/xcheck/R6_DOSE_CURVE_PREREG.md
.cache/xcheck/R6_RERUN_PREREG.md
.cache/xcheck/R6_RERUN_INDEX.md
.cache/mutbak/_idx_probe_24497.py
.cache/r244/doc_dose_curve_audit.py
.cache/r244/mut_doc_dose_curve_audit.py
.cache/r244/_cross_check_24497.py
.cache/r244/_spec_crosscheck_24497.py
.cache/r244/_run_24497_verify.sh
.cache/r244/_run_24497_reg_shm.sh
.cache/r244/_append_24497.py
.cache/r244/_verify_append_guard_24497.py
.cache/r244/_commit_msg_24497.py
.cache/r244/_make_handoff_24497.py
.cache/r244/_gen_readback_24497.py
.cache/r244/_post_commit_readback_24497.py
.cache/r244/_commit_24497.sh
docs/BPATH_VERDICT.md"

echo "──── 提交前的 HEAD ────"
git log --oneline -1

PRE=$(git diff --cached --name-only | LC_ALL=C sort)
if [ -n "$PRE" ]; then
  echo "⚠ 提交前索引里**已经有**内容（可能是同事暂存的）："
  printf '%s\n' "$PRE"
else
  echo "✅ 提交前索引是空的"
fi

python3 .cache/r244/_commit_msg_24497.py > "$MSG" || exit 2
# ⚠⚠⚖ **变量后面紧跟全角标点时必须写成 `${MSG}`**：某些 locale 下 bash 把 `：` 的首字节当成标识符字符
#    ⇒ ⇒ `$MSG（…` 被解析成变量 `MSG…` ⇒ ⇒ `set -u` 直接报 "unbound variable" ⇒ ⇒ 提交链当场断。
echo "提交信息已生成：${MSG}（$(wc -l < "$MSG") 行）"

for f in $FILES; do
  git add -f "$f" || exit 2
done

GOT=$(git diff --cached --name-only | LC_ALL=C sort)
WANT=$(printf '%s\n' $FILES | LC_ALL=C sort)
if [ "$GOT" = "$WANT" ]; then
  echo "✅ 索引 == 预期路径集合（$(printf '%s\n' "$GOT" | wc -l) 条）⇒ ⇒ 走**索引提交**"
  git commit -F "$MSG" || exit 3
else
  echo "⚠ 索引里有**预期外**的路径 ⇒ ⇒ 改走**路径限定提交**（不带走别人的暂存）"
  diff <(printf '%s\n' "$WANT") <(printf '%s\n' "$GOT") || true
  git commit -F "$MSG" -- $FILES || exit 3
fi

echo "──── 提交后回读 ────"
git log --oneline -1
git show --name-only --pretty=format: HEAD
echo ""
echo "COMMIT_RC=0"
