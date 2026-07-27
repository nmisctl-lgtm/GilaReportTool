"""Run the Fortran-parity CIR engine over legacy DAT inputs and read .out fixtures."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .fortran_parity import CIRProfile, FortranParityEngine, Method, weighted_cir
from .legacy_dat import LegacyInputs


MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
MONTH_INDEX = {month: index for index, month in enumerate(MONTHS)}


@dataclass(frozen=True)
class AreaCIRRun:
    area_id: int
    area_name: str
    year: int
    method: Method
    crop_profiles: tuple[tuple[str, float, CIRProfile], ...]
    weighted_monthly_cir_in: tuple[float, ...]

    @property
    def weighted_annual_cir_in(self) -> float:
        return sum(self.weighted_monthly_cir_in)


def run_area(inputs: LegacyInputs, area_id: int, year: int, method: Method) -> AreaCIRRun:
    area = inputs.areas[area_id]
    area_year = area.years[year]
    climate = inputs.climate_for(area_id, year)
    profiles: list[tuple[str, float, CIRProfile]] = []
    for crop_id, mix_pct in zip(area.crop_ids, area_year.crop_mix_pct):
        crop = inputs.crops[crop_id]
        profile = FortranParityEngine(crop, climate).run(method, inputs.limits_for(area_id, crop_id, year))
        profiles.append((crop_id, area_year.total_crop_acres * mix_pct / 100.0, profile))
    return AreaCIRRun(
        area_id=area_id, area_name=area.name, year=year, method=method,
        crop_profiles=tuple(profiles),
        weighted_monthly_cir_in=weighted_cir(tuple((profile, acres) for _, acres, profile in profiles)),
    )


def run_all_areas(inputs: LegacyInputs, year: int, method: Method) -> tuple[AreaCIRRun, ...]:
    return tuple(run_area(inputs, area_id, year, method) for area_id in sorted(inputs.areas))


@dataclass(frozen=True)
class LegacyOutputArea:
    area_name: str
    crop_monthly_cir_in: tuple[tuple[float, ...], ...]
    weighted_monthly_cir_in: tuple[float, ...]


def read_cropcu_output(path: str | Path) -> dict[str, LegacyOutputArea]:
    """Read only the numeric CIR fixtures from a xirrigcu detailed crop output."""

    areas: dict[str, dict[str, object]] = {}
    current_area: str | None = None
    current_crop: list[float] | None = None
    table_crop_mode = False
    weighted_mode = False
    area_pattern = re.compile(r"IRRIGATED AREA:\s*(.*?)\s*$")
    crop_table_pattern = re.compile(r"TABLE\s+\d+\. MONTHLY CIR FOR:")
    weighted_pattern = re.compile(r"WEIGHTED MONTHLY CIRS IN INCHES")
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        area_match = area_pattern.search(line)
        if area_match:
            current_area = area_match.group(1).strip()
            areas.setdefault(current_area, {"crops": [], "weighted": None})
            current_crop = None
            table_crop_mode = False
            weighted_mode = False
            continue
        if current_area is None:
            continue
        if crop_table_pattern.search(line):
            current_crop = [0.0] * 12
            table_crop_mode = True
            weighted_mode = False
            continue
        if weighted_pattern.search(line):
            table_crop_mode = False
            weighted_mode = True
            continue
        tokens = line.split()
        if table_crop_mode and tokens and tokens[0] in MONTH_INDEX:
            # The last rendered numeric field is CIR for both OBC and MBC.
            current_crop[MONTH_INDEX[tokens[0]]] = float(tokens[-1])
            continue
        if table_crop_mode and tokens and tokens[0] == "TOTAL":
            areas[current_area]["crops"].append(tuple(current_crop))
            current_crop = None
            table_crop_mode = False
            continue
        if weighted_mode and len(tokens) == 13:
            try:
                values = tuple(float(value) for value in tokens)
            except ValueError:
                continue
            areas[current_area]["weighted"] = values[:12]
            weighted_mode = False
    result: dict[str, LegacyOutputArea] = {}
    for name, values in areas.items():
        weighted = values["weighted"]
        if weighted is None:
            raise ValueError(f"No weighted monthly CIR table found for {name}")
        result[name] = LegacyOutputArea(name, tuple(values["crops"]), weighted)
    return result


@dataclass(frozen=True)
class RegressionDifference:
    area_name: str
    crop_id: str | None
    month: int
    actual_in: float
    expected_in: float


def compare_to_legacy(run: Iterable[AreaCIRRun], expected: dict[str, LegacyOutputArea], tolerance_in: float = 0.011) -> tuple[RegressionDifference, ...]:
    """Compare all crop and weighted monthly CIRs at the old report's 0.01-in precision."""

    differences: list[RegressionDifference] = []
    for area_run in run:
        legacy = expected[area_run.area_name]
        if len(legacy.crop_monthly_cir_in) != len(area_run.crop_profiles):
            raise ValueError(f"{area_run.area_name}: legacy has {len(legacy.crop_monthly_cir_in)} crop tables, "
                             f"but DAT lists {len(area_run.crop_profiles)} crops")
        for (crop_id, _, profile), expected_months in zip(area_run.crop_profiles, legacy.crop_monthly_cir_in):
            for month, (actual, expected_value) in enumerate(zip((row.cir_in for row in profile.monthly), expected_months), 1):
                if abs(actual - expected_value) > tolerance_in:
                    differences.append(RegressionDifference(area_run.area_name, crop_id, month, actual, expected_value))
        for month, (actual, expected_value) in enumerate(zip(area_run.weighted_monthly_cir_in, legacy.weighted_monthly_cir_in), 1):
            if abs(actual - expected_value) > tolerance_in:
                differences.append(RegressionDifference(area_run.area_name, None, month, actual, expected_value))
    return tuple(differences)
