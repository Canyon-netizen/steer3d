#!/bin/bash
# Serial by design: two of these launch their own browser against the same
# live server, and a mutation sweep running at the same time would hand them a
# page that is mid-mutation.
#
# The aggregator has to be able to say RED. Two rules make that true:
#
#   1. The verifiers disagree about how a check looks on screen. Three print
#      "  ok <text>"; two print "PASS <text>". The old version counted only the
#      first dialect, so picked/entcolor reported "ok=0" while in fact 24/24 and
#      11/11 had passed -- 35 real checks counted as none.
#   2. "zero checks ran" and "every check passed" used to print the same line,
#      because both are FAIL=0. A verifier that crashes on line 1, or that
#      finds its page gone, looked exactly like a clean run. Now a missing
#      summary line is a failure and a zero check count is a failure.
#   3. The three verifiers do not agree on what a verdict line looks like:
#      "ALL PASS", "=== 24/24 passed, 0 failed ===", "断言 188 条：绿 188 / 红 0".
#      Hardcoding all three spellings would break on the fourth. Instead the
#      classifier reads the total the verifier declares for itself and
#      cross-checks it against the number of check lines actually present.
#      Those are two independent numbers -- if a run was truncated, a dialect
#      was mis-parsed, or lines were interleaved, they disagree, and the suite
#      goes red. That cross-check is what replaced the hardcoded spellings.
#
# `bash regress.sh --selftest` feeds synthetic verifier outputs through the
# classifier and asserts it calls each one correctly, including a MISMATCH
# case. If the classifier ever stops being able to report red, the selftest
# goes red too.
set -u
cd /Users/zhourui/code/steer3d

VERIFIERS="cottext/verify_cottext cot32k/verify_cot32k arreadout/verify_answer_readout
picked/verify_picked picked/verify_entcolor readability/verify_readability"

# classify <file> -> sets CLS_STATUS, CLS_OK, CLS_FAIL, CLS_DECLARED.
# One line of truth about what the verifier's own output claims, independent of
# the exit code (which regress.sh deliberately ignores: a verifier that dies
# before its last line exits non-zero and would be indistinguishable from one
# that legitimately found a red check).
classify() {
  local f="$1" ok pass fail declared=""
  ok=$(grep -c '^  ok' "$f" 2>/dev/null || true)
  pass=$(grep -c '^PASS' "$f" 2>/dev/null || true)
  fail=$(grep -cE '^(  FAIL|FAIL )' "$f" 2>/dev/null || true)
  # The total the verifier claims it ran, however it spells it.
  declared=$(grep -oE '断言 [0-9]+ 条' "$f" 2>/dev/null | head -1 | grep -oE '[0-9]+' || true)
  if [ -z "$declared" ]; then
    declared=$(grep -oE '=== [0-9]+/[0-9]+ passed' "$f" 2>/dev/null | head -1 | grep -oE '[0-9]+' | head -1 || true)
  fi
  if [ -z "$declared" ]; then
    # Normalise here, not only in CLS_DECLARED. The status branches below test
    # $declared, and an empty string compares unequal to "none" -- which made a
    # perfectly good "ALL PASS" file report MISMATCH.
    declared=none
  fi
  CLS_OK=$((ok + pass))
  CLS_FAIL=$fail
  CLS_DECLARED="$declared"
  if [ "$CLS_FAIL" -gt 0 ]; then
    CLS_STATUS=FAIL
  elif [ "$CLS_OK" -eq 0 ]; then
    # A clean-looking file with nothing behind it. Same thing, dressed up.
    CLS_STATUS=NO-CHECKS
  elif [ "$declared" != "none" ] && [ "$declared" != "$CLS_OK" ]; then
    # The verifier says it ran N checks; N-1 check lines are on screen. One of
    # those two numbers is wrong and this harness cannot tell which, so it does
    # not get to call the suite green.
    CLS_STATUS=MISMATCH
  elif [ "$declared" = "none" ] && ! grep -qE '^ALL PASS$' "$f"; then
    # No verdict line at all: the verifier did not finish, or wrote to stderr
    # and died. Reporting this as a pass is the failure mode this script exists
    # to prevent.
    CLS_STATUS=NO-VERDICT
  else
    CLS_STATUS=PASS
  fi
}

selftest() {
  local d=".cache/cot32k/selftest"
  mkdir -p "$d"
  printf '  ok a\n  ok b\nALL PASS\n' > "$d/pass.txt"
  printf '  ok a\n  FAIL b\nALL PASS\n' > "$d/red.txt"
  printf '  ok a\n  ok b\n=== 2/2 passed, 0 failed ===\n' > "$d/pickeddialect.txt"
  printf 'boom: ENOENT frontend/public/latent/index.html\n' > "$d/crash.txt"
  # The case this rewrite exists for: a verifier that claims more checks than
  # it printed. Before the cross-check this was indistinguishable from PASS.
  printf '  ok a\n  ok b\n  ok c\n断言 10 条：绿 10 / 红 0\n' > "$d/truncated.txt"
  # And the real third dialect, 188 checks, counted as PASS.
  { for i in $(seq 1 188); do printf '  ok check %d\n' "$i"; done
    printf '\n断言 188 条：绿 188 / 红 0\n'; } > "$d/readabilitydialect.txt"
  local bad=0 want got
  for t in pass red pickeddialect crash truncated readabilitydialect; do
    case "$t" in
      pass)                 want=PASS ;;
      red)                  want=FAIL ;;
      pickeddialect)        want=PASS ;;
      crash)                want=NO-CHECKS ;;
      truncated)            want=MISMATCH ;;
      readabilitydialect)   want=PASS ;;
    esac
    classify "$d/$t.txt"
    got="$CLS_STATUS"
    if [ "$got" = "$want" ]; then
      printf '  ok  selftest %-19s -> %s (ok=%s declared=%s)\n' "$t" "$got" "$CLS_OK" "$CLS_DECLARED"
    else
      printf '  FAIL selftest %-19s -> %s (want %s, ok=%s declared=%s)\n' \
        "$t" "$got" "$want" "$CLS_OK" "$CLS_DECLARED"
      bad=$((bad + 1))
    fi
  done
  if [ "$bad" -eq 0 ]; then echo "SELFTEST PASS"; else echo "SELFTEST FAILED ($bad)"; fi
  return "$bad"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi

overall=0
D_GATE=".cache/cot32k/reg_gate_behaviour.txt"
for v in $VERIFIERS; do
  out=".cache/cot32k/reg_$(echo "$v" | tr '/' '_').txt"
  node ".cache/$v.mjs" > "$out" 2>&1
  classify "$out"
  printf '%-34s %-10s ok=%-4s decl=%-5s fail=%-3s %s\n' "$v" "$CLS_STATUS" "$CLS_OK" "$CLS_DECLARED" "$CLS_FAIL" \
    "$(grep -E '^(ALL PASS|=== [0-9]+/[0-9]+ passed|断言 [0-9]+ 条)' "$out" | tail -1)"
  grep -E '^(  FAIL|FAIL )' "$out" | head -4 | sed 's/^/      /'
  case "$CLS_STATUS" in
    PASS) ;;
    *) overall=$((overall + 1)) ;;
  esac
done
echo
if bash .cache/cot32k/mutate_answershift.sh status | tail -1 | grep -q 'present exactly once'; then
  echo "answershift anchors OK"
else
  echo "answershift anchors BAD"; overall=$((overall + 1))
fi
if bash .cache/cottext/mutate_cottext.sh status | tail -1 | grep -q 'present exactly once'; then
  echo "cottext anchors OK"
else
  echo "cottext anchors BAD"; overall=$((overall + 1))
fi

# Gate behaviour is not a mutation and not a page check: it runs the builder
# against deliberately broken input and asserts it refuses. A gate that has
# only ever seen clean data is untested code wearing a gate's clothes.
bash .cache/arreadout/gate_behaviour.sh > "$D_GATE" 2>&1
grc=$?
tail -1 "$D_GATE" | sed 's/^/  /'
[ $grc -eq 0 ] || overall=$((overall + 1))
# The answer-readout screen ships real text, so its payload can be malformed in
# ways a percentage cannot: two identical arms, a split point outside its own
# window, a "shared head" that runs past the split. Those are checked against
# the payload, not the DOM -- see verify_answer_readout.mjs.

if [ "$overall" -eq 0 ]; then
  echo "REGRESSION ALL PASS"
else
  echo "REGRESSION FAILED ($overall suite(s) not green)"
fi
exit "$overall"
