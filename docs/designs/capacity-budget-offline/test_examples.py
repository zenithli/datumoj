"""Pin public scenario arithmetic independently of the implementation helpers."""

import unittest

from examples import scenarios


class ExampleTests(unittest.TestCase):
    def test_small_example_cannot_credit_cleanup_before_peak(self):
        row = scenarios()["small_hand_calculation"]["projection"]["rounds"][0]
        self.assertEqual(
            (row["before_write_bytes"], row["write_peak_bytes"], row["after_cleanup_bytes"]),
            (90, 120, 80),
        )
        self.assertTrue(row["thresholds"]["cap"]["reached"])

    def test_bucket_scenario_remembers_peak_and_counts_cleanup_once(self):
        result = scenarios()["reported_bucket_with_hypothetical_events"]["projection"]
        first, second = result["rounds"]
        self.assertEqual(
            (first["before_write_bytes"], first["write_peak_bytes"], first["after_cleanup_bytes"]),
            (8_800_774_448, 9_050_774_448, 8_450_774_448),
        )
        self.assertEqual(first["thresholds"]["stop_9gb"]["peak_headroom_bytes"], -50_774_448)
        self.assertEqual(second["write_peak_bytes"], 8_500_000_000)
        self.assertEqual(second["after_cleanup_bytes"], 8_500_000_000)
        self.assertEqual(second["unique_cleanup_bytes"], 0)
        self.assertTrue(second["thresholds"]["freeze_8_5gb"]["reached"])
        self.assertFalse(second["thresholds"]["freeze_8_5gb"]["exceeded"])
        self.assertEqual(result["projected_high_water_bytes"], 9_050_774_448)


if __name__ == "__main__":
    unittest.main()
