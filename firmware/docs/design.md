# Firmware design

ESP-IDF 5.4.2, C11, ESP32-WROOM-32E; hardware contract: ../../docs/pinout.md.
The owner's build prompt authorizes implementation and merge. Existing checkout is
an isolated worktree on skills/firmware. No earlier firmware or tests exist.

A sample task reads SHT31 once per wake. The coordinator exclusively owns an RTC
ring of 64 readings, device session/sequence IDs and the cached next event.
A separate network task joins Wi-Fi with a bounded wait, obtains UTC through
SNTP, fetches the next event and uploads a bounded batch. It hands results back
through a FreeRTOS queue; the coordinator renders an SSD1306 framebuffer over SPI (legacy I²C selectable), emits UART0 diagnostics, stops
Wi-Fi and deep-sleeps for 300 seconds. Failed uploads retain FIFO entries;
overflow drops the oldest reading and increments a visible loss counter.
Only validated synchronous acknowledgments remove entries. RTC state survives
timer deep sleep, not power loss or crashes; cold boot gets a new session ID.
Unsynchronized samples explicitly have timestamp 0, never invented UTC.

OLED was selected over e-paper. Revision 2 uses SPI by default, with legacy I²C retained. It stays
powered so the event is visible during sleep; this costs several mA continuously.
A host-tested pure C core handles CRC/conversion, ring buffering, bounded HTTP
body collection, JSON validation and framebuffer layout. IDF-only drivers handle
I²C, Wi-Fi, TLS and scheduling. HTTPS validates server certificates, HTTP requires
an explicit development opt-in. Redirects are disabled to avoid token forwarding.

LifeOS currently has no native room telemetry endpoint. A Python standard-library
adapter in firmware/tools exposes the small desk API. It obtains the next school
calendar event or task deadline from LifeOS /api/bootstrap and writes room logs
through /api/private-notes/<dedicated-daily-id>, using its normal session, CSRF,
version and mutation protocol. These are new dedicated daily notes only. SQLite
on the adapter deduplicates readings by device/session/sequence across retries;
ESP32 credentials grant access only to this adapter. Account credentials stay on
the host. No private data or secrets are committed, and tests use synthetic data.
The adapter must be configured and run by the owner; this task does not touch a
live LifeOS account. Demo mode provides an isolated runnable contract fixture.

Validation: strict host compilation + sanitizers, protocol/queue/CRC/render tests,
adapter tests including actual HTTP and upstream error paths, ESP-IDF Docker CI
build and size report. No physical device is connected, so radio, sensor accuracy,
screen appearance and power consumption require the documented bench checklist.

Revision 2 follows Jack's required I²C sensor / SPI display / UART logging scope.
See spi-uart-plan.md and ../../docs/pinout.md for the coordinated pin contract.
