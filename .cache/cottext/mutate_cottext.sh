#!/bin/bash
# Mutation test for the "read it word by word" CoT block.
#
# A green check proves nothing until a mutation proves the check has teeth.
# Five mutations, one per failure mode this block is most exposed to:
#
#   M1  Delete the "this is not an essay" warning. The block's whole reason for
#       existing over a table of percentages is that the reader can see the
#       seam where a word was patched. Strip the warning and the block still
#       renders, still shows both texts, still shows correct numbers -- and
#       invites exactly the inverted conclusion the harness makes possible. A
#       presence check on the block would be green here.
#
#   M2  Both arms get the primary's continuation. The data-cotarm key is left
#       alone on purpose: a mutation that only deletes an element is caught by
#       "the element is missing", which proves nothing about whether the checks
#       can tell two DIFFERENT texts from one text pasted twice.
#       `after_shadow` is replaced by
#       `after_primary`. Every number stays correct; the prose becomes
#       self-consistent and completely false -- "the two arms agree" presented
#       as two arms. Only the check that the two texts differ, and the one
#       that the shadow's own text is on the page, can catch this.
#
#   M3  Report the disagreement rate as the agreement rate. (1 - agreement) is
#       printed where agreement belongs. Catches only the checks that read the
#       printed number back out and compare it with the payload.
#
#   M4  Drop the unit from the character position. "第 7" instead of
#       "第 7 个字符" reads as a step number, and the block explicitly warns
#       that the token step and the character offset are different things.
#
#   M6  The jump link scrolls the window instead of the inner scroller.
#   M7  The jump lands on the block's top instead of on the text.
#   M8  The jump hint prints a constant instead of the measured offset.
#
#   M5  Open on index 0 instead of the earliest divergence. This is the exact
#       regression the current code has already survived once: the state field
#       was 0, `idx = 0` was a valid index, and the "pick the best" branch was
#       dead while its comment still described it. M5 exists to keep that dead
#       branch from coming back unnoticed.
#
# Anchors are counted with `grep -oF` (occurrences, not lines) and read back
# after the write, so a substitution that matched nothing is reported as an
# invalid mutation instead of being filed as "the check did not go red".
#
# Every anchor is a SINGLE line. `grep` matches line by line, so an anchor
# containing a newline can never match -- it reports 0, and the guard below
# then says "anchor matched 0 times" while the real mistake is invisible. One
# of these was written with an embedded newline first and counted 2.
#
# Run: bash mutate_cottext.sh apply-M1 | apply-M2 | ... | revert | status
set -u
ROOT="/Users/zhourui/code/steer3d"
F="$ROOT/frontend/public/latent/index.html"
BAK="$ROOT/.cache/cottext/index.html.orig"
V="$ROOT/.cache/cottext/verify_cottext.mjs"

# M1: the warning's opening sentence. Matched on the distinctive run of text,
# not on the whole <div>, so the replacement cannot accidentally reinsert a
# correct-looking warning elsewhere in the block.
A1='    下面那行<b>不是</b>"没有向量时模型会写的那篇文章"。它在每个换词的地方都会语法破碎'
B1='    下面那行就是"没有向量时模型会写的那篇文章"。它在每个换词的地方都会语法破碎'

# M2: the shadow arm is fed the primary's continuation.
A2='  h += arm("没加向量（对照臂）", "#ff8fa3", H.after_shadow, "", "shadow");'
B2='  h += arm("没加向量（对照臂）", "#ff8fa3", H.after_primary, "", "shadow");'

# M3: print the disagreement rate where the agreement rate belongs.
A3='`<b>${(agree*100).toFixed(1)}%</b>`,'
B3='`<b>${((1-agree)*100).toFixed(1)}%</b>`,'

# M4: delete the whole "these are two different units" sentence.
#
# This one took two attempts, and both earlier versions came back ALL PASS:
#   v1 dropped the word 字符 from one of two places the unit is written, and
#      "第 N 个字符" was still printed a few characters away;
#   v2 relabelled the sentence "还有两个单位别搞混" -> "补充", leaving its body.
# In both cases the reader's conclusion was completely unchanged, so neither was
# a mutation at all -- they were no-ops wearing a mutation's clothes, and
# recording them as "the check has no teeth" would have been exactly backwards.
# The mutation now inverts the claim itself: the two numbers ARE the same kind
# of thing. That is the proposition a reader could actually be misled about.
A4='它们不是一回事，混用会让人以为分岔比实际更靠后。'
B4='它们是一回事，可以互换着用。'

# M5: force index 0, disabling the "earliest divergence" default.
A5='  const idx = (S.cotTextPick >= 0 && S.cotTextPick < all.length) ? S.cotTextPick : best;'
B5='  const idx = 0;'

# M6: scroll the window instead of the inner scroller. The page does not
# scroll here (documentElement.scrollHeight == innerHeight), so this is the
# classic dead-button: it throws no error, changes nothing, and looks wired up.
A6='      if(tgt && box) box.scrollTop += tgt.getBoundingClientRect().top - box.getBoundingClientRect().top - 8;'
B6='      if(tgt) window.scrollTo(0, tgt.getBoundingClientRect().top + window.scrollY);'

# M7: land on the block top instead of the text. The block is ~1212px tall in a
# 300px window, so this puts a heading and four numbers on screen and leaves
# the prose 400-700px further down -- the reader sees the feature "work".
A7='      const tgt = tb.querySelector("[data-cotpre]") || tb.querySelector("[data-cottext]");'
B7='      const tgt = tb.querySelector("[data-cottext]");'

# M8: print a constant instead of the measured offset. This is the failure the
# two-pass write was built to prevent: the hint sits above the block, so
# measuring before writing reported the world one text-height earlier.
A8='      jh.textContent = line(blk.getBoundingClientRect().top - box.getBoundingClientRect().top);'
B8='      jh.textContent = line(2407);'

cnt() { grep -oF -- "$1" "$F" 2>/dev/null | wc -l | tr -d ' ' ; }

anchors_for() {
  case "$1" in
    M1) printf '%s' "$A1" ;;
    M2) printf '%s' "$A2" ;;
    M3) printf '%s' "$A3" ;;
    M4) printf '%s' "$A4" ;;
    M5) printf '%s' "$A5" ;;
    M6) printf '%s' "$A6" ;;
    M7) printf '%s' "$A7" ;;
    M8) printf '%s' "$A8" ;;
  esac
}

apply() {
  local label="$1"
  local a b
  case "$label" in
    M1) a="$A1"; b="$B1" ;;
    M2) a="$A2"; b="$B2" ;;
    M3) a="$A3"; b="$B3" ;;
    M4) a="$A4"; b="$B4" ;;
    M5) a="$A5"; b="$B5" ;;
    M6) a="$A6"; b="$B6" ;;
    M7) a="$A7"; b="$B7" ;;
    M8) a="$A8"; b="$B8" ;;
    *) echo "unknown mutation $label"; return 2 ;;
  esac

  local n; n=$(cnt "$a")
  if [ "$n" != "1" ]; then
    echo "FATAL: anchor for $label matched $n times, expected exactly 1."
    echo "       Refusing to mutate: an anchor that matches nothing produces a"
    echo "       no-op, and a no-op reads as 'the check did not go red'."
    return 3
  fi

  # A backup whose lifetime spans several runs will silently restore a tree
  # from an earlier session and delete whatever was edited since -- which is
  # exactly what happened the first time: the backup predated the
  # `data-cotarm` hooks, so every revert wiped them and the later mutations
  # were run against a page that no longer had the feature under test. The
  # backup now lives for exactly one apply/revert pair.
  #
  # The health anchor guards the other half: refuse to mutate a tree that is
  # not the one this script was written against, instead of mutating it and
  # reporting the result as if it meant something.
  local ha; ha=$(cnt 'data-cotarm="${key}"')
  if [ "$ha" != "1" ]; then
    echo "FATAL: health anchor (data-cotarm hook) count=$ha, expected 1."
    echo "       The page is not the tree this mutation script targets."
    echo "       Refusing to mutate it."
    return 6
  fi
  cp "$F" "$BAK"
  python3 - "$F" "$a" "$b" <<'PY'
import sys
path, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(path, encoding='utf-8').read()
assert s.count(a) == 1, f'anchor count is {s.count(a)}, not 1'
open(path, 'w', encoding='utf-8').write(s.replace(a, b))
PY
  # Read back from disk. A successful python exit is not evidence the file on
  # disk changed -- a stale path or a failed write would look identical.
  local m; m=$(cnt "$b"); local k; k=$(cnt "$a")
  if [ "$k" != "0" ] || [ "$m" -lt 1 ]; then
    echo "FATAL: $label did not take (anchor still $k, replacement $m)"
    cp "$BAK" "$F"
    return 4
  fi
  echo "$label applied  (anchor $n -> 0, replacement +$m)"
  node --check <(python3 -c "
import re,sys
s=open('$F',encoding='utf-8').read()
sys.stdout.write(re.findall(r'<script>(.*?)</script>', s, re.S)[0])
") || { echo 'FATAL: mutated page no longer parses'; cp "$BAK" "$F"; return 5; }
  return 0
}

run_checks() { node "$V" 2>&1; }

revert() {
  if [ ! -f "$BAK" ]; then echo "no backup to revert (already reverted?)"; return 1; fi
  cp "$BAK" "$F"
  local ha; ha=$(cnt 'data-cotarm="${key}"')
  if [ "$ha" != "1" ]; then
    echo "FATAL: reverted file lost its health anchor (count=$ha)."
    echo "       The backup was stale; the file on disk is NOT the pre-mutation tree."
    return 7
  fi
  rm -f "$BAK"
  echo "reverted (backup removed, health anchor intact)"
}

status() {
  local miss=0 lbl
  local ha; ha=$(cnt 'data-cotarm="${key}"')
  [ "$ha" = "1" ] || { echo "  health anchor data-cotarm count=$ha (want 1)"; miss=1; }
  if [ -f "$BAK" ]; then echo "  WARNING: stale backup present at $BAK"; fi
  for lbl in M1 M2 M3 M4 M5 M6 M7 M8; do
    local a; a=$(anchors_for "$lbl")
    local n; n=$(cnt "$a")
    [ "$n" = "1" ] || { echo "  $lbl anchor count = $n (want 1)"; miss=1; }
  done
  [ $miss = 0 ] && echo "all 8 mutation anchors present exactly once"
  return $miss
}

case "${1:-}" in
  apply-M1) apply M1 ;;
  apply-M2) apply M2 ;;
  apply-M3) apply M3 ;;
  apply-M4) apply M4 ;;
  apply-M5) apply M5 ;;
  apply-M6) apply M6 ;;
  apply-M7) apply M7 ;;
  apply-M8) apply M8 ;;
  revert) revert ;;
  status) status ;;
  check)  run_checks ;;
  *) echo "usage: $0 apply-M1|apply-M2|apply-M3|apply-M4|apply-M5|apply-M6|apply-M7|apply-M8|revert|status|check"; exit 2 ;;
esac
