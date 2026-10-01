#!/usr/bin/env bash
# Copy Qwen3-1.7B onto local ext4 so the 32k run never touches NFS.
#
# The model is 4.06 GB across two shards. shard1 was completed by ranged
# chunk fetch; shard2 holds a single tensor (lm_head.weight) and only needed
# its 392 trailing junk bytes trimmed. The copy below is a plain `cp`: the
# source is now large-file sequential reads, which NFS does at usable speed —
# it was the tens of thousands of small .so reads in the env that hung.
set -euo pipefail

SRC=~/models/Qwen3-1.7B
DST=/var/tmp/steer3d/models/Qwen3-1.7B
mkdir -p "$DST"

for f in config.json generation_config.json merges.txt vocab.json \
         tokenizer.json tokenizer_config.json model.safetensors.index.json \
         model-00001-of-00002.safetensors model-00002-of-00002.safetensors; do
  if [ ! -f "$SRC/$f" ]; then echo "MISSING $f"; exit 1; fi
done

cp -f "$SRC"/config.json "$SRC"/generation_config.json "$SRC"/merges.txt \
      "$SRC"/vocab.json "$SRC"/tokenizer.json "$SRC"/tokenizer_config.json \
      "$SRC"/model.safetensors.index.json "$DST"/
cp -f "$SRC"/model-0000*.safetensors "$DST"/

echo "=== staged ==="
ls -l "$DST"/*.safetensors
for f in "$DST"/*.safetensors; do
  s=$(stat -c %s "$f")
  r=$(stat -c %s "$SRC/$(basename "$f")")
  [ "$s" = "$r" ] || { echo "SIZE MISMATCH $f: $s vs $r"; exit 1; }
done
echo "SIZES MATCH SOURCE"
