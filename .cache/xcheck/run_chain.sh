#!/bin/bash
# 全量门禁串联器。
#
# ⚠ 本文件存在的理由（§8.9 第十二笔 ⑤）：
#   验证链**自己**要报「跑了 N 条」，不能靠调用方数；
#   绝不把脚本输出接管道再取 $? —— 那是 grep 的退出码，恒 0。
#
# ⚠⚠ 第一版又把「判红 / 装置崩 / 一条都没跑」压成了两态。
#   它判 verify_scene_link 是 [BAD]（exit=2），可那一条是
#   **SKIP 6/6**：本沙箱 Chromium 没有 WebGL，页面走 2D 降级，
#   红的对象根本不是被测对象。**这不是红，也不是绿。**
#   触发层是「用退出码判红绿」；机制层与第十笔同族 ——
#   任何**在输入不成立时仍给出一个数**的量（退出码）都会被误读成判决。
#   ⇒ 判决只从**汇总行**读，退出码只用来发现「装置崩」。
#   三态分别计数：RED / SKIP / 一条都没跑 / GREEN。
ROOT=/Users/zhourui/code/steer3d
U=${1:-http://127.0.0.1:21880/}
cd "$ROOT" || exit 2
ONE=$ROOT/.cache/chain_one.$$.out       # 每次运行**独有**（下面有为什么）
# ⚠⚠⚠ 原来这里是固定路径 `.cache/chain_one.out`。两个后果，都踩过：
#
#   ① **不要把本链的 stdout 重定向到 `chain_one.out`** —— 它就是内部临时文件。
#      `bash run_chain.sh … > .cache/chain_one.out` ⇒ stdout 与 $ONE 成了同一个
#      文件，run() 每判一条就 `( eval ) > "$ONE"` **把已写好的标签行覆盖掉**。
#      症状极具欺骗性：文件**看起来**有内容（只剩最后一条判据 + 末尾汇总），
#      汇总「判红 1 / 跳过 1」也照样打印 —— 而**哪一条红、哪一条跳过全消失**。
#
#   ② **两条链不能同时跑。** $ONE 共享 ⇒ 互相覆盖对方的判据输出，
#      于是 `res` 读到别人正在写的文件 ⇒ 凭空多出标签重复的判决行、
#      甚至一条 NORUN（读到对方刚 truncate 还没写的空档）。
#      实测：并发两条 ⇒ 20 个 run 却报「23 行判决、标签重复、NORUN 1」。
#      看着像判据坏了，其实是**两条链在写同一个文件**。
#      ⇒ $$ 放进文件名，两条链各写各的；顺带让「并行跑」变成安全的。
#      ⚠ 这**只**解决文件互踩，不解决「机器被两个浏览器压着跑」——
#         那仍然会互相干扰（判据是负载敏感的），只是不会再伪造判决行。
#
# 收尾：**故意不删**这个文件。沙箱会把脚本里的 `rm` 拦成 mavis-trash 噪声，
# 而它在 `.cache/` 下（已 gitignore）、每次运行只留一份、内容就是最后一条判据的
# 原始输出 —— 事后回看「最后一条到底印了什么」时它是有用的。
# ⇒ 代价是 `.cache/chain_one.*.out` 会按运行次数累积，需要时手工清。
# ⚠ 别再留一个「打算用来控制它」的变量：上一版留了 `ONE_KEEP=0` 却从没用上，
#   那就是一个只占位、没人读、看着像开关的死变量。
N=0; RED=0; SKIP=0; NORUN=0; CRASH=0; UNJUDGED=0

run() {
  local label="$1"; shift
  N=$((N+1))
  ( eval "$@" ) > "$ONE" 2>&1
  local rc=$?
  # 两种汇总行并存：九个 verify_*.mjs 印「=== N/M passed ===」，
  # xcheck 的 python 与探针印「RESULT …」。两种都要认。
  local res passed total verdict
  res=$(grep -E "^RESULT|^=== [0-9]+/" "$ONE" | tail -1)
  if [ -z "$res" ]; then
    NORUN=$((NORUN+1))
    printf '  [NORUN] %-22s exit=%d  <没有汇总行>\n' "$label" "$rc"
    return
  fi
  # ⚠⚠ 第三十三笔之九：下面这段「探针也算一条判决」是**故意不加**的。
  #   两支 probe_panels 是**装置**，不是判决 —— 它们只回答
  #   「页面上有哪些块」，判「覆盖够不够」的是 scan_panel_coverage。
  #   逼装置印一行 `N/N passed` 就能把它塞进 N 里，但那是**恒真判决**
  #   （与第三十三笔之八修掉的 C3 同一族）：它给出一个自信的绿，
  #   而它判的东西根本不存在。
  #   ⇒ 装置走 stage()：只判「跑成了没有、产物在不在、产物自报的是哪一页」，
  #     装置坏了就 exit 5，与判决红绿**分开计数**。
  # 判决**只**看通过数，不看关键词 —— 两种汇总行用**同一条**规则。
  # ⚠ 第二版用「汇总行里有没有 RED/FAIL/PASS/GREEN/SKIP」来判，
  #   而「=== 54/54 passed ===」里是小写 passed ⇒ 五个全被判成 CRASH。
  #   **判据自己就是一台假阳性机器**：它给出一个自信的错误分类，不吭声。
  #   与第十笔同族 —— 用「行长得像不像判决」代替「数说的是不是判决」。
  #
  # ⚠⚠ 第三版：第二版那两句 sed 在 macOS 上**根本抓不到数**，而失败是静默的。
  #   `\+` 是 GNU BRE 的量词；macOS 自带 BSD sed，`\+` 不被当量词，
  #   输出**空串** ⇒ `[ "$passed" -lt "$total" ]` 拿两个空串比较
  #   ⇒ bash 报 integer expression expected 并**以非零退出** ⇒ if 判假
  #   ⇒ **不管 61/62 还是 62/62 一律判 ok**。
  #   实测后果：verify_outcome 真红了 1 条，串联器印 `[ok ] 61/62`，
  #   再由退出码记成「装置崩」⇒ **一次真判红被说成装置事故**。
  #   ⇒ 第四版：不再按行式分别解析，两种形式**统一**取行里的第一个 N/M
  #     （用 `grep -oE` 而非 sed，避开 BRE/ERE 的方言差异），
  #     并且**解析不出 N/M 就报 UNJUDGED，不许判绿**。
  #
  # ⚠⚠ 第四版自己又错了一次：UNJUDGED 守卫被放在**分流之前**就 return，
  #   于是 10 条 `RESULT …` 形式的脚本全被判成「认不出判决」——
  #   我把一条本来正确的分支条件换成了提前返回。
  #   好在它**喊出来了**（10 条 UNJUDGED、整链 exit 3）而不是默默放行：
  #   这正是它与 `\+` 那个洞的差别 ——
  #   后者静默判绿，前者宁可误报也不放行。**误报代价低，漏报代价高。**
  ratio=$(echo "$res" | grep -oE '[0-9]+/[0-9]+' | head -1)
  if [ -z "$ratio" ]; then
    UNJUDGED=$((UNJUDGED+1)); verdict=UNJUDGED
    printf '  [UNJUDGED] %-22s exit=%d  %s\n' "$label" "$rc" "$res"
    printf '         ！汇总行里没有 N/M ⇒ **不判绿也不判红**（不拿退出码代替判决）\n'
    return
  fi
  passed=${ratio%%/*}
  total=${ratio##*/}
  # SKIP 是第三态，必须先于 RED 判 —— `RESULT SKIP 6/6` 长得像通过。
  if echo "$res" | grep -q "SKIP"; then
    SKIP=$((SKIP+1)); verdict=SKIP
    printf '  [SKIP ] %-22s exit=%d  %s\n' "$label" "$rc" "$res"
    return
  fi
  if [ "$passed" -lt "$total" ]; then
    RED=$((RED+1)); verdict=RED
    printf '  [RED  ] %-22s exit=%d  %s\n' "$label" "$rc" "$res"
    grep -E "^\[FAIL\]" "$ONE" | head -6 | sed 's/^/         /'
    return
  fi
  verdict=ok
  printf '  [ok   ] %-22s exit=%d  %s\n' "$label" "$rc" "$res"
  if [ $rc -ne 0 ]; then
    CRASH=$((CRASH+1))
    printf '         ！汇总行说没事但退出码 %d ⇒ **装置在印完汇总之后才死**\n' "$rc"
  fi
}

stage() {
  # 装置闸：跑完必须「产物存在 + 产物自报了它是哪一页 + 本轮 WebGL 实况已记」。
  # ⚠ 不计入 N —— 装置不是判决。装置坏了整条链的数据都不可信，直接 exit 5。
  local label="$1" out="$2" page="$3" cmd="$4"
  ( eval "$cmd" ) > "$ONE" 2>&1
  local rc=$?
  if [ $rc -ne 0 ]; then
    printf '  [装置崩] %-18s exit=%d\n' "$label" "$rc"
    tail -4 "$ONE" | sed 's/^/           /'
    echo "⇒ 装置崩了，下面所有判决的数据都不可信 ⇒ 停。"; exit 5
  fi
  if [ ! -f "$out" ]; then
    printf '  [装置崩] %-18s 没有写出 %s\n' "$label" "$out"; exit 5
  fi
  local got
  got=$(python3 -c "import json,io,sys;d=json.load(io.open(sys.argv[1],encoding='utf-8'));print('%s|%s|%s'%(d.get('page'),d.get('webglRequested'),(d.get('webgl') or {}).get('available')))" "$out" 2>/dev/null)
  if [ "${got%%|*}" != "$page" ]; then
    printf '  [装置崩] %-18s 产物自报 page=%s，预期 %s\n' "$label" "${got%%|*}" "$page"
    echo "          ⚠ 两页探针跑第二遍时**忘了换 PROBE_OUT** 就会这样："
    echo "            根页那份被 latent 覆盖，于是根页看起来也覆盖了 latent 页。"; exit 5
  fi
  printf '  [装置  ] %-18s ok　page=%s　本轮请求WebGL=%s 实得=%s\n' \
    "$label" "${got%%|*}" "$(echo "$got" | cut -d'|' -f2)" "$(echo "$got" | cut -d'|' -f3)"
}

echo "端口 = $U"
# ⚠⚠ 第三十三笔之九：**先把两页探针跑掉，再让 panel_coverage 读它们。**
#   原先这 21 条里**没有一条**会重跑 probe_panels ——
#   panel_coverage 读的是上一次手工跑完留在磁盘上的 JSON。
#   只有 C0 的「产物 < 7200 秒」兜着，那是**时间**闸不是**因果**闸：
#   有人 1 小时前手工跑过一次，链就照着那份旧数据判绿。
#   ⇒ 覆盖矩阵与它依赖的那份产物之间，必须有**因果**，不能只有时序。
#   ⚠ 两页都要开 WebGL flag，与 verify_scene_link 同一套 swiftshader：
#     否则 scan 看到的根页 DOM 走 2D 降级，8 个 data-scene-* 永远不在。
#   ⚠ 两页都要跑，第二遍**必须换 PROBE_OUT**：忘了换，根页那份会被覆盖，
#     于是根页看起来也覆盖了 latent 页，而其实根页一个标记都没量。
#   ⚠⚠ **探针不开 WebGL，判据侧只有 verify_scene_link 开** —— 这不是疏忽，
#     是实测逼出来的（第三十三笔之九）：
#       根页有**两条渲染路径**，而且它们发出的标记**不重叠**：
#         2D 降级（WebGL 不可用时，data-testid="scene3d-fallback"）
#           → data-painted / data-rendered-points / data-on-screen-points /
#             data-layer / data-has-entropy / data-extent-maxabs /
#             data-extent-fraction　**只有** Scene3DFallback.tsx 设这 7 个
#         真 3D（WebGL 可用时）
#           → data-scene-loaded / -focus-state / -window-high / -window-low
#             以及点击后才有的 -focus / -focus-miss / -focus-step / -focus-token
#       而 21 条里有 **19 条不开 WebGL**（走降级），只有 verify_scene_link 开。
#     覆盖扫描只有**一份** DOM 快照 ⇒ 它必须跟**多数派**那条路径对齐，
#     否则 C2 会拿「3D 路径的 DOM」去核「降级路径的判据」，报 7 个假死引用
#     （实测确实报了这 7 个）。
#     ⇒ 每条判据在**它自己需要**的浏览器环境里跑；扫描读降级那份；
#       3D 那份由 verify_scene_link 13/13 负责。
#       **「两条路径的覆盖要分开记账」是下一笔的活**，不是这一笔能顺手带过的。
stage probe_root   "$ROOT/.cache/browser_verify/panel_blocks.json"       root \
  "BV_URL=$U PROBE_OUT=$ROOT/.cache/browser_verify/panel_blocks.json node .cache/browser_verify/probe_panels.mjs"
stage probe_latent "$ROOT/.cache/browser_verify/panel_blocks_latent.json" latent \
  "BV_URL=${U%/}/latent/index.html PROBE_OUT=$ROOT/.cache/browser_verify/panel_blocks_latent.json node .cache/browser_verify/probe_panels.mjs"
run verify_outcome        "T3D_URL=$U node .cache/browser_verify/verify_outcome.mjs"
run verify_law            "T3D_URL=$U node .cache/browser_verify/verify_law.mjs"
run verify_ladder         "T3D_URL=$U node .cache/browser_verify/verify_ladder.mjs"
run verify_structure      "T3D_URL=$U node .cache/browser_verify/verify_structure.mjs"
run verify_derivation     "T3D_URL=$U node .cache/browser_verify/verify_derivation.mjs"
run verify_subspace       "BV_URL=$U  node .cache/browser_verify/verify_subspace.mjs"
run verify_axis_readout   "BV_URL=$U  node .cache/browser_verify/verify_axis_readout.mjs"
run verify_heldout        "BV_URL=$U  node .cache/browser_verify/verify_heldout.mjs"
run verify_scene_link     "BV_URL=$U  node .cache/browser_verify/verify_scene_link.mjs"
# ⚠⚠⚠ 第三十三笔之十一：**这里默认不开 WebGL，是第三十三笔之九之后改回来的。**
#   那一笔我把它改成了 `STEER3D_WEBGL=1`，链里报 PASS 13/13，
#   我据此说「3D 进链了」—— **那句话是错的，本笔更正。**
#   同一份脚本、同一台服务器、不开任何别的负载，连跑三次：
#
#       第 1 次  RESULT FAIL 12/13   J3b 等 60000ms 仍在增长（769 步）
#       第 2 次  RESULT FAIL 11/13   J3b 等 60000ms 仍在增长（721 步）、J10 752->752
#       第 3 次  RESULT FAIL  7/9    J3b 40s 稳定在 385 步，但 J6 仍红
#                                     + 装置异常 Cannot read properties of null
#
#   ⇒ **13/13 是撞对的**，不是常态。两种失败要分开看：
#     · J3b 是**负载敏感**：软件光栅慢，机器一忙 60 秒预算就不够。
#     · J6 是**前提不成立**：`data-scene-focus` 那 4 个标记要射线拾取点击
#       之后才出现，而「软件光栅能不能拾取」这件事本环境给不出判决
#       （详见 05cc462 的记录：J6 只验了源码接线）。
#       它连带的 `reading 'badge'` 是**判据自己抛的**，不是页面坏了。
#   ⇒ 门禁**随机红**比诚实的「本环境验不了」更糟：前者会让人不再相信它。
#     所以默认退回 SKIP，并在 `verify_scene_link.mjs` 自己的输出里印原因。
#   ⇒ 要在链里真验 3D，需要先做两件事（都还没做）：
#     ① J3b 的预算按实测重标（空闲 40s / 负载 >60s），且**超预算要报独立态**，
#        不能报 FAIL —— 与 run() 的 NORUN 同一族；
#     ② J6 必须在**真机 Chrome** 上验射线拾取，软件光栅下它只能 SKIP。

# ⚠ verify_backmap 读的是 **LAT_URL**，不是 T3D_URL / BV_URL。
#   这一点本身就是个坑：我第一次跑它时给的是 T3D_URL，于是它带着自己的
#   默认端口去访问一个没人监听的地址，回来一个 0/8 的假红，
#   看上去像「这一块整块坏了」。所以这一条在串联器里显式传 LAT_URL，
#   而 verify_backmap.mjs 自己也加了 B0 可达性前置：
#   连不上时它**不报 N/M**，让这里记成 NORUN。
run verify_backmap        "LAT_URL=${U%/}/latent/index.html node .cache/browser_verify/verify_backmap.mjs"
run verify_dv_readout     "LAT_URL=${U%/}/latent/index.html node .cache/browser_verify/verify_divergence_readout.mjs"
# ⚠ 第二十三笔新增：这三块（思维链层面 / 答案位移逐篇读 / 逐字读）本轮
#   从 drawDeltaSide() 搬进了 #extras，而 drawDeltaSide() 在 !S.pMeta 时
#   提前 return ⇒ 它们在默认视图里**从来没渲染过**。
#   判据主体必须在**渲染层**：数 DOM 里的块、读它印出来的字、点它的芯片。
#   只扫源码会假绿 —— 源码里那 16 个 data-cot* / data-ar* 一个都不少。
run verify_cot_extras     "LAT_URL=${U%/}/latent/index.html node .cache/browser_verify/verify_cot_answer_extras.mjs"
# ⚠ 第二十四笔新增：第二十三笔把 cot / answer / cottext 三块搬进 #extras 之后，
#   它们第一次出现在默认视图里 ⇒ C4 立刻多出 24 个「渲染了但没人读」的标记，
#   而这三块的散文合计上万字、承载判决的数字一个都没有判据。
#   「搬出来」不等于「有人核」—— 这一组就是来核它们的。
#   本组防三处当场查出来的手打文案：写死的「净变化是 0」、
#   丢了 "answers verified" 的题库自述转述、两份产物两种措辞的答案域约定。
run verify_latent_prose   "LAT_URL=${U%/}/latent/index.html node .cache/browser_verify/verify_latent_prose.mjs"
# ⚠ 第二十五笔新增：data-lens* 五个标记在覆盖扫描里是「渲染了但没人读」，
#   而这一块正是「各层 hidden state 如何推导出这个 token」最直接的答案。
#   本组核的是那一块里**六处**手打的东西：无源的 0.09（实测离中位数差 13%）、
#   产物没记的 16k、四个写死的层号、过期的写死峰值（L20–L21 vs 实测 argmax=21）、
#   标签与口径差一层的「L27 前」、以及那个自称不了的「注入层」标记。
run verify_logit_lens      "LAT_URL=${U%/}/latent/index.html node .cache/browser_verify/verify_logit_lens.mjs"
run assertion_guard       "python3 .cache/xcheck/assertion_guard.py"
run panel_coverage        "python3 .cache/xcheck/scan_panel_coverage.py"
run dead_url              "python3 .cache/xcheck/dead_url_sweep.py && python3 .cache/xcheck/check_dead_url.py"
run live_blocks           "python3 .cache/xcheck/scan_live_blocks.py"
run json_strict           "python3 .cache/xcheck/scan_json_strict.py"
run artifact_consumers    "python3 .cache/xcheck/scan_artifact_consumers.py"
run dedup_rendered        "BV_URL=$U node .cache/browser_verify/probe_dedup_rendered.mjs"

echo
echo "跑了 $N 条判决（另加 2 道装置闸）：判红 $RED ／ 环境不可验而跳过 $SKIP ／ 一条都没跑 $NORUN ／ 装置崩 $CRASH ／ **认不出判决 $UNJUDGED**"
echo "（跳过与「一条都没跑」都不是绿，但也都不是指控 —— 它们各自印着自己的原因。）"
if [ "$N" -ne 21 ]; then
  echo "⚠ 预期 21 条，实际 $N 条 ⇒ **串联器自己漏了分支**（不是被测物的问题）"
  exit 2
fi
[ "$UNJUDGED" -eq 0 ] || { echo "有 $UNJUDGED 条认不出判决 ⇒ 不许当通过"; exit 3; }
# ⚠ NORUN 以前**不**影响退出码。第十四笔加 verify_backmap 时才发现这个洞：
#   「一条都没跑」在这一版里会一路绿到底 —— 判据没执行，和判据全绿
#   在汇总里长得一模一样（都没有 N/M 可读）。这与 UNJUDGED 判 exit 3
#   是同一个道理，只是当时只给 UNJUDGED 上了闸。
[ "$NORUN" -eq 0 ] || { echo "有 $NORUN 条一条都没跑 ⇒ 不许当通过"; exit 4; }
[ "$RED" -eq 0 ] || exit 1
[ "$CRASH" -eq 0 ] || exit 1
exit 0
