#!/bin/bash
# 单条变异（轨迹选择器）。用法: .cache/browser_verify/mut_picker.sh M1
#
# 后端变异：重启到新端口即可。
# 前端变异：必须重新 next build，否则测的是旧产物 ——
#   第一版 M1 就踩了这个：nohup 的日志路径写错导致后端根本没起来，
#   判据 E7 因为「连不上」而红，看着像变异生效，实际是变异没跑起来。
#   现在每条都先探活（trajectories 数量必须符合预期）再跑判据。
set -u
cd /Users/zhourui/code/steer3d

M="${1:-M1}"
BAK="$PWD/.cache/mutpick"
PY="$PWD/.cache/venv3d/bin/python"
TRASH="/Users/zhourui/.minimax/bin/mavis-trash"
FE_PORT=$(cat .cache/port3d_fe.txt 2>/dev/null || echo 9600)
mkdir -p "$BAK"

case "$M" in
  M1) D="后端不上报轨迹清单"; E=E1; EXPECT_TRAJ=0 ;;
  M2) D="UI 无条件用文本框";   E=E1; EXPECT_TRAJ=48; NEED_BUILD=1 ;;
  M3) D="Start 用原始 localPrompt"; E=E7; EXPECT_TRAJ=48; NEED_BUILD=1 ;;
  M4) D="只报一半轨迹";       E=E2; EXPECT_TRAJ=24 ;;
  *) echo "未知变异 $M"; exit 2 ;;
esac

echo "=== $M: $D ==="
echo "  期望 $E 变红 / trajectories should be $EXPECT_TRAJ"

cp backend/server.py "$BAK/server.pristine"
cp backend/core/replay_runner.py "$BAK/runner.pristine"
cp frontend/components/ControlPanel.tsx "$BAK/panel.pristine"

if ! /usr/bin/python3 "$PWD/.cache/bmmut/apply_mut_picker.py" "$M"; then
  echo "  [ABORT] 锚点 assert 失败"
  cp "$BAK/server.pristine" backend/server.py
  cp "$BAK/runner.pristine" backend/core/replay_runner.py
  cp "$BAK/panel.pristine" frontend/components/ControlPanel.tsx
  exit 3
fi

# 后端总是重启（即使变异在前端，后端也要保证在跑）
for d in backend/core/__pycache__ backend/__pycache__; do
  [ -d "$d" ] && "$TRASH" -- "$d" >/dev/null 2>&1
done
PORT=""
for p in $(seq 9800 9860); do
  if ! lsof -nP -iTCP:$p -sTCP:LISTEN -t >/dev/null 2>&1; then PORT=$p; break; fi
done
[ -z "$PORT" ] && { echo "  [ABORT] 没有空闲端口"; exit 3; }
( cd backend && nohup "$PY" -m uvicorn server:app --host 127.0.0.1 --port "$PORT" \
    > "$BAK/srv_$PORT.log" 2>&1 & )
for i in $(seq 1 25); do
  curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/health" 2>/dev/null && break
  sleep 1
done

# 探活：必须确认这个后端真的带上了变异，否则下面的判据白跑。
ACT=$("$PY" -c "
import asyncio, json, websockets
async def m():
    try:
        async with websockets.connect('ws://127.0.0.1:$PORT/ws', open_timeout=6) as w:
            p = json.loads(await asyncio.wait_for(w.recv(), timeout=6))['payload']
            print(len(p.get('trajectories', [])))
    except Exception as e:
        print('ERR:' + type(e).__name__)
asyncio.run(m())" 2>/dev/null)
echo "  变异后端 $PORT 上 trajectories=$ACT（期望 $EXPECT_TRAJ）"
if [ "$ACT" != "$EXPECT_TRAJ" ]; then
  echo "  [ABORT] 变异后端没带上预期状态，不跑判据"
  cp "$BAK/server.pristine" backend/server.py
  cp "$BAK/runner.pristine" backend/core/replay_runner.py
  cp "$BAK/panel.pristine" frontend/components/ControlPanel.tsx
  exit 3
fi

if [ "${NEED_BUILD:-0}" = "1" ]; then
  echo "  重新构建前端（约 2 分钟）"
  ( cd frontend && npx next build > "$BAK/build.log" 2>&1 )
  if ! grep -q "Compiled successfully" "$BAK/build.log"; then
    echo "  [ABORT] 前端构建失败"; tail -6 "$BAK/build.log" | sed 's/^/    /'
    cp "$BAK/panel.pristine" frontend/components/ControlPanel.tsx
    exit 3
  fi
  kill_p=""   # next start 不会热更新，需要换端口重起
  FPORT=""
  for p in $(seq 9870 9910); do
    if ! lsof -nP -iTCP:$p -sTCP:LISTEN -t >/dev/null 2>&1; then FPORT=$p; break; fi
  done
  ( cd frontend && nohup npx next start -p "$FPORT" > "$BAK/fe.log" 2>&1 & )
  sleep 12
  FE_PORT="$FPORT"
  echo "  变异前端 $FPORT"
fi

T3D_PORT=$PORT T3D_URL=http://127.0.0.1:$FE_PORT/ T3D_PROFILE="$BAK/prof_$M" \
  node .cache/browser_verify/verify_picker.mjs 2>&1 \
  | grep -E '^\[PASS\]|^\[FAIL\]|^===' > "$BAK/$M.out"

cp "$BAK/server.pristine" backend/server.py
cp "$BAK/runner.pristine" backend/core/replay_runner.py
cp "$BAK/panel.pristine" frontend/components/ControlPanel.tsx
for d in backend/core/__pycache__ backend/__pycache__; do
  [ -d "$d" ] && "$TRASH" -- "$d" >/dev/null 2>&1
done
echo "  源码已还原"

if grep -q "\[FAIL\] $E" "$BAK/$M.out"; then
  echo "  RESULT $M OK —— $E 变红，判据有牙齿"
  exit 0
else
  echo "  RESULT $M BAD —— $E 没红，这条判据在变异下不变红，不算数"
  sed 's/^/    /' "$BAK/$M.out"
  exit 1
fi
