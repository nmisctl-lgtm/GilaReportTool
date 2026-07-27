"""Auditable monthly diversion-demand and shortage calculations.

This is the common calculation underlying the metered-ditch blocks in the
2024 workbook.  Area-specific classification of groundwater/estimated supply
belongs in a separate policy layer; this module deliberately requires that
decision as an explicit input instead of silently inferring it from a zero or
missing diversion value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MeasurementStatus = Literal["metered", "estimated", "unavailable"]


@dataclass(frozen=True)
class QAIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str
    ditch_id: str | None = None
    month: int | None = None


@dataclass(frozen=True)
class DitchInput:
    """Raw monthly data and explicit assessment policy for one ditch."""

    ditch_id: str
    name: str
    crop_acres: float
    reservoir_acres: float
    monthly_diversion_acft: tuple[float | None, ...]
    measurement_status: tuple[MeasurementStatus, ...]
    shortage_assessed: tuple[bool, ...]
    monthly_reservoir_net_evap_override_acft: tuple[float | None, ...] | None = None

    def __post_init__(self) -> None:
        if not all(len(values) == 12 for values in (
            self.monthly_diversion_acft, self.measurement_status, self.shortage_assessed
        )):
            raise ValueError("DitchInput requires exactly 12 monthly diversion, status, and assessment values")
        if self.monthly_reservoir_net_evap_override_acft is not None and len(
            self.monthly_reservoir_net_evap_override_acft
        ) != 12:
            raise ValueError("Reservoir net-evaporation overrides must contain exactly 12 values")


@dataclass(frozen=True)
class MonthlyDitchLedger:
    month: int
    diversion_acft: float | None
    measurement_status: MeasurementStatus
    shortage_assessed: bool
    crop_cu_demand_acft: float
    reservoir_net_evap_acft: float
    crop_diversion_required_acft: float
    reservoir_diversion_required_acft: float
    total_diversion_required_acft: float
    diversion_shortage_acft: float


@dataclass(frozen=True)
class DitchLedger:
    ditch_id: str
    name: str
    monthly: tuple[MonthlyDitchLedger, ...]

    @property
    def annual_diversion_required_acft(self) -> float:
        return sum(row.total_diversion_required_acft for row in self.monthly)

    @property
    def annual_assessed_shortage_acft(self) -> float:
        return sum(row.diversion_shortage_acft for row in self.monthly)


@dataclass(frozen=True)
class AreaDiversionLedger:
    area_name: str
    efficiency: float
    ditches: tuple[DitchLedger, ...]

    @property
    def diversion_required_acft(self) -> float:
        return sum(ditch.annual_diversion_required_acft for ditch in self.ditches)

    @property
    def assessed_shortage_acft(self) -> float:
        return sum(ditch.annual_assessed_shortage_acft for ditch in self.ditches)

    @property
    def fractional_shortage_to_required(self) -> float:
        required = self.diversion_required_acft
        return self.assessed_shortage_acft / required if required else 0.0


def validate_ledger_inputs(
    *,
    efficiency: float,
    monthly_cir_ft: tuple[float, ...],
    monthly_pan_evap_ft: tuple[float, ...],
    monthly_precip_ft: tuple[float, ...],
    ditches: tuple[DitchInput, ...],
) -> tuple[QAIssue, ...]:
    """Return input-quality findings without changing any raw values."""

    issues: list[QAIssue] = []
    if not 0 < efficiency <= 1:
        issues.append(QAIssue("error", "invalid_efficiency", "Diversion-to-CU efficiency must be in (0, 1]."))
    for label, values in (
        ("monthly_cir_ft", monthly_cir_ft),
        ("monthly_pan_evap_ft", monthly_pan_evap_ft),
        ("monthly_precip_ft", monthly_precip_ft),
    ):
        if len(values) != 12:
            issues.append(QAIssue("error", "invalid_month_count", f"{label} must contain 12 values."))
        elif any(value < 0 for value in values):
            issues.append(QAIssue("error", "negative_depth", f"{label} cannot contain negative depths."))
    for ditch in ditches:
        if ditch.crop_acres < 0 or ditch.reservoir_acres < 0:
            issues.append(QAIssue("error", "negative_acres", "Crop and reservoir acres cannot be negative.", ditch.ditch_id))
        for month, (diversion, status, assessed) in enumerate(zip(
            ditch.monthly_diversion_acft, ditch.measurement_status, ditch.shortage_assessed
        ), 1):
            if diversion is not None and diversion < 0:
                issues.append(QAIssue("error", "negative_diversion", "Diversion cannot be negative.", ditch.ditch_id, month))
            if status == "metered" and diversion is None:
                issues.append(QAIssue("error", "missing_metered_diversion", "Metered month has no diversion value.", ditch.ditch_id, month))
            if assessed and (status != "metered" or diversion is None):
                issues.append(QAIssue("error", "invalid_shortage_assessment", "Shortage can be assessed only from a present metered diversion.", ditch.ditch_id, month))
            if status == "unavailable" and not assessed:
                issues.append(QAIssue("warning", "unassessed_unavailable_month", "No shortage is inferred from unavailable data; a policy decision is required.", ditch.ditch_id, month))
        if ditch.monthly_reservoir_net_evap_override_acft is not None:
            for month, value in enumerate(ditch.monthly_reservoir_net_evap_override_acft, 1):
                if value is not None and value < 0:
                    issues.append(QAIssue(
                        "error", "negative_reservoir_net_evap_override",
                        "Reservoir net-evaporation override cannot be negative.", ditch.ditch_id, month,
                    ))
    return tuple(issues)


def calculate_ditch_ledger(
    ditch: DitchInput,
    *,
    efficiency: float,
    monthly_cir_ft: tuple[float, ...],
    monthly_pan_evap_ft: tuple[float, ...],
    monthly_precip_ft: tuple[float, ...],
) -> DitchLedger:
    """Calculate crop/reservoir requirements and assessed monthly shortfall."""

    issues = validate_ledger_inputs(
        efficiency=efficiency,
        monthly_cir_ft=monthly_cir_ft,
        monthly_pan_evap_ft=monthly_pan_evap_ft,
        monthly_precip_ft=monthly_precip_ft,
        ditches=(ditch,),
    )
    errors = [issue.message for issue in issues if issue.severity == "error"]
    if errors:
        raise ValueError("; ".join(errors))
    monthly: list[MonthlyDitchLedger] = []
    reservoir_overrides = ditch.monthly_reservoir_net_evap_override_acft or (None,) * 12
    for month, (cir, pan_evap, precip, diversion, status, assessed, reservoir_override) in enumerate(zip(
        monthly_cir_ft,
        monthly_pan_evap_ft,
        monthly_precip_ft,
        ditch.monthly_diversion_acft,
        ditch.measurement_status,
        ditch.shortage_assessed,
        reservoir_overrides,
    ), 1):
        crop_cu = ditch.crop_acres * cir
        reservoir_net = (
            reservoir_override
            if reservoir_override is not None
            else ditch.reservoir_acres * max(pan_evap - precip, 0.0)
        )
        crop_required = crop_cu / efficiency
        reservoir_required = reservoir_net / efficiency
        required = crop_required + reservoir_required
        shortage = max(required - diversion, 0.0) if assessed and diversion is not None else 0.0
        monthly.append(MonthlyDitchLedger(
            month=month,
            diversion_acft=diversion,
            measurement_status=status,
            shortage_assessed=assessed,
            crop_cu_demand_acft=crop_cu,
            reservoir_net_evap_acft=reservoir_net,
            crop_diversion_required_acft=crop_required,
            reservoir_diversion_required_acft=reservoir_required,
            total_diversion_required_acft=required,
            diversion_shortage_acft=shortage,
        ))
    return DitchLedger(ditch.ditch_id, ditch.name, tuple(monthly))


def calculate_area_diversion_ledger(
    area_name: str,
    *,
    efficiency: float,
    monthly_cir_ft: tuple[float, ...],
    monthly_pan_evap_ft: tuple[float, ...],
    monthly_precip_ft: tuple[float, ...],
    ditches: tuple[DitchInput, ...],
) -> AreaDiversionLedger:
    """Apply the same transparent calculation to every ditch in an area."""

    return AreaDiversionLedger(
        area_name=area_name,
        efficiency=efficiency,
        ditches=tuple(calculate_ditch_ledger(
            ditch,
            efficiency=efficiency,
            monthly_cir_ft=monthly_cir_ft,
            monthly_pan_evap_ft=monthly_pan_evap_ft,
            monthly_precip_ft=monthly_precip_ft,
        ) for ditch in ditches),
    )
