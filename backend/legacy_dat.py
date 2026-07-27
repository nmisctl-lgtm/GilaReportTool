"""Read the 2024 xirrigcu fixed-width DAT inputs into explicit Python records.

The parser deliberately preserves every value needed to reproduce the CIR
portion of the legacy program.  It does not read Excel and it does not infer
crop or water-source classifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from .fortran_parity import ClimateYear, CropDefinition, Curve, DateLimits


def _numbers(line: str, cast=float) -> list:
    return [cast(value) for value in line.split()]


def _read_numbers(lines: list[str], index: int, count: int, cast=float) -> tuple[list, int]:
    values: list = []
    while len(values) < count:
        if index >= len(lines):
            raise ValueError(f"Unexpected end of DAT while reading {count} values")
        values.extend(_numbers(lines[index], cast))
        index += 1
    if len(values) != count:
        raise ValueError(f"Expected {count} values but read {len(values)}; malformed fixed-width DAT")
    return values, index


def _jday(year: int, month: int, day: int) -> int | None:
    if month <= 0 or day <= 0:
        return None
    return date(year, month, day).timetuple().tm_yday


def _decimal_latitude(degrees_minutes: float) -> float:
    degrees = int(degrees_minutes)
    return degrees + (degrees_minutes - degrees) * 100.0 / 60.0


@dataclass(frozen=True)
class ControlFile:
    title: str
    crop_data_file: str
    weather_file: str
    crop_coefficient_file: str
    first_year: int
    last_year: int
    region_count: int
    area_count: int
    weather_station_count: int
    data_first_year: int
    data_last_year: int
    original_bc: bool
    modified_bc: bool
    effective_precipitation_flag: int


@dataclass(frozen=True)
class AreaYear:
    year: int
    total_crop_acres: float
    double_crop_acres: float
    crop_mix_pct: tuple[float, ...]
    application_depth_in: float


@dataclass(frozen=True)
class AreaInput:
    area_id: int
    name: str
    latitude_degrees_minutes: float
    precip_station_id: int
    temp_station_id: int
    crop_ids: tuple[str, ...]
    years: dict[int, AreaYear]


@dataclass(frozen=True)
class WeatherStation:
    station_id: int
    name: str
    latitude_degrees_minutes: float
    precipitation_in: dict[int, tuple[float, ...]]
    temperature_f: dict[int, tuple[float, ...]]
    frosts: dict[int, tuple[int | None, int | None, int | None, int | None]]
    prior_december_mean_f: float | None
    next_january_mean_f: float | None


@dataclass(frozen=True)
class LegacyInputs:
    control: ControlFile
    crops: dict[str, CropDefinition]
    areas: dict[int, AreaInput]
    weather: dict[int, WeatherStation]
    date_limits: dict[tuple[int, str, int], DateLimits]
    daylight_by_latitude: tuple[tuple[float, tuple[float, ...]], ...]

    def limits_for(self, area_id: int, crop_id: str, year: int) -> DateLimits:
        return self.date_limits.get((area_id, crop_id, year), DateLimits())

    def climate_for(self, area_id: int, year: int) -> ClimateYear:
        area = self.areas[area_id]
        precipitation_station = self.weather[area.precip_station_id]
        temperature_station = self.weather[area.temp_station_id]
        frost28s, frost32s, frost32f, frost28f = temperature_station.frosts[year]
        return ClimateYear(
            year=year,
            monthly_mean_f=temperature_station.temperature_f[year],
            monthly_precip_in=precipitation_station.precipitation_in[year],
            daylight_pct=self._daylight(area.latitude_degrees_minutes or temperature_station.latitude_degrees_minutes),
            last_spring_28_day=frost28s,
            last_spring_32_day=frost32s,
            first_fall_32_day=frost32f,
            first_fall_28_day=frost28f,
            prior_december_mean_f=temperature_station.prior_december_mean_f,
            next_january_mean_f=temperature_station.next_january_mean_f,
            application_depth_in=area.years[year].application_depth_in,
        )

    def _daylight(self, degrees_minutes: float) -> tuple[float, ...]:
        latitude = _decimal_latitude(degrees_minutes)
        points = self.daylight_by_latitude
        if not points:
            raise ValueError("CDF contains no daylight-hours table")
        if latitude < points[0][0] or latitude > points[-1][0]:
            raise ValueError(f"Latitude {latitude} outside legacy daylight table")
        for (lat0, values0), (lat1, values1) in zip(points, points[1:]):
            if lat0 <= latitude <= lat1:
                if lat1 == lat0:
                    return values0
                ratio = (latitude - lat0) / (lat1 - lat0)
                return tuple(value0 + (value1 - value0) * ratio for value0, value1 in zip(values0, values1))
        return points[-1][1]


def read_control(path: str | Path) -> ControlFile:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    title = lines[0].rstrip()
    crop_data_file, weather_file, crop_coefficient_file = (line.strip() for line in lines[1:4])
    years = _numbers(lines[9], int)
    flags = _numbers(lines[10], int)
    return ControlFile(
        title=title, crop_data_file=crop_data_file, weather_file=weather_file,
        crop_coefficient_file=crop_coefficient_file, first_year=years[0], last_year=years[1],
        region_count=years[2], area_count=years[3], weather_station_count=years[4],
        data_first_year=years[5], data_last_year=years[6], original_bc=flags[0] > 0,
        modified_bc=flags[1] > 0, effective_precipitation_flag=flags[3],
    )


def read_crop_coefficients(path: str | Path, area_count: int, years_count: int) -> tuple[dict[str, CropDefinition], dict[tuple[int, str, int], DateLimits]]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    index = 0
    header = _numbers(lines[index], int)
    index += 1
    crop_count = header[0]
    raw: dict[str, tuple[CropDefinition | None, Curve]] = {}
    limits: dict[tuple[int, str, int], DateLimits] = {}
    for _ in range(crop_count):
        title_line = lines[index]
        index += 1
        crop_id = str(int(title_line[:2]))
        name = title_line[2:].strip()
        params = lines[index]
        index += 1
        crop_type = params[:2].strip()
        values = _numbers(params[2:])
        if values and len(values) != 5:
            raise ValueError(f"Malformed crop parameter line for {crop_id}: {params!r}")
        # FORMAT(13F6.2) repeats once for the 25-element arrays.  Several
        # historical curves intentionally leave trailing fields blank, which
        # Fortran reads as zero; never consume a third record here.
        x = _numbers(lines[index]) + _numbers(lines[index + 1])
        index += 2
        y = _numbers(lines[index]) + _numbers(lines[index + 1])
        index += 2
        if len(x) > 25 or len(y) > 25:
            raise ValueError(f"Malformed MBC curve for crop {crop_id}")
        x.extend([0.0] * (25 - len(x)))
        y.extend([0.0] * (25 - len(y)))
        curve = Curve(tuple(x), tuple(y))
        # Crop 9 is the legacy fall-half Kc curve for winter grain.  It has no
        # independent TEM/TLM/OBC coefficients and is never an area crop.
        crop = CropDefinition(crop_id, name, crop_type, *values, mbc_curve=curve) if values else None
        raw[crop_id] = (crop, curve)
        override_flag = int(_numbers(lines[index], int)[0])
        index += 1
        if override_flag > 0:
            # Legacy program stops at an area-id of zero, even though its outer
            # loops are dimensioned by area_count * years_count.
            for _ in range(area_count * years_count):
                record = _numbers(lines[index], int)
                index += 1
                if record[0] <= 0:
                    break
                area_id, year, plant_month, plant_day, harvest_month, harvest_day = record[:6]
                limits[(area_id, crop_id, year)] = DateLimits(
                    plant_day=_jday(year, plant_month, plant_day),
                    harvest_day=_jday(year, harvest_month, harvest_day),
                )
    crops: dict[str, CropDefinition] = {}
    for crop_id, (crop, curve) in raw.items():
        if crop is None:
            continue
        fall_curve = raw.get(str(int(crop_id) + 1), (None, None))[1] if crop.crop_type == "WG" else None
        crops[crop_id] = CropDefinition(
            crop_id=crop.crop_id, name=crop.name, crop_type=crop.crop_type, tem_f=crop.tem_f,
            tlm_f=crop.tlm_f, obc_k_inside=crop.obc_k_inside, obc_k_outside=crop.obc_k_outside,
            max_growing_season_days=crop.max_growing_season_days, mbc_curve=curve, mbc_fall_curve=fall_curve,
        )
    return crops, limits


def read_crop_data(path: str | Path, control: ControlFile) -> tuple[dict[int, AreaInput], tuple[tuple[float, tuple[float, ...]], ...]]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    index = control.region_count  # region labels are retained in the legacy input but unused by CIR.
    years_count = control.data_last_year - control.data_first_year + 1
    areas: dict[int, AreaInput] = {}
    for area_id in range(1, control.area_count + 1):
        name = lines[index][8:].strip()
        index += 1
        latitude = float(_numbers(lines[index])[0])
        index += 1
        area_config = _numbers(lines[index], int)
        index += 1
        crop_count, precip_station_id, temp_station_id = area_config[1:4]
        crop_ids, index = _read_numbers(lines, index, crop_count, int)
        index += 1  # WWPA: only used for the final-year winter-grain acreage extension.
        annual: dict[int, tuple[float, float, tuple[float, ...]]] = {}
        for _ in range(years_count):
            record = _numbers(lines[index])
            index += 1
            year = int(record[0])
            crop_mix, index = _read_numbers(lines, index, crop_count)
            annual[year] = (record[1], record[2], tuple(crop_mix))
        irrigation: dict[int, float] = {}
        for _ in range(years_count):
            record = _numbers(lines[index])
            index += 1
            irrigation[int(record[0])] = record[7] if len(record) > 7 and record[7] > 0 else 3.0
        shortage_flag = int(_numbers(lines[index], int)[0])
        index += 1
        if shortage_flag > 0:
            index += years_count
        years = {
            year: AreaYear(year, values[0], values[1], values[2], irrigation[year])
            for year, values in annual.items()
        }
        areas[area_id] = AreaInput(area_id, name, latitude, precip_station_id, temp_station_id, tuple(map(str, crop_ids)), years)
    table: list[tuple[float, tuple[float, ...]]] = []
    while index < len(lines):
        record = _numbers(lines[index])
        index += 1
        if not record:
            continue
        if len(record) != 13:
            raise ValueError(f"Malformed daylight record: {record}")
        table.append((record[0], tuple(record[1:])))
    return areas, tuple(table)


def read_weather(path: str | Path, control: ControlFile) -> dict[int, WeatherStation]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    index, years_count = 0, control.data_last_year - control.data_first_year + 1
    stations: dict[int, WeatherStation] = {}
    for station_id in range(1, control.weather_station_count + 1):
        name = lines[index][8:].strip()
        index += 1
        flags = _numbers(lines[index], int)
        index += 1
        latitude = float(_numbers(lines[index])[0])
        index += 1
        precipitation: dict[int, tuple[float, ...]] = {}
        if flags[0] > 0:
            for _ in range(years_count):
                record = _numbers(lines[index])
                index += 1
                precipitation[int(record[0])] = tuple(record[1:])
        prior_december, next_january = None, None
        temperature: dict[int, tuple[float, ...]] = {}
        frosts: dict[int, tuple[int | None, int | None, int | None, int | None]] = {}
        if flags[1] > 0:
            boundary = _numbers(lines[index])
            index += 1
            prior_december, next_january = boundary[0], boundary[1]
            for _ in range(years_count):
                record = _numbers(lines[index])
                index += 1
                temperature[int(record[0])] = tuple(record[1:])
            for _ in range(years_count):
                record = _numbers(lines[index], int)
                index += 1
                year = record[0]
                frosts[year] = (
                    _jday(year, record[1], record[2]), _jday(year, record[3], record[4]),
                    _jday(year, record[5], record[6]), _jday(year, record[7], record[8]),
                )
        stations[station_id] = WeatherStation(station_id, name, latitude, precipitation, temperature, frosts, prior_december, next_january)
    return stations


def read_legacy_inputs(control_path: str | Path) -> LegacyInputs:
    control_path = Path(control_path)
    control = read_control(control_path)
    root = control_path.parent
    crops, limits = read_crop_coefficients(root / control.crop_coefficient_file, control.area_count, control.data_last_year - control.data_first_year + 1)
    areas, daylight = read_crop_data(root / control.crop_data_file, control)
    weather = read_weather(root / control.weather_file, control)
    return LegacyInputs(control, crops, areas, weather, limits, daylight)
