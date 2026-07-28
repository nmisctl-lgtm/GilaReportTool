"""Transparent, testable CIR engine / 透明、可测试的 CIR 计算引擎。

This module deliberately has no GIS, Excel, PDF, or network dependency.  It is
the first replacement layer for the legacy Fortran program: callers supply one
year of area climate and crop parameters, and receive an auditable monthly CIR
ledger for either Original Blaney-Criddle (OBC) or Modified Blaney-Criddle
(MBC).  Area/ditch accounting belongs in a later module.

这是替代旧 Fortran 的已核对生产计算模块。调用方提供一个区域、一年的气象和
作物参数，即可得到 Original Blaney-Criddle（OBC，原始方法）或 Modified
Blaney-Criddle（MBC，修正方法）的可审计月度 CIR 账。区域和水渠核算属于后续模块。
"""

from __future__ import annotations

import calendar
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, Mapping, Sequence


Method = Literal["obc_usbr", "mbc_scs"]


def _fortran_nint(value: float) -> int:
    """Fortran rounding / Fortran 的 INT(value + 0.5) 舍入，不是 Python 银行家舍入。"""
    return math.floor(value + 0.5)


@dataclass(frozen=True)
class Curve:
    """MBC Kc curve / 按生育阶段线性插值的 MBC 作物系数曲线。"""

    x: tuple[float, ...]
    y: tuple[float, ...]

    def value_at(self, stage: float) -> float:
        if len(self.x) != len(self.y) or not self.x:
            raise ValueError("MBC curve must contain matching, non-empty X and Y values")
        if stage <= self.x[0]:
            return self.y[0]
        for index in range(1, len(self.x)):
            if stage <= self.x[index]:
                x0, x1 = self.x[index - 1], self.x[index]
                y0, y1 = self.y[index - 1], self.y[index]
                if x1 == x0:
                    return y1
                return y0 + (y1 - y0) * (stage - x0) / (x1 - x0)
        return self.y[-1]


@dataclass(frozen=True)
class CropDefinition:
    crop_id: str
    name: str
    crop_type: Literal["AN", "BI", "PR", "WG"]
    tem_f: float
    tlm_f: float
    obc_k_inside: float
    obc_k_outside: float
    max_growing_season_days: float = 0.0
    mbc_curve: Curve | None = None
    # xirrigcu uses the next crop's curve for winter grain in Sep-Dec.
    mbc_fall_curve: Curve | None = None


@dataclass(frozen=True)
class DateLimits:
    """Plant/harvest limits / 用户提供的种植、收获或停水日期（儒略日）。"""

    plant_day: int | None = None
    harvest_day: int | None = None


@dataclass(frozen=True)
class ClimateYear:
    """One area-year climate input / 一个区域、一年的气象输入；深度均为英寸。"""

    year: int
    monthly_mean_f: tuple[float, ...]
    monthly_precip_in: tuple[float, ...]
    daylight_pct: tuple[float, ...]
    last_spring_28_day: int | None = None
    last_spring_32_day: int | None = None
    first_fall_32_day: int | None = None
    first_fall_28_day: int | None = None
    prior_december_mean_f: float | None = None
    next_january_mean_f: float | None = None
    application_depth_in: float = 0.0

    def __post_init__(self) -> None:
        if not all(len(values) == 12 for values in (
            self.monthly_mean_f, self.monthly_precip_in, self.daylight_pct
        )):
            raise ValueError("ClimateYear requires exactly 12 values for temperature, precipitation, and daylight")


@dataclass(frozen=True)
class MonthlyCIR:
    month: int
    growing_days: int
    growing_midpoint_day: float | None
    mean_temperature_f: float
    precipitation_in: float
    daylight_pct: float
    consumptive_use_factor: float
    inside_frost_free_days: int
    outside_frost_free_days: int
    coefficient_or_kc: float | None
    kt: float | None
    etc_in: float
    effective_precip_in: float
    cir_in: float


@dataclass(frozen=True)
class CIRProfile:
    crop_id: str
    method: Method
    season_start_day: int
    season_end_day: int
    monthly: tuple[MonthlyCIR, ...]

    @property
    def annual_cir_in(self) -> float:
        return sum(row.cir_in for row in self.monthly)

    @property
    def annual_etc_in(self) -> float:
        return sum(row.etc_in for row in self.monthly)

    @property
    def annual_effective_precip_in(self) -> float:
        return sum(row.effective_precip_in for row in self.monthly)


def load_crop_definitions(path: str | Path) -> dict[str, CropDefinition]:
    """Load the checked-in coefficient JSON without discarding curves or overrides."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    result: dict[str, CropDefinition] = {}
    for crop_id, item in raw.items():
        if "name" not in item:
            continue
        curve_data = item.get("MBC_Curve") or {}
        curve = Curve(tuple(curve_data.get("X", ())), tuple(curve_data.get("Y", ()))) if curve_data else None
        result[str(crop_id)] = CropDefinition(
            crop_id=str(crop_id), name=item["name"], crop_type=item["type"],
            tem_f=float(item["TEM"]), tlm_f=float(item["TLM"]),
            obc_k_inside=float(item["OBC_K_inside"]), obc_k_outside=float(item["OBC_K_outside"]),
            max_growing_season_days=float(item.get("GSL_days", 0.0)), mbc_curve=curve,
        )
    return result


class FortranParityEngine:
    """CIR calculation engine / 实现生长季、OBC、MBC 和有效降水方程的 CIR 引擎。"""

    def __init__(self, crop: CropDefinition, climate: ClimateYear) -> None:
        self.crop = crop
        self.climate = climate
        self.days = tuple(calendar.monthrange(climate.year, month)[1] for month in range(1, 13))
        starts: list[int] = []
        cursor = 1
        for month_days in self.days:
            starts.append(cursor)
            cursor += month_days
        self.month_starts = tuple(starts)
        self.month_ends = tuple(start + days - 1 for start, days in zip(self.month_starts, self.days))
        # xirrigcu uses (previous_month_end + current_month_end) / 2, then
        # INT(value + 0.5).  ``start`` itself is one day later than the prior
        # month end, so using start+end would shift several midpoints by a day.
        self.midpoints = tuple(_fortran_nint((start - 1 + end) / 2.0)
                               for start, end in zip(self.month_starts, self.month_ends))

    def run(self, method: Method, limits: DateLimits | None = None) -> CIRProfile:
        if method not in ("obc_usbr", "mbc_scs"):
            raise ValueError(f"Unknown method: {method}")
        limits = limits or DateLimits()
        start, end = self._season_bounds(limits)
        if self.crop.crop_type == "WG":
            segments = self._winter_grain_segments(start, end, limits)
        else:
            segments = ((start, end, "main"),)

        monthly: list[MonthlyCIR] = []
        days_after_start = 0.0
        for month in range(1, 13):
            m_start, m_end = self.month_starts[month - 1], self.month_ends[month - 1]
            segment = next(((max(m_start, begin), min(m_end, finish), phase, begin, finish)
                            for begin, finish, phase in segments
                            if max(m_start, begin) <= min(m_end, finish)), None)
            if segment is None:
                monthly.append(self._empty_month(month))
                if self.crop.crop_type == "WG" and month == 8:
                    days_after_start = 0.0
                continue
            begin, finish, phase, season_begin, season_finish = segment
            gd = finish - begin + 1
            # For a full calendar month CIRCAL uses DAYMP, which is rounded
            # to a whole Julian day.  Partial first/last months use the raw
            # average of their boundary days.
            midpoint = (
                float(self.midpoints[month - 1])
                if begin == m_start and finish == m_end
                else (begin + finish) / 2.0
            )
            temperature = self._temperature_at(midpoint, month)
            pdh = self.climate.daylight_pct[month - 1] * gd / self.days[month - 1]
            f_factor = temperature * pdh / 100.0
            inside, outside = self._frost_days(
                begin, finish, gd, phase, season_begin, season_finish
            )
            days_after_start += gd
            if method == "obc_usbr":
                etc, coefficient, kt = self._obc_etc(f_factor, gd, inside, outside, phase), None, None
                effective = self._usbr_effective_precip(month) * gd / self.days[month - 1]
            else:
                coefficient = self._kc_at(
                    midpoint,
                    season_begin,
                    season_finish,
                    phase,
                    days_after_start - gd / 2.0,
                )
                kt = max(0.3, 0.0173 * temperature - 0.314)
                etc = f_factor * kt * coefficient
                effective = self._scs_effective_precip(month, etc) * gd / self.days[month - 1]
            effective = min(effective, etc)
            monthly.append(MonthlyCIR(
                month=month, growing_days=gd, growing_midpoint_day=midpoint,
                mean_temperature_f=temperature, precipitation_in=self.climate.monthly_precip_in[month - 1],
                daylight_pct=pdh, consumptive_use_factor=f_factor,
                inside_frost_free_days=inside, outside_frost_free_days=outside,
                coefficient_or_kc=coefficient, kt=kt, etc_in=etc,
                effective_precip_in=effective, cir_in=max(0.0, etc - effective),
            ))
            if self.crop.crop_type == "WG" and month == 8:
                days_after_start = 0.0
        return CIRProfile(self.crop.crop_id, method, start, end, tuple(monthly))

    def _empty_month(self, month: int) -> MonthlyCIR:
        return MonthlyCIR(month, 0, None, self.climate.monthly_mean_f[month - 1],
                          self.climate.monthly_precip_in[month - 1], 0.0, 0.0,
                          0, 0, None, None, 0.0, 0.0, 0.0)

    def _season_bounds(self, limits: DateLimits) -> tuple[int, int]:
        start = self._threshold_day(self.crop.tem_f, spring=True)
        end = self._threshold_day(self.crop.tlm_f, spring=False, start_day=start)
        # A winter-grain record uses the two date fields differently: they are
        # the fall planting and spring harvest dates.  The legacy program
        # applies them only after it has found the independent spring and fall
        # temperature thresholds (labels 190--200 in CIRCAL); treating them as
        # normal start/end limits collapses the cross-calendar season.
        if self.crop.crop_type == "WG":
            return int(start), int(end)
        if limits.plant_day is not None:
            start = max(start, limits.plant_day)
        if limits.harvest_day is not None:
            end = min(end, limits.harvest_day)
        if end < start:
            end = start
        if self.crop.crop_type != "WG" and self.crop.max_growing_season_days > 0:
            end = min(end, start + int(self.crop.max_growing_season_days) - 1)
        return int(start), int(end)

    def _threshold_day(self, threshold: float, *, spring: bool, start_day: int | None = None) -> int:
        frost = {
            (True, 28.0): self.climate.last_spring_28_day,
            (True, 32.0): self.climate.last_spring_32_day,
            (False, 28.0): self.climate.first_fall_28_day,
            (False, 32.0): self.climate.first_fall_32_day,
        }.get((spring, threshold))
        if frost is not None:
            return int(frost)
        values = self.climate.monthly_mean_f
        if spring:
            for index, value in enumerate(values):
                if value < threshold:
                    continue
                if value == threshold:
                    return self.midpoints[index]
                if index == 0:
                    prior = self.climate.prior_december_mean_f
                    if prior is None or prior >= threshold:
                        return 1
                    day = -15 + 31 * (threshold - prior) / (value - prior)
                    return max(1, _fortran_nint(day))
                return _fortran_nint(self.midpoints[index - 1] + (self.midpoints[index] - self.midpoints[index - 1]) *
                                      (threshold - values[index - 1]) / (value - values[index - 1]))
            raise ValueError(f"{self.crop.name}: spring threshold {threshold}°F is never reached")
        first_month = max(7, next((month for month, end in enumerate(self.month_ends, 1) if end >= (start_day or 1))))
        for index in range(first_month - 1, 12):
            value = values[index]
            if value > threshold:
                continue
            if value == threshold:
                return self.midpoints[index]
            if index == 0:
                return 1
            return _fortran_nint(self.midpoints[index - 1] + (self.midpoints[index] - self.midpoints[index - 1]) *
                                 (threshold - values[index - 1]) / (value - values[index - 1]))
        next_january = self.climate.next_january_mean_f
        # At the final data year, the legacy TA1 value is used to interpolate
        # an end date only when the following January is *below* the terminal
        # threshold.  A warm following January means growth remains through
        # December 31.
        if next_january is None or next_january >= threshold:
            return self.month_ends[-1]
        day = self.midpoints[-1] + 31 * (threshold - values[-1]) / (next_january - values[-1])
        return min(self.month_ends[-1], _fortran_nint(day))

    def _winter_grain_segments(self, start: int, end: int, limits: DateLimits) -> tuple[tuple[int, int, str], ...]:
        harvest = limits.harvest_day if limits.harvest_day is not None else self.month_ends[7]
        planting = limits.plant_day if limits.plant_day is not None else self.month_starts[8]
        return ((min(start, harvest), harvest, "spring"), (planting, max(end, planting), "fall"))

    def _temperature_at(self, day: float, month: int) -> float:
        index = month - 1
        if day == self.midpoints[index]:
            return self.climate.monthly_mean_f[index]
        if day < self.midpoints[index]:
            prior_day = self.midpoints[index - 1] if index else self.midpoints[index] - 31
            prior_temp = self.climate.monthly_mean_f[index - 1] if index else self.climate.prior_december_mean_f
            if prior_temp is None:
                return self.climate.monthly_mean_f[index]
            return prior_temp + (self.climate.monthly_mean_f[index] - prior_temp) * (day - prior_day) / (self.midpoints[index] - prior_day)
        next_day = self.midpoints[index + 1] if index < 11 else self.midpoints[index] + 31
        next_temp = self.climate.monthly_mean_f[index + 1] if index < 11 else self.climate.next_january_mean_f
        if next_temp is None:
            return self.climate.monthly_mean_f[index]
        return self.climate.monthly_mean_f[index] + (next_temp - self.climate.monthly_mean_f[index]) * (day - self.midpoints[index]) / (next_day - self.midpoints[index])

    def _frost_days(
        self,
        begin: int,
        finish: int,
        gd: int,
        phase: str,
        season_begin: int,
        season_finish: int,
    ) -> tuple[int, int]:
        if self.crop.crop_type == "WG":
            return (gd, 0) if phase == "spring" else (0, gd)
        spring, fall = self.climate.last_spring_32_day, self.climate.first_fall_32_day
        if spring is None or fall is None:
            return gd, 0
        # CIRCAL classifies a frost-boundary day as outside when a season
        # crosses it, but as inside when the boundary itself is the crop's
        # start/end date.  That subtle distinction matters for crops governed
        # by 32 F thresholds, such as Misc. Vegetable.
        inside_begin = spring if season_begin == spring else spring + 1
        # The detailed legacy outputs consistently charge the first autumn
        # 32 F day at the outside-frost coefficient, including when it is the
        # stated season end (despite an ambiguous branch in the fixed-format
        # source listing).
        inside_end = fall - 1
        inside = max(0, min(finish, inside_end) - max(begin, inside_begin) + 1)
        return inside, gd - inside

    def _obc_etc(self, f_factor: float, gd: int, inside: int, outside: int, phase: str) -> float:
        if self.crop.crop_type == "WG":
            return f_factor * (self.crop.obc_k_inside if phase == "spring" else self.crop.obc_k_outside)
        return f_factor * ((inside / gd) * self.crop.obc_k_inside + (outside / gd) * self.crop.obc_k_outside)

    def _kc_at(
        self,
        midpoint: float,
        start: int,
        end: int,
        phase: str,
        days_after_start_midpoint: float,
    ) -> float:
        curve = self.crop.mbc_fall_curve if self.crop.crop_type == "WG" and phase == "fall" else self.crop.mbc_curve
        if curve is None:
            raise ValueError(f"{self.crop.name}: MBC requires a crop coefficient curve")
        stage = (
            midpoint
            if self.crop.crop_type == "PR"
            else days_after_start_midpoint * 100 / (end - start + 1)
        )
        return curve.value_at(stage)

    def _usbr_effective_precip(self, month: int) -> float:
        p = self.climate.monthly_precip_in[month - 1]
        if p <= 1: return 0.95 * p
        if p <= 2: return 0.90 * (p - 1) + 0.95
        if p <= 3: return 0.82 * (p - 2) + 1.85
        if p <= 4: return 0.65 * (p - 3) + 2.67
        if p <= 5: return 0.45 * (p - 4) + 3.32
        if p <= 6: return 0.25 * (p - 5) + 3.77
        return 0.05 * (p - 6) + 4.02

    def _scs_effective_precip(self, month: int, etc: float) -> float:
        p, depth = self.climate.monthly_precip_in[month - 1], self.climate.application_depth_in
        correction = 0.531747 + 0.295164 * depth - 0.057697 * depth**2 + 0.003804 * depth**3
        return max(0.0, min(p, ((0.70917 * p**0.82416 - 0.11556) * 10**(0.02426 * etc)) * correction))


def weighted_cir(profiles_with_acres: Sequence[tuple[CIRProfile, float]]) -> tuple[float, ...]:
    """Return weighted monthly CIR inches for an area; reject silently empty mixes."""

    total_acres = sum(acres for _, acres in profiles_with_acres)
    if total_acres <= 0:
        raise ValueError("Weighted CIR requires positive crop acreage")
    return tuple(sum(profile.monthly[month].cir_in * acres for profile, acres in profiles_with_acres) / total_acres
                 for month in range(12))


def distribute_obc_annual_by_mbc(obc_annual_in: float, mbc_monthly_in: Sequence[float]) -> tuple[float, ...]:
    """The xirrigcu/2024 Excel bridge: OBC total, MBC monthly timing."""

    total = sum(mbc_monthly_in)
    if total <= 0:
        raise ValueError("Cannot distribute annual OBC CIR with a zero MBC annual total")
    return tuple(obc_annual_in * month / total for month in mbc_monthly_in)
