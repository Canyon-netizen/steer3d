#!/bin/bash
# C0 前置：按 mut_j12.sh 里**已验证过**的配方起 next start，然后重跑两页探针。
#
# ⚠⚠⚠ 为什么不能用静态服务器（修订 188 立）
#   本轮之前有人用 `python3 -m http.server` 起在 8931 上跑过一次装置自检。
#   那个能出 `RESULT OK 36/36`，看着是通的 —— 但它**不是 next start**：
#   ⚗ 根页是 Next.js 应用，产物要经过构建期的 NEXT_PUBLIC_WS_URL 内联，
#     静态服务器直接把源码/旧产物端出去，**不代表产品真实服务的样子**。
#   ⚗ 而 C0 要验的恰恰是「WebGL 档位在两支探针里是否一致」——
#     采集环境本身不对，采出来的档位就没有意义。
#   ⇒ 本脚本只用 next start，且端口每次唯一。
#
# ⚠⚠⚠ 配方里最要紧的一条（mut_j12.sh:116-130）：
#   **curl 到 200 不能证明在服务的是本轮构建。**
#   端口上可能还挂着上一轮的 next start（它持有旧 .next 映射），
#   就绪探测会 curl 到那个旧进程返回 200，当成「新的起来了」。
#   ⇒ 必须回 chunk 里验 WS 地址。这一步把「静默挂两分钟然后印 0 帧」
#     变成「立刻失败并说清是谁在服务」。
set -u
ROOT=/Users/zhourui/code/steer3d
RUN="$ROOT/.cache/nextrun2"
LOGD="$ROOT/.cache/mutbak"
export NEXT_PUBLIC_WS_URL="${NEXT_PUBLIC_WS_URL:-ws://127.0.0.1:9505/ws}"

# 端口从 $$ 派生，每次唯一 —— 端口固定是 mut_3d.sh / mut_j12.sh 都踩过的坑。
PORT="${PORT:-$((22400 + ($$ % 300)))}"
echo "本轮端口：$PORT"

cd "$RUN" || exit 2
echo "--- 构建 ---"
npx next build > "$LOGD/_c0_build.log" 2>&1 || {
  echo "构建失败"; tail -20 "$LOGD/_c0_build.log"; exit 2; }
tail -3 "$LOGD/_c0_build.log"

echo "--- 起服务 ---"
(npx next start -p "$PORT" > "$LOGD/_c0_srv.log" 2>&1 &)
c=""
for i in $(seq 1 25); do
  c=$(curl -s -o /dev/null -m 4 -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null)
  [ "$c" = "200" ] && { echo "就绪（$((i*3))s）"; break; }
  sleep 3
done
[ "$c" = "200" ] || { echo "起不来（last=$c）"; tail -10 "$LOGD/_c0_srv.log"; exit 2; }

# ⚠⚠⚠ bundle 自证：确认端口上服务的是**本轮构建**，不是上一轮的旧进程。
CH=$(curl -s -m 20 "http://127.0.0.1:$PORT/" | grep -oE '/_next/static/chunks/app/page-[^"]+\.js' | head -1)
WS=$(curl -s -m 25 "http://127.0.0.1:$PORT$CH" | grep -oE 'ws://[0-9a-zA-Z\.\-]+:[0-9]+/ws' | sort -u | head -1)
echo "本轮服务的 chunk：$CH"
echo "该 chunk 里的 WS 地址：${WS:-（没有！）}"
if [ "$WS" != "$NEXT_PUBLIC_WS_URL" ]; then
  echo "!! 服务出去的 bundle 不含本后端的 WS 地址 ⇒ 端口 $PORT 上是**旧进程**"
  echo "   （或本轮构建漏了 NEXT_PUBLIC_WS_URL）。判据跑在它上面只会得到 0 帧。"
  echo "   ⇒ 换一个 PORT 重跑，别把这一轮的结果当判决。"
  exit 3
fi
echo "PORT=$PORT" > "$LOGD/_c0_port"
echo "BUNDLE_OK=1" >> "$LOGD/_c0_port"
echo "OK：next start 就绪且 bundle 自证通过"