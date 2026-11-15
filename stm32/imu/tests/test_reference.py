"""Compare the C filter with the Python reference on every trace, byte for byte.

Run from the repository root or from stm32/imu:
    IMU_REPLAY=stm32/imu/build/imu_replay python3 stm32/imu/tests/test_reference.py
"""
import os
import pathlib
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
IMU = HERE.parent
sys.path.insert(0, str(IMU / "reference"))
sys.path.insert(0, str(IMU / "tools"))

import gen_tables  # noqa: E402
import imu_reference  # noqa: E402

REPLAY = pathlib.Path(os.environ.get("IMU_REPLAY", IMU / "build" / "imu_replay"))
TRACES = sorted((IMU / "traces").glob("*.csv"))


def c_replay(path):
    with path.open("rb") as handle:
        result = subprocess.run([str(REPLAY)], stdin=handle, capture_output=True, text=True,
                                timeout=60)
    if result.returncode != 0:
        raise AssertionError("imu_replay failed on %s: %s" % (path.name, result.stderr))
    return result.stdout.splitlines()


def py_reference(path):
    return list(imu_reference.run(path.read_text().splitlines()))


class GeneratedTablesTest(unittest.TestCase):
    def test_committed_tables_match_generator(self):
        self.assertEqual(gen_tables.main(check=True), 0,
                         "run python3 stm32/imu/tools/gen_tables.py and commit the result")


class DivisionTest(unittest.TestCase):
    def test_division_truncates_toward_zero_like_c(self):
        self.assertEqual(imu_reference.div_trunc(-7, 2), -3)
        self.assertEqual(imu_reference.div_trunc(7, -2), -3)
        self.assertEqual(imu_reference.div_trunc(-7, -2), 3)
        self.assertEqual(imu_reference.div_trunc(7, 2), 3)


class AtanTest(unittest.TestCase):
    def test_quadrants_match_math_atan2(self):
        import math
        for y, x in [(1000, 1000), (-1000, 1000), (1000, -1000), (-1000, -1000),
                     (0, 5), (5, 0), (0, -5), (-5, 0), (26795, 100000)]:
            want = math.degrees(math.atan2(y, x)) * 1000
            self.assertLess(abs(imu_reference.atan2_mdeg(y, x) - want), 120, (y, x))


class TraceTest(unittest.TestCase):
    def test_every_trace_matches_c_byte_for_byte(self):
        self.assertTrue(REPLAY.exists(), "build imu_replay first: make -C stm32/imu test")
        self.assertGreater(len(TRACES), 0)
        for path in TRACES:
            with self.subTest(trace=path.name):
                c_lines = c_replay(path)
                py_lines = py_reference(path)
                self.assertEqual(len(c_lines), len(py_lines))
                for index, (c_line, py_line) in enumerate(zip(c_lines, py_lines)):
                    if c_line != py_line:
                        self.fail("%s line %d: C %r, Python %r" % (path.name, index, c_line, py_line))

    def test_bump_trace_raises_bump_and_tilt_flags(self):
        lines = c_replay(IMU / "traces" / "knock.csv")
        flags = [int(line.rsplit(",", 1)[1]) for line in lines]
        self.assertTrue(any(f & 8 for f in flags), "no BUMP flag on the knock trace")
        self.assertTrue(any(f & 16 for f in flags[-200:]), "no TILT flag after the 15 degree move")

    def test_dropped_trace_counts_gaps_and_duplicates(self):
        lines = c_replay(IMU / "traces" / "dropped.csv")
        last = lines[-1].split(",")
        self.assertGreater(int(last[9]), 80, "dropped count too small")
        self.assertTrue(int(last[10]) & 32, "the duplicate line should set DUPLICATE")
        self.assertTrue(any(int(line.split(",")[10]) & 4 for line in lines), "outage should RESET")

    def test_saturated_trace_sets_flag(self):
        lines = c_replay(IMU / "traces" / "saturated.csv")
        self.assertTrue(any(int(line.split(",")[10]) & 1 for line in lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)
