"""Exercise real Scheme and sanitizer-built C processes, without network or hardware."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
REPLAY = os.environ.get("DESK_REPLAY_BIN", str(ROOT / "replay/build/desk-replay"))


def compile_plan(text):
    return subprocess.run(
        ["guile", "--no-auto-compile", "-L", str(ROOT / "replay/scheme"),
         str(ROOT / "replay/compile.scm")], input=text, text=True, capture_output=True)


def replay(data, *args):
    return subprocess.run([REPLAY, *args], input=data, capture_output=True)


class ReplayTests(unittest.TestCase):
    def run_scenario(self, text, *args):
        compiled = compile_plan(text)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        result = replay(compiled.stdout.encode(), *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_known_sensor_round_trip(self):
        result = self.run_scenario("(scenario (sample 25000 50000))")
        self.assertEqual(result, dict(samples=1, faults=0, uploaded=0, queued=1,
                                     dropped=0, oldest=1, newest=1,
                                     temperature_mc=25000, humidity_mpermil=50001))

    def test_outage_overflow_and_recovery(self):
        result = self.run_scenario("(scenario (repeat 70 (sample 25000 50000)) (upload))")
        self.assertEqual([result[k] for k in ("samples", "uploaded", "queued", "dropped")],
                         [70, 64, 0, 6])
        self.assertEqual((result["oldest"], result["newest"]), (0, 0))

    def test_fifo_keeps_latest_64(self):
        result = self.run_scenario("(scenario (repeat 70 (sample 0 0)))")
        self.assertEqual((result["oldest"], result["newest"], result["dropped"]), (7, 70, 6))

    def test_fault_is_not_queued_or_invented(self):
        result = self.run_scenario("(scenario (sample 25000 50000) (fault 25000 50000))")
        self.assertEqual((result["samples"], result["faults"], result["queued"]), (1, 1, 1))
        self.assertIsNone(result["temperature_mc"])
        self.assertIsNone(result["humidity_mpermil"])

    def test_uploads_and_faults_preserve_sequence(self):
        result = self.run_scenario("""(scenario (upload) (sample 25000 50000)
                                  (upload) (fault 0 0) (sample -45000 100000))""")
        self.assertEqual((result["uploaded"], result["oldest"], result["newest"]), (1, 2, 2))
        self.assertEqual(result["temperature_mc"], -45000)
        self.assertEqual(result["humidity_mpermil"], 100000)

    def test_bounded_maximum_scenario(self):
        result = self.run_scenario("(scenario (repeat 4096 (sample 25000 50000)))")
        self.assertEqual((result["samples"], result["queued"], result["dropped"]), (4096, 64, 4032))

    def test_bitmap_uses_oled_page_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "screen.pbm"
            self.run_scenario("(scenario (sample 25000 50000))", "--pbm", str(image))
            tokens = image.read_text().split()
            self.assertEqual(tokens[:3], ["P1", "128", "64"])
            pixels = list(map(int, tokens[3:]))
            self.assertEqual(len(pixels), 8192)
            self.assertEqual(set(pixels), {0, 1})
            # First glyph is L in LIFEOS OFFLINE: columns 7f,40,40,40,40.
            self.assertEqual(pixels[:6], [1, 0, 0, 0, 0, 0])
            self.assertEqual(pixels[6 * 128:6 * 128 + 6], [1, 1, 1, 1, 1, 0])

    def test_invalid_wire_streams(self):
        for data in (b"", b"wrong\nU\n", b"DESK_REPLAY_V1\n", b"DESK_REPLAY_V1\nX\n",
                     b"DESK_REPLAY_V1\nS 6666938000ag\n", b"DESK_REPLAY_V1\nS 6666938000a\n",
                     b"DESK_REPLAY_V1\nU trailing\n", b"DESK_REPLAY_V1\nU\x00evil\n",
                     b"DESK_REPLAY_V1\n" + b"x" * 100 + b"\n",
                     b"DESK_REPLAY_V1\n" + b"U\n" * 4097):
            with self.subTest(data=data[:40]):
                result = replay(data)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"replay:", result.stderr)
                self.assertEqual(result.stdout, b"")

    def test_compiler_rejects_bad_data_without_partial_output(self):
        for text in ("", "(scenario (upload)) (scenario (upload))", "(scenario (sample 0 100001))",
                     "(scenario (upload) (repeat 4097 (upload)))", "(scenario (system \"false\"))",
                     "(scenario", " " * 65537):
            with self.subTest(text=text[:70]):
                result = compile_plan(text)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("scenario:", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_output_failure_is_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = replay(b"DESK_REPLAY_V1\nU\n", "--pbm", tmp)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")

    def test_compiler_output_failure_is_nonzero(self):
        with open(os.devnull, "rb") as closed_output:
            result = subprocess.run(
                ["guile", "--no-auto-compile", "-L", str(ROOT / "replay/scheme"),
                 str(ROOT / "replay/compile.scm")],
                input=b"(scenario (upload))", stdout=closed_output, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"scenario:", result.stderr)

    def test_unknown_option_is_rejected(self):
        self.assertNotEqual(replay(b"DESK_REPLAY_V1\nU\n", "--unknown").returncode, 0)


if __name__ == "__main__":
    unittest.main()
