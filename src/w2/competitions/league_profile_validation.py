from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from w2.competitions.registry import CompetitionRegistryEntry

REQUIRED_OBSERVED_FIELDS = (
    "observed_provider_league_id",
    "observed_provider_league_name",
    "observed_provider_country",
    "observed_provider_season",
    "observed_provider_team_count",
)


@dataclass(frozen=True, kw_only=True)
class LeagueProfileValidationResult:
    competition_id: str
    status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    missing_observed_fields: tuple[str, ...]
    provider_calls: int = 0
    db_reads: int = 0
    db_writes: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "competition_id": self.competition_id,
            "status": self.status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "missing_observed_fields": list(self.missing_observed_fields),
            "provider_calls": self.provider_calls,
            "db_reads": self.db_reads,
            "db_writes": self.db_writes,
        }


def validate_league_profile_mapping(
    entry: CompetitionRegistryEntry,
    observed_evidence: Mapping[str, Any] | None,
) -> LeagueProfileValidationResult:
    observed = observed_evidence or {}
    missing = tuple(
        field
        for field in REQUIRED_OBSERVED_FIELDS
        if _missing_observed_value(observed.get(field))
    )
    if missing:
        return LeagueProfileValidationResult(
            competition_id=entry.competition_id,
            status="NEEDS_PROVIDER_EVIDENCE",
            blockers=("NEEDS_PROVIDER_EVIDENCE",),
            warnings=("PROFILE_NOT_MUTATED",),
            missing_observed_fields=missing,
        )

    payload = _profile_payload(entry)
    checks = {
        "league_id": _text(observed.get("observed_provider_league_id"))
        == _text(entry.provider_mapping.get("api_football_league_id")),
        "season": _text(observed.get("observed_provider_season"))
        == _text(entry.provider_mapping.get("api_football_season") or entry.season),
        "name": _norm(observed.get("observed_provider_league_name"))
        == _norm(payload.get("name") or entry.competition_id),
        "country": _norm(observed.get("observed_provider_country"))
        == _norm(payload.get("country")),
        "team_count": _int(observed.get("observed_provider_team_count"))
        == _int(payload.get("expected_team_count")),
    }
    blockers = tuple(
        f"PROFILE_{key.upper()}_REVIEW_REQUIRED" for key, ok in checks.items() if not ok
    )
    if blockers:
        return LeagueProfileValidationResult(
            competition_id=entry.competition_id,
            status="PROFILE_REVIEW_REQUIRED",
            blockers=blockers,
            warnings=("PROFILE_NOT_MUTATED",),
            missing_observed_fields=(),
        )
    return LeagueProfileValidationResult(
        competition_id=entry.competition_id,
        status="PASS",
        blockers=(),
        warnings=(),
        missing_observed_fields=(),
    )


def _profile_payload(entry: CompetitionRegistryEntry) -> dict[str, Any]:
    try:
        payload = json.loads(entry.config_path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _missing_observed_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _norm(value: Any) -> str:
    return _text(value).lower()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
