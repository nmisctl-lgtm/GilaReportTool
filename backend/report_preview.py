"""Friendly report-preview interface / 便于使用的报告预览接口。

This module is the current *entry seam* for a reviewed 2024 baseline run.  It
hides workbook-cell adapters and individual calculation modules behind one
small interface that returns the calculated Table II annual-use rows.  The
same shape will be reused for 2025 after its input adapters are approved.

本模块是已核对的 2024 基线运行入口。调用方不需要了解工作簿单元格位置或
各个计算模块；只需提供工作簿路径，即可获得计算出的 Table II 年用水行。
2025 输入适配器经确认后会复用这一输出结构。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .annual_summary import AnnualUseSummaryRow, build_annual_use_summary
from .area_consumptive_use import calculate_generic_area_cu, calculate_special_area_cu
from .legacy_area_summary import read_2024_special_area_inputs, read_2024_standard_area_inputs
from .legacy_non_agricultural import read_2024_non_agricultural_inputs
from .non_agricultural_use import (
    GILA_EXCLUSIVE_OF_VIRDEN,
    SAN_FRANCISCO,
    SAN_SIMON,
    VIRDEN,
    calculate_non_agricultural_use,
)


@dataclass(frozen=True)
class TableTwoPreview:
    """Calculated Table II rows / 已计算的 Table II 行。"""

    report_year: int
    rows: tuple[AnnualUseSummaryRow, ...]


def build_2024_table_two_preview(workbook_path: str | Path) -> TableTwoPreview:
    """Calculate the 2024 Table II annual-use rows from the reviewed workbook.

    从已核对的 2024 工作簿计算 Table II 年度用水行。此函数只适用于 2024
    回归验证；它不是把 Excel 公式当作生产计算。
    """

    standard_area_results_by_name = {
        result.area_name: result
        for result in map(calculate_generic_area_cu, read_2024_standard_area_inputs(workbook_path))
    }
    redrock_result, san_simon_result = map(
        calculate_special_area_cu,
        read_2024_special_area_inputs(workbook_path),
    )
    irrigation_consumptive_use_by_stream = {
        SAN_FRANCISCO: sum(
            standard_area_results_by_name[area_name].total_irrigated_cu_af
            for area_name in ("LUNA", "APACHE-ARAGON", "RESERVE", "GLENWOOD")
        ),
        GILA_EXCLUSIVE_OF_VIRDEN: (
            standard_area_results_by_name["UPPER GILA"].total_irrigated_cu_af
            + standard_area_results_by_name["CLIFF-GILA"].total_irrigated_cu_af
            + redrock_result.total_irrigated_cu_af
        ),
        VIRDEN: standard_area_results_by_name["VIRDEN VALLEY"].total_irrigated_cu_af,
        SAN_SIMON: san_simon_result.total_irrigated_cu_af,
    }
    non_agricultural_inputs = read_2024_non_agricultural_inputs(workbook_path)
    non_agricultural_results = calculate_non_agricultural_use(
        livestock=non_agricultural_inputs.livestock,
        stock_tanks=non_agricultural_inputs.stock_tanks,
        lakes=non_agricultural_inputs.lakes,
        municipal_diversions=non_agricultural_inputs.municipal_diversions,
        cliff_gila_municipal=non_agricultural_inputs.cliff_gila_municipal,
    )
    return TableTwoPreview(
        report_year=2024,
        rows=build_annual_use_summary(
            irrigation_consumptive_use_by_stream,
            non_agricultural_results,
        ),
    )
