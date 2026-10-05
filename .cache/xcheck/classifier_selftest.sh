#!/bin/bash
# 分类器自检：证明 `run_chain.sh` 的 SKIP/RED 分流**能判红**。
#
# ⚠ 为什么要有这个文件：链里那一行是
#     if echo "$res" | grep -q "SKIP"; then ... SKIP ... fi
#   它在**任何位置**找 "SKIP" 三个字母。而 verify_scene_link 自己的输出是
#     RESULT FAIL  6/8　有 2 条判红，不能用 SKIP 解释
#   —— 脚本**明说**这条不能算 SKIP，可链 grep 到了那句解释里的 "SKIP"，
#   于是把一条 FAIL 归成 SKIP，RED 计数少 1，整链 exit 0。
#   症状与「拿 round(median,4) 比未舍入中位数」同族：
#   **用「行里有没有这个词」代替「数说的是不是判决」**。
#   链自己的注释已经为 N/M 解析修过一次这个洞（第四版），
#   但 SKIP 这一刀没跟着改。
#
# ⚠ 这个文件只测**分类规则**，不碰链。改链之前先跑它，改完再跑一次。
# ⚠⚠ 两个计数器，不能共用一个。
#   第一版只有一个 R，旧规则那格**预期**失败也往 R 里加，
#   于是末行印「新规则有 1 格不对」—— 而新规则其实 4/4 全对。
#   **末行在撒谎，而撒谎的方向是"不许换"**：它会让人以为新规则也不可靠，
#   于是保留那个已知会把 FAIL 说成 SKIP 的旧规则。
#   与「指标把样本不够报成值是 0」同族：错在**让人更不敢动**的方向。
#   ⇒ 旧规则的失败是**证据**（它就是要变红），单独计数、单独汇报；
#     退出码只由新规则决定。
ROLD=0
RNEW=0
chk_old() { # 名字 期望 实际
  if [ "$2" = "$3" ]; then printf '  PASS  %-46s -> %s\n' "$1" "$3"
  else printf '  wrong %-46s -> %s（应 %s）\n' "$1" "$3" "$2"; ROLD=$((ROLD+1)); fi
}
chk() { # 名字 期望 实际 —— 只用于新规则，它的失败必须挡住替换
  if [ "$2" = "$3" ]; then printf '  PASS  %-46s -> %s\n' "$1" "$3"
  else printf '  FAIL  %-46s -> %s（应 %s）\n' "$1" "$3" "$2"; RNEW=$((RNEW+1)); fi
}

# 旧规则：整行 grep
old() { if echo "$1" | grep -q "SKIP"; then echo SKIP; else echo NOTSKIP; fi; }
# 新规则：只认 RESULT 后面那个状态词
new() {
  local s
  s=$(echo "$1" | grep -oE '^RESULT [A-Z]+' | awk '{print $2}')
  if [ "$s" = "SKIP" ]; then echo SKIP; else echo NOTSKIP; fi
}

echo "=== 真实出现过的 4 种汇总行 ==="
L1='RESULT PASS 51/51'
L2='RESULT FAIL  6/8　有 2 条判红，不能用 SKIP 解释'   # ← 现场抓到的那一行
L3='RESULT SKIP  8/8 源码级检查通过'
L4='=== 104/104 passed ==='

chk_old "旧规则: 真 PASS"        NOTSKIP "$(old "$L1")"
chk_old "旧规则: 真 FAIL(带SKIP字样) 应 NOTSKIP" NOTSKIP "$(old "$L2")"   # ← 旧规则在这里错
chk_old "旧规则: 真 SKIP"        SKIP    "$(old "$L3")"
chk "新规则: 真 PASS"        NOTSKIP "$(new "$L1")"
chk "新规则: 真 FAIL(带SKIP字样)" NOTSKIP "$(new "$L2")"            # ← 修好的是这一格
chk "新规则: 真 SKIP"        SKIP    "$(new "$L3")"
chk "新规则: passed 形式不当 SKIP" NOTSKIP "$(new "$L4")"

echo
echo "旧规则：$([ $ROLD -eq 0 ] && echo '4/4 正确' || echo "$ROLD 格错（**这就是要修的洞**）")"
echo "新规则：$((4-RNEW))/4 正确"
if [ $RNEW -eq 0 ]; then
  echo "⇒ 新规则可以换进链里。旧规则那 $ROLD 格失败是**预期证据**，不是新规则的账。"
else
  echo "⇒ 新规则有 $RNEW 格不对 ⇒ 不许换进链。"
fi
echo
echo "（旧规则在第 2 格是错的：它把一条 FAIL 说成 SKIP，"
echo "  整链因此 exit 0。这条自检先于改链跑，就是为了让这条绿是**判红**出来的。）"
exit $RNEW
