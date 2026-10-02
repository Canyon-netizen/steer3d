#!/bin/bash
# 单条变异（3D 真实回放）。用法: .cache/browser_verify/mut_3d.sh M1
#
# 关键：每条变异都必须**重启后端到新端口**，判据也要指向那个新端口。
# 改源码不影响已经在跑的 uvicorn —— 第一版没重启，判据测的还是旧进程，
# 全绿是假象。这和「改源码不会影响已运行的进程」是同一件事。
set -u
cd /Users/zhourui/code/steer3d

M="${1:-M1}"
BAK="$PWD/.cache/mut3d"
PY="$PWD/.cache/venv3d/bin/python"
TRASH="/Users/zhourui/.minimax/bin/mavis-trash"
mkdir -p "$BAK"

case "$M" in
  M1) D="退回 SyntheticRunner（原始状态）"; E=D2 ;;
  M2) D="d_model 写死 4096";               E=D2 ;;
  M3) D="层列表清空";                      E=D4 ;;
  M4) D="token 文本编造";                  E=D6 ;;
  M5) D="熵改成 sin 公式";                  E=D7 ;;
  M6) D="server 不再上报层列表";           E=D3 ;;
  *) echo "未知变异 $M"; exit 2 ;;
esac

echo "=== $M: $D ==="
echo "  期望 $E 变红"

# 备份并施加
# 目标路径写死，不用循环 + fallback：原来那个 `cp ... backend/core/$f 2>/dev/null ||
# cp ... backend/$f` 在 server.py 上先成功后失败，于是在 backend/core/ 下
# 多出一个 backend/core/server.py —— 一个没人引用的 server.py 副本。
# 脚本的还原步骤不该有能力在工作区里造出新文件。
cp backend/core/replay_runner.py "$BAK/replay_runner.py.pristine"
cp backend/core/model_runner.py  "$BAK/model_runner.py.pristine"
cp backend/server.py             "$BAK/server.py.pristine"
if ! /usr/bin/python3 "$PWD/.cache/bmmut/apply_mut3d.py" "$M"; then
  echo "  [ABORT] 锚点 assert 失败"
  cp "$BAK/replay_runner.py.pristine" backend/core/replay_runner.py
  cp "$BAK/model_runner.py.pristine" backend/core/model_runner.py
  cp "$BAK/server.py.pristine" backend/server.py
  exit 3
fi
echo "  变异已写入"

# 清字节码缓存，否则改动不生效
for d in backend/core/__pycache__ backend/__pycache__; do
  [ -d "$d" ] && "$TRASH" -- "$d" >/dev/null 2>&1
done

# 找一个空闲端口
PORT=""
for p in $(seq 9100 9200); do
  if ! lsof -nP -iTCP:$p -sTCP:LISTEN -t >/dev/null 2>&1; then PORT=$p; break; fi
done
if [ -z "$PORT" ]; then echo "  [ABORT] 没有空闲端口"; exit 3; fi

( cd backend && nohup "$PY" -m uvicorn server:app --host 127.0.0.1 --port "$PORT" \
    > "$BAK/srv_$PORT.log" 2>&1 & )
up=0
for i in $(seq 1 25); do
  if curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/health" 2>/dev/null; then up=1; break; fi
  if grep -q "Errno 48" "$BAK/srv_$PORT.log" 2>/dev/null; then
    echo "  [ABORT] 端口 $PORT 被占"; exit 3
  fi
  sleep 1
done
if [ "$up" -ne 1 ]; then
  echo "  [ABORT] 变异后端没起来"; tail -4 "$BAK/srv_$PORT.log" | sed 's/^/    /'; exit 3
fi
echo "  变异后端在 $PORT 监听"

T3D_PORT=$PORT T3D_URL=http://127.0.0.1:3066/ \
T3D_PROFILE="$BAK/prof_$M" \
node .cache/browser_verify/verify_real_replay.mjs 2>&1 \
  | grep -E '^\[PASS\]|^\[FAIL\]' > "$BAK/$M.out"

# 还原
cp "$BAK/replay_runner.py.pristine" backend/core/replay_runner.py
cp "$BAK/model_runner.py.pristine" backend/core/model_runner.py
cp "$BAK/server.py.pristine" backend/server.py
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
