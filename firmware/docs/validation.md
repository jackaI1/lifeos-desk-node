# Software validation record

The first implementation passed the ESP-IDF v5.4.2 Docker target build on
[GitHub Actions](https://github.com/jackaI1/lifeos-desk-node/actions/runs/41767773244).
Final-head checks are visible on [PR #1](https://github.com/jackaI1/lifeos-desk-node/pull/1).

Independent whole-branch review found two material issues. Regression tests
reproduced each before fixes: recursive JSON could exceed an RTOS stack despite
body-size bounds; room-note updates could discard owner metadata/formatting.
The parser now rejects nesting deeper than eight before entering cJSON, including
acknowledgments. Note writes preserve metadata and refuse text/formatting edits.
Session ID generation also explicitly enables hardware entropy with Wi-Fi off.

The complete local suite after fixes passes 52 pure C checks under ASan/UBSan and
17 Python unit/HTTP tests, including real loopback HTTP requests for device auth,
upstream cookie/CSRF/Origin, redirect rejection and malformed response handling.
Socket fixtures are scoped to context managers; each reports ownership, PID,
start time, port, cleanup method and verified listener closure. Test binaries use
an automatically removed temporary directory. No browser or persistent server is
needed. No physical device or live LifeOS account was used; follow the README
bench checklist before claiming measured hardware behavior.

Revision 2 adds 22 host checks for real shared SSD1306 protocol command/data
ordering, transfer failure propagation and structured UART line bounds. Total:
74 C checks and 17 Python tests. Target CI builds both SPI and legacy I²C OLED
variants with synthetic Wi-Fi/API settings so configured paths are linked.
Physical proof requires J4 SPI capture and J3 115200-8N1 serial monitoring, as
described in firmware/README.md.
