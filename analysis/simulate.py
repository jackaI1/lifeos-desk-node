"""Deterministic synthetic room readings; no recordings or private input required."""
import csv

import numpy as np

from .core import Samples


def simulate(seed=7, count=2048):
    rng = np.random.default_rng(seed)
    seconds = np.arange(count)*300.
    truth = 22 + .8*np.sin(2*np.pi*seconds/7200)
    noise = .6*np.sin(2*np.pi*seconds/900) + rng.normal(0, .18, count)
    spikes = np.arange(83, count, 137)
    noise[spikes] += rng.choice([-1, 1], len(spikes))*3
    data = Samples(1700000000 + seconds, truth + noise, truth)
    return data, {'synthetic': True, 'seed': seed, 'sample_count': count,
                  'sample_period_seconds': 300, 'signal_tone_hz': 1/7200,
                  'noise_tone_hz': 1/900, 'signal_amplitude_c': .8,
                  'noise_amplitude_c': .6, 'gaussian_std_c': .18,
                  'spike_amplitude_c': 3, 'spike_indices': spikes.tolist(),
                  'humidity': '45 percent plus 1.5 times temperature deviation from 22 C'}


def write_csv(path, data):
    with open(path, 'w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['timestamp', 'temperature_mc', 'humidity_mpermil',
                         'true_temperature_mc', 'true_humidity_mpermil'])
        for t, value, truth in zip(data.times, data.values, data.truth):
            writer.writerow([t, value*1000, (45+1.5*(value-22))*1000,
                             truth*1000, (45+1.5*(truth-22))*1000])
