#!/bin/bash
# verify_derivation 的源级变异台。改源码 → 重建 → 起新端口 → 跑判据 → 还原。
#
# 为什么不用 DOM 属性变异：DOM 变异只能证明「判据读的是这个属性」，
# 证不了「判据会红」。源级变异走的是读者真实看到的那条渲染链。
#
# ⚠ 判据的绿侧必须**先跑一遍并确认是绿的**，否则「变异后仍然红/仍然绿」
#   都可能只是因为环境本来就坏。
# ⚠ 还原必须真的执行。用 trap 而不是顺序调用 —— 前面任何一步失败退出时，
#   留在磁盘上的就是被改坏的源码，而那会被下一次构建悄悄带进产品。
set -u
ROOT=/Users/zhourui/code/steer3d
cd "$ROOT" || exit 2
# ⚠ 变异目标文件。默认是面板组件；每条变异可以改它（M3 动的是 store）。
SRCFILE=""
WHICH="${1:-M1}"
BAK="$ROOT/.cache/mutderiv/LayerDerivationPanel.$WHICH.bak"
mkdir -p "$ROOT/.cache/mutderiv"
PORT="${PORT:-22301}"

# ⚠⚠ NEXT_PUBLIC_WS_URL 必须在**构建时**给出（NEXT_PUBLIC_* 会被内联进产物）。
#   漏掉它 ⇒ 页面连的是默认端口 9503，而本机后端在 9505 ⇒ 后端型判据整片 NA，
#   绿侧就不是 PASS，台会在第 61 行退出 3 —— 看起来像「变异无效」，
#   其实是基线跑错了环境。允许外部覆盖，默认跟本机后端一致。
export NEXT_PUBLIC_WS_URL="${NEXT_PUBLIC_WS_URL:-ws://127.0.0.1:9505/ws}"

# ⚠⚠⚠ 还原**必须包含重建**，否则机器会一直发着变异版。
#   `npx next build` 写的是 .next/，而**所有** `next start` 进程共享它 ——
#   还原源码不会动 .next/。于是：
#     · 变异侧那个 next start 还在发变异版（那是对的，本轮要用）
#     · 但之后**任何**端口、**任何**一次测量读到的都是变异版
#   实测后果：变异跑完后的第一次全链门禁，8 条判红
#   （verify_outcome 45/104、verify_law 2/7 …），我一度以为改坏了根页。
#   真相是根页 bodyLen=0 —— React 整个没渲染，因为发的是注入变异后的构建。
#   ⇒ trap 里重建，且**用新端口**验，避免旧进程继续持有旧 .next 的映射。
restore() {
  [ -f "$BAK" ] || return 0
  cp "$BAK" "$SRC" && echo "已还原 $SRC"
  ( cd "$ROOT/frontend" && npx next build >/dev/null 2>&1 ) \
    && echo "已重建（.next/ 回到未变异状态）" \
    || echo "!! 重建失败 —— .next/ 仍是变异版，别在这台机器上测任何东西"
}
trap restore EXIT INT TERM

case "$WHICH" in
  M1) DESC="F5：每根柱子的 data-pfinal 改成常数 0.5"; EXPECT_FAIL="F5 每根柱子"
       MARK="data-pfinal={0.5}" ;;
  # ⚠⚠ 第一版这一路改的是 `const first = step.first_layer_correct`，
  #   而 F6 判据读的是**第一根绿柱**（`page first green=L18`）——
  #   它压根不看 first 变量。变异指错了判据，于是「变异没让判据变红」，
  #   而当时的脚本 grep 整份输出，把 `[PASS] F6 …` 那行当成命中，报了「生效」。
  #   ⇒ 变异必须打在**判据真正读的那个量**上：柱子的 ok。
  M2) DESC="F6/F6b：把柱子的 ok 整体取反（判据读的是第一根 data-ok=1 的柱）"
       EXPECT_FAIL="F6 首个说对" ;;
  # ⚠⚠ 本条撤掉的是 **store 里 reset() 的 pickSeq 比较**，不是面板。
  #   F9b 咬的是「请求 reset 之后选的步会不会被 reset_ack 抹掉」，
  #   而抹它的代码在 lib/store.ts（reset_ack 的处理器）——
  #   所以 SRC 必须指向 store，光改面板永远咬不到这条判据。
  M3) DESC="F9b：撤掉 reset() 的 pickSeq 比较（恢复成无条件清）"
       EXPECT_FAIL="F9b 请求 reset"
       SRCFILE="lib/store.ts" ;;
  *) echo "未知变异 $WHICH"; exit 2 ;;
esac

SRC="$ROOT/frontend/${SRCFILE:-components/LayerDerivationPanel.tsx}"
BAK="$ROOT/.cache/mutderiv/$(basename "$SRC").$WHICH.bak"
echo "变异目标文件：${SRC#$ROOT/}"

echo "=== 变异 ${WHICH}：$DESC ==="

# ---- 绿侧：不改任何东西，先确认判据是绿的 ------------------------------
cd "$ROOT/frontend" && npx next build >/dev/null 2>&1 || { echo "绿侧构建失败"; exit 2; }
(nohup npx next start -p "$PORT" > "$ROOT/.cache/mutderiv/next_${WHICH}.log" 2>&1 &)
sleep 9
GREEN=$(T3D_URL="http://127.0.0.1:$PORT/" node "$ROOT/.cache/browser_verify/verify_derivation.mjs" 2>&1 | tail -1)
echo "绿侧汇总：$GREEN"
case "$GREEN" in
  *"RESULT PASS"*) echo "绿侧 OK，继续" ;;
  *) echo "!! 绿侧就不是绿的 ⇒ 变异无效，停（不拿一个坏基线去证明变异）"; exit 3 ;;
esac

# ---- 备份并改源码 ------------------------------------------------------
cp "$SRC" "$BAK"
python3 - "$SRC" "$WHICH" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); which = sys.argv[2]
s = p.read_text(encoding='utf-8')

# ⚠⚠ 替换类变异**必须断言命中次数**。
#   锚点写错时 sed/python 静默不替换，造出来的「红侧」其实还是绿树 ——
#   而我读到的「变异后没变红」会被当成「判据没牙齿」。
#   这是本项目已经犯过一次的错（改 _sys_boot.path 那次）。
def sub(text, old, new, want=1):
    n = text.count(old)
    assert n == want, f"锚点 {old!r} 命中 {n} 次，应为 {want} —— 变异无效"
    return text.replace(old, new, want)

if which == 'M1':
    # data-pfinal 写成常数：读者看到的是一排等高的柱子，
    # 而 data-ok / 层号仍然是「对」的 —— 正是 F5 要抓的那一类。
    s = sub(s, 'data-pfinal={b.p}', 'data-pfinal={0.5 /*MUT M1*/}')
elif which == 'M2':
    # ok 来自 pl.correct[l]，判据据此找「第一根说对的层」。
    # 取反之后第一根绿柱会跑到别处（或消失）⇒ F6 / F6b 必红。
    s = sub(s, 'const ok = pl.correct[l];',
               'const ok = !pl.correct[l]; /*MUT M2*/')
elif which == 'M3':
    # 改成「永远清」。写成 `s.pickSeq >= 0 ? null : s.focusedStep` 而不是直接
    # `focusedStep: null`，是为了**继续引用 s**：否则 set((s) => …) 的 s 变成未使用，
    # 若哪天 tsconfig 打开 noUnusedParameters，构建就会失败 —— 而那会让变异台
    # 停在「变异侧构建失败」，报出来的是构建错误而不是「判据变红」。
    # 行为上与修复前的代码完全等价（pickSeq 恒 >= 0 ⇒ 恒取 null）。
    s = sub(s,
      'focusedStep: s.pickSeq === s.pickSeqAtResetRequest ? null : s.focusedStep,',
      'focusedStep: (s.pickSeq >= 0 ? null : s.focusedStep), /*MUT M3*/')
p.write_text(s, encoding='utf-8')
print('已注入变异，命中次数已断言')
PY
if [ $? -ne 0 ]; then echo "注入失败（锚点没对上）"; exit 2; fi
grep -q "MUT M" "$SRC" || { echo "!! 注入后源码里找不到 MUT 标记"; exit 2; }

cd "$ROOT/frontend" && npx next build >/dev/null 2>&1 || { echo "变异侧构建失败（源码可能已破坏）"; exit 2; }
(nohup npx next start -p "$((PORT+1))" > "$ROOT/.cache/mutderiv/next_${WHICH}b.log" 2>&1 &)
sleep 9
RED=$(T3D_URL="http://127.0.0.1:$((PORT+1))/" node "$ROOT/.cache/browser_verify/verify_derivation.mjs" 2>&1)
echo "变异侧汇总：$(echo "$RED" | tail -1)"
echo "--- 变异侧判红的条目 ---"
echo "$RED" | grep -E "^\[FAIL\]" | head -6 | sed 's/^/  /'

# ⚠⚠⚠ 只能 grep **FAIL 行**。第一版 grep 整份输出，而通过的那些检查
#   也会印出名字（`[PASS] F6 首个说对的层…`）⇒ 变异**根本没让判据变红**时
#   照样匹配成功，脚本报「变异生效」。
#   一台只会说「是」的仪器比没有仪器更坏：它让「已验证」这三个字失去含义。
FAILONLY=$(echo "$RED" | grep -E '^\[FAIL\]' || true)
if echo "$FAILONLY" | grep -q "$EXPECT_FAIL"; then
  echo "⇒ 变异生效：命中「${EXPECT_FAIL}」"
  exit 0
fi
echo "⇒ !! 变异没让判据变红（期望 FAIL 行里出现「${EXPECT_FAIL}」）"
echo "   变异侧实际判红的条目："
if [ -z "$FAILONLY" ]; then
  echo "     （一条都没有 —— 判据全绿）"
else
  echo "$FAILONLY" | sed 's/^/     /'
fi
exit 1
