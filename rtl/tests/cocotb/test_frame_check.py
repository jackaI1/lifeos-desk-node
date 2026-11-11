"""cocotb testbench: replay the desk-node scenarios and random frames through the RTL.

Each transfer is driven one byte per clock with optional idle cycles in between.
A monitor records every frame event the RTL reports. The events must match the
Python reference in order, the good-frame words must equal the sensor words, and
the saturating counters must match the counts. Coverage counters for good, bad
(temperature, humidity and both), and truncated transfers are checked to be non-zero.
"""
import os
import random
from collections import Counter
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge

import sht31_ref

WIRE_DIR = Path(os.environ.get('WIRE_DIR', 'build/wire'))
SCENARIOS = ['outage', 'clean', 'corrupt', 'mixed-corruption']
RANDOM_TRANSFERS = 3000


async def reset(dut):
    dut.rst_n.value = 0
    dut.in_valid.value = 0
    dut.in_data.value = 0
    dut.in_last.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def monitor(dut, events):
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(dut.frame_valid.value):
            events.append(sht31_ref.Expected(
                truncated=bool(int(dut.frame_truncated.value)),
                good=bool(int(dut.frame_good.value)),
                bad=bool(int(dut.frame_bad.value)),
                temp_ok=None, hum_ok=None,
                temp_raw=int(dut.temp_raw.value), hum_raw=int(dut.hum_raw.value)))


async def drive(dut, rng, transfers, gap_rate):
    for payload in transfers:
        for index, byte in enumerate(payload):
            while rng.random() < gap_rate:
                dut.in_valid.value = 0
                await RisingEdge(dut.clk)
            dut.in_valid.value = 1
            dut.in_data.value = byte
            dut.in_last.value = 1 if index == len(payload) - 1 else 0
            await RisingEdge(dut.clk)
        dut.in_valid.value = 0
        dut.in_last.value = 0
        await RisingEdge(dut.clk)
    for _ in range(4):
        await RisingEdge(dut.clk)


def coverage_of(expectations):
    bins = Counter()
    for item in expectations:
        if item.truncated:
            bins['truncated'] += 1
        elif item.good:
            bins['good'] += 1
        elif not item.temp_ok and not item.hum_ok:
            bins['bad_both'] += 1
        elif not item.temp_ok:
            bins['bad_temp'] += 1
        else:
            bins['bad_hum'] += 1
    return bins


async def run_and_check(dut, transfers, gap_rate, seed):
    rng = random.Random(seed)
    events = []
    watcher = cocotb.start_soon(monitor(dut, events))
    await drive(dut, rng, transfers, gap_rate)
    watcher.cancel()
    expected = [sht31_ref.classify(payload) for payload in transfers]
    assert len(events) == len(expected), f'{len(events)} events for {len(expected)} transfers'
    for index, (got, want) in enumerate(zip(events, expected)):
        assert (got.truncated, got.good, got.bad) == (want.truncated, want.good, want.bad), \
            f'transfer {index}: got {got}, want {want} for {transfers[index].hex()}'
        if want.good:
            assert (got.temp_raw, got.hum_raw) == (want.temp_raw, want.hum_raw), f'transfer {index} words'
    counts = Counter()
    for item in expected:
        counts['truncated' if item.truncated else 'good' if item.good else 'bad'] += 1
    assert int(dut.good_count.value) == counts['good']
    assert int(dut.bad_count.value) == counts['bad']
    assert int(dut.truncated_count.value) == counts['truncated']
    bad_temp = sum(1 for i in expected if not i.truncated and not i.good and not i.temp_ok)
    bad_hum = sum(1 for i in expected if not i.truncated and not i.good and not i.hum_ok)
    assert int(dut.bad_temp_count.value) == bad_temp
    assert int(dut.bad_hum_count.value) == bad_hum
    return coverage_of(expected)


@cocotb.test()
async def replayed_scenarios(dut):
    """Every frame in the replay scenarios, including the deliberately corrupted checksums."""
    cocotb.start_soon(Clock(dut.clk, 10, unit='ns').start())
    await reset(dut)
    coverage = Counter()
    for name in SCENARIOS:
        frames = sht31_ref.wire_frames(WIRE_DIR / f'{name}.wire')
        transfers = [bytes(frame) for frame in frames]
        await reset(dut)
        coverage.update(await run_and_check(dut, transfers, gap_rate=0.0, seed=1))
    dut._log.info(f'replayed scenario coverage: {dict(coverage)}')
    assert coverage['good'] > 0 and coverage['bad_temp'] > 0


@cocotb.test()
async def random_frames_with_gaps_and_truncation(dut):
    """Random good, corrupted and truncated transfers with idle cycles between bytes."""
    cocotb.start_soon(Clock(dut.clk, 10, unit='ns').start())
    await reset(dut)
    rng = random.Random(2026)
    transfers = sht31_ref.random_transfers(rng, RANDOM_TRANSFERS)
    coverage = await run_and_check(dut, transfers, gap_rate=0.2, seed=7)
    dut._log.info(f'random coverage: {dict(coverage)}')
    for bin_name in ['good', 'bad_temp', 'bad_hum', 'bad_both', 'truncated']:
        assert coverage[bin_name] > 0, f'coverage bin {bin_name} never hit'
