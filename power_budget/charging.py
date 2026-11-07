"""Duty-cycle and simplified one-cell CC/CV model, explicitly not a charger design."""
import argparse
import csv
from dataclasses import dataclass
import json
import math


def finite(*values):
    if not all(type(x) in (float, int) and math.isfinite(x) for x in values):
        raise ValueError('finite numeric inputs required')


def duty_cycle(profile, *, capacity_mah=500, voltage=3.7, temperature_c=25, cutoff=3.4):
    finite(capacity_mah, voltage, temperature_c, cutoff)
    if capacity_mah <= 0 or cutoff <= 0 or not -20 <= temperature_c <= 60:
        raise ValueError('invalid battery assumptions')
    if not profile: raise ValueError('empty current profile')
    total = charge = 0
    for row in profile:
        duration, current = row['seconds'], row['ma']
        finite(duration, current)
        if duration <= 0 or current < 0: raise ValueError('invalid current phase')
        total += duration
        charge += duration*current
    average = charge/total
    # Deliberately visible assumption: 1% capacity loss per C below 20 C,
    # bounded at 50%. This is not a cell manufacturer's characterisation.
    derating = max(.5, 1 - max(0, 20-temperature_c)*.01)
    brownout = voltage <= cutoff
    return dict(average_ma=average, runtime_hours=0 if brownout else capacity_mah*derating/average if average else None,
                derating=derating, brownout=brownout, cycle_seconds=total)


@dataclass(frozen=True)
class Cell:
    capacity_mah: float = 500
    initial_soc: float = .2
    current_ma: float = 100
    termination_ma: float = 10
    temperature_c: float = 25
    resistance_ohm: float = 2.0
    target_v: float = 4.2

    def validate(self):
        finite(*self.__dict__.values())
        if not (self.capacity_mah > 0 and 0 <= self.initial_soc <= 1 and
                0 < self.termination_ma < self.current_ma and self.resistance_ohm > 0 and
                4.1 <= self.target_v <= 4.2): raise ValueError('invalid cell/charger assumptions')
        if not 0 <= self.temperature_c <= 45: raise ValueError('charging inhibited outside 0..45 C')


def charge(cell=Cell(), step_s=5):
    cell.validate()
    finite(step_s)
    if not .1 <= step_s <= 60: raise ValueError('step must be .1..60 seconds')
    current_limit = cell.current_ma * (.5 if cell.temperature_c < 10 or cell.temperature_c > 40 else 1)
    if current_limit <= cell.termination_ma: raise ValueError('derated current below termination')
    soc, seconds = cell.initial_soc, 0
    trace = []
    # Linear OCV(SOC) 3.0..4.2 V plus series resistance. CV current tapers
    # with remaining headroom; integrate coulombs, no claimed electrochemistry.
    for _ in range(math.ceil(48*3600/step_s)):
        ocv = 3 + 1.2*soc
        cv_ma = max(0, (cell.target_v-ocv)/cell.resistance_ohm*1000)
        current = min(current_limit, cv_ma)
        voltage = min(cell.target_v, ocv + current/1000*cell.resistance_ohm)
        stage = 'CC' if cv_ma > current_limit else 'CV'
        trace.append(dict(seconds=seconds, soc=soc, ma=current, voltage=voltage, stage=stage))
        if current <= cell.termination_ma:
            return dict(label='SIMULATED, linear OCV + series resistance', charge_hours=seconds/3600,
                        terminated=True, trace=trace)
        soc = min(1, soc + current*step_s/3600/cell.capacity_mah)
        seconds += step_s
    raise ValueError('charge did not terminate within 48 hours')


def check_trace(rows, *, budget_ma, cutoff_v=3.4, max_temperature_c=45):
    finite(budget_ma, cutoff_v, max_temperature_c)
    if budget_ma <= 0 or cutoff_v <= 0: raise ValueError('positive limits required')
    if len(rows) < 2: raise ValueError('trace needs at least two samples')
    integral = 0
    alarms = []
    previous = None
    for row in rows:
        t, ma, voltage, temperature = (float(row[k]) for k in ('seconds', 'ma', 'voltage', 'temperature_c'))
        finite(t, ma, voltage, temperature)
        if t < 0 or ma < 0: raise ValueError('invalid sample')
        if previous:
            if t <= previous[0]: raise ValueError('trace time must increase')
            integral += (t-previous[0])*(ma+previous[1])/2
        if voltage <= cutoff_v: alarms.append(dict(seconds=t, error='brownout'))
        if temperature > max_temperature_c: alarms.append(dict(seconds=t, error='temperature'))
        previous = t, ma
    average = integral/(float(rows[-1]['seconds'])-float(rows[0]['seconds']))
    if average > budget_ma: alarms.append(dict(error='budget', average_ma=average))
    return dict(average_ma=average, alarms=alarms)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', help='JSON array of seconds/ma duty-cycle phases')
    p.add_argument('--capacity-mah', type=float, default=500)
    p.add_argument('--voltage', type=float, default=3.7)
    p.add_argument('--temperature-c', type=float, default=25)
    p.add_argument('--trace', help='CSV seconds,ma,voltage,temperature_c, simulated or measured')
    p.add_argument('--budget-ma', type=float, default=10)
    p.add_argument('--output', help='optional simulated charging CSV')
    a = p.parse_args()
    if a.profile:
        with open(a.profile) as stream:
            result = duty_cycle(json.load(stream), capacity_mah=a.capacity_mah, voltage=a.voltage, temperature_c=a.temperature_c)
    elif a.trace:
        with open(a.trace, newline='') as stream: result = check_trace(list(csv.DictReader(stream)), budget_ma=a.budget_ma)
    else:
        result = charge()
        if a.output:
            with open(a.output, 'w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(result['trace'][0]))
                writer.writeheader(); writer.writerows(result['trace'])
        result = {k: v for k, v in result.items() if k != 'trace'}
        result['duty_cycle'] = duty_cycle([dict(seconds=300, ma=3.0652), dict(seconds=.02, ma=3.6), dict(seconds=2, ma=242.055)])
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__': main()
