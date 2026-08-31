"""
IFS feed step computation: pure-function tests for the 6-hourly step
list a feed derives from its inclusive day range. No Django, no network.
"""

import unittest

from georiva_source_ecmwf.steps import six_hourly_steps


class SixHourlyStepsTest(unittest.TestCase):
    def test_day_range_expands_to_six_hourly_steps(self):
        self.assertEqual(
            six_hourly_steps(0, 2),
            [0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66],
        )

    def test_single_day_range(self):
        self.assertEqual(six_hourly_steps(3, 3), [72, 78, 84, 90])

    def test_steps_beyond_360h_are_clamped(self):
        self.assertEqual(six_hourly_steps(15, 15), [360])

    def test_full_range_ends_at_360(self):
        steps = six_hourly_steps(0, 15)
        self.assertEqual(steps[0], 0)
        self.assertEqual(steps[-1], 360)
        self.assertEqual(len(steps), 61)
        self.assertTrue(all(s % 6 == 0 for s in steps))


if __name__ == "__main__":
    unittest.main()
