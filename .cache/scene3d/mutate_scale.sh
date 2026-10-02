#!/bin/bash
# Mutation test: undo the world-scale fix in the built bundle and confirm the
# pixel assertions go red. A green check that has never been shown to turn red
# is not a check.
#
# The target is exact: `let n=1200,r=1;` is PCA_WORLD_SCALE=1200 next to
# WORLD_HALF_EXTENT=1. The other `1200` in the build is Next.js's image
# deviceSizes list, which is why the pattern includes the `,r=1;` tail --
# a bare sed on "1200" would hit 3 places and mutate unrelated code.
#
# Run: bash mutate_scale.sh apply | revert
set -u
CHUNK="/Users/zhourui/code/steer3d/frontend/.next/static/chunks/870-953609927d479f7a.js"
BAK="${CHUNK}.orig"
PATTERN='let n=1200,r=1;'
MUTATED='let n=1,r=1;'

hits() { grep -oF "$1" "$2" 2>/dev/null | wc -l | tr -d ' '; }

case "${1:-}" in
  apply)
    [ -f "$BAK" ] || cp "$CHUNK" "$BAK"
    before=$(hits "$PATTERN" "$CHUNK")
    if [ "$before" != "1" ]; then
      echo "ABORT: expected exactly 1 occurrence of '$PATTERN', found $before."
      echo "A mutation that changes 0 places looks identical to a check with no teeth."
      exit 2
    fi
    sed -i '' "s/$PATTERN/$MUTATED/" "$CHUNK"
    after=$(hits "$MUTATED" "$CHUNK")
    still=$(hits "$PATTERN" "$CHUNK")
    echo "applied: '$MUTATED' x$after, original left x$still"
    if [ "$after" != "1" ] || [ "$still" != "0" ]; then
      echo "ABORT: post-write read-back does not match what was intended."
      cp "$BAK" "$CHUNK"; exit 2
    fi
    ;;
  revert)
    if [ -f "$BAK" ]; then cp "$BAK" "$CHUNK"; rm -f "$BAK"; fi
    echo "reverted: '$PATTERN' x$(hits "$PATTERN" "$CHUNK")"
    ;;
  status)
    echo "live: '$PATTERN' x$(hits "$PATTERN" "$CHUNK"), '$MUTATED' x$(hits "$MUTATED" "$CHUNK")"
    ;;
  *)
    echo "usage: $0 apply|revert|status"; exit 2 ;;
esac
