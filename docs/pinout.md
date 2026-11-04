# Desk node pinout contract — revision 2

Firmware owns this contract; PCB layout on `skills/pcb` follows it.

## Controller and programming

- ESP32-WROOM-32E, 4 MB flash, no PSRAM; ESP-IDF target `esp32`.
- All signals and peripheral supplies are **3.3 V**. GPIOs are not 5 V tolerant.
- EN: 10 kΩ pull-up to 3V3, reset button to ground, local reset capacitor per module reference design.
- GPIO0: 10 kΩ pull-up, BOOT button to ground; hold low during reset to flash.
- UART0 programming header: GND, 3V3 reference, U0TXD/GPIO1, U0RXD/GPIO3, EN, GPIO0. Use a 3.3 V USB–UART adapter; never connect two power sources directly.
- Preserve boot strapping levels on GPIO0/2/5/12/15. GPIO6–11 are internal flash connections and unavailable.

## I²C sensor and legacy expansion

| Net | ESP32 GPIO | Connection |
| --- | --- | --- |
| I2C_SDA | 21 | SHT31 SDA + J2 expansion SDA |
| I2C_SCL | 22 | SHT31 SCL + J2 expansion SCL |
| 3V3 | — | SHT31 VDD + peripheral power |
| GND | — | Common ground |

- I²C controller 0, 100 kHz; one effective pair of 4.7 kΩ pull-ups to 3V3 (account for breakout pull-ups).
- SHT31-DIS: 7-bit address **0x44**, ADDR tied low, ALERT unused, nRESET pulled high; decouple VDD with 100 nF. Firmware uses single-shot high repeatability, no clock stretching (`0x2400`).
- J2 expansion / optional legacy display: **1 GND, 2 3V3, 3 SCL, 4 SDA**. Legacy SSD1306 I²C address **0x3C** is supported only when selected in firmware menuconfig. Do not connect both display variants simultaneously.
- No power-gating GPIO. OLED remains powered and displays its last frame while ESP32 deep-sleeps. On-chip RTC memory preserves the offline ring only across deep sleep; full power loss clears it.

## Default SPI display — J4

SSD1306 128×64 **seven-pin, 4-wire SPI module**, internal charge pump. Select its
4-wire SPI interface straps per module datasheet; a four-pin I²C-only module is
not a plug-in replacement. SH1106 is not supported. The module supplies its own
charge-pump capacitors. SPI2 host, mode 0, MSB first, **4 MHz**, write only (no MISO).

| J4 pin | Net | ESP32 GPIO |
| --- | --- | --- |
| 1 | GND | — |
| 2 | 3V3 | — |
| 3 | SCLK | 18 |
| 4 | MOSI / display DIN | 23 |
| 5 | RESET, active low | 25 |
| 6 | D/C, 0 command / 1 data | 26 |
| 7 | CS, active low | 27 |

Use a 10 kΩ pull-up on RESET and CS, and a 10 kΩ pull-down on D/C so the powered
OLED retains its frame when ESP32 GPIOs become high impedance during deep sleep.
Firmware pulses RESET only before drawing a fresh frame, then leaves RESET high
and CS inactive before releasing its GPIOs. Keep the display powered in sleep.
PCB agent confirmed these pins have no conflicts. Existing J2 expansion stays.

## UART logging — J3

UART0 **115200 baud, 8 data bits, no parity, 1 stop bit, no flow control**.
TX GPIO1 goes to USB–UART RX; RX GPIO3 goes to USB–UART TX; common GND is required.
The programming header also exposes EN/BOOT as above. Each cycle logs sample
status, FIFO occupancy/loss, API acknowledgment and sleep interval, with a bounded
transmit drain before deep sleep. USB-C is power-only; it is not a USB serial link.

## Power assumptions

- USB **5 V input**, regulated to **3.3 V**; PCB uses an **AZ1117C 800 mA LDO**, exceeding the firmware assumption of **at least 600 mA transient output**, with input/output capacitors per regulator datasheet and local module bulk/ceramic decoupling.
- USB-powered desk device, not a battery-life claim. Default wake interval is 300 s; Wi-Fi and HTTP work have finite timeouts, then timer deep sleep.
- Planning estimates at 3V3: ESP32 Wi-Fi active 80–240 mA (design transient margin above this); ESP32 module deep sleep about 10 µA; OLED typically 5–25 mA depending on lit pixels; SHT31 idle sub-µA, measurement about 1 mA briefly. Regulator, LEDs and USB–UART add to these values.
- Example only: 10 s at 150 mA + 290 s at 10 mA gives 14.7 mA cycle average, about 48 mW at 3V3. Measure the assembled board before quoting battery life or thermal accuracy; keep sensor away from regulator/ESP32 heat and give it airflow.

## Sources and change control

- [Espressif ESP32-WROOM-32E documentation](https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf)
- [Sensirion SHT3x-DIS datasheet](https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf)
- [Solomon Systech SSD1306 datasheet](https://cdn-shop.adafruit.com/datasheets/SSD1306.pdf)

Changes to MCU, addresses, pins, voltage or display controller require matching firmware and PCB updates before merge.
