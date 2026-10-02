#!/bin/bash
# 整套变异测试的入口。
#
# 为什么不再在这里一次跑完：整套跑一次超过 290s，会被 bash 工具超时砍掉，
# 连同全部输出一起丢失 —— 跑完只知道"超时了"，不知道跑到第几条。
# 所以真正的逻辑在 mut_one.sh（单条、可重跑、每条留档到 .cache/wsmut2/<M>.out），
# 这里只负责逐条调用并汇总。
#
# 用法:  bash .cache/browser_verify/mutate_ws_endpoint.sh
set -u
cd /Users/zhourui/code/steer3d

ONE=".cache/browser_verify/mut_one.sh"
pass=0
fail=0

for m in M1 M2 M3; do
  if bash "$ONE" "$m" >/dev/null 2>&1; then
    echo "[OK]   $m  变异打断了目标判据"
    pass=$((pass+1))
  else
    echo "[BAD]  $m  目标判据没红 —— 该判据在变异下不变红，不算数"
    echo "       详见 .cache/wsmut2/$m.out"
    fail=$((fail+1))
  fi
done

echo ""
echo "=================================================="
echo "变异测试：$pass 通过 / $fail 失败（$fail 应为 0）"
echo "=================================================="
[ "$fail" -eq 0 ]
