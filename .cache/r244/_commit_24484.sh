#!/bin/bash
# ⚖ 244.84 的**提交链**：落账 → 重建索引 → 重生成提交信息 ⇒ 显式路径入库 ⇒ 提交
#   ⇒ 提交后生成交接 ⇒ **双回读**
# ⛔ 不用 `git add -A`、⛔ 不加整个目录、⛔ 只带下面这张**显式清单**
set -u
cd /Users/zhourui/code/steer3d || exit 2

PATHS=(
  ".cache/r244/alignment_distribution_audit.py"
  ".cache/r244/mut_alignment_distribution_audit.py"
  ".cache/r244/_cross_check_24484.py"
  ".cache/r244/_spec_crosscheck_24484.py"
  ".cache/r244/_run_24484_verify.sh"
  ".cache/r244/_run_24484_reg_shm.sh"
  ".cache/r244/_append_24484.py"
  ".cache/r244/_commit_msg_24484.py"
  ".cache/r244/_make_handoff_24484.py"
  ".cache/r244/_gen_readback_24484.py"
  ".cache/r244/_post_commit_readback_24484.py"
  ".cache/r244/_commit_24484.sh"
  ".cache/xcheck/R6_ALIGNMENT_DISTRIBUTION_PREREG.md"
  ".cache/xcheck/R6_RERUN_PREREG.md"
  ".cache/xcheck/R6_RERUN_INDEX.md"
)

echo "=== 1) 落账（只追加；⛔ 幂等闸会拦重复）==="
python3 .cache/r244/_append_24484.py || { echo "⛔ 落账失败"; exit 3; }

echo
echo "=== 2) 重建索引 ==="
python3 .cache/mutbak/r100_build_index.py || { echo "⛔ 索引重建失败"; exit 3; }

echo
echo "=== 3) 生成双回读的期望值（⛔ 必须**在提交之前**）==="
python3 .cache/r244/_gen_readback_24484.py || { echo "⛔ 生成期望值失败"; exit 3; }

echo
echo "=== 4) 重生成提交信息（吃收据，⛔ 不手抄）==="
python3 .cache/r244/_commit_msg_24484.py || { echo "⛔ 提交信息生成失败"; exit 3; }

echo
echo "=== 5) 显式路径入库 ==="
for p in "${PATHS[@]}"; do
  if [ ! -f "${p}" ]; then echo "⛔ 缺文件：${p}"; exit 3; fi
  git add -f -- "${p}" || { echo "⛔ git add 失败：${p}"; exit 3; }
  echo "  staged: ${p}"
done

echo
echo "=== 6) 核对索引（⛔ 不能把别人的东西带进去）==="
git diff --cached --name-only > .cache/r244/_staged_24484.txt
n_expected="${#PATHS[@]}"
n_got="$(grep -c "" .cache/r244/_staged_24484.txt)"
echo "期望 ${n_expected} 条 ｜ 实得 ${n_got} 条"
if [ "${n_expected}" != "${n_got}" ]; then
  echo "⛔ 暂存条数对不上 ⇒ 中止"; exit 4
fi
for p in "${PATHS[@]}"; do
  grep -qx -- "${p}" .cache/r244/_staged_24484.txt || { echo "⛔ 暂存清单里没有：${p}"; exit 4; }
done
while read -r q; do
  hit=0
  for p in "${PATHS[@]}"; do
    [ "${q}" = "${p}" ] && hit=1 && break
  done
  [ "${hit}" = "1" ] || { echo "⛔ 暂存清单里有清单外的路径：${q} ⇒ 中止"; exit 4; }
done < .cache/r244/_staged_24484.txt
echo "✅ 暂存清单与显式清单**逐条一致**"

echo
echo "=== 7) 提交（⛔ 提交**索引**，不用路径参数 ⇒ 不会把工作区里别人的改动卷进来）==="
git commit -F .cache/r244/_commit_msg_24484.txt || { echo "⛔ 提交失败"; exit 5; }
git log --oneline -1

echo
echo "=== 8) 提交后**再生成一次**交接（内嵌 commit hash）==="
python3 .cache/r244/_make_handoff_24484.py || { echo "⛔ 交接生成失败"; exit 6; }

echo
echo "=== 9) 提交后**双回读**（账本 ＋ 索引，断言式，含「旧前缀逐字节不变」与「能红」自证）==="
python3 .cache/r244/_post_commit_readback_24484.py || { echo "⛔ 提交后双回读不过"; exit 7; }

echo
echo "DONE_COMMIT_24484"
