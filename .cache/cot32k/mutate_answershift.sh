#!/bin/bash
# Mutation test for the "换个问法：答案其实会变" block.
#
# The block corrects a claim the page used to make without qualification, so
# the failure mode is not a crash -- it is the old claim quietly surviving next
# to the new one, or the new one quietly vanishing. All four mutations are
# built to be silent.
#
#   M1  Delete the whole block. Nothing else on the page changes, the old
#       scoped sentence still reads fine, and the answer-shift measurement
#       simply stops being shown.
#
#   M2  Report the wrong denominator: `comparable` (answers parseable at all)
#       instead of `comparable_both_closed` (both arms finished). That mixes
#       finished runs against runs that ran out of budget -- precisely the
#       comparison the page says it is not making.
#
#   M3  Drop the sentence saying the change is real rather than an artefact of
#       a loose extractor. The numbers stay and become unfalsifiable.
#
#   M4  Reinstate an unqualified "the answer is stable" conclusion. This is the
#       one that matters most: the page would then carry two contradictory
#       statements, and the contradiction check is the only thing between a
#       reader and whichever one they skim.
#
# The backup lives for exactly one apply/revert pair, and a health anchor
# refuses to mutate a tree that is not the one this was written against.
set -u
ROOT="/Users/zhourui/code/steer3d"
F="$ROOT/frontend/public/latent/index.html"
BAK="$ROOT/.cache/cot32k/index.html.orig"
HEALTH='const AS = C.answer_shift_free_run;'

A1="$HEALTH"
B1='  const AS = null;'

A2='${a.changed_both_closed}/${a.comparable_both_closed} 次不同</b>'
B2='${a.changed}/${a.comparable} 次不同</b>'

A3='这些「变了」是真的变了，不是提取器编的：'
B3='这些「变了」：'

A4='换成上面那个自由生成的比较，结论就反过来了'
B4='所以答案是稳定的，不受向量影响'

cnt() { grep -oF -- "$1" "$F" 2>/dev/null | wc -l | tr -d ' ' ; }

anchor_of() {
  case "$1" in
    M1) printf '%s' "$A1" ;; M2) printf '%s' "$A2" ;;
    M3) printf '%s' "$A3" ;; M4) printf '%s' "$A4" ;;
  esac
}

apply() {
  local label="$1" a b
  case "$label" in
    M1) a="$A1"; b="$B1" ;; M2) a="$A2"; b="$B2" ;;
    M3) a="$A3"; b="$B3" ;; M4) a="$A4"; b="$B4" ;;
    *) echo "unknown $label"; return 2 ;;
  esac

  local ha; ha=$(cnt "$HEALTH")
  if [ "$ha" != "1" ]; then
    echo "FATAL: health anchor count=$ha (want 1). The page is not the tree this"
    echo "       script targets. Refusing to mutate."
    return 6
  fi

  local n; n=$(cnt "$a")
  if [ "$n" != "1" ]; then
    echo "FATAL: $label anchor matched $n times (want 1). Refusing to mutate:"
    echo "       an anchor that matches nothing is a no-op, and a no-op reads"
    echo "       as 'the check did not go red'."
    return 3
  fi

  cp "$F" "$BAK"
  python3 - "$F" "$a" "$b" <<'PY'
import sys
path, a, b = sys.argv[1:4]
s = open(path, encoding='utf-8').read()
assert s.count(a) == 1, 'anchor count %d' % s.count(a)
open(path, 'w', encoding='utf-8').write(s.replace(a, b))
PY
  local k m; k=$(cnt "$a"); m=$(cnt "$b")
  if [ "$k" != "0" ] || [ "$m" -lt 1 ]; then
    echo "FATAL: $label did not take (anchor $k, replacement $m)"
    cp "$BAK" "$F"; return 4
  fi
  echo "$label applied (anchor $n -> 0, replacement +$m)"
}

revert() {
  [ -f "$BAK" ] || { echo "no backup to revert"; return 1; }
  cp "$BAK" "$F"; rm -f "$BAK"
  local ha; ha=$(cnt "$HEALTH")
  [ "$ha" = "1" ] || { echo "FATAL: reverted file lost its health anchor ($ha)"; return 7; }
  echo "reverted (backup removed, health anchor intact)"
}

case "${1:-}" in
  apply-M1) apply M1 ;; apply-M2) apply M2 ;;
  apply-M3) apply M3 ;; apply-M4) apply M4 ;;
  revert) revert ;;
  status)
    miss=0
    for l in M1 M2 M3 M4; do
      a=$(anchor_of "$l"); n=$(cnt "$a")
      printf '  %s anchor=%s\n' "$l" "$n"
      [ "$n" = "1" ] || miss=1
    done
    ha=$(cnt "$HEALTH")
    printf '  health=%s\n' "$ha"
    [ "$ha" = "1" ] || miss=1
    [ $miss = 0 ] && echo "all 4 anchors + health present exactly once"
    exit $miss ;;
  *) echo "usage: $0 apply-M1|apply-M2|apply-M3|apply-M4|revert|status"; exit 2 ;;
esac
