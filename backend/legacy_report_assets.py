"""Extract auditable 2024 metered-ditch assets from the report workbook.

This is a baseline reader, not the future report generator.  It exposes the
crop/reservoir/pre-plant acreage and the existing shortage-cell treatment so
those manual policy decisions can be moved into a reviewable input table.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .diversion_mapping import SourceDitchMapping


AREA_SHEET_NAMES = {
    "LUNA": "luna",
    "APACHE-ARAGON": "apachearagon",
    "RESERVE": "reserve",
    "GLENWOOD": "glenwood",
    "UPPER GILA": "uppergila",
    "CLIFF-GILA": "cliffgila",
    "REDROCK": "redrock",
    "VIRDEN VALLEY": "virden",
    "SAN SIMON": "sansimon",
}


@dataclass(frozen=True)
class LegacyMeteredDitchAsset:
    """One metered-ditch block as stored in the 2024 report workbook."""

    canonical_ditch_id: str
    area_name: str
    report_ditch_name: str
    crop_acres: float
    reservoir_acres: float
    preplant_acres: float
    monthly_diversion_acft: tuple[float, ...]
    shortage_formula_months: tuple[bool, ...]
    monthly_shortage_acft: tuple[float, ...]


def read_2024_metered_ditch_assets(
    path: str | Path, mappings: Iterable[SourceDitchMapping]
) -> tuple[LegacyMeteredDitchAsset, ...]:
    """Read configured 2024 report blocks without inferring policy semantics."""

    try:
        import openpyxl
    except ImportError as error:  # pragma: no cover - project dependency
        raise RuntimeError("Reading legacy report assets requires openpyxl.") from error

    mappings = tuple(mapping for mapping in mappings if mapping.disposition == "report_ditch")
    values = openpyxl.load_workbook(Path(path), data_only=True, read_only=False)
    formulas = openpyxl.load_workbook(Path(path), data_only=False, read_only=False)
    assets: list[LegacyMeteredDitchAsset] = []
    for mapping in mappings:
        sheet_name = AREA_SHEET_NAMES[mapping.area_name or ""]
        value_sheet = values[sheet_name]
        formula_sheet = formulas[sheet_name]
        diversion_column = _find_report_ditch_column(value_sheet, mapping.report_ditch_name or "")
        acre_column = diversion_column + 1
        monthly_diversion = tuple(_number(value_sheet.cell(row, diversion_column).value) for row in range(12, 24))
        monthly_shortage = tuple(_number(value_sheet.cell(row, diversion_column + 5).value) for row in range(12, 24))
        shortage_formula_months = tuple(
            isinstance(formula_sheet.cell(row, diversion_column + 5).value, str)
            and formula_sheet.cell(row, diversion_column + 5).value.startswith("=")
            for row in range(12, 24)
        )
        assets.append(LegacyMeteredDitchAsset(
            canonical_ditch_id=mapping.canonical_ditch_id or "",
            area_name=mapping.area_name or "",
            report_ditch_name=mapping.report_ditch_name or "",
            reservoir_acres=_number(value_sheet.cell(7, acre_column).value),
            preplant_acres=_number(value_sheet.cell(8, acre_column).value),
            crop_acres=_number(value_sheet.cell(9, acre_column).value),
            monthly_diversion_acft=monthly_diversion,
            shortage_formula_months=shortage_formula_months,
            monthly_shortage_acft=monthly_shortage,
        ))
    return tuple(assets)


def _find_report_ditch_column(sheet: object, report_ditch_name: str) -> int:
    for column in range(1, sheet.max_column + 1):
        if sheet.cell(6, column).value == report_ditch_name:
            return column
    raise ValueError(f"{sheet.title}: report ditch block {report_ditch_name!r} was not found in row 6.")


def _number(value: object) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"Expected a numeric legacy report value, got {value!r}")
    return float(value)
