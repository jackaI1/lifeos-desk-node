import math
import unittest
from automation.control import Reading, Thermostat
from automation.sources import SimulatedRoom


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.model = Thermostat()

    def feed(self, temp, **kwargs):
        self.model.update(Reading(temp, kwargs.get('humidity', 45), kwargs.get('timestamp', 1000)),
                          kwargs.get('now', 1000))

    def test_hysteresis_both_directions_and_boundaries(self):
        for temp, heat in [(22, False), (21.5, True), (22, True), (22.49, True),
                           (22.5, False), (22, False), (21.51, False), (21.5, True)]:
            with self.subTest(temp=temp, expected=heat):
                self.feed(temp)
                self.assertEqual((self.model.heat, self.model.fan, self.model.fault), (heat, heat, False))

    def test_setpoint_and_deadband_change(self):
        self.model.configure(setpoint=25, deadband=2)
        self.feed(24)
        self.assertTrue(self.model.heat)
        self.feed(26)
        self.assertFalse(self.model.heat)

    def test_invalid_settings_are_atomic(self):
        for value in [math.nan, math.inf, -1, 0, 31, True]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.model.configure(setpoint=value)
                self.assertEqual(self.model.setpoint, 22)
        with self.assertRaises(ValueError):
            self.model.configure(setpoint=25, deadband=0.1)
        self.assertEqual((self.model.setpoint, self.model.deadband), (22, 1))

    def test_missing_input_is_off(self):
        self.feed(20)
        self.model.update(None, 1000)
        self.assertEqual((self.model.heat, self.model.fan, self.model.fault), (False, False, True))

    def test_freshness_boundary_and_recovery(self):
        self.feed(20, now=1900)
        self.assertTrue(self.model.heat)
        self.feed(20, now=1900.001)
        self.assertEqual((self.model.heat, self.model.fan, self.model.fault), (False, False, True))
        self.feed(20, now=1901, timestamp=1901)
        self.assertTrue(self.model.heat)
        self.assertFalse(self.model.fault)

    def test_future_and_unknown_time_are_faults(self):
        for stamp in [0, -1, 1001, math.nan, math.inf]:
            with self.subTest(stamp=stamp):
                self.feed(20, timestamp=stamp)
                self.assertTrue(self.model.fault)
                self.assertFalse(self.model.heat)

    def test_invalid_sensor_cannot_heat(self):
        for temp, humidity in [(math.nan, 45), (math.inf, 45), (-46, 45), (126, 45),
                               (20, math.nan), (20, -1), (20, 101)]:
            with self.subTest(temp=temp, humidity=humidity):
                self.feed(temp, humidity=humidity)
                self.assertTrue(self.model.fault)
                self.assertFalse(self.model.heat)
                self.assertEqual(self.model.registers()[:2], [0, 0])

    def test_register_scaling_negative_and_age_saturation(self):
        self.feed(-5.25, humidity=67.25)
        self.assertEqual(self.model.registers()[:2], [65011, 6725])
        self.feed(20, now=100000)
        self.assertEqual(self.model.registers()[-1], 65535)

    def test_simulated_room_closes_loop_repeatedly(self):
        room = SimulatedRoom()
        transitions = []
        last = False
        for i in range(300):
            now = 1000 + i * 0.5
            self.model.update(room.sample(now, self.model.heat), now)
            if self.model.heat != last:
                transitions.append(self.model.heat)
                last = self.model.heat
        self.assertGreaterEqual(len(transitions), 5)
        self.assertTrue(all(a != b for a, b in zip(transitions, transitions[1:])))
        self.assertTrue(21 <= room.temperature <= 23)
