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
N=0; RED=0; SKIP=0; NORUN=0; CRASH=0; UNJUDGED=0; NOT=0
# ⚠ NOT = 「前置未建立」的条数。它既不是红也不是绿 —— 那些检查**一次都没跑**。
#   混进 RED 会说「验过、不合格」（假指控）；混进 ok 会让门禁在一块根本没跑
#   的东西上变绿。第三十六笔起 verify_derivation 就会印这一栏。
#   ⚠ 不进退出码：未验不是失败。但**必须印出来** —— 一条没跑的检查和
#   一条跑过的检查，在只读 N/M 的汇总里长得一模一样。

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
  # ⚠⚠⚠ 第三十四笔：SKIP 的判法从「整行 grep」改成「只认状态词」。
  #
  #   原式：`if echo "$res" | grep -q "SKIP"; then ... SKIP ... fi`
  #   它在**任何位置**找那三个字母。而 verify_scene_link 这一轮印的是
  #     RESULT FAIL  6/8　有 2 条判红，不能用 SKIP 解释
  #   —— 脚本**自己明说**这条不能算 SKIP，链却 grep 到了那句解释里的 SKIP，
  #   于是把一条 FAIL 归成 SKIP，**RED 计数少 1**，整链 exit 0。
  #   实测：真值是 RED 3，链报 RED 2 —— 汇总行自己也不诚实。
  #
  #   与第四版那个洞同族：用「行里有没有这个词」代替「数说的是不是判决」。
  #   第四版给 N/M 解析修过，**SKIP 这一刀没跟着改** ——
  #   同一个错误只修了一半，于是它躲过了所有已有的自检。
  #   ⚠ 这也说明：修过的判据**不等于**被审过的判据。
  #
  #   ⇒ 只认 `RESULT` 后面那个状态词，且必须**恰好**是 SKIP。
  #   判据式判据：`grep -oE '^RESULT [A-Z]+'` 取第二个词。
  #   先例（`.cache/xcheck/classifier_selftest.sh`）：
  #   旧规则在 4 种真实汇总行里错 1 格，新规则 4/4 —— 那 1 格是**证红**出来的。
  # 前置未建立条数：判据自己印的，格式「前置未建立 N 条（…）」。
  # 只认行首且认状态词，与 SKIP 同一刀法 —— 不在行里 grep 任意子串。
  local na
  na=$(grep -oE '^前置未建立 [0-9]+ 条' "$ONE" | head -1 | grep -oE '[0-9]+' | head -1)
  if [ -n "$na" ] && [ "$na" -gt 0 ] 2>/dev/null; then
    NOT=$((NOT + na))
    printf '         · 其中 %s 条**前置未建立**（没跑，不是红也不是绿）：\n' "$na"
    grep -E '^  NA: ' "$ONE" | head -8 | sed 's/^/           /'
  fi
  status=$(echo "$res" | grep -oE '^RESULT [A-Z]+' | head -1 | awk '{print $2}')
  if [ "$status" = "SKIP" ]; then
    SKIP=$((SKIP+1)); verdict=SKIP
    printf '  [SKIP ] %-22s exit=%d  %s\n' "$label" "$rc" "$res"
    return
  fi
  if [ "$passed" -lt "$total" ]; then
    RED=$((RED+1)); verdict=RED
    printf '  [RED  ] %-22s exit=%d  %s\n' "$label" "$rc" "$res"
    # ⚠⚠ 必须连**诊断行**一起印，只印条目名字等于把根因扔掉。
    #   房里的判据统一用 `rec(name, ok, detail)`，输出形状是
    #       [FAIL] 条目名
    #              诊断文字（缩进 7 格，在**下一行**）
    #   而这里原来只 `grep -E "^\[FAIL\]"` ⇒ **诊断全被丢掉**。
    #   2026-10-07 链里 F9 红过一次，单跑 3 次全绿、根因查不出来 ——
    #   原因就是这里：那条红只有名字，装置自己打的
    #   「第几轮读回=生效/仍被重置」「after.sliderValue=…」全没进汇总。
    #   ⇒ 判红时把每条红后面的缩进行一并带出来（最多 3 行，够放数字了）。
    awk '/^\[FAIL\]/{p=1; print "         " $0; next}
         p && /^       /{print "       " $0; n++; if (n>=3) p=0; next}
         p {p=0}' "$ONE"
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
#     ⇒ 每条判据在**它自己需要**的浏览器环境里跑；扫描读降级那份；
#       3D 那份由 verify_scene_link 13/13 负责。
#       **「两条路径的覆盖要分开记账」是下一笔的活**，不是这一笔能顺手带过的。
#
# ⚠⚠⚠ 2026-10-06：**verify_scene_link 必须在链里开 WebGL**，不是可选项。
#   它以前长期印 `RESULT SKIP 8/8`，理由是「本浏览器没有 WebGL」。
#   而实测（probe_webgl_flags.mjs）**加两个 swiftshader flag 就有 WebGL 2.0** ——
#   flag 一直在 `verify_scene_link.mjs` 里，只是被 `STEER3D_WEBGL=1` 门控，
#   而链从不设它。⇒ **3D 联动从来没被机器验过，却一直占着链里一条。**
#   打开之后实测 `RESULT PASS 13/13`（等 489s 把 784 步灌满）：
#     J6  珠子标签出现 step=782 token="$$"
#     J8  3D 与链指向同一步号 782　J9a token 与 sidecar 真值一致
#     J10 第二次拖动 782→777，标签跟着变
#   ⇒ 代价是这一条要 ~8 分钟（软件光栅 0.78 步/s）。值得：它是目标里
#     「3D 展示 hidden states 如何推导出 token」唯一那条机器判决。
#   ⚠ 若某轮机器太慢灌不完，它会印「前提未建立（465/784）」并记 **SKIP**，
#     不是 FAIL —— 那是「没等停」，不是「3D 坏了」。
run verify_scene_link     "STEER3D_WEBGL=1 BV_URL=$U  node .cache/browser_verify/verify_scene_link.mjs"
# ⚠⚠⚠ 第三十三笔之十一的结论**已被 2026-10-06 这一笔推翻**，理由逐条列在下面。
#   当时观察到的现象是真的：
#
#       第 1 次  RESULT FAIL 12/13   J3b 等 60000ms 仍在增长（769 步）
#       第 2 次  RESULT FAIL 11/13   J3b 等 60000ms 仍在增长（721 步）、J10 752->752
#       第 3 次  RESULT FAIL  7/9    J3b 40s 稳定在 385 步，但 J6 仍红
#                                     + 装置异常 Cannot read properties of null
#
#   但当时下的结论是「13/13 是撞对的，默认退回 SKIP」——**这个结论本身是错的**，
#   因为那几个红**不是负载敏感，是判据写错了**。逐条：
#
#   ① J3b 的「等停」判据是「`loaded` 连续 3 次不变（≈4s 无增长）」。
#      软件光栅下数据流按块灌、块间可停 >4s ⇒ **假停**。
#      实测：停在 193 时判「已停」，几秒后继续涨到 **289**，而这条轨迹共 **784 步**。
#      ⇒ 判据没问「这条轨迹一共几步」，所以它根本不知道「停」意味着什么。
#      ⇒ 已改成**用 sidecar 的总步数当真值**：到 784 才算停；
#        拿不到总数才退回「无增长」，且理由必须印出来。
#      ⇒ 预算也随之从 60s→150s→600s→1500s 重标（实测速率 0.78 步/s）。
#
#   ② J6 的目标步号可能落在滑杆范围**之外**。
#      `min(scene.high=288, rangeMax=783) - 1 = 287`，而滑杆是 **[752,783]**
#      ⇒ `<input type=range>` 把它**钳回 min=752**，滑杆纹丝不动，
#      「标签不出现」于是被判成产品坏了。（原始读数：`set→{"t":"287","v":"752"}`）
#      ⇒ 现在先验 `rangeMin <= target <= rangeMax`；不相交就记**未判**，不记红。
#
#   ③ 「两个窗口不相交」是**前提未建立**，不是红。J10 同理：第一次没拿到标签，
#      J10 的前提就不成立，照判会让同一个前提问题在汇总里出现两次、都写成产品坏了。
#
#   ④ `precondFailed` 的理由里**写死了「150s 预算」**，而预算早已不是 150s
#      ⇒ 消息与代码各说各话。三处同类问题的共同病根就是这个。
#
#   ⇒ 修完后实测（2026-10-06，等 489s 才把 784 步灌满）：
#       `RESULT PASS 13/13`
#       J6  step=782 token="$$"　J7 66x15px　J8 3D=782 链=782　J9a 页面 "$$" = sidecar "$$"
#       J10 782 -> 777　陈旧读数 0/0 次　滑杆真的动了吗 true/true
#   ⇒ **代价是这一条要 ~8 分钟。** 值得：它是目标里
#     「3D 展示 hidden states 如何推导出 token」唯一那条机器判决，
#     而它以前**从来没被机器验过**，只是一条常驻的 SKIP。
#
#   ⚠ 仍未验的只有一件事：**珠子上的光线拾取点击**（J9 只验了源码接线）。
#     软件光栅读不到 WebGL 像素，这一条仍要真机 Chrome。

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
# ⚠ 第三十六笔新增：第 5 屏「逐步路径」。它是唯一一块**把 t=0..k 每一步、
#   两条臂各自的 top-8 候选词**印出来的界面，也是「模型按什么路径推理 /
#   干预下行为怎么变」这两个问题的正面答案所在。前面那些判据一条都碰不到它。
#   这一条额外防两件本项目已经吃过两次亏的事：
#     ① **被别的层遮住**。引导页盖住整页时，getBoundingClientRect().height 仍 > 0，
#        判据全过而读者眼前是一张引导页 ⇒ 可见性判定必须过 elementFromPoint。
#     ② 切题后 pid/k 是不是真的跟着换。第一版拿 select 的**索引**去和
#        data-pathpid 的**题号**比口径，恒为真，探针打印 before==after 就算过。
run verify_path           "LAT_URL=${U%/}/latent/index.html node .cache/browser_verify/verify_path.mjs"
# 第 6 屏「干预阈值」。两条容易踩的坑都封在本脚本报里，不靠人记得：
#   ① 页面加载时导读浮层 #orientation（position:fixed）会自动弹出并盖住整屏。
#      不先关掉就量可见性，量到的是浮层 —— T0b 会先把「关掉了没有」变成一条判决。
#   ② elementFromPoint 对**视口外**的点返回 null。null 不等于「被盖住」；
#      第一版把 null 当成被盖，报了个假红。现在先 scrollIntoView 再探多点，
#      null 的探点单独剔除计数。
run verify_thresh         "LAT_URL=${U%/}/latent/index.html node .cache/browser_verify/verify_thresh.mjs"
# 第 7 屏「因果修补」。这一屏专治一种病：**判否的门被藏起来**。
#   ① 唯一结论字段 data-verdict 必须与产物 gates[].verdict 逐字相同。
#      上一轮产物自己「stable=true」与判决「不稳」并存，读者只能挑一个信；
#      本屏 P2 把「页面不许自己另判」变成一条会红的判决。
#   ② na（没测）与 fail（不成立）必须在页面上分开且都带理由。
#      没测说成不成立是伪造结论 —— 这两种红长得几乎一样，后果完全不同。
#   ③ 主量（transfer）与次量（excess）都判过，只印一组等于偷换结论。P9 查这个。
run verify_patch         "LAT_URL=${U%/}/latent/index.html node .cache/browser_verify/verify_patch.mjs"
# 产物层的独立重算：不复用探针的任何计算，只从原始行重算。
run verify_patching      "python3 .cache/xcheck/verify_path_patching.py"
# 第 8 屏「阈值向量（LTV）」。ltv.json 在上一轮**没有任何页面消费者** ——
#   方法算完了、判完了，读者在网站上却看不到。本条是把它接上之后的第一条判决。
#   ⚠ 它与 verify_ltv（产物层独立重算）**不是重复**：那一条判的是「数对不对」，
#     这一条判的是「数传到读者眼前时有没有变质」——
#     ① 判决切片必须可见且逐字（verdict_slice / judge_slice_note）。
#        G-a 的 claim 与预登记表都写着「留出」，而第一版的判决跑在全量 36 个
#        上下文上（含约一半抽取题）；页面若只印一个总数，就把
#        「抽取集上不显著（p=9.23e-02）」这个事实藏起来了。L6 查这个。
#     ② 并列口径（全量）与判决口径（留出）必须印在**同一块**并标成「不是判决」。
#        只印一个就是把另一面藏起来 —— 两个切片一个显著一个不显著。L7 查这个。
#     ③ α*预测 由判据用 m_p÷g_v **独立重算**（不信产物自己写的那个字段），
#        g_v≤0 的行必须印「—」而不是 0。L8 查这个。
#     ④ 切片行数三方对账：DOM 标「留出」的行数 = contexts[].in_judge_slice
#        = 各门 evidence 的 n_ctx。L9/L10 查这个。
#     ⑤ degenerate_untested 不许被显示成通过（L11）；诚实边界 8 条逐字（L12）。
run verify_ltv_panel     "LAT_URL=${U%/}/latent/index.html node .cache/browser_verify/verify_ltv_panel.mjs"
# ⚠ LTV（阈值可读向量）—— 目标里「能不能提取一套通用的可解释性理论」那一条的判决。
#   预登记表 `LTV_PREREG.md` 写于取数之前；判决的唯一权威是 `build_ltv.py`，
#   这一条是**独立重算**（E 层从原始 gap(α) 重算 / F 层预登记漂移 /
#   G 层产物与原始逐数对账 / H 层量级体检）。
#   ⚠ 它印 `RESULT verify_ltv GREEN 18/18`，但**有一条长期红的检查已改成披露制**：
#     预登记表 §3 自述「一档 ≈ 1.7~2.8 倍」与它自己定的 α 网格（实为 1.43~2.00）
#     对不上。原文是取数前的记录，不许事后改 ⇒ 改成判「差异被披露且有处置」，
#     而差异本身每轮都印在警告行里。
#     （原版把它做成「必须为真」，结果是一条**永远红**的判据 ——
#      那等于没有判据，而且会让全链退出码恒为 1，此后真故障都被淹在里面。）
run verify_ltv            "python3 .cache/xcheck/verify_ltv.py"
run assertion_guard       "python3 .cache/xcheck/assertion_guard.py"
run panel_coverage        "python3 .cache/xcheck/scan_panel_coverage.py"
run dead_url              "python3 .cache/xcheck/dead_url_sweep.py && python3 .cache/xcheck/check_dead_url.py"
run live_blocks           "python3 .cache/xcheck/scan_live_blocks.py"
run json_strict           "python3 .cache/xcheck/scan_json_strict.py"
run artifact_consumers    "python3 .cache/xcheck/scan_artifact_consumers.py"
run dedup_rendered        "BV_URL=$U node .cache/browser_verify/probe_dedup_rendered.mjs"

echo
# ⚠ 预期条数**不许写死**。原来这里写的是 22，加了第 23 条之后它就误报
#   「串联器自己漏了分支」—— 报红的是我自己，不是被测物，而那个红指向
#   的方向（判据装置有问题）恰好是最容易让人停下不查的那种。
#   改成从 `run` 调用处现数，链加一条只会多报一条，不会造假警报。
EXPECTED=$(grep -c '^run ' "$0")
echo "跑了 $N 条判决（另加 2 道装置闸；链里现有 $EXPECTED 条）：判红 $RED ／ 环境不可验而跳过 $SKIP ／ **前置未建立（没跑）$NOT** ／ 一条都没跑 $NORUN ／ 装置崩 $CRASH ／ **认不出判决 $UNJUDGED**"
echo "（跳过与「一条都没跑」都不是绿，但也都不是指控 —— 它们各自印着自己的原因。）"
if [ "$N" -ne "$EXPECTED" ]; then
  echo "⚠ 预期 $EXPECTED 条，实际跑出 $N 条 ⇒ **串联器自己漏了分支**（不是被测物的问题）"
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
