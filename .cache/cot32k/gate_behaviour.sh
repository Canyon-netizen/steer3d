#!/bin/bash
# Behavioural test for the attribution gate in build_cot_effect.py.
#
# M5 disables the gate in the script. A page-level check cannot see that: the
# payload on disk is unchanged, so every DOM assertion still passes and the
# mutation looks like a no-op. Testing it needs data that actually violates
# the gate, which means perturbing one zero-vector run's digest so two runs of
# the same question stop matching.
#
# What must hold:
#   gate ON   + violating data  -> the build REFUSES and says why
#   gate OFF  + violating data  -> the build succeeds (that is what M5 buys)
#   gate ON   + clean data      -> the build succeeds
#
# The middle case is the point. A gate that is never observed to fail is
# indistinguishable from no gate at all.
set -u
ROOT="/Users/zhourui/code/steer3d"
G="$ROOT/backend/examples/build_cot_effect.py"
SRC="$ROOT/.cache/32k_journal/cot_divergence_32k.json"
DIR="$ROOT/.cache/cot32k/gatetest"
BAK="$DIR/gate.py.orig"
cd "$ROOT"
mkdir -p "$DIR"

fails=0
chk() { if [ "$1" = "1" ]; then echo "  ok   $2"; else echo "  FAIL $2 ${3:-}"; fails=$((fails+1)); fi; }

# Every output path carries a per-run tag. "The gate refused, so nothing was
# written" is only meaningful against a path that did not already exist -- and
# step 3 of a previous run writes one, so a fixed name makes this check pass on
# the first invocation and fail on every one after. That is the worst possible
# shape for a check, and it is a bug in the test, not in the gate.
TAG="run_$$_$(date +%s)"
OUT_CLEAN1="$DIR/clean_out_$TAG.json"
OUT_VIOL="$DIR/violating_out_$TAG.json"
OUT_CLEAN2="$DIR/clean_out2_$TAG.json"

cp "$G" "$BAK"
python3 - "$SRC" "$DIR/violating.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
# Flip one zero-vector run's digest so it no longer matches its same-question
# partner. That is exactly the condition the gate exists to catch.
hit = 0
for r in d['per_run']:
    if r['strength'] == 0.0 and r['direction'] == 'confidence_down':
        r['reason_text_digest'] = 'f' * 64
        hit += 1
        break
assert hit == 1, 'no zero-vector confidence_down run to perturb'
json.dump(d, open(sys.argv[2], 'w'))
print('  (扰动了 1 个零向量运行的摘要)')
PY

# Both inputs live under $DIR so --src is the same in every case; passing a
# path that does not exist just makes the build exit 1 for the wrong reason,
# and a test that fails for the wrong reason is worse than no test.
cp "$SRC" "$DIR/clean.json"

build() {  # build <src-basename> <dest>
  python3 "$G" --src "$DIR" --source "$1" --dest "$2" --planned-runs 96 \
    > "$DIR/build.log" 2>&1
  echo $?
}

echo "=== 1. 闸门开着 + 干净数据 → 应当成功 ==="
rc=$(build clean.json "$OUT_CLEAN1")
chk "$([ "$rc" = 0 ] && echo 1 || echo 0)" "干净数据下构建成功 (rc=$rc)"

echo
echo "=== 2. 闸门开着 + 违反闸门的数据 → 应当拒绝 ==="
rc=$(build violating.json "$OUT_VIOL")
msg=$(grep -o "前向不可复现" "$DIR/build.log" | head -1)
chk "$([ "$rc" != 0 ] && echo 1 || echo 0)" "构建被拒绝 (rc=$rc)"
chk "$([ -n "$msg" ] && echo 1 || echo 0)" "并且说明了原因（提到前向不可复现）"
chk "$([ ! -f "$OUT_VIOL" ] && echo 1 || echo 0)" "没有写出产物"

echo
echo "=== 3. 施加 M5（闸门被关掉）后，同样的数据 → 应当成功，这正是 M5 的代价 ==="
bash .cache/cot32k/mutate_answershift.sh apply-M5 > /dev/null 2>&1
rc=$(build violating.json "$OUT_VIOL")
chk "$([ "$rc" = 0 ] && echo 1 || echo 0)" "M5 之后构建成功（不再拦截） (rc=$rc)"
chk "$([ -f "$OUT_VIOL" ] && echo 1 || echo 0)" "并且写出了本该被拦下的产物"
cp "$BAK" "$G"
rm -f "$BAK"
chk "$([ "$(grep -cF -- '    if n_same != len(det):' "$G")" = 1 ] && echo 1 || echo 0)" \
    "脚本已还原，闸门在原位"

echo
echo "=== 4. 还原后再跑一次干净构建，确认没被弄坏 ==="
rc=$(build clean.json "$OUT_CLEAN2")
chk "$([ "$rc" = 0 ] && echo 1 || echo 0)" "还原后仍能构建 (rc=$rc)"

echo
if [ "$fails" = 0 ]; then echo "ALL PASS"; else echo "FAIL $fails 条"; fi
exit $fails
