#!/bin/bash
# Mutation test for the entropy colouring of the 2-D scatter.
#
#   M1  flat fill.  Put back `g.fillStyle = "#4a5a78"` and ignore tks[k].ent.
#       This is the original code. Must turn the ramp checks red -- they are
#       the only ones that can see it, since a flat canvas still has the axes,
#       the grid, the depth trail and the current-token marker on it.
#
#   M2  reversed ramp.  Keep reading the entropy but negate it, so certainty
#       reads as alarming and vice versa. Monotonicity catches this; a
#       "there are many colours" check does not.
#
# Run: bash mutate_entcolor.sh apply-M1 | apply-M2 | revert | status
set -u
F="/Users/zhourui/code/steer3d/frontend/public/latent/index.html"
BAK="/Users/zhourui/code/steer3d/.cache/picked/index_ent.orig"

A1='    g.fillStyle = entColor(tks[k]?.ent, emax);'
B1='    g.fillStyle = "#4a5a78";'
A2='  const t = Math.min(1, Math.max(0, Math.log1p(ent) / m));'
B2='  const t = 1 - Math.min(1, Math.max(0, Math.log1p(ent) / m));'

cnt() { grep -oF -- "$1" "$F" 2>/dev/null | wc -l | tr -d ' '; }

apply() {
  local label="$1" a="$2" b="$3"
  [ -f "$BAK" ] || cp "$F" "$BAK"
  local before; before=$(cnt "$a")
  if [ "$before" != "1" ]; then
    echo "ABORT [$label]: anchor found $before times, expected 1"
    cp "$BAK" "$F"; exit 2
  fi
  python3 - "$F" "$a" "$b" <<'PY'
import sys
path, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(path, encoding='utf-8').read()
n = s.count(a)
assert n == 1, f"anchor matched {n} times, expected 1: {a!r}"
open(path, 'w', encoding='utf-8').write(s.replace(a, b, 1))
PY
  local aa ab; aa=$(cnt "$a"); ab=$(cnt "$b")
  echo "[$label] wrote 1 site | anchor now x$aa, replacement x$ab"
  if [ "$aa" != "0" ] || [ "$ab" != "1" ]; then
    echo "ABORT [$label]: post-write read-back does not match intent."
    cp "$BAK" "$F"; exit 2
  fi
}

case "${1:-}" in
  apply-M1) apply M1 "$A1" "$B1" ;;
  apply-M2) apply M2 "$A2" "$B2" ;;
  revert)
    if [ -f "$BAK" ]; then cp "$BAK" "$F"; rm -f "$BAK"; fi
    echo "reverted: ent-fill=$(cnt "$A1") ramp-t=$(cnt "$A2")" ;;
  status)
    echo "live: ent-fill=$(cnt "$A1") ramp-t=$(cnt "$A2")"
    echo "      M1-mutant=$(cnt "$B1") M2-mutant=$(cnt "$B2")" ;;
  *) echo "usage: $0 apply-M1|apply-M2|revert|status"; exit 2 ;;
esac
