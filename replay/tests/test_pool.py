"""Parallel scenario replay: every thread count must match the single-thread run byte for byte.

Run under ThreadSanitizer (see run.sh); any reported data race makes the binary exit
with code 66, and these tests require exit code 0 and an empty stderr."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
REPLAY = os.environ.get("DESK_REPLAY_BIN", str(ROOT / "replay/build/desk-replay"))

SCENARIOS = [
    "(scenario (sample 25000 50000))",
    "(scenario (repeat 70 (sample 25000 50000)) (upload))",
    "(scenario (repeat 70 (sample 0 0)))",
    "(scenario (sample 25000 50000) (fault 25000 50000))",
    "(scenario (upload) (sample 25000 50000) (upload) (fault 0 0) (sample -45000 100000))",
    "(scenario (repeat 4096 (sample 25000 50000)))",
    "(scenario (sample -45000 100000))",
    "(scenario (sample 130000 0) (upload))",
    "(scenario (repeat 3 (sample 21500 45000) (sample 23000 50000)) (upload) "
    "(fault 25000 50000) (sample -500 60000))",
    "(scenario (repeat 2 (sample 1 1) (repeat 2 (upload))))",
    "(scenario (repeat 30 (sample 10000 20000) (upload)))",
    "(scenario (repeat 100 (fault 1 2) (sample 3 4)))",
]


def compile_scenario(text):
    result = subprocess.run(
        ["guile", "--no-auto-compile", "-L", str(ROOT / "replay/scheme"),
         str(ROOT / "replay/compile.scm")], input=text, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.encode()


def run(args):
    return subprocess.run([REPLAY, *args], capture_output=True)


class PoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.wires = []
        for index, text in enumerate(SCENARIOS):
            path = cls.dir / f"scenario-{index:02}.wire"
            path.write_bytes(compile_scenario(text))
            cls.wires.append(path)
        # Repeat and interleave the scenarios so workers see many different jobs.
        cls.jobs = [str(cls.wires[(i * 7) % len(cls.wires)]) for i in range(240)]
        cls.single = run(["--jobs", "1", *cls.jobs])
        assert cls.single.returncode == 0, cls.single.stderr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def assertSameAsSingle(self, result, expected):
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.stdout, expected.stdout)

    def test_thread_counts_match_single_thread_byte_for_byte(self):
        # Varying thread counts, including one that does not divide the job count evenly.
        for threads in (2, 3, 4, 5, 8, 16, 64):
            for repeat in range(3):
                with self.subTest(threads=threads, repeat=repeat):
                    self.assertSameAsSingle(run(["--jobs", str(threads), *self.jobs]), self.single)

    def test_each_line_matches_the_original_stdin_mode(self):
        lines = self.single.stdout.splitlines()
        self.assertEqual(len(lines), len(self.jobs))
        for index, wire in enumerate(self.wires):
            with self.subTest(scenario=wire.name):
                stdin = subprocess.run([REPLAY], input=wire.read_bytes(), capture_output=True)
                self.assertEqual(stdin.returncode, 0, stdin.stderr)
                position = next(i for i, job in enumerate(self.jobs) if job == str(wire))
                self.assertEqual(lines[position] + b"\n", stdin.stdout)

    def test_output_follows_argument_order_not_finish_order(self):
        reversed_jobs = list(reversed(self.jobs))
        result = run(["--jobs", "6", *reversed_jobs])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"".join(reversed(self.single.stdout.splitlines(True))))

    def test_more_threads_than_scenarios(self):
        one = [str(self.wires[0])]
        self.assertSameAsSingle(run(["--jobs", "8", *one]), run(["--jobs", "1", *one]))

    def test_stress_many_scenarios_repeatedly(self):
        jobs = [str(self.wires[(i * 5 + i // 3) % len(self.wires)]) for i in range(1000)]
        expected = run(["--jobs", "1", *jobs])
        self.assertEqual(expected.returncode, 0, expected.stderr)
        self.assertEqual(len(expected.stdout.splitlines()), 1000)
        for threads in (4, 8):
            for repeat in range(2):
                with self.subTest(threads=threads, repeat=repeat):
                    self.assertSameAsSingle(run(["--jobs", str(threads), *jobs]), expected)

    def test_first_failing_argument_is_reported_and_nothing_printed(self):
        bad_header = self.dir / "bad-header.wire"
        bad_header.write_bytes(b"DESK_REPLAY_V1\nX\n")
        missing = self.dir / "missing.wire"
        jobs = list(self.jobs)
        jobs[37] = str(bad_header)
        jobs[150] = str(missing)
        for threads in (1, 6):
            with self.subTest(threads=threads):
                result = run(["--jobs", str(threads), *jobs])
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(
                    result.stderr,
                    f"replay: {bad_header}: expected S plus six hex bytes, or U\n".encode())

    def test_oversized_scenario_is_rejected(self):
        huge = self.dir / "huge.wire"
        huge.write_bytes(b"DESK_REPLAY_V1\n" + b"U\n" * 40000)
        result = run(["--jobs", "3", str(self.wires[0]), str(huge)])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"larger than 64 KiB", result.stderr)

    def test_bad_options_are_rejected(self):
        for args in (["--jobs", "0", str(self.wires[0])], ["--jobs", "65", str(self.wires[0])],
                     ["--jobs", "x", str(self.wires[0])], ["--jobs", "2"],
                     ["--jobs", "2", "--pbm", "x.pbm", str(self.wires[0])],
                     ["--jobs", str(self.wires[0])], ["--unknown", str(self.wires[0])]):
            with self.subTest(args=args):
                result = run(args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")

    def test_single_scenario_mode_still_accepts_stdin(self):
        result = subprocess.run([REPLAY], input=self.wires[1].read_bytes(), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'"uploaded":64', result.stdout)


if __name__ == "__main__":
    unittest.main()
