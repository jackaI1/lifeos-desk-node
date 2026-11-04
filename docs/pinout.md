# Desk node pinout contract — revision 1

Firmware owns this contract; PCB layout on `skills/pcb` follows it.

## Controller and programming

- ESP32-WROOM-32E, 4 MB flash, no PSRAM; ESP-IDF target `esp32`.
- All signals and peripheral supplies are **3.3 V**. GPIOs are not 5 V tolerant.
- EN: 10 kΩ pull-up to 3V3, reset button to ground, local reset capacitor per module reference design.
- GPIO0: 10 kΩ pull-up, BOOT button to ground; hold low during reset to flash.
- UART0 programming header: GND, 3V3 reference, U0TXD/GPIO1, U0RXD/GPIO3, EN, GPIO0. Use a 3.3 V USB–UART adapter; never connect two power sources directly.
- Preserve boot strapping levels on GPIO0/2/5/12/15. GPIO6–11 are internal flash connections and unavailable.

## Shared I²C bus

| Net | ESP32 GPIO | Connection |
| --- | --- | --- |
| I2C_SDA | 21 | SHT31 SDA + SSD1306 SDA |
| I2C_SCL | 22 | SHT31 SCL + SSD1306 SCL |
| 3V3 | — | SHT31 VDD + OLED module VCC |
| GND | — | Common ground |

- I²C controller 0, 100 kHz; one effective pair of 4.7 kΩ pull-ups to 3V3 (account for breakout pull-ups).
- SHT31-DIS: 7-bit address **0x44**, ADDR tied low, ALERT unused, nRESET pulled high; decouple VDD with 100 nF. Firmware uses single-shot high repeatability, no clock stretching (`0x2400`).
- Display: **SSD1306 128×64, four-pin I²C module**, 7-bit address **0x3C**. Header order **1 GND, 2 3V3, 3 SCL, 4 SDA**; verify the purchased module. SH1106 and SPI modules are not substitutes. Module provides its own reset/power-on circuitry and charge-pump capacitors; no ESP32 reset GPIO is assigned.
- No power-gating GPIO. OLED remains powered and displays its last frame while ESP32 deep-sleeps. On-chip RTC memory preserves the offline ring only across deep sleep; full power loss clears it.

## Power assumptions

- USB **5 V input**, regulated to **3.3 V**; regulator must support **at least 600 mA transient output**, with input/output capacitors per regulator datasheet and local module bulk/ceramic decoupling.
- USB-powered desk device, not a battery-life claim. Default wake interval is 300 s; Wi-Fi and HTTP work have finite timeouts, then timer deep sleep.
- Planning estimates at 3V3: ESP32 Wi-Fi active 80–240 mA (design transient margin above this); ESP32 module deep sleep about 10 µA; OLED typically 5–25 mA depending on lit pixels; SHT31 idle sub-µA, measurement about 1 mA briefly. Regulator, LEDs and USB–UART add to these values.
- Example only: 10 s at 150 mA + 290 s at 10 mA gives 14.7 mA cycle average, about 48 mW at 3V3. Measure the assembled board before quoting battery life or thermal accuracy; keep sensor away from regulator/ESP32 heat and give it airflow.

## Sources and change control

- [Espressif ESP32-WROOM-32E documentation](https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf)
- [Sensirion SHT3x-DIS datasheet](https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf)
- [Solomon Systech SSD1306 datasheet](https://cdn-shop.adafruit.com/datasheets/SSD1306.pdf)

Changes to MCU, addresses, pins, voltage or display controller require matching firmware and PCB updates before merge.
