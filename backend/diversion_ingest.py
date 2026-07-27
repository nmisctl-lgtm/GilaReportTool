"""Daily diversion aggregation and QA, independent of any spreadsheet layout."""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .diversion_ledger import QAIssue


# One mean cubic-foot-per-second day converted to acre-feet.  The legacy flow
# workbook uses this six-decimal factor, so it is retained for report parity.
CFS_DAY_TO_ACRE_FEET = 1.98347


@dataclass(frozen=True)
class DailyDiversionRecord:
    ditch_id: str
    measured_on: date
    mean_cfs: float | None


@dataclass(frozen=True)
class MonthlyDiversionSummary:
    ditch_id: str
    year: int
    month: int
    acre_feet: float
    observed_days: int
    calendar_days: int
    missing_days: tuple[date, ...]

    @property
    def completeness(self) -> float:
        return self.observed_days / self.calendar_days


@dataclass(frozen=True)
class DiversionAggregation:
    monthly: tuple[MonthlyDiversionSummary, ...]
    issues: tuple[QAIssue, ...]


def aggregate_daily_diversions(
    records: Iterable[DailyDiversionRecord], *, year: int
) -> DiversionAggregation:
    """Aggregate CFS-day observations and report coverage/quality defects.

    A zero is a valid observed diversion. ``None`` is missing data and is not
    converted to zero.  This distinction is carried into the downstream
    shortage-assessment policy.
    """

    issues: list[QAIssue] = []
    values: dict[tuple[str, date], float | None] = {}
    ditch_ids: set[str] = set()
    for record in records:
        if record.measured_on.year != year:
            issues.append(QAIssue(
                "error", "outside_report_year", f"Record date {record.measured_on} is outside {year}.",
                record.ditch_id,
            ))
            continue
        ditch_ids.add(record.ditch_id)
        key = (record.ditch_id, record.measured_on)
        if key in values:
            issues.append(QAIssue(
                "error", "duplicate_daily_record", f"Duplicate record for {record.measured_on}.",
                record.ditch_id, record.measured_on.month,
            ))
            continue
        if record.mean_cfs is not None and (not math.isfinite(record.mean_cfs) or record.mean_cfs < 0):
            issues.append(QAIssue(
                "error", "invalid_daily_cfs", "Daily mean CFS must be finite and non-negative.",
                record.ditch_id, record.measured_on.month,
            ))
            continue
        values[key] = record.mean_cfs

    monthly: list[MonthlyDiversionSummary] = []
    for ditch_id in sorted(ditch_ids):
        for month in range(1, 13):
            days = calendar.monthrange(year, month)[1]
            dates = tuple(date(year, month, day) for day in range(1, days + 1))
            observed = [values.get((ditch_id, observed_date)) for observed_date in dates]
            missing = tuple(observed_date for observed_date, value in zip(dates, observed) if value is None)
            total_cfs_days = sum(value for value in observed if value is not None)
            monthly.append(MonthlyDiversionSummary(
                ditch_id=ditch_id,
                year=year,
                month=month,
                acre_feet=total_cfs_days * CFS_DAY_TO_ACRE_FEET,
                observed_days=days - len(missing),
                calendar_days=days,
                missing_days=missing,
            ))
            if missing:
                issues.append(QAIssue(
                    "warning", "incomplete_daily_coverage",
                    f"{len(missing)} of {days} daily values are missing; monthly volume is not complete.",
                    ditch_id, month,
                ))
    return DiversionAggregation(tuple(monthly), tuple(issues))
