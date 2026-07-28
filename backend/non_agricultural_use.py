"""Transparent non-agricultural consumptive-use calculations / 透明的非农耗水计算。

These calculations replace the one-off scripts in ``archive_scripts``.  They
intentionally do not fetch web data or read spreadsheets: callers supply
validated raw inputs, and this module returns auditable intermediate results.
The 2024 legacy-workbook adapter lives in :mod:`legacy_non_agricultural`.

本模块是 2025 的生产计算路径：调用方提供已经 QA/QC 的原始或准备后输入，
模块返回可审计的中间结果。2024 的工作簿单元格读取只存在于
``legacy_non_agricultural`` 适配器中。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


SAN_FRANCISCO = "SAN FRANCISCO RIVER"
GILA_EXCLUSIVE_OF_VIRDEN = "GILA RIVER EXCLUSIVE OF VIRDEN VALLEY"
VIRDEN = "GILA RIVER - VIRDEN VALLEY"
SAN_SIMON = "SAN SIMON"

REPORT_STREAMS = (SAN_FRANCISCO, GILA_EXCLUSIVE_OF_VIRDEN, VIRDEN, SAN_SIMON)
# The documented 2024 workbook uses 325,851 gallons per acre-foot.  Retain
# that report convention for regression parity rather than the rounded value
# in the retired livestock script.
GALLONS_PER_ACRE_FOOT = 325_851.0
LEGACY_REPORT_DAYS = 365


@dataclass(frozen=True)
class LivestockInventory:
    """County inventory and forest head-months / 县级存栏量和森林 head-months。

    The report convention is 365 days even in leap years, matching the
    historical workbook.  National Forest figures are head-months and are
    converted to average annual head before the drainage allocation.
    """

    cattle_by_county: Mapping[str, float]
    sheep_by_county: Mapping[str, float]
    national_forest_cattle_head_months: float


@dataclass(frozen=True)
class LivestockUse:
    cattle_head: float
    sheep_head: float
    cattle_use_af: float
    sheep_use_af: float

    @property
    def total_use_af(self) -> float:
        return self.cattle_use_af + self.sheep_use_af


def calculate_livestock_use(inventory: LivestockInventory) -> dict[str, LivestockUse]:
    """Allocate livestock and calculate CU / 分配牲畜并计算年度耗水量。

    Allocation fractions are the documented 2024 report assumptions.  Forest
    cattle are first assigned from Gila National Forest head-months, then
    removed from the corresponding county allocation to avoid double-counting.
    """

    _validate_inventory(inventory)
    catron_cattle = _county(inventory.cattle_by_county, "CATRON")
    grant_cattle = _county(inventory.cattle_by_county, "GRANT")
    hidalgo_cattle = _county(inventory.cattle_by_county, "HIDALGO")
    catron_sheep = _county(inventory.sheep_by_county, "CATRON")
    grant_sheep = _county(inventory.sheep_by_county, "GRANT")
    hidalgo_sheep = _county(inventory.sheep_by_county, "HIDALGO")

    forest_average_head = inventory.national_forest_cattle_head_months / 12.0
    sfr_forest = forest_average_head * 0.488
    gila_forest = forest_average_head * 0.512
    sfr_cattle = catron_cattle * 0.41
    gila_cattle = grant_cattle * 0.53
    if sfr_forest > sfr_cattle or gila_forest > gila_cattle:
        raise ValueError("National Forest allocation exceeds the corresponding county allocation")

    heads = {
        SAN_FRANCISCO: (sfr_cattle, catron_sheep * 0.41, 10.0),
        GILA_EXCLUSIVE_OF_VIRDEN: (gila_cattle, grant_sheep * 0.53, 10.0),
        VIRDEN: (hidalgo_cattle * 0.06, hidalgo_sheep * 0.06, 12.0),
        SAN_SIMON: (hidalgo_cattle * 0.07, hidalgo_sheep * 0.07, 12.0),
    }
    # County allocations are inclusive of the forest population.  Retain the
    # split only as an audit trail; total use is based on the allocated heads.
    return {
        stream: LivestockUse(
            cattle_head=cattle_head,
            sheep_head=sheep_head,
            cattle_use_af=cattle_head * cattle_gallons_per_day * LEGACY_REPORT_DAYS / GALLONS_PER_ACRE_FOOT,
            sheep_use_af=sheep_head * 2.2 * LEGACY_REPORT_DAYS / GALLONS_PER_ACRE_FOOT,
        )
        for stream, (cattle_head, sheep_head, cattle_gallons_per_day) in heads.items()
    }


@dataclass(frozen=True)
class StockTankSite:
    """Stock-tank evaporation input / 一个区域或一组牲畜饮水池的蒸发输入。"""

    name: str
    stream_system: str
    adjusted_pan_evaporation_in: float
    precipitation_in: float
    average_surface_area_acres: float
    tank_count: float
    in_service_fraction: float = 0.85

    @property
    def net_evaporation_ft(self) -> float:
        return max(self.adjusted_pan_evaporation_in - self.precipitation_in, 0.0) / 12.0

    @property
    def use_per_tank_af(self) -> float:
        return self.net_evaporation_ft * self.average_surface_area_acres

    @property
    def total_use_af(self) -> float:
        return self.use_per_tank_af * self.tank_count * self.in_service_fraction


def calculate_stock_tank_evaporation(sites: tuple[StockTankSite, ...]) -> dict[str, float]:
    """Sum non-negative annual evaporation by report stream system."""

    totals = _zero_totals()
    for site in sites:
        _validate_stock_tank(site)
        totals[site.stream_system] = totals.get(site.stream_system, 0.0) + site.total_use_af
    return totals


@dataclass(frozen=True)
class LakeEvaporationSite:
    """Lake CU calculated from net evaporation or supplied as an allocation."""

    name: str
    stream_system: str
    adjusted_pan_evaporation_in: float | None = None
    precipitation_in: float | None = None
    surface_area_acres: float | None = None
    fixed_use_af: float | None = None

    @property
    def total_use_af(self) -> float:
        if self.fixed_use_af is not None:
            return self.fixed_use_af
        assert self.adjusted_pan_evaporation_in is not None
        assert self.precipitation_in is not None
        assert self.surface_area_acres is not None
        return max(self.adjusted_pan_evaporation_in - self.precipitation_in, 0.0) / 12.0 * self.surface_area_acres


def calculate_lake_evaporation(sites: tuple[LakeEvaporationSite, ...]) -> dict[str, float]:
    """Sum lake surface evaporation by report stream system."""

    totals = _zero_totals()
    for site in sites:
        _validate_lake(site)
        totals[site.stream_system] = totals.get(site.stream_system, 0.0) + site.total_use_af
    return totals


@dataclass(frozen=True)
class MunicipalDiversion:
    """A metered municipal/industrial/domestic diversion with a CU fraction."""

    name: str
    stream_system: str
    diversion_af: float
    nonconsumptive_af: float = 0.0
    consumptive_fraction: float = 0.5

    @property
    def consumptive_use_af(self) -> float:
        return (self.diversion_af - self.nonconsumptive_af) * self.consumptive_fraction


@dataclass(frozen=True)
class FreeportAccounting:
    """Raw Freeport entries used in the industrial CU accounting statement."""

    tyrone_wells_af: float
    evans_reservoir_to_mine_af: float
    bill_evans_evaporation_af: float
    t_irrigation_cu_af: float
    t13_usfs_diversion_af: float
    seepage_credit_af: float

    @property
    def consumptive_use_af(self) -> float:
        return (
            self.tyrone_wells_af
            + self.evans_reservoir_to_mine_af
            + self.bill_evans_evaporation_af
            + self.t_irrigation_cu_af
            + self.t13_usfs_diversion_af
            - self.seepage_credit_af
        )


@dataclass(frozen=True)
class CliffGilaMunicipalUse:
    """Special Cliff-Gila M/I calculation documented in the 2024 workbook."""

    fish_pond_diversion_af: float
    fish_pond_nonconsumptive_af: float
    exported_to_mimbres_af: float
    freeport: FreeportAccounting
    fish_pond_evaporation_allocation_af: float

    @property
    def consumptive_use_af(self) -> float:
        return (
            (self.fish_pond_diversion_af - self.fish_pond_nonconsumptive_af) * 0.5
            + self.exported_to_mimbres_af
            + self.freeport.consumptive_use_af
            + self.fish_pond_evaporation_allocation_af
        )


def calculate_municipal_use(
    diversions: tuple[MunicipalDiversion, ...],
    cliff_gila: CliffGilaMunicipalUse,
) -> dict[str, float]:
    """Aggregate standard and documented Cliff-Gila M/I CU calculations."""

    totals = _zero_totals()
    for diversion in diversions:
        _validate_municipal_diversion(diversion)
        totals[diversion.stream_system] = totals.get(diversion.stream_system, 0.0) + diversion.consumptive_use_af
    _validate_cliff_gila(cliff_gila)
    totals[GILA_EXCLUSIVE_OF_VIRDEN] += cliff_gila.consumptive_use_af
    return totals


@dataclass(frozen=True)
class NonAgriculturalUseResult:
    stock_tank_evaporation_af: Mapping[str, float]
    livestock_af: Mapping[str, float]
    municipal_industrial_domestic_af: Mapping[str, float]
    lake_evaporation_af: Mapping[str, float]


def calculate_non_agricultural_use(
    *,
    livestock: LivestockInventory,
    stock_tanks: tuple[StockTankSite, ...],
    lakes: tuple[LakeEvaporationSite, ...],
    municipal_diversions: tuple[MunicipalDiversion, ...],
    cliff_gila_municipal: CliffGilaMunicipalUse,
) -> NonAgriculturalUseResult:
    """Calculate all Table II non-ag components / 从原始输入计算 Table II 全部非农分项。"""

    livestock_results = calculate_livestock_use(livestock)
    return NonAgriculturalUseResult(
        stock_tank_evaporation_af=calculate_stock_tank_evaporation(stock_tanks),
        livestock_af={stream: result.total_use_af for stream, result in livestock_results.items()},
        municipal_industrial_domestic_af=calculate_municipal_use(municipal_diversions, cliff_gila_municipal),
        lake_evaporation_af=calculate_lake_evaporation(lakes),
    )


def _zero_totals() -> dict[str, float]:
    return {stream: 0.0 for stream in REPORT_STREAMS}


def _county(values: Mapping[str, float], county: str) -> float:
    try:
        return float(values[county])
    except KeyError as error:
        raise ValueError(f"Missing {county} livestock inventory") from error


def _validate_inventory(inventory: LivestockInventory) -> None:
    values = (*inventory.cattle_by_county.values(), *inventory.sheep_by_county.values(), inventory.national_forest_cattle_head_months)
    if any(float(value) < 0 for value in values):
        raise ValueError("Livestock inventory cannot be negative")


def _validate_stock_tank(site: StockTankSite) -> None:
    values = (
        site.adjusted_pan_evaporation_in,
        site.precipitation_in,
        site.average_surface_area_acres,
        site.tank_count,
        site.in_service_fraction,
    )
    if any(value < 0 for value in values) or site.in_service_fraction > 1:
        raise ValueError(f"Invalid stock tank inputs for {site.name}")


def _validate_lake(site: LakeEvaporationSite) -> None:
    if site.fixed_use_af is not None:
        if site.fixed_use_af < 0:
            raise ValueError(f"Fixed lake use cannot be negative for {site.name}")
        return
    values = (site.adjusted_pan_evaporation_in, site.precipitation_in, site.surface_area_acres)
    if any(value is None or value < 0 for value in values):
        raise ValueError(f"Lake inputs must be complete and non-negative for {site.name}")


def _validate_municipal_diversion(diversion: MunicipalDiversion) -> None:
    if diversion.diversion_af < 0 or diversion.nonconsumptive_af < 0:
        raise ValueError(f"Municipal diversion cannot be negative for {diversion.name}")
    if diversion.nonconsumptive_af > diversion.diversion_af:
        raise ValueError(f"Nonconsumptive use exceeds diversion for {diversion.name}")
    if not 0 <= diversion.consumptive_fraction <= 1:
        raise ValueError(f"Invalid consumptive fraction for {diversion.name}")


def _validate_cliff_gila(inputs: CliffGilaMunicipalUse) -> None:
    if any(value < 0 for value in (
        inputs.fish_pond_diversion_af,
        inputs.fish_pond_nonconsumptive_af,
        inputs.exported_to_mimbres_af,
        inputs.fish_pond_evaporation_allocation_af,
    )):
        raise ValueError("Cliff-Gila municipal inputs cannot be negative")
    if inputs.fish_pond_nonconsumptive_af > inputs.fish_pond_diversion_af:
        raise ValueError("Cliff-Gila nonconsumptive use exceeds diversion")
    freeport_values = vars(inputs.freeport).values()
    if any(value < 0 for value in freeport_values):
        raise ValueError("Freeport accounting inputs cannot be negative")
