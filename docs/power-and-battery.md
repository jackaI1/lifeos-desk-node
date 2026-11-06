# Moving the desk node away from USB

I built a smaller battery board because the desk node's original regulator and
power light use current even while its controller sleeps. Rev A remains the USB
board. Rev B keeps the same sensor, display and programming pins, replaces the
regulator and adds a separate charging position. Neither board has been built.
Every current, runtime and percentage below is **calculated from datasheets and
explicit assumptions, not a bench measurement**.

## Try the comparison

With Python 3.11 or newer, from the repository root:

```sh
python3 -m power_budget.compare
python3 -m power_budget.compare --awake-s 92 --awake-ma 239 --display-ma 15
python3 -m power_budget.compare --sdkconfig firmware/sdkconfig --json
```

The second command is a deliberately expensive scenario, not a measured failure
cycle. The last command reads only the configured sleep interval and never
prints network credentials. The original `python3 -m power_budget` command is
still available for the preliminary Rev A estimate.

The normal example assumes 10 seconds awake, a 3 mA OLED module and a 500 mAh
battery. A milliamp-hour (mAh) describes stored charge. The example assigns just
60% of Rev B's nameplate charge to operation **above 3.7 V under load**; this is an
assumption to replace with the selected cell's discharge curve and a pulse-load
bench test. It is not a generic LiPo capacity fact.

| Calculated input-current contribution | Rev A (mA) | Rev B (mA) |
| --- | ---: | ---: |
| Controller awake | 3.61290 | 3.61290 |
| Controller asleep with retained memory | 0.00968 | 0.00968 |
| Sensor conversion and idle | 0.00023 | 0.00023 |
| Continuously powered display, assumed | 3.00000 | 3.00000 |
| I²C pull-up resistors, assumed low time | 0.00002 | 0.00002 |
| GPIO pull resistors, awake allowance | 0.03194 | 0.03194 |
| Other leakage allowance, assumed | 0.00500 | 0.00500 |
| Regulator's own current | 4.00000 | 0.05500 |
| Power light, assumed 2 V LED drop | 1.30000 | 0 |
| Charger, physically disconnected in RUN | 0 | 0 |
| **Total, calculated** | **11.9598** | **6.7148** |

The calculated reduction is **43.86%**. The regulator and light consume about
44% of Rev A's input current; awake work and the display dominate Rev B. The JSON
report gives exact shares for every row. Leaving the display on keeps the last
event visible and preserves existing firmware behavior. It also prevents any
claim of microamp whole-board sleep.

Calculated Rev B runtime is **44.68 hours**, `500 × 0.60 / 6.7148`. For Rev A,
a hypothetical external 500 mAh, 3.7 V USB battery pack with an assumed 85% boost
efficiency gives **26.30 hours**, `3.7 × 500 × 0.85 / (5 × 11.9598)`.
Rev A cannot take a LiPo directly. These are different supply arrangements, not
a controlled battery-life experiment. Rev B's runtime excludes charging time;
there is no run-while-charging path. Capacity, temperature, aging, self-discharge,
radio conditions and regulator dropout can shorten both predictions.

## Where the inputs come from

| Input used in the calculation | Origin and limit |
| --- | --- |
| Sleep 300 s by default | `firmware/main/Kconfig.projbuild`, `DESK_UPDATE_SECONDS`; parser reads the real default or supplied sdkconfig. |
| Work followed by sleep | `firmware/main/app_main.c`, `sleep_now()` starts the wake timer after work and stops Wi-Fi. A cycle is awake + sleep, not 300 s total. |
| Awake 10 s | Explicit assumption for boot, reading, networking, drawing and UART drain together. Firmware does not guarantee this duration. Sensor wait is 2 s and network task wait is 90 s; boot and cleanup add time. The 92 s scenario is not a hard total bound. |
| Awake 112 mA | [WROOM-32E datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf), current-consumption table: typical 20 MHz RX. Used as a proxy for the entire awake interval; it understates sustained TX. Set 239 mA for its 802.11b TX average; the table also lists a 379 mA peak. |
| Deep sleep 10 µA | Same module datasheet, RTC timer + retained RTC memory. Actual firmware retains its queue and event; the lower hibernation figure is inappropriate. |
| SHT31 0.6 mA measuring, 0.2 µA idle, 15 ms conversion | [Sensirion SHT3x-DIS v7](https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf), electrical characteristics and high-repeatability duration. Firmware uses single-shot mode, waits 20 ms and leaves the heater off. |
| Rev A regulator 4 mA typical | [AZ1117C](https://www.diodes.com/datasheet/download/AZ1117C.pdf), electrical table (6 mA maximum). A no-load typical proxy, not a guaranteed loaded value. |
| Rev B regulator 55 µA typical | [AP2112](https://www.diodes.com/datasheet/download/AP2112.pdf), electrical table (80 µA maximum). 600 mA output rating, 250 mV typical / 400 mV maximum dropout at 600 mA for 3.3 V. Requires rail-droop/thermal validation. |
| LED `(3.3 - 2.0) / 1k = 1.3 mA` | Actual Rev A R8 = 1 kΩ; LED forward voltage 2.0 V is assumed. Rev B omits R8/D2. |
| Display 3 mA | Assumed **module** load, not an SSD1306 controller-only datasheet number. Replace with measured module current for the actual image and brightness. |
| Pull-ups and leakage | Actual 4.7 kΩ I²C resistors with assumed 4 ms low per line each cycle; a conservative three 10 kΩ output-pull resistor loads for the entire awake interval; 5 µA miscellaneous leakage allowance. |
| Charger 0 mA in RUN | JP1 disconnects its BAT pin from the battery; no reverse-current credit needed. This says nothing about USB input current while charging. |
| Charge 100 mA, termination about 7.5 mA | [MCP73831](https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP73831-Family-Data-Sheet-DS20001984H.pdf): 10 kΩ PROG sets 100 mA, -2ACI 4.2 V option with 7.5% termination ratio. |

This is an input-current model for linear regulators: input current is output
load plus regulator current. I do not apply switching-converter efficiency to
Rev B. Runtime divides usable charge by average cell current. Rev A uses stored
energy divided by 5 V input power because its external pack must boost voltage.
The model does not simulate a discharge curve or guarantee the 3.3 V rail.

## Bench sheet, intentionally empty

Use a current meter with a microamp range and a low-burden, logged high-current
range capable of Wi-Fi peaks. A narrow microamp range alone can brown out the
controller and give a misleading result. Measure rail voltage alongside current.
Start with a current-limited supply, then the specified protected cell. Compare
both boards with the same firmware, display image, brightness and radio setup.

| Quantity to measure | Rev A measured | Rev B measured | Conditions / instrument / date |
| --- | --- | --- | --- |
| Input voltage and supply type | pending | pending | |
| Sleep current, display connected | pending | pending | |
| Sleep current, display unplugged | pending | pending | |
| Wake duration and full-cycle charge | pending | pending | |
| Peak current and minimum 3.3 V rail | pending | pending | |
| Average current over at least ten cycles | pending | pending | |
| Regulator temperature during repeated wake | pending | pending | |
| Charge current and termination, node disconnected | N/A | pending | |
| Capacity delivered before 3.7 V loaded cutoff | N/A | pending | |
| Runtime to rail failure under normal use | pending | pending | |

Populate a copy with real readings and instrument settings; do not replace
"pending" with model output. No microamp meter, battery or VNA measurements
were available for this revision.
