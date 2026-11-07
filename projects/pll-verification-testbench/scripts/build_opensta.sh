#!/usr/bin/env bash
# Build only in Linux CI; the resulting executable is cached by pinned revision.
set -euo pipefail
mkdir -p build/tools build/tool-src
task_root="$(pwd)/build/tool-src"
task_log="$(pwd)/build/opensta-build.log"
exec 3>&1
trap 'code=$?; if [ "$code" -ne 0 ]; then tail -60 "$task_log" >&3; fi' EXIT
{
  curl --fail --location --silent --show-error \
    https://codeload.github.com/ivmai/cudd/tar.gz/f54f533303640afd5dbe47a05ebeabb3066f2a25 \
    | tar -xz -C "$task_root"
  cd "$task_root/cudd-f54f533303640afd5dbe47a05ebeabb3066f2a25"
  ./configure --enable-silent-rules --disable-shared
  make -j4
  cd "$task_root"
  git init opensta
  cd opensta
  git remote add origin https://github.com/The-OpenROAD-Project/OpenSTA.git
  git fetch --depth 1 origin f8e13cbf12d02a07a2d1ec4a64f3e6985b747eab
  git checkout --detach FETCH_HEAD
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_TESTS=OFF -DUSE_TCL_READLINE=OFF \
    -DCUDD_DIR="$task_root/cudd-f54f533303640afd5dbe47a05ebeabb3066f2a25" \
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE=OFF
  cmake --build build -j4
  cp build/sta "$task_root/../tools/sta"
} > "$task_log" 2>&1
