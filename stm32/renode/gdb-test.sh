#!/usr/bin/env bash
set -euo pipefail
mkdir -p stm32/build/debug
renode --disable-xwt --console --execute 'include @stm32/renode/debug.resc' > stm32/build/debug/renode.log 2>&1 &
pid=$!
started=$(date -u +%FT%TZ)
printf 'owner=STM32 hardfault test pid=%s started=%s port=3333 cleanup=kill-TERM-%s\n' "$pid" "$started" "$pid" > stm32/build/debug/owned-resource.txt
trap 'kill -TERM "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true' EXIT
python3 - <<'PY'
import socket,time
for _ in range(100):
 try:
  with socket.create_connection(('127.0.0.1',3333),.1): break
 except OSError: time.sleep(.1)
else: raise SystemExit('Renode GDB port did not open')
PY
timeout 60 gdb-multiarch -q -batch -x stm32/renode/hardfault.gdb stm32/build/bare.elf | tee stm32/build/debug/gdb.txt
grep -q 'PASS: stacked PC' stm32/build/debug/gdb.txt
