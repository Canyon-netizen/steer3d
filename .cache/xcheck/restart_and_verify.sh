#!/bin/bash
# 重建 → 起服务 → 跑全链。
#
# ⚠ 为什么要重建而不是直接起：
#   `.next/BUILD_ID` 的 mtime 只比 `verifyRandomControl.tsx` 新 11 秒。
#   Next 的 build 要几十秒，11 秒的差说明 build 与那次编辑**不是同一次运行**，
#   谁先谁后无法从 mtime 判定 ⇒ 可能是旧 build。
#   用一个"大概是新的" build 去验新组件，验的是**上一个版本**，
#   而它给出的绿与真版本无关 —— 与「拿 round(median,4) 比未舍入中位数」同族。
#   ⇒ 前端源码一改就重建，不赌 mtime。
#
# ⚠ 顺序：先 build，再起服务，再跑链。链自己会先跑两页探针（stage），
#   然后才跑 scan_panel_coverage —— 覆盖扫描必须读**本轮**的 DOM 快照。
PORT=${1:-22210}
ROOT=/Users/zhourui/code/steer3d
cd "$ROOT" || exit 2
LOGD=$ROOT/.cache/logs
mkdir -p "$LOGD"

echo "=== [1/4] next build ==="
( cd "$ROOT/frontend" && npx next build ) > "$LOGD/build_$PORT.log" 2>&1
rc=$?
if [ $rc -ne 0 ]; then
  echo "build 失败 exit=$rc ⇒ 后面全部不可信，停。"
  tail -25 "$LOGD/build_$PORT.log"
  exit 5
fi
grep -E "Compiled|Route \(pages\)|✓|Error" "$LOGD/build_$PORT.log" | head -8
echo "build exit=0"

echo "=== [2/4] next start -p $PORT ==="
# ⚠ 不要把 stdout 重定向到任何被测工具会自己写的文件。
( cd "$ROOT/frontend" && nohup npx next start -p "$PORT" ) > "$LOGD/next_$PORT.log" 2>&1 &
SRV=$!
echo "server pid=$SRV"
echo "$SRV" > "$LOGD/next_$PORT.pid"

ok=0
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://127.0.0.1:$PORT/" 2>/dev/null)
  if [ "$code" = "200" ]; then ok=1; break; fi
  sleep 2
done
if [ $ok -ne 1 ]; then
  echo "起不来（等了 120s）⇒ 停。"
  tail -15 "$LOGD/next_$PORT.log"
  exit 5
fi
echo "/ -> 200"

echo "=== [3/4] 三份产物可达性 ==="
for f in repetition_collapse axis_generalisation random_direction_distribution; do
  printf '  %-32s %s\n' "$f.json" \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$PORT/latent/data/$f.json")"
done
printf '  %-32s %s\n' "latent/index.html" \
  "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$PORT/latent/index.html")"

echo "=== [4/4] 全链 21 条 + 2 道装置闸 ==="
# ⚠ 不要 `> .cache/chain_one.out` —— 那是 run() 内部的临时文件，
#   重定向到它会把每条标签行覆盖掉（run_chain.sh 头部 ① 记着这个坑）。
bash "$ROOT/.cache/xcheck/run_chain.sh" "http://127.0.0.1:$PORT/"
rc=$?
echo "=== 链 exit=$rc ==="
exit $rc
