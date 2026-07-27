import unittest
from pathlib import Path

from backend.annual_summary import build_annual_use_summary
from backend.area_consumptive_use import calculate_generic_area_cu, calculate_special_area_cu
from backend.legacy_area_summary import read_2024_special_area_inputs, read_2024_standard_area_inputs
from backend.legacy_non_agricultural import read_2024_non_agricultural_inputs
from backend.non_agricultural_use import (
    GILA_EXCLUSIVE_OF_VIRDEN,
    SAN_FRANCISCO,
    SAN_SIMON,
    VIRDEN,
    LivestockInventory,
    MunicipalDiversion,
    calculate_municipal_use,
    calculate_non_agricultural_use,
)


WORKBOOK = Path(__file__).resolve().parents[1] / "OldMethod_Report/Spreadsheet/2024 Gila Report Data_WORKING.xlsx"


class NonAgriculturalRegressionTests(unittest.TestCase):
    def setUp(self):
        self.inputs = read_2024_non_agricultural_inputs(WORKBOOK)
        self.results = calculate_non_agricultural_use(
            livestock=self.inputs.livestock,
            stock_tanks=self.inputs.stock_tanks,
            lakes=self.inputs.lakes,
            municipal_diversions=self.inputs.municipal_diversions,
            cliff_gila_municipal=self.inputs.cliff_gila_municipal,
        )

    def test_reproduces_2024_non_agricultural_table_ii_components(self):
        self.assertAlmostEqual(self.results.stock_tank_evaporation_af[SAN_FRANCISCO], 423.436595, places=7)
        self.assertAlmostEqual(self.results.stock_tank_evaporation_af[GILA_EXCLUSIVE_OF_VIRDEN], 1153.851625, places=7)
        self.assertAlmostEqual(self.results.stock_tank_evaporation_af[VIRDEN], 29.924675, places=7)
        self.assertAlmostEqual(self.results.stock_tank_evaporation_af[SAN_SIMON], 128.21536, places=7)
        self.assertAlmostEqual(self.results.livestock_af[SAN_FRANCISCO], 156.35012935360027, places=7)
        self.assertAlmostEqual(self.results.livestock_af[GILA_EXCLUSIVE_OF_VIRDEN], 160.29258771647164, places=7)
        self.assertAlmostEqual(self.results.livestock_af[VIRDEN], 14.759015623705313, places=7)
        self.assertAlmostEqual(self.results.livestock_af[SAN_SIMON], 17.218851560989535, places=7)
        self.assertAlmostEqual(self.results.municipal_industrial_domestic_af[SAN_FRANCISCO], 65.3, places=7)
        self.assertAlmostEqual(self.results.municipal_industrial_domestic_af[GILA_EXCLUSIVE_OF_VIRDEN], 6449.286666666667, places=7)
        self.assertAlmostEqual(self.results.municipal_industrial_domestic_af[VIRDEN], 9.25, places=7)
        self.assertAlmostEqual(self.results.municipal_industrial_domestic_af[SAN_SIMON], 9.27, places=7)
        self.assertEqual(self.results.lake_evaporation_af[SAN_FRANCISCO], 0.0)
        self.assertAlmostEqual(self.results.lake_evaporation_af[GILA_EXCLUSIVE_OF_VIRDEN], 561.9247916666667, places=7)

    def test_table_ii_annual_totals_are_built_from_calculated_components(self):
        standard = {result.area_name: result for result in map(calculate_generic_area_cu, read_2024_standard_area_inputs(WORKBOOK))}
        redrock, san_simon = map(calculate_special_area_cu, read_2024_special_area_inputs(WORKBOOK))
        irrigation = {
            SAN_FRANCISCO: sum(standard[name].total_irrigated_cu_af for name in ("LUNA", "APACHE-ARAGON", "RESERVE", "GLENWOOD")),
            GILA_EXCLUSIVE_OF_VIRDEN: standard["UPPER GILA"].total_irrigated_cu_af + standard["CLIFF-GILA"].total_irrigated_cu_af + redrock.total_irrigated_cu_af,
            VIRDEN: standard["VIRDEN VALLEY"].total_irrigated_cu_af,
            SAN_SIMON: san_simon.total_irrigated_cu_af,
        }
        rows = {row.stream_system: row for row in build_annual_use_summary(irrigation, self.results)}
        self.assertAlmostEqual(rows[SAN_FRANCISCO].annual_use_af, 2546.3322856634422, places=7)
        self.assertAlmostEqual(rows[GILA_EXCLUSIVE_OF_VIRDEN].annual_use_af, 14233.018278561705, places=7)
        self.assertAlmostEqual(rows[VIRDEN].annual_use_af, 234.20373795703867, places=7)
        self.assertAlmostEqual(rows[SAN_SIMON].annual_use_af, 1088.6778532276562, places=7)

    def test_invalid_inputs_are_rejected_before_a_report_is_created(self):
        invalid_inventory = LivestockInventory(
            cattle_by_county={"CATRON": 1, "GRANT": 1, "HIDALGO": 1},
            sheep_by_county={"CATRON": 0, "GRANT": 0, "HIDALGO": 0},
            national_forest_cattle_head_months=100,
        )
        with self.assertRaisesRegex(ValueError, "exceeds"):
            calculate_non_agricultural_use(
                livestock=invalid_inventory,
                stock_tanks=(),
                lakes=(),
                municipal_diversions=(),
                cliff_gila_municipal=self.inputs.cliff_gila_municipal,
            )
        with self.assertRaisesRegex(ValueError, "exceeds diversion"):
            calculate_municipal_use((MunicipalDiversion("bad", SAN_FRANCISCO, 1, nonconsumptive_af=2),), self.inputs.cliff_gila_municipal)


if __name__ == "__main__":
    unittest.main()
