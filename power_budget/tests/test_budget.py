import unittest
from power_budget.__main__ import estimate


class BudgetTest(unittest.TestCase):
    def test_weighted_current(self):
        result = estimate(10, 300, 112, 3, 2)
        self.assertAlmostEqual(result['ESP32'], (10 * 112 + 300 * 0.010) / 310)
        self.assertAlmostEqual(sum(result.values()), 11.922780645161291)

    def test_zero_awake(self):
        self.assertEqual(estimate(0, 300, 112, 0, 3.3)['ESP32'], 0.010)

    def test_rejects_invalid_inputs(self):
        for args in [(-1, 300, 112, 0, 2), (1, 0, 112, 0, 2), (1, 300, float('nan'), 0, 2), (1, 300, 112, 0, 4)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                estimate(*args)


if __name__ == '__main__':
    unittest.main()
