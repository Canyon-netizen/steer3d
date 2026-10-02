#!/bin/bash
# 单独跑一条变异并留档。用法: .cache/browser_verify/mut_one.sh M1
# 整套跑一次超过 290s 会被 bash 工具超时砍掉、丢掉全部输出，
# 所以拆成独立可重跑的单条。
set -u
cd /Users/zhourui/code/steer3d
WHICH="${1:-M1}"
OUT="$PWD/.cache/wsmut2/$WHICH.out"
mkdir -p "$PWD/.cache/wsmut2"

case "$WHICH" in
  M1) DESC="Frame.to_dict() 不再带 kind"; EXPECT=P8; PORT=8701; MARK='return asdict(self)'
      REWRITE='.cache/venv3d/bin/python .cache/wsmut2/m1.py' ;;
  M2) DESC="后端 /ws 路由改名";         EXPECT=P1; PORT=8702; MARK='ws-gone'
      REWRITE='.cache/venv3d/bin/python .cache/wsmut2/m2.py' ;;
  M3) DESC="后端忽略 start 指令";       EXPECT=P7; PORT=8703; MARK='and False'
      REWRITE='.cache/venv3d/bin/python .cache/wsmut2/m3.py' ;;
  *)  echo "未知变异 $WHICH"; exit 2 ;;
esac

BAK="$PWD/.cache/wsmut2"
PY="$PWD/.cache/venv3d/bin/python"
TRASH="/Users/zhourui/.minimax/bin/mavis-trash"

restore() {
  [ -f "$BAK/protocol.py" ] && cp "$BAK/protocol.py" backend/core/protocol.py
  [ -f "$BAK/server.py" ] && cp "$BAK/server.py" backend/server.py
  for d in backend/core/__pycache__ backend/__pycache__; do
    [ -d "$d" ] && "$TRASH" -- "$d" >/dev/null 2>&1
  done
  echo "  已还原"
}

{
  echo "=== $WHICH: $DESC ==="
  echo "期望 $EXPECT 变红"

  if ! grep -q 'return {"kind": "frame", \*\*asdict(self)}' backend/core/protocol.py; then
    echo "[ABORT] 基线不对：protocol.py 里没有 kind 修复，先重建基线"
    exit 3
  fi
  cp backend/core/protocol.py "$BAK/protocol.py"
  cp backend/server.py "$BAK/server.py"

  eval "$REWRITE" || { echo "[ABORT] 改写脚本失败"; restore; exit 3; }
  if ! grep -q "$MARK" backend/core/protocol.py backend/server.py 2>/dev/null; then
    echo "[ABORT] 变异没落到文件上（标记 '$MARK' 未命中）"
    restore; exit 3
  fi
  echo "  变异已写入源码"

  for d in backend/core/__pycache__ backend/__pycache__; do
    [ -d "$d" ] && "$TRASH" -- "$d" >/dev/null 2>&1
  done
  ( cd backend && nohup "$PY" -m uvicorn server:app --host 127.0.0.1 --port "$PORT" \
      > "$BAK/srv_$PORT.log" 2>&1 & )

  # 探活用 HTTP /health，不能用 /ws 握手：
  # M2 恰恰是把 /ws 改名的那一条，等握手会白等 25 秒然后误报"没起来"。
  up=0
  for i in $(seq 1 25); do
    if curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/health" 2>/dev/null; then
      up=1; break
    fi
    if grep -q "Errno 48" "$BAK/srv_$PORT.log" 2>/dev/null; then
      echo "[ABORT] 端口 $PORT 已被占用（沙箱里端口不释放）。换一个端口重跑。"
      tail -3 "$BAK/srv_$PORT.log" | sed 's/^/      /'
      restore; exit 3
    fi
    sleep 1
  done
  if [ "$up" -ne 1 ]; then
    echo "[ABORT] 变异后端没起来"
    tail -6 "$BAK/srv_$PORT.log" 2>/dev/null | sed 's/^/      /'
    restore; exit 3
  fi
  echo "  变异后端在 $PORT 监听（HTTP 探活通过）"

  T3D_URL=http://127.0.0.1:3055/ \
  T3D_PROFILE="$BAK/prof_$PORT" \
  T3D_PORT="$PORT" \
  node .cache/browser_verify/verify_ws_endpoint.mjs 2>&1 | grep -E '^\[PASS\]|^\[FAIL\]'

  restore
} 2>&1 | tee "$OUT"

if grep -q "\[FAIL\] $EXPECT" "$OUT"; then
  echo "RESULT=$WHICH OK ($EXPECT 变红)"
  exit 0
else
  echo "RESULT=$WHICH BAD ($EXPECT 没红)"
  exit 1
fi
