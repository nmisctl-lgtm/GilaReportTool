import unittest
from pathlib import Path

from backend.diversion_ingest import aggregate_daily_diversions
from backend.diversion_mapping import map_monthly_diversions
from backend.legacy_2024_diversion_mapping import LEGACY_2024_SOURCE_MAPPINGS
from backend.legacy_diversion_workbook import read_2024_flow_workbook
from backend.legacy_report_assets import read_2024_metered_ditch_assets


SPREADSHEET_ROOT = Path(__file__).resolve().parents[1] / "OldMethod_Report/Spreadsheet"


class Legacy2024DiversionMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        aggregation = aggregate_daily_diversions(
            read_2024_flow_workbook(SPREADSHEET_ROOT / "2024 Ditch Diversions_FINAL.xlsx"),
            year=2024,
        )
        cls.mapping_result = map_monthly_diversions(aggregation.monthly, LEGACY_2024_SOURCE_MAPPINGS)
        cls.assets = read_2024_metered_ditch_assets(
            SPREADSHEET_ROOT / "2024 Gila Report Data_WORKING.xlsx",
            LEGACY_2024_SOURCE_MAPPINGS,
        )

    def test_every_2024_flow_channel_has_an_explicit_disposition(self):
        error_codes = {issue.code for issue in self.mapping_result.issues if issue.severity == "error"}
        self.assertEqual(error_codes, set())
        self.assertEqual(len(self.mapping_result.mapped_monthly), 21 * 12)

    def test_w_s_laney_and_w_s_are_different_canonical_ditches(self):
        annual_by_canonical = {}
        for row in self.mapping_result.mapped_monthly:
            annual_by_canonical[row.canonical_ditch_id] = annual_by_canonical.get(row.canonical_ditch_id, 0.0) + row.acre_feet
        self.assertAlmostEqual(annual_by_canonical["luna_william_s_laney"], 640.74808309, places=5)
        self.assertAlmostEqual(annual_by_canonical["glenwood_ws_gsf39_supplement"], 1771.09391675, places=5)
        self.assertNotEqual(
            annual_by_canonical["luna_william_s_laney"],
            annual_by_canonical["glenwood_ws_gsf39_supplement"],
        )

    def test_mapped_monthly_values_and_report_assets_reproduce_each_2024_metered_block(self):
        by_canonical = {}
        for row in self.mapping_result.mapped_monthly:
            by_canonical.setdefault(row.canonical_ditch_id, []).append(row.acre_feet)
        self.assertEqual(len(self.assets), 21)
        for asset in self.assets:
            for mapped_value, workbook_value in zip(
                by_canonical[asset.canonical_ditch_id], asset.monthly_diversion_acft
            ):
                self.assertAlmostEqual(mapped_value, workbook_value, places=7)
            self.assertGreaterEqual(asset.crop_acres, 0)
            self.assertGreaterEqual(asset.reservoir_acres, 0)


if __name__ == "__main__":
    unittest.main()
