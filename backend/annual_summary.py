"""Report-ready annual-use summary / 不依赖 Excel 公式的年度耗水汇总。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .non_agricultural_use import REPORT_STREAMS, NonAgriculturalUseResult


@dataclass(frozen=True)
class AnnualUseSummaryRow:
    """One Table II stream-system row / Table II 中一个流域的汇总行。"""
    stream_system: str
    irrigation_af: float
    stock_tank_evaporation_af: float
    livestock_af: float
    municipal_industrial_domestic_af: float
    lake_evaporation_af: float

    @property
    def annual_use_af(self) -> float:
        return (
            self.irrigation_af
            + self.stock_tank_evaporation_af
            + self.livestock_af
            + self.municipal_industrial_domestic_af
            + self.lake_evaporation_af
        )


def build_annual_use_summary(
    irrigation_by_stream: Mapping[str, float],
    non_agricultural: NonAgriculturalUseResult,
) -> tuple[AnnualUseSummaryRow, ...]:
    """Build Table II component rows / 生成 Table II 年用水分项汇总行。"""

    _validate_irrigation(irrigation_by_stream)
    return tuple(
        AnnualUseSummaryRow(
            stream_system=stream,
            irrigation_af=float(irrigation_by_stream.get(stream, 0.0)),
            stock_tank_evaporation_af=float(non_agricultural.stock_tank_evaporation_af.get(stream, 0.0)),
            livestock_af=float(non_agricultural.livestock_af.get(stream, 0.0)),
            municipal_industrial_domestic_af=float(non_agricultural.municipal_industrial_domestic_af.get(stream, 0.0)),
            lake_evaporation_af=float(non_agricultural.lake_evaporation_af.get(stream, 0.0)),
        )
        for stream in REPORT_STREAMS
    )


def _validate_irrigation(irrigation_by_stream: Mapping[str, float]) -> None:
    if any(value < 0 for value in irrigation_by_stream.values()):
        raise ValueError("Irrigation consumptive use cannot be negative")
