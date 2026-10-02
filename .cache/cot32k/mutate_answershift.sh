#!/bin/bash
# Mutation test for the "换个问法：答案其实会变" block.
#
# The block corrects a claim the page used to make without qualification, so
# the failure mode is not a crash -- it is the old claim quietly surviving next
# to the new one, or the new one quietly vanishing. All ten mutations are
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
G="$ROOT/backend/examples/build_cot_effect.py"
H="$ROOT/backend/examples/run_intervention.py"
# The backup is keyed BY TARGET, and the target is recorded alongside it.
# One shared path for three different files (the page, the analysis script, the
# collection script) means a failure in the middle of M6 restores
# run_intervention.py's bytes into index.html -- which is exactly what happened,
# and it destroyed 2884 lines of page that only survived because git happened to
# have them. A backup is a backup of one specific file, and the restore path
# must name that file, not assume it.
BAKDIR="$ROOT/.cache/cot32k/backs"
mkdir -p "$BAKDIR"
HEALTH='const AS = C.answer_shift_free_run;'

A1="$HEALTH"
B1='  const AS = null;'

A2='${a.changed_both_closed}/${a.comparable_both_closed} 次不同</b>'
B2='${a.changed}/${a.comparable} 次不同</b>'

A3='这些「变了」是真的变了，不是提取器编的：'
B3='这些「变了」：'

A4='换成上面那个自由生成的比较，结论就反过来了'
B4='所以答案是稳定的，不受向量影响'

# M5, in the ANALYSIS SCRIPT rather than the page: relax the gate so a batch
# with an unreproducible forward pass still builds. This is the one that
# matters most -- the gate is the only thing standing between "the vector did
# it" and "the GPU did it", and a gate nobody can see failing is not a gate.
A5='    if n_same != len(det):'
B5='    if False:'

# M6, in the COLLECTION script rather than the analysis or the page. The page
# says the two zero-vector runs of one problem are separated by a full
# generation, and that is only true because run_intervention.py nests
# `for direction:` outside `for strength:`. Swap the two loops and the bound
# silently weakens to "the same call twice", while every number in the payload
# stays exactly as it was -- the page would be quoting a measurement taken
# under an assumption that no longer holds.
A6='        for direction in directions:
            for strength in args.sweep:'
B6='        for strength in args.sweep:
            for direction in directions:'

# M7, the one that matters for the accuracy row. The panel now prints how many
# questions were answered correctly before and after, next to how many answers
# changed at all. A realistic bug here is not a crash: someone retypes a count
# instead of reading it out of the payload, and the page keeps rendering fine
# while quietly disagreeing with the data. The check that catches it compares
# the rendered string against the payload field, so a hardcoded 5 is red
# against a payload that says 6 and 4 in the two directions.
A7='对→对 ${V["right->right"]} · 对→错 ${V["right->wrong"]}'
B7='对→对 5 · 对→错 ${V["right->wrong"]}'

# M8 is the mistake I actually made while writing this block. The prose first
# read "（7 → 7）——1 题从错变对、1 题从对变错、6 次错换错" with every number
# typed by hand: correct for today's 84 runs, silently wrong the moment the
# remaining 12 land, and with nothing on the page to say so. A rendered-value
# check cannot catch it -- the hardcoded text and the generated text are the
# same string today. So this one is checked in the source, and this is the
# mutation that proves the check bites.
#
# The value is written as a single-quoted shell string with no apostrophe
# inside it. A single-quoted string cannot contain an apostrophe, and escaping
# one as \' closes the quote early instead -- the rest of the line is parsed as
# a command and the file dies with "command not found" pointing at an arrow
# character. Double quotes are no better: ${...} still expands there. So the
# anchor is the inner expression, which has neither problem.
A8='${dnAcc.correct_zero} → ${dnAcc.correct_steered}'
B8='7 → 7'

# M9 flips the provenance declaration to the opposite claim. This is the
# mutation that matters: the failure mode here is not a missing caveat but a
# confident wrong one. Every 题号 on the page is shaped like an AIME id
# (1983_I_1, 2025_I_1), and the instinct when cleaning up a page is to make
# the problems sound more official, not less. Nothing on the page would look
# broken afterwards — the numbers are unchanged, the layout is unchanged, and
# "标准答案 760" would sit right under a sentence promising it is the real
# AIME key. So the declaration has to be checked for its own wording, not
# merely for its presence.
A9='道题不是历年 AIME 原题。'
B9='道题是历年 AIME 真题。'

# M10 puts "32k" back in the title and drops the budget explanation. The
# anchor is the whole title line, not the substring: `加长预算重跑` also
# appears in the function's header comment, and an anchor that matches twice
# makes the mutation refuse to run — which reads as "the check is fine" when
# nothing was actually mutated.
A10='同一件事，加长预算重跑（${C.n_runs} 次运行'
B10='同一件事，32k 预算重跑（${C.n_runs} 次运行'

cnt() { grep -oF -- "$1" "$F" 2>/dev/null | wc -l | tr -d ' ' ; }

# M6's anchor spans two lines, and `grep -F` matches line by line: a
# multi-line pattern either becomes two independent patterns (matching twice
# for the wrong reason) or, with the newline turned into \001, never matches
# at all. Both were tried and both report a plausible wrong number. Python is
# the only thing here that can count a two-line anchor honestly.
cnt2() {  # cnt2 <file> <two-line-anchor>
  python3 - "$1" "$2" <<'PYEOF'
import sys
path, pat = sys.argv[1], sys.argv[2]
print(open(path, encoding='utf-8').read().count(pat))
PYEOF
}

anchor_of() {
  case "$1" in
    M1) printf '%s' "$A1" ;; M2) printf '%s' "$A2" ;; M5) printf '%s' "$A5" ;;
    M3) printf '%s' "$A3" ;; M4) printf '%s' "$A4" ;; M6) printf '%s' "$A6" ;;
    M7) printf '%s' "$A7" ;; M8) printf '%s' "$A8" ;;
    M9) printf '%s' "$A9" ;; M10) printf '%s' "$A10" ;;
  esac
}

apply() {
  local label="$1" a b target="$F"
  case "$label" in
    M1) a="$A1"; b="$B1" ;; M2) a="$A2"; b="$B2" ;;
    M3) a="$A3"; b="$B3" ;; M4) a="$A4"; b="$B4" ;;
    M5) a="$A5"; b="$B5"; target="$G" ;;
    M6) a="$A6"; b="$B6"; target="$H" ;;
    M7) a="$A7"; b="$B7" ;; M8) a="$A8"; b="$B8" ;;
    M9) a="$A9"; b="$B9" ;; M10) a="$A10"; b="$B10" ;;
    *) echo "unknown $label"; return 2 ;;
  esac

  local ha
  case "$label" in
    M5) ha=$(grep -cF -- "$A5" "$G") ;;
    M6) ha=$(cnt2 "$H" "$A6") ;;
    *)  ha=$(cnt "$HEALTH") ;;
  esac
  if [ "$ha" != "1" ]; then
    echo "FATAL: health anchor count=$ha (want 1). Not the tree this script"
    echo "       targets. Refusing to mutate."
    return 6
  fi

  local n
  case "$label" in
    M5) n=$(grep -cF -- "$a" "$G") ;;
    M6) n=$(cnt2 "$H" "$a") ;;
    *)  n=$(cnt "$a") ;;
  esac
  if [ "$n" != "1" ]; then
    echo "FATAL: $label anchor matched $n times (want 1). Refusing to mutate:"
    echo "       an anchor that matches nothing is a no-op, and a no-op reads"
    echo "       as 'the check did not go red'."
    return 3
  fi

  # The backup is named after the file it belongs to, and the target is
  # recorded next to it, so revert() cannot restore the wrong file.
  local bak="$BAKDIR/$(basename "$target").orig"
  printf '%s' "$target" > "$BAKDIR/target"
  cp "$target" "$bak"
  python3 - "$target" "$a" "$b" <<'PY'
import sys
path, a, b = sys.argv[1:4]
s = open(path, encoding='utf-8').read()
assert s.count(a) == 1, 'anchor count %d' % s.count(a)
open(path, 'w', encoding='utf-8').write(s.replace(a, b))
PY
  local k m
  case "$label" in
    M5) k=$(grep -cF -- "$a" "$G"); m=$(grep -cF -- "$b" "$G") ;;
    M6) k=$(cnt2 "$H" "$a"); m=$(cnt2 "$H" "$b") ;;
    *)  k=$(cnt "$a"); m=$(cnt "$b") ;;
  esac
  if [ "$k" != "0" ] || [ "$m" -lt 1 ]; then
    echo "FATAL: $label did not take (anchor $k, replacement $m)"
    # Restores $target, never a hard-coded $F. The earlier version restored $F
    # from a backup that held $target, and that single wrong filename replaced
    # 160KB of page with the contents of the collection script.
    cp "$bak" "$target"; rm -f "$bak" "$BAKDIR/target"
    return 4
  fi
  echo "$label applied (anchor $n -> 0, replacement +$m)"
}

revert() {
  local trg="$BAKDIR/target"
  [ -f "$trg" ] || { echo "no backup to revert"; return 1; }
  local target; target=$(cat "$trg")
  local bak="$BAKDIR/$(basename "$target").orig"
  [ -f "$bak" ] || { echo "backup missing for $target"; return 1; }
  cp "$bak" "$target"
  mv "$bak" "$BAKDIR/$(basename "$target").reverted"
  rm -f "$trg"
  local ha
  ha=$(cnt2 "$H" "$A6")
  [ "$ha" = "1" ] || { echo "FATAL: reverted collection script lost its loop ($ha)"; return 8; }
  ha=$(grep -cF -- "$A5" "$G")
  [ "$ha" = "1" ] || { echo "FATAL: reverted script lost its gate ($ha)"; return 7; }
  ha=$(cnt "$HEALTH")
  [ "$ha" = "1" ] || { echo "FATAL: reverted file lost its health anchor ($ha)"; return 7; }
  echo "reverted (backup removed, health anchor intact)"
}

case "${1:-}" in
  apply-M1) apply M1 ;; apply-M2) apply M2 ;;
  apply-M3) apply M3 ;; apply-M4) apply M4 ;; apply-M5) apply M5 ;;
  apply-M6) apply M6 ;; apply-M7) apply M7 ;; apply-M8) apply M8 ;;
  apply-M9) apply M9 ;; apply-M10) apply M10 ;;
  revert) revert ;;
  status)
    miss=0
    for l in M1 M2 M3 M4 M5 M6 M7 M8 M9 M10; do
      a=$(anchor_of "$l")
      case $l in
        M5) n=$(grep -cF -- "$a" "$G") ;;
        M6) n=$(cnt2 "$H" "$a") ;;
        *)  n=$(cnt "$a") ;;
      esac
      printf '  %s anchor=%s\n' "$l" "$n"
      [ "$n" = "1" ] || miss=1
    done
    ha=$(cnt "$HEALTH")
    printf '  health=%s\n' "$ha"
    [ "$ha" = "1" ] || miss=1
    [ $miss = 0 ] && echo "all 10 anchors + health + gate + loop present exactly once"
    exit $miss ;;
  *) echo "usage: $0 apply-M1|apply-M2|apply-M3|apply-M4|apply-M5|apply-M6|apply-M7|apply-M8|apply-M9|apply-M10|revert|status"; exit 2 ;;
esac
