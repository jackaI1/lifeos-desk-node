#!/bin/sh
# Fetch the pinned CMSIS-DSP sources the IMU filter calls (headers and the q31 biquad).
# They go into third_party/, which is not committed. Run once; later runs do nothing.
set -eu
TAG=v1.18.0
CORE_TAG=5.9.0   # CMSIS-Core headers (cmsis_compiler.h) that arm_math_types.h needs on Linux
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEST="$ROOT/third_party/CMSIS-DSP"
CORE="$ROOT/third_party/CMSIS-Core"
if [ -f "$DEST/Include/arm_math.h" ] && [ -f "$CORE/Include/cmsis_compiler.h" ]; then
    exit 0
fi
mkdir -p "$ROOT/third_party"
if [ ! -f "$DEST/Include/arm_math.h" ]; then
    rm -rf "$DEST"
    git clone --depth 1 --branch "$TAG" --filter=blob:none --sparse \
        https://github.com/ARM-software/CMSIS-DSP.git "$DEST"
    git -C "$DEST" sparse-checkout set Include PrivateInclude Source/FilteringFunctions
    echo "CMSIS-DSP $TAG fetched into $DEST"
fi
if [ ! -f "$CORE/Include/cmsis_compiler.h" ]; then
    rm -rf "$CORE"
    git clone --depth 1 --branch "$CORE_TAG" --filter=blob:none --sparse \
        https://github.com/ARM-software/CMSIS_5.git "$CORE"
    git -C "$CORE" sparse-checkout set CMSIS/Core/Include
    mv "$CORE/CMSIS/Core/Include" "$CORE/Include.tmp"
    rm -rf "$CORE/CMSIS" && mv "$CORE/Include.tmp" "$CORE/Include"
    echo "CMSIS-Core $CORE_TAG fetched into $CORE"
fi
