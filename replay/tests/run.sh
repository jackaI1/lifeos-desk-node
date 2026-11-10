#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/desk-replay-test.XXXXXX")
trap 'rm -rf "$test_dir"' EXIT HUP INT TERM
GUILE_AUTO_COMPILE=0 guile -L replay/scheme replay/tests/test-scenario.scm

echo "== AddressSanitizer and UndefinedBehaviorSanitizer: all replay tests =="
make -C replay BUILD="$test_dir/asan" CFLAGS='-g -fsanitize=address,undefined -fno-omit-frame-pointer' all
DESK_REPLAY_BIN="$test_dir/asan/desk-replay" GUILE_AUTO_COMPILE=0 \
  python3 -m unittest discover -s replay/tests -p 'test_*.py' -v

echo "== ThreadSanitizer: parallel worker pool must report no data race =="
make -C replay BUILD="$test_dir/tsan" CFLAGS='-g -O1 -fsanitize=thread -fno-omit-frame-pointer' all
# A reported race stops the binary with a non-zero exit, which fails the test that ran it.
TSAN_OPTIONS='halt_on_error=1:exitcode=66' DESK_REPLAY_BIN="$test_dir/tsan/desk-replay" \
  GUILE_AUTO_COMPILE=0 python3 -m unittest discover -s replay/tests -p 'test_pool.py' -v
