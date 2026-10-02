#!/bin/bash
# Does the duplication gate actually refuse, or does it just print a warning?
#
# A gate that has only ever been run on clean data is untested code wearing a
# gate's clothes. The determinism gate next door got its own behaviour test for
# the same reason, and writing this one immediately paid for itself: the first
# version of the "uneven runs per problem" branch raised
#   TypeError: not enough arguments for format string
# because it formatted a (label, direction) pair with a three-slot pattern.
# Nobody would have seen that on the real batch, which is perfectly even.
#
# Four cases, all built by mutating a copy of the real analysis file:
#   1. clean          -> must succeed and write the payload
#   2. duplicated     -> must refuse, name the cell, and write nothing
#   3. missing arm    -> must refuse, name the short pair, and write nothing
#   4. the same two, but with the gate disabled -> must succeed, because that
#      is what proves cases 2 and 3 are the gate's doing and not a crash
set -u
ROOT="/Users/zhourui/code/steer3d"
B="$ROOT/backend/examples/build_cot_effect.py"
SRC="$ROOT/.cache/32k_journal"
REAL="$SRC/cot_divergence_32k.json"
D="$ROOT/.cache/arreadout/gate"
BAK="$D/build_cot_effect.py.orig"

mkdir -p "$D"
fails=0
chk() { if [ "$2" = "1" ]; then echo "  ok   $1"; else echo "  FAIL $1"; fails=$((fails+1)); fi; }

# ---- build the three inputs -------------------------------------------------
python3 - "$REAL" "$D" <<'PY'
import json, sys
src = json.load(open(sys.argv[1], encoding='utf-8'))
dup = dict(src); dup['per_run'] = src['per_run'] + [src['per_run'][0]]
json.dump(dup, open(sys.argv[2] + '/dup.json', 'w'), ensure_ascii=False)
# Write down which cell was duplicated. The assertion below used to grep the
# log for a hard-coded "1987_I_1" -- the first record of the batch at the time.
# The batch grew from 84 to 88 runs, per_run[0] became 1983_I_1, and the check
# went red on a gate that was refusing exactly the right thing. Ask the INPUT
# which cell is duplicated instead; the whole point is that a gate's verdict
# must not depend on which problem happens to be first.
open(sys.argv[2] + '/dup_label.txt', 'w').write(src['per_run'][0]['label'])
miss = dict(src)
miss['per_run'] = [r for r in src['per_run']
                   if not (r['label'] == '1994_I_1'
                           and r['direction'] == 'confidence_down'
                           and r['strength'] == 0.2)]
json.dump(miss, open(sys.argv[2] + '/missing.json', 'w'), ensure_ascii=False)
PY

run() {  # run <srcdir> <source> <outfile> -> exit code in $RC, log in $D/last.log
  rm -f "$3"
  python3 "$B" --src "$1" --source "$2" --dest "$3" --planned-runs 96 \
      > "$D/last.log" 2>&1
  RC=$?
}

echo "--- 闸门行为 ---"
run "$SRC" cot_divergence_32k.json "$D/out_clean.json"
chk "干净输入成功（退出码 0）" "$([ $RC -eq 0 ] && echo 1 || echo 0)"
chk "干净输入写出产物" "$([ -s "$D/out_clean.json" ] && echo 1 || echo 0)"

run "$D" dup.json "$D/out_dup.json"
chk "重复单元被拒（退出码非 0）" "$([ $RC -ne 0 ] && echo 1 || echo 0)"
chk "重复时不写产物" "$([ ! -f "$D/out_dup.json" ] && echo 1 || echo 0)"
DUPL="$D/dup_label.txt"
chk "重复时指名了那个单元（题号取自输入，不是写死的）" \
    "$(grep -qF "$(cat "$DUPL")" "$D/last.log" && echo 1 || echo 0)"

run "$D" missing.json "$D/out_miss.json"
chk "缺一个臂被拒（退出码非 0）" "$([ $RC -ne 0 ] && echo 1 || echo 0)"
chk "缺臂时不写产物" "$([ ! -f "$D/out_miss.json" ] && echo 1 || echo 0)"
chk "缺臂时指名了那个 (题,方向)" "$(grep -q "1994_I_1/confidence_down=1" "$D/last.log" && echo 1 || echo 0)"
# 41 对正常 + 1 对异常时，消息必须只列那 1 对。基准取 sorted()[0]（最小值）
# 的版本会把 41 对正常的全报成异常、且从不提真正缺臂的那一对。
chk "缺臂消息只列异常项，不 dump 整张表" \
    "$(grep -q "有 1 个 (题, 方向)" "$D/last.log" && echo 1 || echo 0)"

# ---- and the control: with the gate off, the same inputs go through --------
cp "$B" "$BAK"
python3 - "$B" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding='utf-8').read()
a = "    if dupes:"
assert s.count(a) == 1
s = s.replace(a, "    if False:  # MUTATED: gate off")
b = "    if per_cell and any("
assert s.count(b) == 1
s = s.replace(b, "    if False and per_cell and any(")
open(p, 'w', encoding='utf-8').write(s)
PY
run "$D" dup.json "$D/out_dup_muted.json"
chk "闸门关掉后，重复输入能跑通（证明前两条是闸门在拒绝，不是崩了）" \
    "$([ $RC -eq 0 ] && echo 1 || echo 0)"
run "$D" missing.json "$D/out_miss_muted.json"
chk "闸门关掉后，缺臂输入也能跑通" "$([ $RC -eq 0 ] && echo 1 || echo 0)"
cp "$BAK" "$B"
rm -f "$BAK"
run "$SRC" cot_divergence_32k.json "$D/out_after.json"
chk "还原后干净输入仍然成功（脚本没被改坏）" \
    "$([ $RC -eq 0 ] && [ -s "$D/out_after.json" ] && echo 1 || echo 0)"
chk "还原后重复输入重新被拒（闸门真的回来了）" \
    "$(run "$D" dup.json "$D/out_dup2.json"; [ $RC -ne 0 ] && echo 1 || echo 0)"

echo
if [ "$fails" -eq 0 ]; then echo "GATE BEHAVIOUR ALL PASS"; else echo "GATE BEHAVIOUR FAILED ($fails)"; fi
exit "$fails"
