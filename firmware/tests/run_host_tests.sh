#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/desk-node-test.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wno-deprecated-declarations -fsanitize=address,undefined -g -Itests/vendor -c tests/vendor/cJSON.c -o "$build_dir/cJSON.o"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined -g \
  -Icomponents/desk_core/include -Itests/vendor \
  components/desk_core/desk_core.c "$build_dir/cJSON.o" tests/test_core.c \
  -lm -o "$build_dir/test_core"
"$build_dir/test_core"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined -g \
  -Icomponents/desk_core/include -Icomponents/desk_drivers/include -Itests/vendor \
  components/desk_core/desk_core.c components/desk_drivers/desk_ssd1306.c \
  "$build_dir/cJSON.o" tests/test_peripherals.c -lm -o "$build_dir/test_peripherals"
"$build_dir/test_peripherals"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined -g \
  -Icomponents/desk_can/include \
  components/desk_can/desk_can.c tests/test_can.c -o "$build_dir/test_can"
"$build_dir/test_can"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined -g \
  -Icomponents/desk_core/include -Icomponents/desk_ess/include -Itests/vendor \
  components/desk_core/desk_core.c components/desk_ess/desk_ess.c "$build_dir/cJSON.o" tests/test_ess.c \
  -lm -o "$build_dir/test_ess"
"$build_dir/test_ess"
python3 -m unittest discover -s tests -p 'test_*.py' -v
