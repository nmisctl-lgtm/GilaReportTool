"""Area-level irrigation consumptive-use aggregation outside Excel.

The generic nine-area workbook layout separates metered surface water,
unmetered surface water, and groundwater.  Only the two surface-water classes
receive the measured diversion-shortage fraction; groundwater is full supply.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AcreageClass:
    """Crop and reservoir/pond acreage under one water-supply classification."""

    crop_acres: float = 0.0
    reservoir_acres: float = 0.0

    @property
    def total_acres(self) -> float:
        return self.crop_acres + self.reservoir_acres

    def full_supply_cu(self, *, annual_cir_ft: float, annual_reservoir_net_evap_ft: float) -> float:
        return self.crop_acres * annual_cir_ft + self.reservoir_acres * annual_reservoir_net_evap_ft


@dataclass(frozen=True)
class MeteredSurfaceSupply:
    """Annual metered ditch demand and measured shortage for an area."""

    acreage: AcreageClass
    diversion_required_acft: float
    diversion_shortage_acft: float

    @property
    def fractional_shortage(self) -> float:
        return self.diversion_shortage_acft / self.diversion_required_acft if self.diversion_required_acft else 0.0


@dataclass(frozen=True)
class GenericAreaCUInput:
    """Auditable inputs for the standard yellow-box area calculation."""

    area_name: str
    annual_cir_ft: float
    annual_reservoir_net_evap_ft: float
    metered_surface: MeteredSurfaceSupply
    unmetered_surface: AcreageClass
    groundwater: AcreageClass
    preplant_acres: float = 0.0


@dataclass(frozen=True)
class GenericAreaCUResult:
    area_name: str
    fractional_surface_shortage: float
    total_acres: float
    full_supply_cu_af: float
    shortage_to_cu_af: float
    crop_and_pond_cu_af: float
    groundwater_cu_af: float
    incidental_losses_af: float
    total_irrigated_cu_af: float


@dataclass(frozen=True)
class CRPMeasuredUse:
    """CRP/natural-grassland area whose CU is the recorded diversion."""

    acres: float = 0.0
    measured_diversion_acft: float = 0.0


@dataclass(frozen=True)
class SpecialAreaCUInput:
    """Redrock/San Simon layout with full-CIR and CRP measured-use classes."""

    area_name: str
    annual_cir_ft: float
    annual_reservoir_net_evap_ft: float
    metered_surface: MeteredSurfaceSupply
    unmetered_surface: AcreageClass = AcreageClass()
    groundwater: AcreageClass = AcreageClass()
    groundwater_cu_override_af: float | None = None
    metered_full_cir: AcreageClass = AcreageClass()
    crp_measured_use: CRPMeasuredUse = CRPMeasuredUse()
    incidental_base_rate: float = 0.0
    incidental_groundwater_supplement_rate: float = 0.0


@dataclass(frozen=True)
class SpecialAreaCUResult:
    area_name: str
    total_acres: float
    full_supply_cu_af: float
    shortage_to_cu_af: float
    crop_and_pond_cu_af: float
    groundwater_cu_af: float
    incidental_losses_af: float
    total_irrigated_cu_af: float


def calculate_generic_area_cu(inputs: GenericAreaCUInput) -> GenericAreaCUResult:
    """Calculate the common area-sheet rows used by seven 2024 area layouts.

    Workbook equivalence:

    - the metered fraction is ``I_total / H_total``;
    - that fraction applies to metered and unmetered *surface* CU only;
    - groundwater CU is full supply; and
    - incidental use is 10% of surface CU plus 2% of groundwater CU.
    """

    _validate(inputs)
    metered_cu = inputs.metered_surface.acreage.full_supply_cu(
        annual_cir_ft=inputs.annual_cir_ft,
        annual_reservoir_net_evap_ft=inputs.annual_reservoir_net_evap_ft,
    )
    surface_cu = inputs.unmetered_surface.full_supply_cu(
        annual_cir_ft=inputs.annual_cir_ft,
        annual_reservoir_net_evap_ft=inputs.annual_reservoir_net_evap_ft,
    )
    groundwater_cu = inputs.groundwater.full_supply_cu(
        annual_cir_ft=inputs.annual_cir_ft,
        annual_reservoir_net_evap_ft=inputs.annual_reservoir_net_evap_ft,
    )
    fraction = inputs.metered_surface.fractional_shortage
    shortage = (metered_cu + surface_cu) * fraction
    full_supply = metered_cu + surface_cu + groundwater_cu
    crop_and_pond = full_supply - shortage
    incidental = (crop_and_pond - groundwater_cu) * 0.10 + groundwater_cu * 0.02
    total_acres = (
        inputs.metered_surface.acreage.total_acres
        + inputs.unmetered_surface.total_acres
        + inputs.groundwater.total_acres
        + inputs.preplant_acres
    )
    return GenericAreaCUResult(
        area_name=inputs.area_name,
        fractional_surface_shortage=fraction,
        total_acres=total_acres,
        full_supply_cu_af=full_supply,
        shortage_to_cu_af=shortage,
        crop_and_pond_cu_af=crop_and_pond,
        groundwater_cu_af=groundwater_cu,
        incidental_losses_af=incidental,
        total_irrigated_cu_af=crop_and_pond + incidental,
    )


def calculate_special_area_cu(inputs: SpecialAreaCUInput) -> SpecialAreaCUResult:
    """Calculate the Redrock/San Simon special class layout.

    The extra ``metered_full_cir`` class is full supply and does not receive
    the surface-shortage fraction.  CRP/natural-grassland CU is its recorded
    diversion, matching the special workbook column that does not apply CIR.
    """

    _validate_special(inputs)
    metered_cu = inputs.metered_surface.acreage.full_supply_cu(
        annual_cir_ft=inputs.annual_cir_ft,
        annual_reservoir_net_evap_ft=inputs.annual_reservoir_net_evap_ft,
    )
    unmetered_surface_cu = inputs.unmetered_surface.full_supply_cu(
        annual_cir_ft=inputs.annual_cir_ft,
        annual_reservoir_net_evap_ft=inputs.annual_reservoir_net_evap_ft,
    )
    groundwater_cu = (
        inputs.groundwater_cu_override_af
        if inputs.groundwater_cu_override_af is not None
        else inputs.groundwater.full_supply_cu(
            annual_cir_ft=inputs.annual_cir_ft,
            annual_reservoir_net_evap_ft=inputs.annual_reservoir_net_evap_ft,
        )
    )
    full_cir_cu = inputs.metered_full_cir.full_supply_cu(
        annual_cir_ft=inputs.annual_cir_ft,
        annual_reservoir_net_evap_ft=inputs.annual_reservoir_net_evap_ft,
    )
    shortage = (metered_cu + unmetered_surface_cu) * inputs.metered_surface.fractional_shortage
    full_supply = (
        metered_cu + unmetered_surface_cu + groundwater_cu + full_cir_cu
        + inputs.crp_measured_use.measured_diversion_acft
    )
    total_acres = (
        inputs.metered_surface.acreage.total_acres + inputs.unmetered_surface.total_acres
        + inputs.groundwater.total_acres + inputs.metered_full_cir.total_acres
        + inputs.crp_measured_use.acres
    )
    crop_and_pond = full_supply - shortage
    # Redrock's legacy layout applies 10% to all crop/pond CU plus an
    # additional 2% groundwater amount.  San Simon has no incidental-use
    # addition.  The rates make that policy explicit instead of burying it in
    # the Table II formula.
    incidental = (
        crop_and_pond * inputs.incidental_base_rate
        + groundwater_cu * inputs.incidental_groundwater_supplement_rate
    )
    return SpecialAreaCUResult(
        area_name=inputs.area_name,
        total_acres=total_acres,
        full_supply_cu_af=full_supply,
        shortage_to_cu_af=shortage,
        crop_and_pond_cu_af=crop_and_pond,
        groundwater_cu_af=groundwater_cu,
        incidental_losses_af=incidental,
        total_irrigated_cu_af=crop_and_pond + incidental,
    )


def _validate(inputs: GenericAreaCUInput) -> None:
    values = (
        inputs.annual_cir_ft,
        inputs.annual_reservoir_net_evap_ft,
        inputs.metered_surface.diversion_required_acft,
        inputs.metered_surface.diversion_shortage_acft,
        inputs.preplant_acres,
        inputs.metered_surface.acreage.crop_acres,
        inputs.metered_surface.acreage.reservoir_acres,
        inputs.unmetered_surface.crop_acres,
        inputs.unmetered_surface.reservoir_acres,
        inputs.groundwater.crop_acres,
        inputs.groundwater.reservoir_acres,
    )
    if any(value < 0 for value in values):
        raise ValueError("Area CU inputs cannot be negative")
    if inputs.metered_surface.diversion_shortage_acft > inputs.metered_surface.diversion_required_acft:
        raise ValueError("Diversion shortage cannot exceed diversion required")


def _validate_special(inputs: SpecialAreaCUInput) -> None:
    _validate(GenericAreaCUInput(
        area_name=inputs.area_name,
        annual_cir_ft=inputs.annual_cir_ft,
        annual_reservoir_net_evap_ft=inputs.annual_reservoir_net_evap_ft,
        metered_surface=inputs.metered_surface,
        unmetered_surface=inputs.unmetered_surface,
        groundwater=inputs.groundwater,
    ))
    if inputs.metered_full_cir.crop_acres < 0 or inputs.metered_full_cir.reservoir_acres < 0:
        raise ValueError("Metered full-CIR acreage cannot be negative")
    if inputs.crp_measured_use.acres < 0 or inputs.crp_measured_use.measured_diversion_acft < 0:
        raise ValueError("CRP acres and diversion cannot be negative")
    if inputs.groundwater_cu_override_af is not None and inputs.groundwater_cu_override_af < 0:
        raise ValueError("Groundwater CU override cannot be negative")
    if inputs.incidental_base_rate < 0 or inputs.incidental_groundwater_supplement_rate < 0:
        raise ValueError("Incidental-use rates cannot be negative")
