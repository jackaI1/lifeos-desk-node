# lifeos-desk-node
ESP32 desk companion for LifeOS: embedded C firmware (ESP-IDF, FreeRTOS) and a KiCad PCB.

## Firmware

The [ESP-IDF C firmware](firmware/) shows the next LifeOS class or deadline on an
SSD1306 SPI OLED and samples an SHT31 temperature/humidity sensor over I²C. FreeRTOS
tasks coordinate sampling and Wi-Fi/API work, with timer deep sleep between
updates, UART0 cycle logging and a 64-reading offline FIFO retained across deep sleep.

Start with the [wiring and power contract](docs/pinout.md), then follow the
[build, API adapter and bench-test instructions](firmware/README.md).
[GitHub Actions](.github/workflows/firmware.yml) runs host sanitizer/API tests and
builds both SPI and legacy I²C display firmware using `espressif/idf:v5.4.2`. Hardware operation and current
draw require bench validation; documented power figures are estimates.

## Skills demonstrated

- **Embedded C / ESP-IDF:** FreeRTOS queues/tasks, Wi-Fi/TLS HTTP, retained RTC
  buffering and deep sleep in [`firmware/main/`](firmware/main/).
- **I²C, SPI and UART:** SHT31 single-shot I²C measurement with CRC validation,
  SSD1306 SPI framebuffer output and UART0 diagnostics at 115200 8N1 in [`firmware/components/desk_drivers/`](firmware/components/desk_drivers/).
- **Testable firmware design:** platform-independent FIFO, sensor conversion,
  JSON validation and text rendering in [`firmware/components/desk_core/`](firmware/components/desk_core/),
  exercised by host C sanitizer tests in [`firmware/tests/`](firmware/tests/).
- **API integration:** a deduplicating adapter maps the device API to LifeOS's
  authenticated schedule and dedicated daily room-log notes in
  [`firmware/tools/desk_api.py`](firmware/tools/desk_api.py).
