#!/usr/bin/env python3
"""Replay fixed-step temperature samples through the C controller."""
import csv
import random
import subprocess
import sys
import unittest
from pathlib import Path

DRIVER = str(Path(sys.argv.pop(1)).resolve())


def reference(samples, low=19000, high=21000, timeout=3):
    heat = False
    fault = False
    misses = 0
    result = []
    for valid, temperature in samples:
        if valid:
            misses = 0
            fault = False
            if temperature <= low:
                heat = True
            elif temperature >= high:
                heat = False
        else:
            misses = min(misses + 1, timeout)
            if misses == timeout:
                fault = True
                heat = False
        result.append((int(heat), int(fault)))
    return result


def replay(samples):
    data = ''.join(f'{valid} {temp}\n' for valid, temp in samples)
    proc = subprocess.run([DRIVER], input=data, text=True, capture_output=True, check=True)
    return [tuple(map(int, line.split())) for line in proc.stdout.splitlines()]


class ControllerTests(unittest.TestCase):
    def test_recorded_trace(self):
        with (Path(__file__).parent / 'thermostat_trace.csv').open() as f:
            rows = list(csv.DictReader(f))
        samples = [(int(r['valid']), int(r['milli_c'])) for r in rows]
        expected = [(int(r['heat']), int(r['fault'])) for r in rows]
        self.assertEqual(reference(samples), expected)
        self.assertEqual(replay(samples), expected)

    def test_seeded_random_traces(self):
        rng = random.Random(721)
        samples = [(int(rng.random() > .22), rng.randint(17000, 23000)) for _ in range(20000)]
        self.assertEqual(replay(samples), reference(samples))


if __name__ == '__main__':
    unittest.main()
