"""Cross-checks: the Python reference, the replay tool, the CRC block and the buffer self-test.

These tests need the replay tool (built from ../replay) and the simulation outputs
written by `make test-crc` and `make test-dft`.
"""
import json
import random
import re
import subprocess
from pathlib import Path

import pytest

import sht31_ref

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
REPLAY_BIN = ROOT.parent / 'replay' / 'build' / 'desk-replay'
WIRES = sorted((BUILD / 'wire').glob('*.wire'))


@pytest.fixture(scope='session')
def replay_bin():
    if not REPLAY_BIN.exists():
        subprocess.run(['make', '-C', str(ROOT.parent / 'replay')], check=True, capture_output=True)
    return REPLAY_BIN


def test_reference_matches_the_sht31_datasheet_example():
    assert sht31_ref.crc8(bytes([0xBE, 0xEF])) == 0x92


def test_reference_classifies_the_scheme_vectors():
    good = sht31_ref.classify(bytes.fromhex('6666938000a2'))
    corrupt = sht31_ref.classify(bytes.fromhex('6666928000a2'))
    assert good.good and not corrupt.good
    assert not corrupt.temp_ok and corrupt.hum_ok
    assert (good.temp_raw, good.hum_raw) == (0x6666, 0x8000)


def test_random_transfers_are_classified_consistently():
    rng = random.Random(1)
    for payload in sht31_ref.random_transfers(rng, 500):
        expected = sht31_ref.classify(payload)
        assert expected.truncated == (len(payload) < 6)
        assert expected.good != expected.bad or expected.truncated


@pytest.mark.parametrize('wire', WIRES, ids=lambda p: p.stem)
def test_replay_tool_counts_the_same_bad_frames(replay_bin, wire):
    result = subprocess.run([str(replay_bin), str(wire)], capture_output=True, text=True, check=True)
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    bad = sum(1 for frame in sht31_ref.wire_frames(wire) if not sht31_ref.classify(bytes(frame)).good)
    assert summary['faults'] == bad


def test_crc_block_agrees_with_replay_on_every_frame(replay_bin):
    log = BUILD / 'crc8_word_stream_tb.log'
    if not log.exists():
        pytest.skip('run make test-crc first')
    frame_words = {}
    for line in log.read_text().splitlines():
        match = re.fullmatch(r'W (\d+) (\d+) ([01])', line)
        if match:
            frame, _, ok = map(int, match.groups())
            frame_words.setdefault(frame, []).append(ok)
    wire_frames = sum(len(sht31_ref.wire_frames(w)) for w in WIRES)
    rtl_bad = sum(1 for index in range(wire_frames) if not all(frame_words[index]))
    replay_bad = 0
    for wire in WIRES:
        result = subprocess.run([str(replay_bin), str(wire)], capture_output=True, text=True, check=True)
        replay_bad += json.loads(result.stdout.strip().splitlines()[-1])['faults']
    assert rtl_bad == replay_bad
    assert rtl_bad > 0, 'the scenarios must include corrupted checksums'


def test_dft_report_shows_full_coverage():
    report = BUILD / 'dft_report.txt'
    if not report.exists():
        pytest.skip('run make test-dft first')
    text = report.read_text()
    assert 'RESULT PASS failures=0' in text
    assert 'memory stuck-at: detected 512/512 (100.00%)' in text
    assert 'scan chain stuck-at: detected 22/22 (100.00%)' in text
