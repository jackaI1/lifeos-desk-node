import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("ess_decode", Path(__file__).parents[1] / "tools/ess_decode.py")
ess = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ess)


class EssDecodeTest(unittest.TestCase):
    # Same vectors as tests/test_ess.c: 21.37 degC and 45.12 %RH, and -1.00 degC.
    def test_known_vectors(self):
        self.assertEqual(ess.temperature("59 08"), 21.37)
        self.assertEqual(ess.humidity("a0 11"), 45.12)
        self.assertEqual(ess.temperature("9c ff"), -1.0)

    def test_range_and_length(self):
        with self.assertRaises(ValueError): ess.temperature("fc 30")   # 12540 = 125.40 degC, too high
        with self.assertRaises(ValueError): ess.humidity("11 27")      # 10001 = 100.01 %, too high
        with self.assertRaises(ValueError): ess.humidity("11")         # one byte only
        with self.assertRaises(ValueError): ess.temperature("59 08 00")
