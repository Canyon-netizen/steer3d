#!/usr/bin/env bash
# Finish Qwen3-1.7B shard 1 by ranged chunk fetch.
#
# What went wrong before: the partial shard-2 download hit HTTP 416 on every
# offset past ~622 MB, which looked like a CDN range limit and led to
# writing the whole 1.7B model off. That reading was wrong. The 416s were all
# on shard 2, and the arithmetic says why:
#
#     index.json metadata.total_size   = 4,063,479,808
#     shard 1 real size (tail probe)   = 3,441,185,608
#     => shard 2 real size              =   622,294,200
#
# A byte past 622,294,200 IS past the end of shard 2. The server was
# answering correctly; the "truncated mirror" conclusion was a false one.
# Shard 1 serves 206 at every offset including the resume point.
#
# The earlier failure was a *resume* failure, not a range failure: the
# existing 1,107,182,070 bytes are kept and the remainder is fetched as
# explicit, checksummed-by-size chunks.
set -euo pipefail

DST=~/models/Qwen3-1.7B
URL=https://hf-mirror.com/Qwen/Qwen3-1.7B/resolve/main/model-00001-of-00002.safetensors
FULL=3441185608
HAVE=1107182070
CHUNK=$((32 * 1024 * 1024))
PAR=${PAR:-6}
WORK=/var/tmp/s1

mkdir -p "$WORK"

# Verify the existing prefix really is the first HAVE bytes of this file
# before appending to it. A partial file from a *different* URL or a
# re-rolled upstream would otherwise be silently extended into garbage.
echo "=== prefix check ==="
head -c 1048576 "$DST/model-00001-of-00002.safetensors" > "$WORK/head_local.bin"
curl -sL --range 0-1048575 -m 60 -o "$WORK/head_remote.bin" "$URL"
if cmp -s "$WORK/head_local.bin" "$WORK/head_remote.bin"; then
  echo "  local first 1 MiB matches remote -> prefix is valid, resuming at $HAVE"
else
  echo "  PREFIX MISMATCH — the existing 1.1 GB is not this file."
  echo "  Refusing to append. Delete it and re-run with HAVE=0."
  exit 1
fi

START=$HAVE
N=$(( (FULL - START + CHUNK - 1) / CHUNK ))
echo "=== $N chunks of $((CHUNK/1024/1024)) MiB from offset $START ==="

fetch() {
  local i=$1
  local off=$(( START + i * CHUNK ))
  local end=$(( off + CHUNK - 1 ))
  [ "$end" -ge "$FULL" ] && end=$(( FULL - 1 ))
  local want=$(( end - off + 1 ))
  local out="$WORK/$(printf '%04d' "$i").part"
  [ -f "$out" ] && [ "$(stat -c %s "$out")" = "$want" ] && return 0
  for attempt in 1 2 3 4 5; do
    if curl -sL --fail --range "${off}-${end}" -m 300 -o "$out" "$URL" \
       && [ "$(stat -c %s "$out")" = "$want" ]; then
      return 0
    fi
    sleep $((attempt * 3))
  done
  echo "CHUNK $i FAILED (offset $off, want $want, got $(stat -c %s "$out" 2>/dev/null || echo 0))" >&2
  return 1
}

running=0
for ((i=0; i<N; i++)); do
  fetch "$i" &
  running=$((running + 1))
  if [ "$running" -ge "$PAR" ]; then wait -n; running=$((running - 1)); fi
done
wait
echo "=== all chunks done ==="

# Size check before concatenating: a missing chunk would otherwise produce a
# file that is short by exactly one chunk and fails much later, inside
# safetensors, with an error that does not point at the download.
TOTAL=0
for ((i=0; i<N; i++)); do
  f="$WORK/$(printf '%04d' "$i").part"
  TOTAL=$(( TOTAL + $(stat -c %s "$f") ))
done
echo "chunks sum to $TOTAL, expected $((FULL - START))"
[ "$TOTAL" -eq $((FULL - START)) ] || { echo "SIZE MISMATCH"; exit 1; }

cat "$WORK"/[0-9]*.part > "$DST/.shard1_tail"
cat "$DST/model-00001-of-00002.safetensors" "$DST/.shard1_tail" \
    > "$DST/.shard1.new" && mv "$DST/.shard1.new" "$DST/model-00001-of-00002.safetensors"
rm -f "$DST/.shard1_tail"

echo "=== final ==="
ls -l "$DST/model-00001-of-00002.safetensors"
[ "$(stat -c %s "$DST/model-00001-of-00002.safetensors")" = "$FULL" ] \
  && echo "SHARD1 COMPLETE ($FULL bytes)" || { echo "SHARD1 WRONG SIZE"; exit 1; }
rm -rf "$WORK"
echo "DONE"
