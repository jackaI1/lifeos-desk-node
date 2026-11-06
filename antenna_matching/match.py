"""Fit finite-Q L and pi networks to a calibrated one-port Touchstone sweep."""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import skrf as rf
from scipy.optimize import differential_evolution


def load(path):
    antenna = rf.Network(str(path))
    if antenna.nports != 1 or len(antenna.f) < 3:
        raise ValueError('need a one-port sweep with at least three frequency samples')
    if (not np.all(np.isfinite(antenna.s)) or not np.all(np.isfinite(antenna.z0)) or
            np.any(antenna.f <= 0) or np.any(np.diff(antenna.f) <= 0)):
        raise ValueError('sweep must be finite with positive increasing frequencies')
    antenna.renormalize(50)
    if np.any(np.abs(antenna.s) > 1 + 1e-6):
        raise ValueError('passive antenna required; check calibration and input data')
    return antenna


def element(frequency, connection, kind, value, q):
    """ABCD network; ESR = |reactance|/Q at each frequency (assumed constant Q)."""
    if not np.isfinite(value) or value <= 0 or not np.isfinite(q) or q <= 0:
        raise ValueError('component and Q must be finite and positive')
    if kind not in ('L', 'C'):
        raise ValueError('component must be L or C')
    w = 2 * np.pi * frequency.f
    x = w * value if kind == 'L' else -1 / (w * value)
    z = np.abs(x) / q + 1j * x
    a = np.tile(np.eye(2, dtype=complex), (len(w), 1, 1))
    if connection == 'series':
        a[:, 0, 1] = z
    elif connection == 'shunt':
        a[:, 1, 0] = 1 / z
    else:
        raise ValueError('connection must be series or shunt')
    return rf.Network(frequency=frequency, a=a, z0=50)


def apply(antenna, parts, q):
    network = None
    for part in parts:  # listed from radio/source toward antenna/load
        e = element(antenna.frequency, part['connection'], part['kind'], part['value_si'], q)
        network = e if network is None else network ** e
    return network ** antenna


def return_loss(network):
    return -20 * np.log10(np.maximum(np.abs(network.s[:, 0, 0]), 1e-15))


def e24(value):
    preferred = np.array([10,11,12,13,15,16,18,20,22,24,27,30,33,36,39,43,47,51,56,62,68,75,82,91,100])
    decade = 10 ** np.floor(np.log10(value))
    return float(preferred[np.argmin(np.abs(preferred / 10 * decade - value))] / 10 * decade)


def design(antenna, topology, low=2.4e9, high=2.5e9, q=50, tolerance=.05):
    if (not np.isfinite([low, high, q, tolerance]).all() or low >= high or q <= 0 or not 0 <= tolerance < 1):
        raise ValueError('invalid band, Q or tolerance')
    if low < antenna.f[0] or high > antenna.f[-1]:
        raise ValueError('requested band extends outside the measured sweep; no extrapolation')
    band = (antenna.f >= low) & (antenna.f <= high)
    if band.sum() < 3:
        raise ValueError('need at least three measured samples in band')
    if topology == 'L':
        arrangements = [('series','shunt'), ('shunt','series')]
    elif topology == 'pi':
        arrangements = [('shunt','series','shunt')]
    else:
        raise ValueError('topology must be L or pi')
    best = None
    for connections in arrangements:
        for kinds in itertools.product('LC', repeat=len(connections)):
            scales = [1e-9 if k == 'L' else 1e-12 for k in kinds]
            def parts(logs):
                return [dict(connection=c,kind=k,value_si=float(10**v*scale))
                        for c,k,v,scale in zip(connections,kinds,logs,scales)]
            def score(logs):
                s = apply(antenna, parts(logs), q).s[band,0,0]
                return float(np.mean(np.abs(s)**2))
            result = differential_evolution(score, [(-1, np.log10(30))]*len(kinds), seed=13,
                                            popsize=6, maxiter=65, tol=1e-7, polish=True, workers=1)
            candidate = parts(result.x)
            for part in candidate:
                part['value_si'] = e24(part['value_si'])
            fitted = apply(antenna,candidate,q)
            reflected = float(np.mean(np.abs(fitted.s[band,0,0])**2))
            if best is None or reflected < best[0]:
                best = reflected, candidate, fitted
    _, parts, fitted = best
    corners = []
    for signs in itertools.product((-1,1),repeat=len(parts)):
        varied = [dict(p,value_si=p['value_si']*(1+tolerance*s)) for p,s in zip(parts,signs)]
        corners.append(float(return_loss(apply(antenna,varied,q))[band].min()))
    before, after = return_loss(antenna), return_loss(fitted)
    center = int(np.argmin(abs(antenna.f - (low + high)/2)))
    report = dict(topology=topology, parts_source_to_antenna=parts, q_assumed=q,
                  tolerance_assumed=tolerance, band_hz=[low,high], center_sample_hz=float(antenna.f[center]),
                  before_center_rl_db=float(before[center]), after_center_rl_db=float(after[center]),
                  before_worst_band_rl_db=float(before[band].min()), after_worst_band_rl_db=float(after[band].min()),
                  worst_tolerance_corner_rl_db=min(corners),
                  before_mean_reflected_power=float(np.mean(np.abs(antenna.s[band,0,0])**2)),
                  after_mean_reflected_power=best[0],
                  limitation='Calculated constant-Q lumped elements; no pads, traces, self-resonance or radiation-efficiency model. Validate with a VNA.')
    return report, fitted


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('touchstone', type=Path)
    p.add_argument('--source-kind', choices=['synthetic','measured'],required=True,
                   help='describe the actual file origin honestly')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--low-ghz', type=float,default=2.4)
    p.add_argument('--high-ghz',type=float,default=2.5)
    p.add_argument('--q',type=float,default=50)
    args = p.parse_args()
    try:
        antenna = load(args.touchstone)
        results = [design(antenna,t,args.low_ghz*1e9,args.high_ghz*1e9,args.q) for t in ('L','pi')]
    except (ValueError, OSError) as e:
        p.error(str(e))
    args.output.mkdir(parents=True,exist_ok=True)
    report = dict(source_kind=args.source_kind, input_file=args.touchstone.name,
                  input_sha256=hashlib.sha256(args.touchstone.read_bytes()).hexdigest(),
                  label='CALCULATED matching predictions, not measured matched results',
                  designs=[r for r,n in results])
    (args.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    with (args.output/'sweep.csv').open('w',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['frequency_hz','before_rl_db','L_calculated_rl_db','pi_calculated_rl_db'])
        writer.writerows(zip(antenna.f,return_loss(antenna),*(return_loss(n) for r,n in results)))
    for report, network in results:
        network.write_touchstone(str(args.output/(report['topology']+'-predicted')))
        print(f"{report['topology']}: worst-band return loss {report['before_worst_band_rl_db']:.2f} -> {report['after_worst_band_rl_db']:.2f} dB (calculated)")


if __name__ == '__main__':
    main()
