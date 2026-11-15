#!/bin/sh
# Fetch the pinned CMSIS-DSP sources the IMU filter calls (headers and the q31 biquad).
# They go into third_party/, which is not committed. Run once; later runs do nothing.
set -eu
TAG=v1.18.0
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEST="$ROOT/third_party/CMSIS-DSP"
if [ -f "$DEST/Include/arm_math.h" ]; then
    exit 0
fi
mkdir -p "$ROOT/third_party"
rm -rf "$DEST"
git clone --depth 1 --branch "$TAG" --filter=blob:none --sparse \
    https://github.com/ARM-software/CMSIS-DSP.git "$DEST"
git -C "$DEST" sparse-checkout set Include PrivateInclude Source/FilteringFunctions
echo "CMSIS-DSP $TAG fetched into $DEST"
