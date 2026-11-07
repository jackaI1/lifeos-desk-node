# A persistent simulated port switch

I built a port-switch daemon because I wanted to learn how a small Linux service
could keep control state through a restart and notice missing hardware replies.
It pairs 16 pretend optical ports. No optical hardware or desk-node output is
connected; this is a control-service experiment beside the sensor replay.

```sh
make -C optical_switch test
.venv/bin/python -m pytest optical_switch/tests -q
optical_switch/build/desk-switch 8094 /tmp/desk-switch.state
```

The last command prints its loopback port and runs in the foreground. Ctrl-C or
SIGTERM closes the listener. A TCP client sends one newline-terminated command:
`CONNECT 1 2`, `ACK 1`, `DISCONNECT 1` or `STATUS 1`. Connections are symmetric;
invalid ports, self-connections, conflicts, extra fields, embedded zeros and
overlong commands are rejected. There are at most 80 input bytes per request.
The protocol is for a trusted local client and has no remote authentication.

A connection waits 200 ms for a simulated acknowledgement for each end. A missing
reply sets that port's fault flag. Disconnect clears the pair; an ACK cannot
clear a held fault. The daemon writes the register-style state to a checksummed
file using a unique temporary file, fsync and atomic rename. It refuses corrupt
saved state and restarts the watchdog for restored active connections. An
acknowledged status is not assumed to mean hardware survived a process restart.

C unit tests cover state rules. A Python client drives actual sockets, checks
fault deadlines and restart persistence and verifies malformed traffic is
rejected. GitHub Actions builds with GCC and Clang under AddressSanitizer and
UBSan. Test subprocesses are owned by their fixture and stopped and joined in
finally blocks, with PID, start time, port and cleanup details recorded.
