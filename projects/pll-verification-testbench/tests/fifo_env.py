"""Cycle scoreboard for the PLL sample queue, including non-power-of-two depths."""
from collections import deque
import os
import random

import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def randomized_queue(d):
    depth = int(os.environ['FIFO_DEPTH'])
    rng = random.Random(int(os.environ['TEST_SEED']))
    model, bins = deque(), set()
    writes = reads = 0

    async def cycle(push=0, pop=0, reset=0):
        nonlocal writes, reads
        d.clk.value = 0
        d.reset.value, d.push.value, d.pop.value = reset, push, pop
        value = rng.getrandbits(32)
        d.data_in.value = value
        await Timer(5, unit='ns')
        if reset:
            if model: bins.add('reset_nonempty')
            model.clear()
        else:
            if not model and pop: bins.add('empty_pop')
            if len(model) == depth and push and not pop: bins.add('full_reject')
            take = pop and bool(model)
            put = push and (len(model) < depth or take)
            if take:
                assert int(d.data_out.value) == model.popleft(), 'FIFO order mismatch'
                reads += 1
            if put:
                model.append(value)
                writes += 1
            if take and put: bins.add('simultaneous')
            if reads > depth and writes > depth: bins.add('wrap')
        d.clk.value = 1
        await Timer(5, unit='ns')
        assert int(d.count.value) == len(model)
        assert int(d.empty.value) == (len(model) == 0)
        assert int(d.full.value) == (len(model) == depth)
        assert int(d.data_out.value) == (model[0] if model else 0)
        if not model: bins.add('empty')
        if len(model) == depth: bins.add('full')

    await cycle(reset=1)
    await cycle(pop=1)
    for _ in range(depth): await cycle(push=1)
    await cycle(push=1)
    for _ in range(depth * 3): await cycle(push=1, pop=1)
    await cycle(reset=1)
    # Bias toward filling/draining in alternating windows; keep illegal requests
    # so rejected operations are checked too. Reset may interrupt queued data.
    for n in range(1500):
        fill = (n // 50) % 2 == 0
        await cycle(rng.random() < (0.8 if fill else 0.2),
                    rng.random() < (0.2 if fill else 0.8), rng.random() < 0.01)
    required = {'empty', 'full', 'empty_pop', 'full_reject', 'simultaneous', 'wrap', 'reset_nonempty'}
    assert required <= bins, f'missing bins: {required-bins}'
    print(f'FIFO_COVERAGE depth={depth} seed={os.environ["TEST_SEED"]} hit={len(required)} total={len(required)}')
