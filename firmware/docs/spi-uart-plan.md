# SPI display and UART logging implementation plan

Jack requires real I²C sensor, SPI display and UART logging use. Keep existing
features, legacy I²C OLED builds, API behavior and hardware work. The owner
explicitly authorized choosing pins, implementation, conflict resolution and merge.

- [x] Publish revision 2 pinout first: SHT31 I²C21/22; SSD1306 SPI18/23/27/26/25;
      UART0 TX1/RX3. PCB owner confirmed and adds CS/RESET pull-ups and D/C pull-down.
- [x] Write failing tests for SSD1306 command/data/frame ordering and failures,
      and bounded structured UART cycle log formatting; implement and pass them.
- [x] Add SPI default and legacy I²C Kconfig choice, independent peripheral init,
      real UART0 driver configuration/write/drain, and idle SPI GPIO release.
- [x] Update documentation and build both display variants in ESP-IDF Docker CI.
- [ ] Independent review; resolve material findings, fetch/rebase origin/main,
      preserve both firmware/hardware changes, merge only after all CI checks pass.

The SSD1306 protocol writer remains pure C and takes a synchronous transport
callback. SPI sends command/data using D/C with CS controlled by the IDF master;
legacy I²C supplies its control byte. SPI RESET is pulsed only when drawing a
fresh frame. CS and RESET are held inactive by board resistors in deep sleep.
UART0 owns the existing programming pins at 115200 8N1, routes ESP-IDF console to
its driver, emits a bounded sample/FIFO/API log, and drains before deep sleep.
No schedule titles or credentials are printed. Host tests verify protocol and
formatting; IDF CI verifies both target variants. Actual wire timing/display/
serial output still require physical hardware and the documented bench steps.
