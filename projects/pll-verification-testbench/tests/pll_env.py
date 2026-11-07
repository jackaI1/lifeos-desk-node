import random

import cocotb
from cocotb.triggers import Timer
from pyuvm import uvm_component, uvm_test, test


class Reference:
    def __init__(self):
        self.count = 0
        self.control = 8
        self.stable = 0
        self.locked = 0

    def step(self, reset, ref, ratio):
        if reset:
            self.__init__()
            return (0, 0, 0, 0, 8)
        tick = self.count == max(2, ratio) - 1
        self.count = 0 if tick else self.count + 1
        up, down = int(ref and not tick), int(tick and not ref)
        self.control = min(15, self.control + up) if up else max(0, self.control - down)
        if ref and tick:
            self.stable = min(4, self.stable + 1)
            if self.stable == 4:
                self.locked = 1
        elif ref or tick:
            self.stable = 0
            self.locked = 0
        return (int(tick), up, down, self.locked, self.control)


class Scoreboard(uvm_component):
    def build_phase(self):
        self.model = Reference()
        self.bins = set()

    def check(self, stimulus, actual):
        reset, ref, ratio = stimulus
        expected = self.model.step(reset, ref, ratio)
        assert actual == expected, f'divider/control mismatch: input={stimulus} expected={expected} actual={actual}'
        if not reset:
            self.bins.add(('ratio', ratio))
            self.bins.add(('phase', actual[1], actual[2]))
            if actual[3]: self.bins.add(('locked',))


class Monitor(uvm_component):
    def sample(self, dut, stimulus):
        actual = tuple(int(getattr(dut, name).value) for name in ('feedback', 'up', 'down', 'locked', 'control'))
        self.parent.scoreboard.check(stimulus, actual)


class Driver(uvm_component):
    async def cycle(self, reset, ref, ratio):
        d = cocotb.top
        d.clk.value = 0
        d.reset.value, d.ref_pulse.value, d.ratio.value = reset, ref, ratio
        await Timer(5, unit='ns')
        d.clk.value = 1
        await Timer(5, unit='ns')
        self.parent.monitor.sample(d, (reset, ref, ratio))


@test()
class PLLTest(uvm_test):
    def build_phase(self):
        self.scoreboard = Scoreboard('scoreboard', self)
        self.monitor = Monitor('monitor', self)
        self.driver = Driver('driver', self)

    async def run_phase(self):
        self.raise_objection()
        rng = random.Random(20261106)
        # Reset for every ratio so changing it cannot strand the divider counter.
        for ratio in range(2, 9):
            await self.driver.cycle(1, 0, ratio)
            # Aligned pulses must acquire lock after four coincident edges.
            for cycle in range(ratio * 5):
                await self.driver.cycle(0, int(cycle % ratio == ratio - 1), ratio)
            assert int(cocotb.top.locked.value) == 1, 'lock did not acquire'
            # A mismatched phase must immediately drop lock.
            await self.driver.cycle(0, 1, ratio)
            assert int(cocotb.top.locked.value) == 0, 'lock did not drop'
            for _ in range(120):
                await self.driver.cycle(0, int(rng.random() < 0.3), ratio)
        required = {('ratio', r) for r in range(2, 9)} | {('phase', 0, 0), ('phase', 1, 0), ('phase', 0, 1), ('locked',)}
        assert required <= self.scoreboard.bins, f'missing coverage: {required - self.scoreboard.bins}'
        self.logger.info('Coverage: %d/%d required bins', len(required), len(required))
        self.drop_objection()
