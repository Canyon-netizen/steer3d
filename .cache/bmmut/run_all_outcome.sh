#!/bin/bash
# ⚠ 这个汇总曾经**永远**说成功，有两个独立原因，都已修：
#   ① 不给参数时 for m in "$@" 是空循环 —— 我跑了一次 `run_all_outcome.sh BASE`，
#      以为在跑全量，实际只跑了 1 条，日志里只有一段 BASE 就 ALL DONE。
#      ⇒ 现在一个参数都不给就直接报错退出。
#   ② `$PY ... | grep ...` 的退出码是 **grep 的**，python 判红/崩/没跑
#      在这里全变成 0 ⇒ 外层 EXIT=0 什么都不代表。
#      ⇒ 现在用 PIPESTATUS[0] 取 python 自己的码，并累计失败数。
cd /Users/zhourui/code/steer3d || exit 1

if [ "$#" -eq 0 ]; then
    echo "ABORT: 没给变异名。空跑会打出一行 ALL DONE，看着像跑完了。"
    echo "用法: bash .cache/bmmut/run_all_outcome.sh BASE O1 N5"
    exit 2
fi

PY=.cache/venv3d/bin/python
bad=0
ran=0
for m in "$@"; do
    echo "########## $m ##########"
    $PY .cache/bmmut/run_mut_outcome.py "$m" > ".cache/bmmut/out/$m.out" 2>&1
    rc=${PIPESTATUS[0]}
    ran=$((ran + 1))
    grep -E "^\s+\[|^===|RESULT|ABORT|frontend|build failed" ".cache/bmmut/out/$m.out"
    if [ "$rc" -ne 0 ]; then
        bad=$((bad + 1))
        echo "    [HARNESS] run_mut_outcome.py $m 退出码 $rc  ← 判红 / 崩 / 没跑，在这里"
    fi
    echo ""
done
echo "########## SUMMARY: 跑了 $ran 条，非零退出 $bad 条 ##########"
[ "$bad" -eq 0 ] || exit 1
