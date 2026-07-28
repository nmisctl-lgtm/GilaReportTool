"""Tests for the small user-facing report-preview interface / 报告预览入口测试。"""

import unittest
from pathlib import Path

from backend.non_agricultural_use import (
    GILA_EXCLUSIVE_OF_VIRDEN,
    SAN_FRANCISCO,
    SAN_SIMON,
    VIRDEN,
)
from backend.report_preview import build_2024_table_two_preview


WORKBOOK = Path(__file__).resolve().parents[1] / "OldMethod_Report/Spreadsheet/2024 Gila Report Data_WORKING.xlsx"


class ReportPreviewTests(unittest.TestCase):
    def test_one_entry_point_reproduces_all_2024_table_two_annual_totals(self):
        preview = build_2024_table_two_preview(WORKBOOK)
        rows_by_stream = {row.stream_system: row for row in preview.rows}

        self.assertEqual(preview.report_year, 2024)
        self.assertAlmostEqual(rows_by_stream[SAN_FRANCISCO].annual_use_af, 2546.3322856634422, places=7)
        self.assertAlmostEqual(rows_by_stream[GILA_EXCLUSIVE_OF_VIRDEN].annual_use_af, 14233.018278561705, places=7)
        self.assertAlmostEqual(rows_by_stream[VIRDEN].annual_use_af, 234.20373795703867, places=7)
        self.assertAlmostEqual(rows_by_stream[SAN_SIMON].annual_use_af, 1088.6778532276562, places=7)


if __name__ == "__main__":
    unittest.main()
