#!/bin/bash
# Mutation test for the "why this token" panel.
#
# Two independent mutations, because the panel had two separable defects:
#
#   M1  softmax -> raw logits.  Reverting to printing the logit (31.13) and
#       sizing the bar by (logit - lo) / (best - lo) is the original code.
#       The percentage assertions must go red, because they compare against
#       an independent softmax of the same file.
#
#   M2  visTokHtml -> esc.  Reverting to plain HTML drops the newline markers,
#       so '.\n\n' and '.' render identically again. Only the distinctness
#       assertions can catch this -- a percentage check cannot see it.
#
#   M3  visTokHtml -> visTok.  Drops the HTML escaping while keeping the
#       whitespace glyphs, so the whitespace checks stay green and only the
#       "this row must not be empty" check can notice. It is the exact defect
#       that shipped, so it is the one worth keeping as a regression test:
#       the vocabulary is full of strings that are valid HTML, and at step 0
#       the top-4 candidates are `<think>`, `</think>`, `<|im_start|>`,
#       `<|im_end|>`, with `<tool_response>` / `</tool_response>` at 6 and 9.
#       Unescaped, four of the ten visible rows rendered EMPTY -- including
#       the cell under the headline that answers the user's actual question.
#
# Anchors are counted before and after and read back, so a substitution that
# matches nothing is reported as an invalid mutation rather than being
# recorded as "the check did not go red".
#
# Run: bash mutate_picked.sh apply-M1 | apply-M2 | revert | status
set -u
F="/Users/zhourui/code/steer3d/frontend/public/latent/index.html"
BAK="/Users/zhourui/code/steer3d/.cache/picked/index.html.orig"

# M1: the bar width and the printed number both switch to logit space.
A1='    const w = r.p / hi * wBar;'
B1='    const w = (r.logit - top[27].logit) / (hi - top[27].logit || 1) * wBar;'
# The table cell, likewise.
A2='      + `<td class="n" style="width:62px">${pctTxt}</td></tr>`;'
B2='      + `<td class="n" style="width:62px">${r.logit.toFixed(2)}</td></tr>`;'
# M2: the whitespace-revealing wrapper.
A3='<td class="tok" style="color:${isChosen?"var(--acc)":"var(--ink)"}">${visTokHtml(tokStr(r.id))}'
B3='<td class="tok" style="color:${isChosen?"var(--acc)":"var(--ink)"}">${esc(tokStr(r.id))}'
# M3: drop the HTML escaping but keep the whitespace glyphs.
A4='${visTokHtml(tokStr(r.id))}'
B4='${visTok(tokStr(r.id))}'

# Count occurrences, not lines. `grep -c` counts matching *lines*, so an
# anchor appearing on one line twice reports 1 -- and the read-back then
# cannot tell a successful mutation from a partial one. `grep -o` also exits
# 1 on zero matches, which is why the result is not taken from $? here.
cnt() { grep -oF -- "$1" "$F" 2>/dev/null | wc -l | tr -d ' '; }

apply() {  # apply <label> <anchor> <replacement> [<anchor> <replacement> ...]
  local label="$1"; shift
  [ -f "$BAK" ] || cp "$F" "$BAK"
  local pairs=("$@") n=$(( ${#pairs[@]} / 2 )) i
  for (( i=0; i<n; i++ )); do
    local a="${pairs[$((i*2))]}" b="${pairs[$((i*2+1))]}"
    local before; before=$(cnt "$a")
    if [ "$before" != "1" ]; then
      echo "ABORT [$label]: anchor found $before times, expected exactly 1:"
      echo "  $a"
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
  done
  # read back
  for (( i=0; i<n; i++ )); do
    local a="${pairs[$((i*2))]}" b="${pairs[$((i*2+1))]}"
    local after_a after_b; after_a=$(cnt "$a"); after_b=$(cnt "$b")
    echo "[$label] wrote: $(echo "$b" | cut -c1-58)…  | anchor now x$after_a, replacement x$after_b"
    if [ "$after_a" != "0" ] || [ "$after_b" != "1" ]; then
      echo "ABORT [$label]: post-write read-back does not match intent."
      cp "$BAK" "$F"; exit 2
    fi
  done
}

case "${1:-}" in
  apply-M1) apply M1 "$A1" "$B1" "$A2" "$B2" ;;
  apply-M2) apply M2 "$A3" "$B3" ;;
  apply-M3) apply M3 "$A4" "$B4" ;;
  revert)
    if [ -f "$BAK" ]; then cp "$BAK" "$F"; rm -f "$BAK"; fi
    echo "reverted: M1 bar=$(cnt "$A1") cell=$(cnt "$A2")  M2=$(cnt "$A3")  M3=$(cnt "$A4")" ;;
  status)
    echo "live: M1 bar=$(cnt "$A1") cell=$(cnt "$A2")  M2=$(cnt "$A3")  M3=$(cnt "$A4")"
    echo "      M1bar-mutant=$(cnt "$B1") M1cell-mutant=$(cnt "$B2") M2-mutant=$(cnt "$B3") M3-mutant=$(cnt "$B4")" ;;
  *) echo "usage: $0 apply-M1|apply-M2|apply-M3|revert|status"; exit 2 ;;
esac
