#!/bin/bash
# Turn a finished paired collection into the deliverable bundle.
#
# Ordered, and the order is the point. The old synthetic bundle is removed
# *before* the new one is written, not after, so there is never a moment where
# the page could be served a manifest that points at files from two different
# datasets. The arithmetic check runs before the tar is built, because a tar
# that has already been uploaded is expensive to replace.
#
# --no-upload builds and verifies everything but leaves obs alone. That flag
# exists so this script can be rehearsed end-to-end on synthetic input without
# ever putting fake data where the user will download it from.
set -euo pipefail

REPO=/Users/zhourui/code/steer3d
DATA=$REPO/frontend/public/latent/data
PAIRS_SRC=$REPO/.cache/analysis/real_paired
TRASH=/Users/zhourui/.minimax/bin/mavis-trash
UPLOAD=1
[ "${1:-}" = "--no-upload" ] && UPLOAD=0

cd "$REPO"

echo "=== 0. 输入检查 ==="
ls -la "$PAIRS_SRC"/*.npz 2>/dev/null | head -8
N=$(ls "$PAIRS_SRC"/*.npz 2>/dev/null | wc -l | tr -d ' ')
[ "$N" -gt 0 ] || { echo "没有 pair_*.npz，采集还没产出"; exit 1; }
echo "配对文件 $N 个"
if [ "$UPLOAD" = "0" ]; then
  echo ">>> --no-upload：只构建与验证，不上传 obs"
fi

echo "=== 1. 移除合成数据 ==="
# Never a mix: the synthetic T1/T2 pairs and the real ones are the same file
# names' siblings, and a stale manifest entry renders as "no data" rather than
# as an error.
if [ -d "$DATA/pairs" ]; then
  "$TRASH" -- "$DATA/pairs" >/dev/null && echo "  旧 pairs/ 已移入回收站"
fi
mkdir -p "$DATA"

echo "=== 2. 打包 ==="
python3 backend/examples/build_paired_bundle.py --paired-dir "$PAIRS_SRC"

echo "=== 3. 生成对拍真值（独立 numpy 计算） ==="
python3 .cache/make_delta_ref.py

echo "=== 4. 算术验证：页面算的 vs numpy 算的 ==="
node .cache/delta_check.mjs

echo "=== 5. 体积 ==="
du -sh "$DATA" "$DATA/pairs" 2>/dev/null
ls "$DATA/pairs" | wc -l | xargs echo "  pairs 文件数:"

echo "=== 6. 打 tar ==="
cd "$REPO/frontend/public"
tar czf "$REPO/.cache/latent_viewer.tar.gz" latent
cd "$REPO"
ls -la .cache/latent_viewer.tar.gz
shasum -a 256 .cache/latent_viewer.tar.gz | tee .cache/latent_viewer.sha256

echo "=== 7. 上传到 obs（zju-57 的 s3fs） ==="
if [ "$UPLOAD" = "0" ]; then
  echo "  跳过（--no-upload）"
else
  LOCAL_SHA=$(cut -d' ' -f1 < .cache/latent_viewer.sha256)
  sha_remote=$(ssh zju-57 'sha256sum /obs/zhourui/steer3d/latent_viewer.tar.gz 2>/dev/null | cut -d" " -f1' || true)
  if [ "$sha_remote" = "$LOCAL_SHA" ]; then
    echo "  obs 上已是同一份（逐位一致），跳过上传"
  else
    scp -q .cache/latent_viewer.tar.gz zju-57:/obs/zhourui/steer3d/latent_viewer.tar.gz
    echo "  上传完成，校验远端 SHA256 …"
    REMOTE_SHA=$(ssh zju-57 'sha256sum /obs/zhourui/steer3d/latent_viewer.tar.gz | cut -d" " -f1')
    echo "  本地: $LOCAL_SHA"
    echo "  远端: $REMOTE_SHA"
    [ "$REMOTE_SHA" = "$LOCAL_SHA" ] || { echo "  ✗ 不一致，obs 上的包不可信"; exit 1; }
    echo "  ✓ 逐位一致"
  fi
fi
echo "=== 完成 ==="
