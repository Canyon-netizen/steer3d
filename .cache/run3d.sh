#!/bin/bash
# 启动 3D WebSocket 后端。
#
# 为什么需要这个脚本而不是直接 `uvicorn server:app`：
#
#  1. 默认端口 8000 常被无关进程占用（本机就撞上一个 python http.server
#     目录列表），而沙箱禁止所有信号，端口一旦占住就永不释放 —— kill 报
#     "Operation not permitted"。所以这里自动挑一个真正空闲的端口。
#  2. 解释器不是系统的 python3。系统 3.9.6 没装 fastapi；依赖装在
#     仓库内的 .cache/venv3d 里，不污染全局环境。
#  3. 前端已经改成运行时探测端口（frontend/lib/ws-endpoint.ts），只要后端
#     在候选列表 [8000,8001,8010,8100,8200,8300] 里就能自动接上。
#
# 用法：  .cache/run3d.sh          # 自动选端口
#         .cache/run3d.sh 8300     # 指定端口
set -u

REPO="/Users/zhourui/code/steer3d"
VENV="$REPO/.cache/venv3d/bin/python"
BACKEND="$REPO/backend"

if [ ! -x "$VENV" ]; then
  echo "FATAL: 解释器不存在 $VENV" >&2
  echo "先跑: /usr/bin/python3 -m venv .cache/venv3d && .cache/venv3d/bin/pip install -r backend/requirements.txt" >&2
  exit 3
fi

if ! "$VENV" -c "import fastapi, uvicorn, websockets, numpy" 2>/dev/null; then
  echo "FATAL: 依赖未装齐（fastapi/uvicorn/websockets/numpy）" >&2
  echo "跑: .cache/venv3d/bin/pip install -r $BACKEND/requirements.txt" >&2
  exit 3
fi

pick_port() {
  local want="${1:-}"
  if [ -n "$want" ]; then
    if lsof -nP -iTCP:"$want" -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "FATAL: 端口 $want 已被占用" >&2
      exit 4
    fi
    echo "$want"
    return
  fi
  for p in 8200 8000 8001 8300 8400 8500; do
    if ! lsof -nP -iTCP:"$p" -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "$p"
      return
    fi
  done
  echo "FATAL: 候选端口全被占用" >&2
  exit 4
}

PORT="$(pick_port "${1:-}")"
cd "$BACKEND" || exit 5

echo "backend  = $BACKEND"
echo "port     = $PORT"
echo "ws       = ws://127.0.0.1:$PORT/ws"
echo "runner   = SyntheticRunner (no torch needed)"

# 绑 127.0.0.1：前端用 window.location.hostname 探测，不该暴露到局域网。
exec "$VENV" -m uvicorn server:app --host 127.0.0.1 --port "$PORT"
