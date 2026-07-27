import unittest
from pathlib import Path

from backend.cir_bridge import build_cir_bridges
from backend.cir_runner import run_all_areas
from backend.diversion_ledger import (
    DitchInput,
    calculate_area_diversion_ledger,
    validate_ledger_inputs,
)
from backend.legacy_dat import read_legacy_inputs


INPUT_ROOT = Path(__file__).resolve().parents[1] / "OldMethod_Report/Fortran_FINAL_2024/Inputs_FINAL"

# Captured from the visible CIR bridge rows in the 2024 working workbook.
# These values are intentionally rounded to the workbook's 0.01-inch storage.
WORKBOOK_CIR_BRIDGE = {
    "LUNA": (16.67, (0, 0, 0, 0.56, 2.6, 4.38, 2.33, 2.96, 2.92, 1.57, 0, 0)),
    "APACHE-ARAGON": (18.11, (0, 0, 0, 1.16, 2.96, 4.56, 3.36, 3.63, 3.1, 1.65, 0.02, 0)),
    "RESERVE": (19.76, (0, 0, 0, 1.78, 3.31, 5.05, 3.63, 4.51, 3.06, 1.8, 0.11, 0)),
    "GLENWOOD": (27.01, (0, 0, 0.2, 2.55, 4.31, 5.76, 4.55, 5.42, 3.44, 2.72, 0.75, 0.03)),
    "UPPER GILA": (21.84, (0, 0, 0.4, 2.1, 3.66, 4.16, 4.04, 3.67, 3.49, 2.22, 0.29, 0)),
    "CLIFF-GILA": (27.34, (0, 0, 0.63, 2.75, 4.68, 6.13, 4.65, 5.75, 4.01, 2.66, 0.47, 0)),
    "REDROCK": (34.82, (0, 0.01, 1.41, 3, 4.93, 6.88, 6.37, 6.2, 4.77, 3.21, 0.94, 0.58)),
    "VIRDEN VALLEY": (33.94, (0, 0.03, 0.89, 2.2, 4.3, 6.61, 7.66, 7.15, 5.11, 3.06, 0.66, 0.41)),
    "SAN SIMON": (37.43, (0.03, 0.28, 1.42, 3.16, 5.29, 7.48, 7.71, 6.89, 5.11, 3.56, 1.01, 0.72)),
}


class CIRBridgeTests(unittest.TestCase):
    def test_reproduces_all_2024_workbook_cir_bridge_inputs(self):
        inputs = read_legacy_inputs(INPUT_ROOT / "Gila'24obc-usbrControl.DAT")
        bridges = build_cir_bridges(
            run_all_areas(inputs, 2024, "obc_usbr"),
            run_all_areas(inputs, 2024, "mbc_scs"),
        )
        self.assertEqual({bridge.area_name for bridge in bridges}, set(WORKBOOK_CIR_BRIDGE))
        for bridge in bridges:
            workbook_annual, workbook_monthly = WORKBOOK_CIR_BRIDGE[bridge.area_name]
            self.assertAlmostEqual(bridge.obc_annual_wcir_in, workbook_annual, delta=0.005)
            for actual, expected in zip(bridge.mbc_monthly_wcir_in, workbook_monthly):
                self.assertAlmostEqual(actual, expected, delta=0.005)
            self.assertAlmostEqual(sum(bridge.monthly_obc_wcir_in), bridge.obc_annual_wcir_in)


class DiversionLedgerTests(unittest.TestCase):
    def test_calculates_crop_and_reservoir_demand_before_assessed_shortage(self):
        ditch = DitchInput(
            ditch_id="demo",
            name="Demo Ditch",
            crop_acres=10.0,
            reservoir_acres=2.0,
            monthly_diversion_acft=(1.0,) * 12,
            measurement_status=("metered",) * 12,
            shortage_assessed=(True,) * 12,
        )
        ledger = calculate_area_diversion_ledger(
            "Demo Area",
            efficiency=0.5,
            monthly_cir_ft=(0.1,) * 12,
            monthly_pan_evap_ft=(0.2,) * 12,
            monthly_precip_ft=(0.05,) * 12,
            ditches=(ditch,),
        )
        january = ledger.ditches[0].monthly[0]
        self.assertAlmostEqual(january.crop_cu_demand_acft, 1.0)
        self.assertAlmostEqual(january.reservoir_net_evap_acft, 0.3)
        self.assertAlmostEqual(january.total_diversion_required_acft, 2.6)
        self.assertAlmostEqual(january.diversion_shortage_acft, 1.6)
        self.assertAlmostEqual(ledger.fractional_shortage_to_required, 1.6 / 2.6)

    def test_qaqc_never_silently_treats_missing_data_as_no_shortage(self):
        ditch = DitchInput(
            ditch_id="missing",
            name="Missing Record",
            crop_acres=1.0,
            reservoir_acres=0.0,
            monthly_diversion_acft=(None,) + (0.0,) * 11,
            measurement_status=("unavailable",) + ("metered",) * 11,
            shortage_assessed=(False,) * 12,
        )
        issues = validate_ledger_inputs(
            efficiency=0.3,
            monthly_cir_ft=(0.1,) * 12,
            monthly_pan_evap_ft=(0.1,) * 12,
            monthly_precip_ft=(0.0,) * 12,
            ditches=(ditch,),
        )
        self.assertIn("unassessed_unavailable_month", {issue.code for issue in issues})


if __name__ == "__main__":
    unittest.main()
