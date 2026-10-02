#!/bin/bash
# Mutation test for the problem-provenance declaration on the answer-readout
# screen.
#
# This screen is the one place a reader meets 标准答案 head-on: the line reads
#
#     1984_I_1 · 标准答案 10 · 原本答错，加向量后答对了
#
# and the number comes from aime_loader._BUILTIN's own `answer` field, over
# problems the bank documents as inspired-by-AIME and re-worded. So the
# declaration is not decoration -- it is the only thing standing between
# "the model got 10 wrong" and "10 is the official AIME key".
#
# Three mutations, all silent: the page keeps every number and every layout.
#
#   M1  Delete the declaration call. The screen still shows 标准答案 and the
#       verdict; the caveat simply is not there any more.
#
#   M2  Flip the declaration's claim to the opposite — these ARE the official
#       AIME problems. This is the realistic failure: the ids all look like
#       AIME ids, and "tidying up a page" pushes toward sounding more official.
#       Nothing looks broken afterwards.
#
#   M3  Move the declaration to the END of the block, below the two arm texts
#       and the "读这两段之前" note. It is still inside [data-aroot] and still
#       on screen, so a presence-only check still passes. Only the gap check
#       tells this apart from M1 — which is the whole point: a caveat that is
#       present but below the fold is not read by anyone looking for the
#       number.
set -u
ROOT="/Users/zhourui/code/steer3d"
F="$ROOT/frontend/public/latent/index.html"
BAKDIR="$ROOT/.cache/arreadout/backs"
mkdir -p "$BAKDIR"

# Health anchor: a line that exists only when this block is present. Without
# it, running this script against a different tree silently mutates whatever
# happens to match, and a green result means nothing.
HEALTH='function renderProblemSetNote(PS, where){'

A1='  h += renderProblemSetNote(T.problem_set, "answer_readout");'
B1='  // h += renderProblemSetNote(T.problem_set, "answer_readout");'

A2='道题不是历年 AIME 原题。'
B2='道题就是历年 AIME 原题。'

# A3 is the same line as A1, so the mutation has to both DELETE it and INSERT
# it lower down. A single replace that only deleted it would collapse into M1,
# and a single replace that only moved it would leave two declarations on the
# page — a different defect, but one this file does not claim to cover.
A3='  h += renderProblemSetNote(T.problem_set, "answer_readout");'
# The closing-tag line alone matches 8 times in this file, so anchoring on it
# makes the mutation refuse to run — and a refusal reads exactly like "the
# check is fine" when nothing was mutated. Anchor on the two-line sequence
# that ends this function, which matches once.
B3='  h += `</div>`;
  return h;
}

function renderCotTexts(){'
C3='  h += renderProblemSetNote(T.problem_set, "answer_readout");
  h += `</div>`;
  return h;
}

function renderCotTexts(){'

cnt() { grep -oF -- "$1" "$F" 2>/dev/null | wc -l | tr -d ' ' ; }

# M3's anchor spans four lines, and `grep -F` matches line by line: a
# multi-line pattern is looked for as four independent lines, each of which
# matches many times, so the uniqueness check reports a wrong number and the
# mutation refuses to run. The first version of this script hit exactly that
# and printed "anchor did not take" while the page was untouched.
cnt2() {  # cnt2 <two-or-more-line-anchor>
  python3 - "$F" "$1" <<'PYEOF'
import sys
path, pat = sys.argv[1], sys.argv[2]
print(open(path, encoding='utf-8').read().count(pat))
PYEOF
}

anchor_of() {
  case "$1" in
    M1) printf '%s' "$A1" ;; M2) printf '%s' "$A2" ;; M3) printf '%s' "$A3" ;;
  esac
}

apply() {
  local label="$1" a b
  case "$label" in
    M1) a="$A1"; b="$B1" ;; M2) a="$A2"; b="$B2" ;;
    M3) a="$B3"; b="$C3" ;;   # insert-after, not replace
    *) echo "unknown $label"; return 2 ;;
  esac

  local ha; ha=$(cnt "$HEALTH")
  if [ "$ha" != "1" ]; then
    echo "FATAL: health anchor count=$ha (want 1). Not the tree this script"
    echo "       targets. Refusing to mutate."
    return 6
  fi

  # A1 and A3 are the SAME line, so the M3 anchor is the block's closing tag
  # instead. Both must still match exactly once, or the mutation is refused.
  local n
  case "$label" in
    M3) n=$(cnt2 "$a") ;;   # multi-line anchor; grep -F cannot count it
    *)  n=$(cnt "$a") ;;
  esac
  if [ "$n" != "1" ]; then
    echo "FATAL: $label anchor matched $n times (want 1). Refusing to mutate:"
    echo "       an anchor that matches nothing is a no-op, and a no-op reads"
    echo "       as 'the check did not go red'."
    return 3
  fi

  local bak="$BAKDIR/$(basename "$F").orig"
  printf '%s' "$F" > "$BAKDIR/target"
  cp "$F" "$bak"
  if [ "$label" = "M3" ]; then
    # Delete the call in place, then insert it after the block's closing tag.
    # Doing it as a plain replace would either leave two declarations on the
    # page (the original line plus a moved copy) or delete it and stop --
    # and the second is exactly M1 wearing a different name, which would make
    # the comment above a lie.
    python3 - "$F" "$A1" "$B3" "$C3" <<'PY'
import sys
path, call, close_tag, moved = sys.argv[1:5]
s = open(path, encoding='utf-8').read()
assert s.count(call) == 1, 'call anchor count %d' % s.count(call)
assert s.count(close_tag) == 1, 'close anchor count %d' % s.count(close_tag)
s = s.replace(call, '')
# Insert INSIDE [data-aroot], immediately before this block's closing tag.
# Inserting after it would put the declaration outside the block, and the
# check it is meant to exercise would then be measuring M1.
s = s.replace(close_tag, moved)
open(path, 'w', encoding='utf-8').write(s)
PY
  else
    python3 - "$F" "$a" "$b" <<'PY'
import sys
path, a, b = sys.argv[1:4]
s = open(path, encoding='utf-8').read()
assert s.count(a) == 1, 'anchor count %d' % s.count(a)
open(path, 'w', encoding='utf-8').write(s.replace(a, b))
PY
  fi
  # Prove the file actually changed before claiming the mutation took, and
  # prove the declaration still exists somewhere — M3 in particular must
  # leave it present, or the check it is meant to exercise never runs.
  local ha2; ha2=$(cnt 'renderProblemSetNote(T.problem_set, "answer_readout")')
  if [ "$label" = "M3" ] && [ "$ha2" != "1" ]; then
    echo "FATAL: M3 left $ha2 declaration call(s); it must leave exactly 1"
    cp "$bak" "$F"
    return 5
  fi
  # Prove the file actually changed before claiming the mutation took. A
  # replacement that is already present elsewhere in the file (M2's wording
  # differs by one character, so this is not hypothetical) would otherwise
  # report success while the page is untouched.
  #
  # M3 is checked by POSITION, not by string content: the replacement text
  # ends with the anchor it replaced, so "anchor count 0" is impossible and
  # "replacement count >= 1" is true before the mutation as well. Both were
  # the first version of this check, and together they rejected a mutation
  # that had in fact applied -- the guard reporting failure on a successful
  # edit is its own kind of lie, and it hid the fact that M3 was untested.
  local k m
  if [ "$label" = "M3" ]; then
    m=$(python3 - "$F" <<'PY'
import sys
s = open(sys.argv[1], encoding='utf-8').read()
call = s.index('renderProblemSetNote(T.problem_set, "answer_readout")')
# The last arm card is unambiguously below the 标准答案 line in the healthy
# tree, so a moved declaration has to come after it. The marker is the
# armCard() CALL, not `data-armtext="tail:steered"` -- that attribute is
# written by a template literal at render time and does not exist in the
# source at all, so searching for it raises and the guard below fails on a
# mutation that applied correctly.
arm = s.index('armCard("tail:steered"')
print(1 if call > arm else 0)
PY
)
    if [ "$m" != "1" ]; then
      echo "FATAL: M3 did not move the declaration below the arm texts"
      cp "$bak" "$F"
      return 4
    fi
    echo "applied M3 (declaration moved below the arm texts)"
    return 0
  fi
  k=$(cnt "$a"); m=$(cnt "$b")
  if [ "$k" != "0" ] || [ "$m" -lt 1 ]; then
    echo "FATAL: $label did not take (anchor $k, replacement $m)"
    cp "$bak" "$F"
    return 4
  fi
  echo "applied $label"
}

revert() {
  [ -f "$BAKDIR/target" ] || { echo "nothing to revert"; return 0; }
  local t; t=$(cat "$BAKDIR/target")
  [ -f "$BAKDIR/$(basename "$t").orig" ] || { echo "FATAL: no backup for $t"; return 7; }
  cp "$BAKDIR/$(basename "$t").orig" "$t"
  local ha; ha=$(grep -cF -- "$HEALTH" "$t")
  [ "$ha" = "1" ] || { echo "FATAL: reverted script lost its health anchor ($ha)"; return 7; }
  ha=$(cnt "$HEALTH")
  [ "$ha" = "1" ] || { echo "FATAL: reverted file lost its health anchor ($ha)"; return 7; }
  echo "reverted (backup kept, health anchor intact)"
}

case "${1:-}" in
  apply-M1) apply M1 ;; apply-M2) apply M2 ;; apply-M3) apply M3 ;;
  revert) revert ;;
  status)
    miss=0
    for l in M1 M2 M3; do
      case $l in
        M3) n=$(cnt2 "$B3") ;;
        *)  n=$(cnt "$(anchor_of "$l")") ;;
      esac
      printf '  %s anchor=%s\n' "$l" "$n"
      [ "$n" = "1" ] || miss=1
    done
    ha=$(cnt "$HEALTH")
    printf '  health=%s\n' "$ha"
    [ "$ha" = "1" ] || miss=1
    [ $miss = 0 ] && echo "all 3 anchors + health present exactly once"
    exit $miss ;;
  *) echo "usage: $0 apply-M1|apply-M2|apply-M3|revert|status"; exit 2 ;;
esac
