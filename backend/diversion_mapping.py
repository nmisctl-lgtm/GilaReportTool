"""Strict source-channel to report-ditch mapping / 严格的来源水渠到报告水渠映射。

Diversion source labels are identifiers, not names to be normalized or
fuzzy-matched.  A report run must provide an explicit disposition for every
source channel: either it feeds one canonical report ditch, or it is
deliberately excluded with a documented reason.

来源标签是标识符，不允许模糊匹配。每个来源水渠必须明确映射到一个报告水渠，
或填写排除原因；这样 2025 新格式不会把名称相近的水渠错误合并。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from .diversion_ingest import MonthlyDiversionSummary
from .diversion_ledger import QAIssue


MappingDisposition = Literal["report_ditch", "excluded"]


@dataclass(frozen=True)
class SourceDitchMapping:
    """One explicit source disposition / 一个明确的来源水渠处理决定。"""

    source_ditch_id: str
    disposition: MappingDisposition
    canonical_ditch_id: str | None = None
    area_name: str | None = None
    report_ditch_name: str | None = None
    rationale: str | None = None

    def __post_init__(self) -> None:
        is_report_ditch = self.disposition == "report_ditch"
        required = (self.canonical_ditch_id, self.area_name, self.report_ditch_name)
        if is_report_ditch and not all(required):
            raise ValueError("A report-ditch mapping requires canonical id, area, and report ditch name.")
        if not is_report_ditch and any(required):
            raise ValueError("An excluded source must not identify a report ditch.")
        if self.disposition == "excluded" and not self.rationale:
            raise ValueError("An excluded source requires a documented rationale.")


@dataclass(frozen=True)
class MappedMonthlyDiversion:
    """A monthly source volume labelled for the area/report ledger."""

    source_ditch_id: str
    canonical_ditch_id: str
    area_name: str
    report_ditch_name: str
    year: int
    month: int
    acre_feet: float
    observed_days: int
    calendar_days: int


@dataclass(frozen=True)
class DiversionMappingResult:
    mapped_monthly: tuple[MappedMonthlyDiversion, ...]
    issues: tuple[QAIssue, ...]


def map_monthly_diversions(
    monthly: Iterable[MonthlyDiversionSummary], mappings: Iterable[SourceDitchMapping]
) -> DiversionMappingResult:
    """Apply exact mappings and flag all missing/ambiguous dispositions.

    应用精确映射，并标记所有缺失或有歧义的处理决定。

    The current report configuration is one source channel per canonical ditch.
    If a future method intentionally combines sources, it must introduce an
    explicit aggregation policy instead of relying on duplicate mappings here.
    """

    monthly = tuple(monthly)
    mappings = tuple(mappings)
    issues: list[QAIssue] = []
    by_source: dict[str, SourceDitchMapping] = {}
    canonical_sources: dict[str, str] = {}
    for mapping in mappings:
        if mapping.source_ditch_id in by_source:
            issues.append(QAIssue(
                "error", "duplicate_source_mapping",
                "A source channel may have only one mapping disposition.",
                mapping.source_ditch_id,
            ))
            continue
        by_source[mapping.source_ditch_id] = mapping
        if mapping.canonical_ditch_id:
            previous = canonical_sources.setdefault(mapping.canonical_ditch_id, mapping.source_ditch_id)
            if previous != mapping.source_ditch_id:
                issues.append(QAIssue(
                    "error", "duplicate_canonical_mapping",
                    "Multiple source channels require an explicit aggregation policy before sharing a report ditch.",
                    mapping.canonical_ditch_id,
                ))

    source_ids = {summary.ditch_id for summary in monthly}
    for source_id in sorted(source_ids - set(by_source)):
        issues.append(QAIssue(
            "error", "unmapped_source_channel",
            "No explicit source-channel mapping was supplied; name matching is prohibited.",
            source_id,
        ))
    for source_id in sorted(set(by_source) - source_ids):
        issues.append(QAIssue(
            "warning", "configured_source_not_present",
            "Configured source channel is not present in this input.",
            source_id,
        ))

    mapped: list[MappedMonthlyDiversion] = []
    for summary in monthly:
        mapping = by_source.get(summary.ditch_id)
        if mapping is None or mapping.disposition == "excluded":
            continue
        mapped.append(MappedMonthlyDiversion(
            source_ditch_id=summary.ditch_id,
            canonical_ditch_id=mapping.canonical_ditch_id or "",
            area_name=mapping.area_name or "",
            report_ditch_name=mapping.report_ditch_name or "",
            year=summary.year,
            month=summary.month,
            acre_feet=summary.acre_feet,
            observed_days=summary.observed_days,
            calendar_days=summary.calendar_days,
        ))
    return DiversionMappingResult(tuple(mapped), tuple(issues))
