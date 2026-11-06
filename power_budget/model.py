"""Input-referred LDO power model. Every output is calculated, never measured."""
from dataclasses import asdict, dataclass
from pathlib import Path
import math
import re

ROOT = Path(__file__).resolve().parents[1]


def sleep_seconds(config=None):
    """Read just the public timing option, never serialize a private sdkconfig."""
    if config:
        match = re.search(r'^CONFIG_DESK_UPDATE_SECONDS=(\d+)$', Path(config).read_text(), re.M)
    else:
        text = (ROOT / 'firmware/main/Kconfig.projbuild').read_text()
        match = re.search(r'config DESK_UPDATE_SECONDS\b.*?default (\d+)', text, re.S)
    if not match or not 60 <= int(match[1]) <= 86400:
        raise ValueError('missing or invalid firmware sleep interval')
    return int(match[1])


@dataclass(frozen=True)
class Assumptions:
    awake_s: float = 10.0  # assumed, includes boot, sensor, networking, render and log
    awake_ma: float = 112.0  # datasheet RX proxy; use 239 for a TX-heavy scenario
    display_ma: float = 3.0  # external module assumption, NOT an SSD1306 datasheet value
    led_vf: float = 2.0  # assumed forward voltage for Rev A LED
    capacity_mah: float = 500.0  # assumed protected 1S LiPo/nameplate USB-pack capacity
    usable_fraction: float = 0.60  # assumed capacity available ABOVE 3.7 V under load
    usb_efficiency: float = 0.85  # assumed external USB boost efficiency, Rev A only
    leakage_ma: float = 0.005  # assumed unmodelled PCB/peripheral leakage allowance

    def validate(self):
        if not all(math.isfinite(v) for v in asdict(self).values()):
            raise ValueError('assumptions must be finite')
        if (self.awake_s < .02 or self.awake_ma <= 0 or self.display_ma < 0 or
                not 0 <= self.led_vf <= 3.3 or self.capacity_mah <= 0 or
                not 0 < self.usable_fraction <= 1 or not 0 < self.usb_efficiency <= 1 or self.leakage_ma < 0):
            raise ValueError('invalid assumption range')


def compare(a=Assumptions(), sleep_s=None):
    a.validate()
    sleep_s = sleep_seconds() if sleep_s is None else sleep_s
    if not math.isfinite(sleep_s) or sleep_s <= 0:
        raise ValueError('sleep duration must be positive and finite')
    period = sleep_s + a.awake_s  # timer starts AFTER the work, not a wall-clock period
    duty = a.awake_s / period
    common = {
        'ESP32 awake': a.awake_ma * duty,
        'ESP32 deep sleep (RTC retained)': .010 * (1 - duty),
        'SHT31 conversion + idle': (.6 * .015 + .0002 * (period - .015)) / period,
        'OLED continuously powered (assumed)': a.display_ma,
        'I2C pull-ups (4ms low per line assumed)': 2 * (3.3 / 4.7) * .004 / period,
        'GPIO pull resistors (awake upper allowance)': 3 * (3.3 / 10) * duty,
        'unmodelled leakage allowance (assumed)': a.leakage_ma,
    }
    boards = {}
    for rev, iq, led, vin in [('A', 4.0, 3.3 - a.led_vf, 5.0), ('B', .055, 0, 3.7)]:
        parts = dict(common, **{'regulator quiescent': iq, 'power LED': led})
        # JP1 physically isolates charger from BAT_PLUS in RUN: zero cell drain.
        parts['charger (disconnected in RUN)'] = 0
        total = sum(parts.values())
        if rev == 'A':
            hours = (3.7 * a.capacity_mah * a.usb_efficiency) / (5 * total)
            basis = 'hypothetical external 5V USB battery pack; Rev A cannot accept a LiPo directly'
        else:
            hours = a.capacity_mah * a.usable_fraction / total
            basis = 'protected 1S LiPo; assumed usable fraction above 3.7V loaded cutoff, not full nameplate'
        boards[rev] = dict(parts_ma=parts, average_ma=total, runtime_hours=hours,
                           input_power_mw=vin * total, runtime_basis=basis,
                           share_percent={k: 100 * v / total for k, v in parts.items()})
    return dict(label='CALCULATED from datasheets + explicit assumptions; NOT bench measurements',
                assumptions=asdict(a), sleep_s=sleep_s, cycle_s=period, awake_duty=duty,
                boards=boards, current_reduction_percent=100*(1-boards['B']['average_ma']/boards['A']['average_ma']))
