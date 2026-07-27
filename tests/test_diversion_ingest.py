import unittest
from datetime import date

from backend.diversion_ingest import CFS_DAY_TO_ACRE_FEET, DailyDiversionRecord, aggregate_daily_diversions


class DiversionIngestTests(unittest.TestCase):
    def test_aggregates_observed_cfs_days_to_acre_feet_and_flags_missing_days(self):
        aggregation = aggregate_daily_diversions((
            DailyDiversionRecord("ditch", date(2024, 1, 1), 1.0),
            DailyDiversionRecord("ditch", date(2024, 1, 2), 0.0),
        ), year=2024)
        january = aggregation.monthly[0]
        self.assertEqual(january.observed_days, 2)
        self.assertEqual(january.calendar_days, 31)
        self.assertEqual(january.acre_feet, CFS_DAY_TO_ACRE_FEET)
        self.assertIn("incomplete_daily_coverage", {issue.code for issue in aggregation.issues})

    def test_rejects_duplicate_and_negative_daily_values(self):
        aggregation = aggregate_daily_diversions((
            DailyDiversionRecord("ditch", date(2024, 1, 1), 1.0),
            DailyDiversionRecord("ditch", date(2024, 1, 1), 2.0),
            DailyDiversionRecord("ditch", date(2024, 1, 2), -1.0),
        ), year=2024)
        codes = {issue.code for issue in aggregation.issues}
        self.assertIn("duplicate_daily_record", codes)
        self.assertIn("invalid_daily_cfs", codes)


if __name__ == "__main__":
    unittest.main()
