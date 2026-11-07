# Concurrent desk readings over TCP

I built a telemetry receiver because I wanted to learn how to handle several
desk-node clients without a slow or damaged message blocking all the others.
It echoes an accepted temperature/humidity packet and rejects malformed ones.
The example uses simulated clients, so it needs no ESP32 or LifeOS account.

```sh
cmake -S tcp_telemetry -B tcp_telemetry/build
cmake --build tcp_telemetry/build --config Debug -j2
.venv/bin/python -m pytest tcp_telemetry/tests -q
```

On Windows, set `DESK_TCP_BINARY=tcp_telemetry/build/Debug/desk-tcp.exe` for the
Python test. C++17 uses a small socket wrapper around Winsock on Windows and
POSIX sockets on Linux/macOS. Four worker threads share a bounded 64-connection
queue protected by a mutex and condition variable. Shutdown stops accepting,
closes queued clients, waits for bounded in-flight transactions and joins each
worker. A two-second transaction deadline also bounds a peer that trickles bytes.

Each message is a two-byte big-endian payload length, the payload and a four-byte
CRC-32 over header plus payload. The incremental parser has a 4096-byte maximum.
The current desk transaction is exactly eight payload bytes: signed 32-bit
temperature in millidegrees and unsigned 32-bit humidity in thousandths of a
percent, both big-endian. Invalid ranges are rejected. One message is handled
per connection; the checksum detects corruption, not deliberate forgery.

The server binds only to loopback. `desk-tcp 0 10000` chooses a free port and
runs for ten seconds, printing that port first. Tests run 100 valid transactions
with 16 concurrent client workers, then truncated, corrupted, oversized and slow
messages and a healthy recovery transaction. CI runs the same actual socket
tests on Windows and Linux, plus ThreadSanitizer on Linux to check data races.
It is a local lab protocol, not a replacement for the TLS MQTT upload path.
