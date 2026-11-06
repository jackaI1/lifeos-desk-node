"""SCPI drivers, simulated link, test sequencing, and analysis."""
from dataclasses import dataclass
from itertools import product
import html
import random
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

@dataclass
class Link:
    length_km: float = 10
    attenuation_db_km: float = 0.2
    connector_loss_db: float = 1
    splice_loss_db: float = 0.5
    noise_dbm: float = -45
    seed: int = 42

    @property
    def loss_db(self):
        return self.length_km * self.attenuation_db_km + self.connector_loss_db + self.splice_loss_db

class MockResource:
    """A PyVISA-like resource with shared instrument state and seeded noise."""
    def __init__(self, link):
        self.link = link
        self.rng = random.Random(link.seed)
        self.wavelength = 1550.0
        self.launch = 0.0
        self.fail_next = False
        self.dropout_next = False
        self.outlier_next = False

    def _check(self):
        if self.fail_next:
            self.fail_next = False
            raise TimeoutError('Injected instrument timeout')

    def write(self, command):
        self._check()
        parts = command.strip().upper().split()
        if len(parts) != 2 or parts[0] not in ('SOUR:WAV', 'SOUR:POW'):
            raise ValueError(f'Unsupported SCPI command: {command}')
        value = float(parts[1])
        if parts[0] == 'SOUR:WAV': self.wavelength = value
        else: self.launch = value

    def query(self, command):
        self._check()
        command = command.strip().upper()
        if command == '*IDN?': return 'SIMULATED,OPTICAL-STATION,1,1.0'
        if command not in ('MEAS:POW?', 'MEAS:OSNR?'):
            raise ValueError(f'Unsupported SCPI query: {command}')
        if self.dropout_next:
            self.dropout_next = False
            return 'nan'
        signal = self.launch - self.link.loss_db + self.rng.gauss(0, 0.03)
        if self.outlier_next:
            self.outlier_next = False
            signal += 30
        return str(signal if command == 'MEAS:POW?' else signal - self.link.noise_dbm)

class Laser:
    def __init__(self, resource): self.resource = resource
    def configure(self, wavelength_nm, launch_dbm):
        self.resource.write(f'SOUR:WAV {wavelength_nm}')
        self.resource.write(f'SOUR:POW {launch_dbm}')

class PowerMeter:
    def __init__(self, resource): self.resource = resource
    def read(self): return float(self.resource.query('MEAS:POW?'))

class Analyser:
    def __init__(self, resource): self.resource = resource
    def osnr(self): return float(self.resource.query('MEAS:OSNR?'))

def clean_readings(values):
    series = pd.to_numeric(pd.Series(values, dtype='float64'), errors='coerce').dropna()
    series = series[series.abs() != float('inf')]
    if len(series) < 3: return series.tolist()
    median = series.median()
    deviation = (series - median).abs()
    mad = deviation.median()
    # A zero MAD is common for rounded instruments; use a small absolute tolerance.
    return series[deviation <= max(3 * 1.4826 * mad, 0.1)].tolist()

def run_plan(plan, resource):
    if plan.get('version') != 1: raise ValueError('Unsupported plan version')
    if not plan.get('wavelength_nm') or not plan.get('launch_dbm') or int(plan.get('samples', 0)) < 3:
        raise ValueError('Plan requires sweep values and at least three samples')
    laser, meter, analyser = Laser(resource), PowerMeter(resource), Analyser(resource)
    results = []
    for wavelength, launch in product(plan['wavelength_nm'], plan['launch_dbm']):
        laser.configure(wavelength, launch)
        powers, osnrs = [], []
        errors = []
        for _ in range(plan['samples']):
            try:
                powers.append(meter.read()); osnrs.append(analyser.osnr())
            except (TimeoutError, ValueError) as exc:
                errors.append(str(exc))
        power, osnr = clean_readings(powers), clean_readings(osnrs)
        minimum = max(3, (plan['samples'] + 1) // 2)
        if len(power) < minimum or len(osnr) < minimum:
            results.append(dict(wavelength_nm=wavelength, launch_dbm=launch, status='fail', reason='Insufficient valid readings', errors=errors)); continue
        loss = launch - sum(power) / len(power)
        snr = sum(osnr) / len(osnr)
        loss_margin = plan['max_loss_db'] - loss
        osnr_margin = snr - plan['min_osnr_db']
        status = 'fail' if min(loss_margin, osnr_margin) < 0 else ('marginal' if min(loss_margin, osnr_margin) < plan.get('margin_db', 1) else 'pass')
        results.append(dict(wavelength_nm=wavelength, launch_dbm=launch, loss_db=loss, osnr_db=snr, loss_margin_db=loss_margin, osnr_margin_db=osnr_margin, status=status, valid_power=len(power), valid_osnr=len(osnr), errors=errors))
    return results

def train_classifier():
    # Synthetic examples are labelled by the same documented engineering thresholds.
    rng = random.Random(25)
    x, y = [], []
    for _ in range(1200):
        a, b = rng.uniform(-5, 5), rng.uniform(-5, 5)
        x.append([a, b]); y.append('fail' if min(a, b) < 0 else ('marginal' if min(a, b) < 1 else 'pass'))
    train_x, test_x, train_y, test_y = train_test_split(x, y, test_size=0.25, random_state=42, stratify=y)
    model = RandomForestClassifier(n_estimators=100, random_state=42, min_samples_leaf=2).fit(train_x, train_y)
    pred = model.predict(test_x)
    return model, {'accuracy': accuracy_score(test_y, pred), 'test_count': len(test_y), 'report': classification_report(test_y, pred, output_dict=True, zero_division=0)}

def render_report(results):
    table = pd.DataFrame(results).to_html(index=False, escape=True)
    return '<!doctype html><html><head><meta charset="utf-8"><title>Optical test report</title></head><body><h1>Optical test report</h1>' + table + '</body></html>'
