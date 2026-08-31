"""
IFS feed step computation: pure-function tests for the step list a feed
derives from its inclusive day range and cadence. No Django, no network.
"""

import unittest

from georiva_source_ecmwf.steps import ifs_steps, six_hourly_steps


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


class IFSStepsTest(unittest.TestCase):
    def test_six_hourly_interval_matches_six_hourly_steps(self):
        self.assertEqual(ifs_steps(0, 2, 6), six_hourly_steps(0, 2))
        self.assertEqual(ifs_steps(0, 15, 6), six_hourly_steps(0, 15))

    def test_three_hourly_within_first_144h(self):
        self.assertEqual(
            ifs_steps(0, 0, 3),
            [0, 3, 6, 9, 12, 15, 18, 21],
        )
        self.assertEqual(
            ifs_steps(5, 5, 3),
            [120, 123, 126, 129, 132, 135, 138, 141],
        )

    def test_transition_day_drops_to_six_hourly_after_144h(self):
        # Day 6 spans the 144h boundary: 144 is the last 3-hourly step,
        # then only 6-hourly steps (150, 156, 162) — no 147h.
        self.assertEqual(ifs_steps(6, 6, 3), [144, 150, 156, 162])

    def test_three_hourly_feed_continues_six_hourly_beyond_144h(self):
        self.assertEqual(ifs_steps(7, 7, 3), [168, 174, 180, 186])

    def test_three_hourly_steps_are_clamped_at_360h(self):
        self.assertEqual(ifs_steps(15, 15, 3), [360])

    def test_full_three_hourly_range(self):
        steps = ifs_steps(0, 15, 3)
        # 0..144 every 3h (49 steps) + 150..360 every 6h (36 steps)
        self.assertEqual(len(steps), 85)
        self.assertEqual(steps[0], 0)
        self.assertEqual(steps[-1], 360)
        self.assertTrue(all(s % 3 == 0 for s in steps if s <= 144))
        self.assertTrue(all(s % 6 == 0 for s in steps if s > 144))
        self.assertNotIn(147, steps)
        self.assertIn(144, steps)
        self.assertIn(150, steps)


if __name__ == "__main__":
    unittest.main()
