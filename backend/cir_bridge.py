"""Bridge the two legacy CIR methods into the monthly values used by reports.

The 2024 workbook uses the annual weighted Original Blaney-Criddle (OBC)
result for the amount of consumptive irrigation requirement, while using the
monthly Modified Blaney-Criddle (MBC) result only to establish the timing.
Keeping this bridge separate makes that otherwise hidden Excel relationship
explicit and reusable by the diversion ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .cir_runner import AreaCIRRun


@dataclass(frozen=True)
class AreaCIRBridge:
    """Annual OBC demand allocated among months by MBC timing, in inches."""

    area_id: int
    area_name: str
    year: int
    obc_annual_wcir_in: float
    mbc_monthly_wcir_in: tuple[float, ...]
    monthly_obc_wcir_in: tuple[float, ...]

    @property
    def monthly_obc_wcir_ft(self) -> tuple[float, ...]:
        return tuple(value / 12.0 for value in self.monthly_obc_wcir_in)


def build_area_cir_bridge(obc: AreaCIRRun, mbc: AreaCIRRun) -> AreaCIRBridge:
    """Allocate a matched area/year's OBC annual CIR using MBC monthly ratios."""

    if (obc.area_id, obc.area_name, obc.year) != (mbc.area_id, mbc.area_name, mbc.year):
        raise ValueError("OBC and MBC runs must represent the same area and year")
    timing_total = sum(mbc.weighted_monthly_cir_in)
    if timing_total <= 0:
        raise ValueError(f"{obc.area_name}: MBC annual CIR must be positive to allocate OBC demand")
    monthly = tuple(obc.weighted_annual_cir_in * value / timing_total
                    for value in mbc.weighted_monthly_cir_in)
    return AreaCIRBridge(
        area_id=obc.area_id,
        area_name=obc.area_name,
        year=obc.year,
        obc_annual_wcir_in=obc.weighted_annual_cir_in,
        mbc_monthly_wcir_in=mbc.weighted_monthly_cir_in,
        monthly_obc_wcir_in=monthly,
    )


def build_cir_bridges(
    obc_runs: Iterable[AreaCIRRun], mbc_runs: Iterable[AreaCIRRun]
) -> tuple[AreaCIRBridge, ...]:
    """Join OBC and MBC area runs by stable area id; reject missing counterparts."""

    obc_by_id = {run.area_id: run for run in obc_runs}
    mbc_by_id = {run.area_id: run for run in mbc_runs}
    if set(obc_by_id) != set(mbc_by_id):
        missing_obc = sorted(set(mbc_by_id) - set(obc_by_id))
        missing_mbc = sorted(set(obc_by_id) - set(mbc_by_id))
        raise ValueError(f"Mismatched CIR area runs; missing OBC={missing_obc}, missing MBC={missing_mbc}")
    return tuple(build_area_cir_bridge(obc_by_id[area_id], mbc_by_id[area_id])
                 for area_id in sorted(obc_by_id))
