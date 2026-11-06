# Rev A current estimate (work in progress)

This estimates the existing USB-powered board only. It is not a Rev B design or a battery runtime prediction. Example with an assumed 10-second wake, 3 mA display and 2 V LED forward voltage:

```sh
python3 -m power_budget --active-seconds 10 --display-ma 3 --led-forward-v 2
python3 -m unittest discover -s power_budget/tests -v
```

All output is calculated from datasheet values and explicit assumptions, not measured. The default 300 seconds is the actual `DESK_UPDATE_SECONDS` default and is the sleep duration *after* the wake, not the whole cycle. Wake duration and current vary with networking. The default 112 mA is an illustrative Wi-Fi receive current with idle CPU, not a measured average of this firmware's transmit, receive and CPU phases. Change it when a cycle measurement is available. The ESP32 deep-sleep figure assumes RTC timer and memory. SHT31 idle is modeled continuously; measurement energy, pull-up and GPIO leakage, USB CC currents and other losses are omitted. Display and LED values must be supplied; the display remains powered during sleep. Regulator quiescent current is specified at zero load and is only an approximation under load. Do not use this estimate as a battery life guarantee or infer that Rev A accepts a LiPo: its regulator needs sufficient input headroom.

Sources: [ESP32 module RF currents](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf), table 16; [ESP32 sleep current](https://documentation.espressif.com/esp32_datasheet_en.html), power modes; [SHT3x idle current](https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf), table 3; [AZ1117C](https://www.diodes.com/datasheet/download/AZ1117C.pdf), electrical characteristics. LED current uses (3.3 V minus the assumed forward voltage) / 1 kΩ.

| Bench measurement once hardware exists | Result |
| --- | --- |
| USB input sleep current, display fitted | Not measured |
| USB input average across complete wake and sleep cycle | Not measured |
| Wake duration and Wi-Fi conditions | Not measured |
| Display current and LED forward voltage | Not measured |
