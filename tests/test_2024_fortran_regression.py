"""End-to-end 2024 regression fixtures for the legacy xirrigcu replacement."""

from pathlib import Path
import unittest

from backend.cir_runner import compare_to_legacy, read_cropcu_output, run_all_areas
from backend.legacy_dat import read_legacy_inputs


REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_ROOT = REPO_ROOT / "OldMethod_Report/Fortran_FINAL_2024/Inputs_FINAL"


class Legacy2024RegressionTests(unittest.TestCase):
    """Parse real DAT inputs, compute CIRs, then check every printed monthly value."""

    def _differences(self, method: str, control_name: str, output_name: str, tolerance: float):
        inputs = read_legacy_inputs(INPUT_ROOT / control_name)
        actual = run_all_areas(inputs, 2024, method)
        expected = read_cropcu_output(INPUT_ROOT / output_name)
        return inputs, compare_to_legacy(actual, expected, tolerance)

    def test_parses_complete_2024_dat_inputs(self):
        inputs = read_legacy_inputs(INPUT_ROOT / "Gila'24obc-usbrControl.DAT")
        self.assertEqual(len(inputs.crops), 29)
        self.assertEqual(len(inputs.areas), 9)
        self.assertEqual(len(inputs.weather), 9)
        self.assertEqual(len(inputs.date_limits), 2217)
        self.assertEqual(len(inputs.daylight_by_latitude), 26)

    def test_obc_usbr_matches_every_2024_reported_monthly_cir(self):
        _, differences = self._differences(
            "obc_usbr",
            "Gila'24obc-usbrControl.DAT",
            "Anuual 2024/gila'24obc-usbr_cropcu.out",
            0.011,
        )
        self.assertEqual(differences, ())

    def test_mbc_scs_matches_with_two_documented_legacy_temperature_rounding_deltas(self):
        _, differences = self._differences(
            "mbc_scs",
            "Gila'24mbc-scsControl.DAT",
            "Anuual 2024/gila'24mbc-scs_cropcu.out",
            0.011,
        )
        self.assertEqual(
            {(item.area_name, item.crop_id, item.month) for item in differences},
            {("CLIFF-GILA", "8", 9), ("REDROCK", "8", 9)},
        )

        # The archived MBC output prints September temperatures 0.1 F lower
        # than its paired Weather DAT for these two areas.  The resulting
        # monthly CIR discrepancy is 0.012 in, so it remains inside the
        # documented 0.015-in legacy-report comparison tolerance.
        _, report_tolerance_differences = self._differences(
            "mbc_scs",
            "Gila'24mbc-scsControl.DAT",
            "Anuual 2024/gila'24mbc-scs_cropcu.out",
            0.015,
        )
        self.assertEqual(report_tolerance_differences, ())


if __name__ == "__main__":
    unittest.main()
