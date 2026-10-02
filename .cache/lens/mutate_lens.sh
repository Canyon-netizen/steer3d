#!/bin/bash
# Mutations for the two new blocks. Each must turn the verifier red; a mutation
# that leaves it green proves the check has no teeth.
#
#   M1  NaN back into the product. Python's json writes it and reads it back
#       happily, so the producer's own round-trip check passes -- and the page
#       loses the whole block with no trace. Reproduced by injecting a NaN
#       directly, which is exactly what the pre-fix build produced.
#   M2  Drop the "循环口径下不通过" line. The held-out gate passes creativity
#       at 1.8 sigma, so without the in-sample cross-reference the page shows
#       a marginal win as a clean PASS.
#   M3  Print the textbook floor instead of the random control.
#   M4  Half a bar chart: 28 layers -> 14. The presence check still sees a
#       chart; only the bar count catches it.
set -u
ROOT="/Users/zhourui/code/steer3d"
F="$ROOT/frontend/public/latent/index.html"
P="$ROOT/frontend/public/latent/data/vector_roles.json"
BAK="$ROOT/.cache/lens/backs"
mkdir -p "$BAK"
HEALTH='function renderLogitLens(){'

A1='PLACEHOLDER_M1'
A2='<span style="color:#ff8fa3">循环口径下不通过</span>'
A3='而是<b>打败全部 ${one.n_random_directions} 个随机方向</b>'
A4='const N = am.length;'

restore() {
  [ -f "$BAK/index.html.orig" ] && cp "$BAK/index.html.orig" "$F"
  [ -f "$BAK/roles.orig" ] && cp "$BAK/roles.orig" "$P"
  echo "reverted"
}
snapshot() { cp "$F" "$BAK/index.html.orig"; cp "$P" "$BAK/roles.orig"; }

case "${1:-}" in
  snapshot) snapshot; echo "snapshot taken" ;;
  revert) restore ;;
  apply-M1)
    snapshot
    # Re-introduce the exact defect: a bare NaN token in the payload.
    /usr/bin/python3 -c "
import sys
p=sys.argv[1]; s=open(p,encoding='utf-8').read()
s=s.replace('\"n_runs\": 23','\"injected_norm\": NaN, \"n_runs\": 23',1)
open(p,'w',encoding='utf-8').write(s)" "$P"
    grep -q 'injected_norm": NaN' "$P" || { echo "FATAL: M1 did not apply"; restore; exit 1; }
    echo "applied M1 (NaN back into the payload)" ;;
  apply-M2)
    snapshot
    /usr/bin/python3 -c "
import sys
p=sys.argv[1]; s=open(p,encoding='utf-8').read()
a='''<span style=\"color:#ff8fa3\">循环口径下不通过</span>'''
if s.count(a)!=1: print('anchor count',s.count(a)); sys.exit(1)
open(p,'w',encoding='utf-8').write(s.replace(a,''))" "$F" || { restore; exit 1; }
    echo "applied M2" ;;
  apply-M3)
    snapshot
    /usr/bin/python3 -c "
import sys
p=sys.argv[1]; s=open(p,encoding='utf-8').read()
a='而是<b>打败全部 \${one.n_random_directions} 个随机方向</b>'
if s.count(a)!=1: print('anchor count',s.count(a)); sys.exit(1)
open(p,'w',encoding='utf-8').write(s.replace(a,'而是<b>大于 1/√(n−3)</b>'))" "$F" || { restore; exit 1; }
    echo "applied M3" ;;
  apply-M4)
    snapshot
    /usr/bin/python3 -c "
import sys
p=sys.argv[1]; s=open(p,encoding='utf-8').read()
a='const N = am.length;'
if s.count(a)!=1: print('anchor count',s.count(a)); sys.exit(1)
open(p,'w',encoding='utf-8').write(s.replace(a,'const N = Math.floor(am.length/2);'))" "$F" || { restore; exit 1; }
    echo "applied M4" ;;
  status)
    h=$(grep -cF -- "$HEALTH" "$F")
    for a in "$A2" "$A3" "$A4"; do
      printf '  %-46s count=%s\n' "$a" "$(grep -oF -- "$a" "$F" | wc -l | tr -d ' ')"
    done
    printf '  health=%s\n' "$h" ;;
  *) echo "usage: $0 snapshot|apply-M1|apply-M2|apply-M3|apply-M4|revert|status"; exit 2 ;;
esac
