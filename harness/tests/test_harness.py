import copy
import csv
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from harness.check import load, validate
from harness.generate import generate

EXAMPLE = Path(__file__).resolve().parents[1] / 'example.json'

class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.data = load(EXAMPLE)

    def test_example_and_crossed_uart(self):
        self.assertEqual(validate(self.data), [])
        wires = {w['id']: w for w in self.data['wires']}
        self.assertEqual(wires['P2']['to'], ['UART adapter', 'RX'])
        self.assertEqual(wires['P3']['to'], ['UART adapter', 'TX'])

    def test_duplicate_pin_and_wire_id(self):
        self.data['wires'][1]['from'] = self.data['wires'][0]['from']
        self.data['wires'][1]['id'] = self.data['wires'][0]['id']
        errors = '\n'.join(validate(self.data))
        self.assertIn('used by both', errors)
        self.assertIn('duplicate wire id', errors)

    def test_missing_ground(self):
        self.data['wires'] = [w for w in self.data['wires'] if w['id'] != 'S1']
        self.assertIn('Sensor: missing ground', validate(self.data))

    def test_current_limit(self):
        self.data['wires'][0]['current_a'] = 0.51
        self.assertIn('too small', '\n'.join(validate(self.data)))
        self.data['wires'][0]['current_a'] = 0.5
        self.assertEqual(validate(self.data), [])

    def test_invalid_fields(self):
        self.data['wires'][0]['length_mm'] = -1
        self.data['wires'][0]['to'] = ['unknown', '1']
        self.assertIn('length_mm', '\n'.join(validate(self.data)))
        self.assertIn('unknown connector', '\n'.join(validate(self.data)))

    def test_outputs_and_escaping(self):
        self.data['title'] = 'A & B'
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            generate(self.data, out)
            with (out / 'cut-list.csv').open() as f:
                cuts = list(csv.DictReader(f))
            with (out / 'labels.csv').open() as f:
                labels = list(csv.DictReader(f))
            with (out / 'test-sheet.csv').open() as f:
                tests = list(csv.DictReader(f))
            self.assertEqual(len(cuts), 7)
            self.assertEqual(len(labels), 14)
            self.assertEqual(len(tests), 9)
            self.assertEqual(cuts[0]['Cut length (mm)'], '200')
            self.assertIn('A & B', ''.join(ET.parse(out / 'harness.svg').getroot().itertext()))

    def test_invalid_map_produces_no_files(self):
        self.data['wires'][0]['awg'] = 99
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                generate(self.data, Path(folder) / 'out')
            self.assertFalse((Path(folder) / 'out').exists())

    def test_cli_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'bad.json'
            p.write_text(json.dumps({'wires': []}))
            result = subprocess.run([sys.executable, '-m', 'harness.check', str(p)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('nonempty', result.stderr)

if __name__ == '__main__':
    unittest.main()
