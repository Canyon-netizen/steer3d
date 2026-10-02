#!/bin/bash
# Serial by design: two of these launch their own browser against the same
# live server, and a mutation sweep running at the same time would hand them a
# page that is mid-mutation.
set -u
cd /Users/zhourui/code/steer3d
for v in cottext/verify_cottext cot32k/verify_cot32k picked/verify_picked \
         picked/verify_entcolor readability/verify_readability; do
  out=".cache/cot32k/reg_$(echo "$v" | tr '/' '_').txt"
  node ".cache/$v.mjs" > "$out" 2>&1
  printf '%-34s FAIL=%-3s ok=%-4s %s\n' "$v" \
    "$(grep -c '^  FAIL' "$out" || true)" \
    "$(grep -c '^  ok' "$out" || true)" \
    "$(grep -E '^(ALL PASS|FAIL [0-9]+/)' "$out" | tail -1)"
  grep -E '^  FAIL' "$out" | head -4 | sed 's/^/      /'
done
echo
bash .cache/cot32k/mutate_answershift.sh status | tail -1
bash .cache/cottext/mutate_cottext.sh status | tail -1
