#!/bin/bash
# 单条变异 + 判据。用法: .cache/browser_verify/mut_bm.sh M1
#
# 整套六条跑完超过 280s，bash 工具会超时砍掉并丢掉全部输出。所以拆成单条。
# 每条都必须满足三件事，缺一条就说明这条变异不算数：
#   1. 锚点 assert 通过（变异真的落到文件上）
#   2. 变异后的判据真的变红（不是脚本崩了）
#   3. 源码被还原（否则下一条测的是上一条的残留）
set -u
cd /Users/zhourui/code/steer3d

M="${1:-M1}"
HTML="frontend/public/latent/index.html"
BAK="$PWD/.cache/bmmut"
mkdir -p "$BAK"
cp "$HTML" "$BAK/index.html.pristine"

case "$M" in
  M1) D="boot() 不再加载叙述性数据（还原真实事故）"; E=B1; K="MUT_NO_NARRATIVE" ;;
  M2) D="删掉「零空间是空的」";                     E=B2; K="MUT_ZEROSPACE" ;;
  M3) D="条件数字段名取错（cond→condition）";       E=B3; K="rk.condition" ;;
  M4) D="厚锥/薄锥合并成一行";                     E=B4; K="MUT_MERGED" ;;
  M5) D="步按钮点击无响应";                         E=B8; K="MUT_NO_OP" ;;
  M6) D="删掉「并列而不是翻转」";                   E=B9; K="MUT_TIE_GONE" ;;
  *) echo "未知变异 $M"; exit 2 ;;
esac

echo "=== $M: $D ==="
echo "  期望 $E 变红"

if ! /usr/bin/python3 "$BAK/apply_mut.py" "$M"; then
  echo "  [ABORT] 锚点 assert 失败 —— 变异没落到文件上"
  cp "$BAK/index.html.pristine" "$HTML"; exit 3
fi
if ! grep -q "$K" "$HTML"; then
  echo "  [ABORT] 标记 '$K' 未命中，改写可能没生效"
  cp "$BAK/index.html.pristine" "$HTML"; exit 3
fi
echo "  变异已写入（标记命中）"

LAT_URL=http://127.0.0.1:8917/latent/index.html \
LAT_PROFILE="$BAK/prof_$M" \
node .cache/browser_verify/verify_backmap.mjs 2>&1 \
  | grep -E '^\[PASS\]|^\[FAIL\]' > "$BAK/$M.out"

cp "$BAK/index.html.pristine" "$HTML"
echo "  源码已还原"

if grep -q "\[FAIL\] $E" "$BAK/$M.out"; then
  echo "  RESULT $M OK —— $E 变红，判据有牙齿"
  exit 0
else
  echo "  RESULT $M BAD —— $E 没红，这条判据在变异下不变红，不算数"
  sed 's/^/    /' "$BAK/$M.out"
  exit 1
fi
