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
ONE=$ROOT/.cache/chain_one.out          # 固定路径，不逐条删（沙箱会把 rm 拦成 mavis-trash 噪声）
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

echo "端口 = $U"
run verify_outcome        "T3D_URL=$U node .cache/browser_verify/verify_outcome.mjs"
run verify_law            "T3D_URL=$U node .cache/browser_verify/verify_law.mjs"
run verify_ladder         "T3D_URL=$U node .cache/browser_verify/verify_ladder.mjs"
run verify_structure      "T3D_URL=$U node .cache/browser_verify/verify_structure.mjs"
run verify_derivation     "T3D_URL=$U node .cache/browser_verify/verify_derivation.mjs"
run verify_subspace       "BV_URL=$U  node .cache/browser_verify/verify_subspace.mjs"
run verify_axis_readout   "BV_URL=$U  node .cache/browser_verify/verify_axis_readout.mjs"
run verify_heldout        "BV_URL=$U  node .cache/browser_verify/verify_heldout.mjs"
run verify_scene_link     "BV_URL=$U  node .cache/browser_verify/verify_scene_link.mjs"
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
echo "跑了 $N 条：判红 $RED ／ 环境不可验而跳过 $SKIP ／ 一条都没跑 $NORUN ／ 装置崩 $CRASH ／ **认不出判决 $UNJUDGED**"
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
