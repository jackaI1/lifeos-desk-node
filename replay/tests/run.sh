#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/desk-replay-test.XXXXXX")
trap 'rm -rf "$test_dir"' EXIT HUP INT TERM
GUILE_AUTO_COMPILE=0 guile -L replay/scheme replay/tests/test-scenario.scm
make -C replay BUILD="$test_dir" CFLAGS='-g -fsanitize=address,undefined -fno-omit-frame-pointer' all
DESK_REPLAY_BIN="$test_dir/desk-replay" GUILE_AUTO_COMPILE=0 \
  python3 -m unittest discover -s replay/tests -p 'test_*.py' -v
