from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from w2.domain.time import require_utc

ROOT = Path(__file__).resolve().parents[3]


class ContextValidationStatus(StrEnum):
    EXPLANATORY_ONLY_UNVALIDATED = "EXPLANATORY_ONLY_UNVALIDATED"


@dataclass(frozen=True, kw_only=True)
class TournamentStage:
    stage_id: str
    name: str
    stage_type: str
    result_semantics: str


@dataclass(frozen=True, kw_only=True)
class GroupDefinition:
    group_id: str
    qualification_rule_id: str
    team_slots: int


@dataclass(frozen=True, kw_only=True)
class KnockoutRound:
    round_id: str
    name: str
    entrant_count: int
    extra_time_enabled: bool
    penalties_enabled: bool


@dataclass(frozen=True, kw_only=True)
class QualificationRule:
    rule_id: str
    description: str
    advances: int
    tie_breakers: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class OperationsSchedule:
    collection_phases: tuple[str, ...]
    lineup_expected_window_minutes: int
    settlement_delay_hours: int
    gate_audit_hour_utc: int


@dataclass(frozen=True, kw_only=True)
class TournamentProfile:
    competition_id: str
    version: str
    provider_mapping: dict[str, str]
    season: str
    hosts: tuple[str, ...]
    neutral_site_policy: str
    stages: tuple[TournamentStage, ...]
    groups: tuple[GroupDefinition, ...]
    knockout_rounds: tuple[KnockoutRound, ...]
    qualification_rules: tuple[QualificationRule, ...]
    operations_schedule: OperationsSchedule
    strategy_version: str
    freeze_policy: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class MatchContext:
    fixture_id: str
    competition_id: str
    kickoff_utc: datetime
    stage_id: str
    neutral_site: bool
    host_context: str

    def __post_init__(self) -> None:
        require_utc(self.kickoff_utc, "kickoff_utc")


@dataclass(frozen=True, kw_only=True)
class MatchImportanceContext:
    fixture_id: str
    group_standings_context: str
    qualification_state: str
    must_win: bool
    draw_sufficient: bool
    eliminated: bool
    qualified: bool
    knockout_path: str
    rest_days: int | None
    host_context: str
    validation_status: ContextValidationStatus = (
        ContextValidationStatus.EXPLANATORY_ONLY_UNVALIDATED
    )
    model_feature_enabled: bool = False


def load_tournament_profile(path: Path) -> TournamentProfile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TournamentProfile(
        competition_id=payload["competition_id"],
        version=payload["version"],
        provider_mapping=payload["provider_mapping"],
        season=payload["season"],
        hosts=tuple(payload["hosts"]),
        neutral_site_policy=payload["neutral_site_policy"],
        stages=tuple(TournamentStage(**item) for item in payload["stages"]),
        groups=tuple(GroupDefinition(**item) for item in payload["groups"]),
        knockout_rounds=tuple(KnockoutRound(**item) for item in payload["knockout_rounds"]),
        qualification_rules=tuple(
            QualificationRule(
                rule_id=item["rule_id"],
                description=item["description"],
                advances=item["advances"],
                tie_breakers=tuple(item["tie_breakers"]),
            )
            for item in payload["qualification_rules"]
        ),
        operations_schedule=OperationsSchedule(**payload["operations_schedule"]),
        strategy_version=payload["strategy_version"],
        freeze_policy=payload["freeze_policy"],
    )


def load_stage5b_world_cup_fixtures(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        item
        for item in rows
        if str(item.get("competition", "")).lower().startswith("worldcup")
    ]


def kickoff_from_stage5b(row: dict[str, Any]) -> datetime:
    raw_date = str(row.get("match_date"))
    return datetime.combine(datetime.fromisoformat(raw_date).date(), time(18, 0), tzinfo=UTC)


def build_match_context(row: dict[str, Any], profile: TournamentProfile) -> MatchContext:
    stage_id = "qualifying" if "qualifier" in str(row.get("competition", "")).lower() else "group"
    return MatchContext(
        fixture_id=str(row["fixture_uuid"]),
        competition_id=profile.competition_id,
        kickoff_utc=kickoff_from_stage5b(row),
        stage_id=stage_id,
        neutral_site=bool(row.get("neutral_site", False)),
        host_context="HOST_CONTEXT_CONFIGURED" if row.get("neutral_site") else "STANDARD_CONTEXT",
    )


def build_importance_context(match: MatchContext) -> MatchImportanceContext:
    return MatchImportanceContext(
        fixture_id=match.fixture_id,
        group_standings_context="GROUP_TABLE_REQUIRES_VALIDATED_STANDINGS_FEED",
        qualification_state="UNKNOWN_UNTIL_VALIDATED_TABLE",
        must_win=False,
        draw_sufficient=False,
        eliminated=False,
        qualified=False,
        knockout_path="NOT_APPLICABLE_OR_UNVALIDATED",
        rest_days=None,
        host_context=match.host_context,
    )


def build_operations_plan(
    profile: TournamentProfile,
    fixtures: list[dict[str, Any]],
    *,
    limit: int = 48,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    sorted_fixtures = sorted(
        fixtures,
        key=lambda item: (str(item.get("match_date")), str(item.get("fixture_uuid"))),
    )
    for row in sorted_fixtures[:limit]:
        match = build_match_context(row, profile)
        phase_plan = []
        for phase in profile.operations_schedule.collection_phases:
            if phase == "Closing":
                scheduled_at = match.kickoff_utc - timedelta(minutes=10)
            else:
                hours = int(phase.removeprefix("T-").removesuffix("h"))
                scheduled_at = match.kickoff_utc - timedelta(hours=hours)
            phase_plan.append({"phase": phase, "scheduled_at": scheduled_at.isoformat()})
        lineup_check = match.kickoff_utc - timedelta(
            minutes=profile.operations_schedule.lineup_expected_window_minutes
        )
        plan.append(
            {
                "fixture_id": match.fixture_id,
                "competition_id": match.competition_id,
                "stage_id": match.stage_id,
                "kickoff_utc": match.kickoff_utc.isoformat(),
                "neutral_site": match.neutral_site,
                "phase_plan": phase_plan,
                "lineup_check_at": lineup_check.isoformat(),
                "closing_cutoff_at": (match.kickoff_utc - timedelta(minutes=10)).isoformat(),
                "watch_skip_lock_windows": [
                    {
                        "phase": "T-24h",
                        "lock_at": (match.kickoff_utc - timedelta(hours=24)).isoformat(),
                    },
                    {
                        "phase": "T-1h",
                        "lock_at": (match.kickoff_utc - timedelta(hours=1)).isoformat(),
                    },
                ],
                "settlement_at": (
                    match.kickoff_utc
                    + timedelta(hours=profile.operations_schedule.settlement_delay_hours)
                ).isoformat(),
                "gate_audit_at": datetime.combine(
                    match.kickoff_utc.date(),
                    time(profile.operations_schedule.gate_audit_hour_utc, 0),
                    tzinfo=UTC,
                ).isoformat(),
                "importance_context": build_importance_context(match).__dict__,
            }
        )
    return plan


def readiness_report(profile: TournamentProfile, plan: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = []
    if profile.strategy_version != "NOT_AVAILABLE_GATE4":
        blockers.append("STRATEGY_VERSION_MUST_BE_NOT_AVAILABLE_GATE4")
    if not plan:
        blockers.append("WORLD_CUP_FIXTURE_COVERAGE_MISSING")
    payload = {
        "competition_id": profile.competition_id,
        "profile_version": profile.version,
        "fixture_coverage_count": len(plan),
        "data_coverage": {
            "stage5b_world_cup_fixture_source": "AVAILABLE" if plan else "MISSING",
            "market_data": "READINESS_ONLY",
            "lineup_data": "EXPECTED_WINDOW_CONFIGURED",
        },
        "phase_count_per_fixture": len(profile.operations_schedule.collection_phases),
        "gate_status": "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "strategy_version": profile.strategy_version,
        "production_deployment": "DISABLED",
        "shadow_runtime": "DISABLED_PENDING_GATE4",
        "blockers": blockers,
    }
    payload["readiness_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    return payload
