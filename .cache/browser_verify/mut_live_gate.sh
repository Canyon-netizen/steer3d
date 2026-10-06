#!/usr/bin/env bash
# 变异台：证明「后端在线后新解锁的 8 条」不是空转。
#
# 背景：这 8 条此前是第四态 NA（前置未建立 = 没跑），后端修好后变成真判决
# 并全绿。全绿有两种可能：(a) 它们真在验东西，(b) 门禁变空转、什么都没验。
# 本台只区分这两种。
#
# 手法：把 ready 消息里 trajectories[].id 换成裸题号（丢掉 `aime__` 前缀）。
# 这一刀正好打在 8 条的共同依赖上——选择器 <option value> 与产物
# logit_lens.json 的 id 必须逐字相同才能对账。改完之后预期：
#   F0b  页面上不再有含 `aime__` 的选项        -> 红
#   F2   选中的 id 在 logit_lens.json 查不到     -> 红
#   F9/F11/F12 换记录后链条对不上                -> 红
#
# ── 为什么本台要自己起后端和前端 ──────────────────────────────────────
# 本沙箱里 kill 别的进程会被拒（`kill -9 <pid>` → Operation not permitted），
# 所以不能「改源码→重启 9503→还原→重启」就地往返。改用**并存**：
#   · 变异体后端起在 MUT_BPORT（前端用 NEXT_PUBLIC_WS_URL 指过去）
#   · 绿体后端继续留在 9503 不动
#   · 前端各用各的构建：绿体 build→FE_GPORT，变异体 build（带 env）→FE_MPORT
# NEXT_PUBLIC_* 是**构建期内联**的，所以必须重建，不能靠运行时环境变量。
# 这也是「变异台必须还原装置状态，不只源码」——装置状态 = 源码 + .next + 端口。
#
# 用法:
#   bash .cache/browser_verify/mut_live_gate.sh apply  <MUT_BPORT> <FE_MPORT>
#   bash .cache/browser_verify/mut_live_gate.sh restore <MUT_BPORT> <FE_MPORT>
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 2

SRC="backend/core/replay_runner.py"
BAK=".cache/mutlive/replay_runner.py.bak"
VENV=".cache/venv3d/bin/python"
FE_DIR="frontend"

ANCHOR_ORIG='                    "id": rid,'
ANCHOR_MUT='                    "id": (r.get("problem_id") or rid),'

count_anchor() { grep -Fc "$1" "$SRC" 2>/dev/null | tr -d ' '; }

wait_listen() {  # $1=port  $2=描述
  for _ in $(seq 1 40); do
    [ -n "$(lsof -ti tcp:"$1" -sTCP:LISTEN 2>/dev/null | tr -d ' ')" ] && {
      echo "  [$2] 监听就绪 :$1"; return 0; }
    sleep 0.4
  done
  echo "  !! 装置故障：[$2] :$1 没起来"; return 1
}

build_and_serve() {  # $1=FE端口  $2=WS_URL(可空)  $3=描述
  if [ -n "$2" ]; then export NEXT_PUBLIC_WS_URL="$2"; else unset NEXT_PUBLIC_WS_URL; fi
  ( cd "$FE_DIR" \
    && npx next build > "$ROOT/.cache/mutlive/build-$1.log" 2>&1 \
    && nohup npx next start -p "$1" > "$ROOT/.cache/mutlive/fe-$1.log" 2>&1 & ) \
    || { echo "  !! 装置故障：[$3] 构建/启动失败"; tail -12 "$ROOT/.cache/mutlive/build-$1.log"; return 2; }
  wait_listen "$1" "[$3] FE" || return 2
}

MUT_BPORT="${2:-9504}"
FE_MPORT="${3:-22231}"

case "${1:-}" in
  apply)
    [ "$(count_anchor "$ANCHOR_ORIG")" = "1" ] || {
      echo "装置故障：锚点命中 $(count_anchor "$ANCHOR_ORIG") 次（应为 1），拒绝改"; exit 2; }
    mkdir -p .cache/mutlive
    [ -f "$BAK" ] || cp "$SRC" "$BAK"
    "$VENV" - "$SRC" "$ANCHOR_ORIG" "$ANCHOR_MUT" <<'PY'
import sys
p, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(p, encoding="utf-8").read()
n = s.count(a)
assert n == 1, f"锚点命中 {n} 次，应为 1 —— 这是无效变异，不是修复"
open(p, "w", encoding="utf-8").write(s.replace(a, b))
print(f"  变异已写入（命中 {n} 次）")
PY
    [ "$(count_anchor "$ANCHOR_MUT")" = "1" ] || { echo "装置故障：写入后读不回"; exit 2; }
    "$VENV" -c "import ast;ast.parse(open('$SRC',encoding='utf-8').read());print('  变异体 AST 过了（仍不等于能跑）')" || exit 2

    echo "  起变异体后端 :$MUT_BPORT"
    ( cd backend && nohup "../$VENV" -m uvicorn server:app --host 127.0.0.1 --port "$MUT_BPORT" \
        > "$ROOT/.cache/mutlive/backend-$MUT_BPORT.log" 2>&1 & )
    wait_listen "$MUT_BPORT" "变异体 BE" || exit 2

    echo "  重建前端（NEXT_PUBLIC_WS_URL=ws://127.0.0.1:$MUT_BPORT/ws）"
    build_and_serve "$FE_MPORT" "ws://127.0.0.1:$MUT_BPORT/ws" "变异体" || exit 2
    echo
    echo "  跑变异侧：T3D_URL=http://127.0.0.1:$FE_MPORT/ node .cache/browser_verify/verify_derivation.mjs"
    ;;
  restore)
    [ -f "$BAK" ] || { echo "装置故障：没有备份 $BAK"; exit 2; }
    cp "$BAK" "$SRC"
    [ "$(count_anchor "$ANCHOR_ORIG")" = "1" ] || { echo "装置故障：还原后锚点不对"; exit 2; }
    echo "  源码已还原"
    echo "  重建前端（不带 NEXT_PUBLIC_WS_URL → 回到默认 9503 绿体后端）"
    FE_GPORT="${4:-22232}"
    build_and_serve "$FE_GPORT" "" "绿体" || exit 2
    echo
    echo "  跑绿侧：T3D_URL=http://127.0.0.1:$FE_GPORT/ node .cache/browser_verify/verify_derivation.mjs"
    ;;
  *) echo "用法: $0 {apply|restore} <MUT_BPORT> <FE_MPORT> [FE_GPORT]"; exit 2 ;;
esac
