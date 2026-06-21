from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from w2.domain.time import require_utc


class HistoricalSourceStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NOT_SELECTED = "NOT_SELECTED"


@dataclass(frozen=True, kw_only=True)
class HistoricalSourceRegistry:
    source_id: str
    provider: str
    national_or_club: str
    competitions: tuple[str, ...]
    seasons: tuple[str, ...]
    date_range: tuple[datetime, datetime]
    fixtures_coverage: HistoricalSourceStatus
    results_coverage: HistoricalSourceStatus
    one_x_two_coverage: HistoricalSourceStatus
    asian_handicap_coverage: HistoricalSourceStatus
    totals_coverage: HistoricalSourceStatus
    lineups_coverage: HistoricalSourceStatus
    injuries_coverage: HistoricalSourceStatus
    opening_capability: HistoricalSourceStatus
    first_seen_capability: HistoricalSourceStatus
    closing_capability: HistoricalSourceStatus
    snapshot_frequency: str
    provider_ids: tuple[str, ...]
    provenance: str
    licence_commercial_use_status: HistoricalSourceStatus
    acquisition_status: HistoricalSourceStatus
    validation_status: HistoricalSourceStatus
    notes: str = ""

    def __post_init__(self) -> None:
        if self.national_or_club not in {"national", "club"}:
            raise ValueError("national_or_club must be national or club")
        start, end = self.date_range
        object.__setattr__(
            self, "date_range", (require_utc(start, "start"), require_utc(end, "end"))
        )
        for field_name, value in self.__dict__.items():
            if (
                field_name.endswith("_status")
                or field_name.endswith("_coverage")
                or field_name.endswith("_capability")
            ):
                if not isinstance(value, HistoricalSourceStatus):
                    raise ValueError(f"{field_name} must be HistoricalSourceStatus")


def registry_to_manifest(source: HistoricalSourceRegistry) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "provider": source.provider,
        "national_or_club": source.national_or_club,
        "competitions": list(source.competitions),
        "seasons": list(source.seasons),
        "date_range": [source.date_range[0].isoformat(), source.date_range[1].isoformat()],
        "coverage": {
            "fixtures": source.fixtures_coverage.value,
            "results": source.results_coverage.value,
            "1X2": source.one_x_two_coverage.value,
            "AH": source.asian_handicap_coverage.value,
            "OU": source.totals_coverage.value,
            "lineups": source.lineups_coverage.value,
            "injuries": source.injuries_coverage.value,
        },
        "capability": {
            "opening": source.opening_capability.value,
            "first_seen": source.first_seen_capability.value,
            "closing": source.closing_capability.value,
        },
        "snapshot_frequency": source.snapshot_frequency,
        "provider_ids": list(source.provider_ids),
        "provenance": source.provenance,
        "licence_commercial_use_status": source.licence_commercial_use_status.value,
        "acquisition_status": source.acquisition_status.value,
        "validation_status": source.validation_status.value,
        "notes": source.notes,
    }
