import unittest
from pathlib import Path

from backend.diversion_ingest import aggregate_daily_diversions
from backend.diversion_mapping import map_monthly_diversions
from backend.legacy_2024_diversion_mapping import LEGACY_2024_SOURCE_MAPPINGS
from backend.legacy_diversion_workbook import read_2024_flow_workbook
from backend.legacy_report_assets import (
    build_historical_ditch_inputs,
    read_2024_area_diversion_inputs,
    read_2024_metered_ditch_assets,
    validate_historical_requirement_overrides,
)
from backend.diversion_ledger import calculate_area_diversion_ledger


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
        cls.area_inputs = read_2024_area_diversion_inputs(
            SPREADSHEET_ROOT / "2024 Gila Report Data_WORKING.xlsx"
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

    def test_recalculates_2024_metered_ditch_requirements_and_assessed_shortages(self):
        assets_by_area = {}
        for asset in self.assets:
            assets_by_area.setdefault(asset.area_name, []).append(asset)
        for area_input in self.area_inputs:
            assets = assets_by_area.get(area_input.area_name, [])
            if not assets:
                continue
            ledger = calculate_area_diversion_ledger(
                area_input.area_name,
                efficiency=area_input.efficiency,
                monthly_cir_ft=area_input.monthly_report_cir_ft,
                monthly_pan_evap_ft=area_input.monthly_adjusted_pan_evap_ft,
                monthly_precip_ft=area_input.monthly_precip_ft,
                ditches=build_historical_ditch_inputs(assets),
            )
            assets_by_id = {asset.canonical_ditch_id: asset for asset in assets}
            for ditch in ledger.ditches:
                expected = assets_by_id[ditch.ditch_id]
                for month, (calculation, required, shortage, requirement_is_formula, reservoir_is_formula) in enumerate(zip(
                    ditch.monthly,
                    expected.monthly_diversion_required_acft,
                    expected.monthly_shortage_acft,
                    expected.requirement_formula_months,
                    expected.reservoir_net_evap_formula_months,
                ), 1):
                    if requirement_is_formula and reservoir_is_formula:
                        self.assertAlmostEqual(calculation.total_diversion_required_acft, required, places=8)
                    self.assertAlmostEqual(calculation.diversion_shortage_acft, shortage, delta=0.03)

    def test_standard_formula_corrects_the_three_legacy_constants_without_creating_shortage(self):
        area = next(value for value in self.area_inputs if value.area_name == "LUNA")
        assets = [asset for asset in self.assets if asset.area_name == "LUNA"]
        ledger = calculate_area_diversion_ledger(
            "LUNA",
            efficiency=area.efficiency,
            monthly_cir_ft=area.monthly_report_cir_ft,
            monthly_pan_evap_ft=area.monthly_adjusted_pan_evap_ft,
            monthly_precip_ft=area.monthly_precip_ft,
            ditches=build_historical_ditch_inputs(assets),
        )
        by_id = {ditch.ditch_id: ditch for ditch in ledger.ditches}
        leslie_march = by_id["luna_leslie_laney"].monthly[2]
        self.assertAlmostEqual(leslie_march.reservoir_net_evap_acft, 0.0095, places=8)
        self.assertAlmostEqual(leslie_march.total_diversion_required_acft, 0.03166666666666667, places=8)
        self.assertEqual(leslie_march.diversion_shortage_acft, 0.0)
        a_laney_march = by_id["luna_a_laney"].monthly[2]
        self.assertEqual(a_laney_march.reservoir_net_evap_acft, 0.0)
        self.assertEqual(a_laney_march.crop_diversion_required_acft, 0.0)
        self.assertEqual(a_laney_march.total_diversion_required_acft, 0.0)
        self.assertEqual(a_laney_march.diversion_shortage_acft, 0.0)

    def test_flags_one_nonzero_legacy_requirement_override_for_policy_review(self):
        issues = [issue for issue in validate_historical_requirement_overrides(self.assets) if issue.severity == "error"]
        self.assertEqual(
            [(issue.ditch_id, issue.month) for issue in issues],
            [("luna_a_laney", 3)],
        )


if __name__ == "__main__":
    unittest.main()
