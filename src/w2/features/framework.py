from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from w2.competitions.registry import CompetitionRegistry, CoverageProfile
from w2.domain.time import require_utc


class TeamSide(StrEnum):
    HOME = "HOME"
    AWAY = "AWAY"
    NEUTRAL = "NEUTRAL"


class FeatureStatus(StrEnum):
    READY = "READY"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DEGRADED = "DEGRADED"
    NOT_WHITELISTED = "NOT_WHITELISTED"
    LEAKAGE_BLOCKED = "LEAKAGE_BLOCKED"


ACTIVE_COVERAGE_PREFIXES = (
    "API_FOOTBALL",
    "FUTURE_REFRESH",
    "INTERNAL_",
    "TRANSFERMARKT_",
)


@dataclass(frozen=True, kw_only=True)
class FeatureContext:
    fixture_id: str
    competition_id: str
    home_team_id: str
    away_team_id: str
    kickoff_at: datetime
    as_of: datetime
    stage_id: str | None = None
    venue_country: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kickoff_at", require_utc(self.kickoff_at, "kickoff_at"))
        object.__setattr__(self, "as_of", require_utc(self.as_of, "as_of"))


@dataclass(frozen=True, kw_only=True)
class FeatureContribution:
    feature_id: str
    label: str
    status: FeatureStatus
    score: float | None
    weight: float
    side: TeamSide = TeamSide.NEUTRAL
    reason: str
    risk: str | None = None
    coverage_key: str | None = None
    diagnostics: tuple[str, ...] = ()
    observed_at: datetime | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    source_group: str | None = None
    is_independent_signal: bool = False
    proxy_of: str | None = None
    collection_status: str = "NOT_COLLECTED"
    candidate: bool = False
    formal_recommendation: bool = False

    def __post_init__(self) -> None:
        if self.observed_at is not None:
            object.__setattr__(
                self,
                "observed_at",
                require_utc(self.observed_at, f"{self.feature_id}.observed_at"),
            )
        if self.candidate or self.formal_recommendation:
            raise ValueError("analysis features cannot set candidate/formal_recommendation")


@dataclass(frozen=True, kw_only=True)
class FeatureSet:
    fixture_id: str
    competition_id: str
    as_of: datetime
    contributions: tuple[FeatureContribution, ...]
    status: FeatureStatus
    disclaimer: str = "分析参考，非保证盈利"
    candidate: bool = False
    formal_recommendation: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", require_utc(self.as_of, "as_of"))
        if self.candidate or self.formal_recommendation:
            raise ValueError("analysis feature set cannot set candidate/formal_recommendation")


def unavailable_contribution(
    *,
    feature_id: str,
    label: str,
    reason: str,
    weight: float,
    coverage_key: str | None = None,
    diagnostics: tuple[str, ...] = (),
) -> FeatureContribution:
    return FeatureContribution(
        feature_id=feature_id,
        label=label,
        status=FeatureStatus.UNAVAILABLE,
        score=None,
        weight=weight,
        reason=reason,
        coverage_key=coverage_key,
        diagnostics=diagnostics,
    )


def require_competition_enabled(
    context: FeatureContext,
    registry: CompetitionRegistry | None = None,
) -> CoverageProfile | FeatureContribution:
    resolved = registry or CompetitionRegistry()
    entry = resolved.entries().get(context.competition_id)
    if entry is None or not entry.enabled:
        return FeatureContribution(
            feature_id="COMPETITION_WHITELIST",
            label="Competition whitelist",
            status=FeatureStatus.NOT_WHITELISTED,
            score=None,
            weight=0.0,
            reason="COMPETITION_NOT_ENABLED",
            diagnostics=(f"competition_id={context.competition_id}",),
        )
    return entry.coverage_profile


def coverage_available(profile: CoverageProfile, key: str) -> bool:
    value = profile.as_dict().get(key, "")
    unavailable_markers = ("NOT_AUDITED", "UNAVAILABLE", "DISABLED", "MISSING")
    if any(marker in value for marker in unavailable_markers):
        return False
    return value.startswith(ACTIVE_COVERAGE_PREFIXES)


def coverage_or_unavailable(
    *,
    profile: CoverageProfile,
    key: str,
    feature_id: str,
    label: str,
    weight: float,
) -> FeatureContribution | None:
    if coverage_available(profile, key):
        return None
    value = profile.as_dict().get(key, "UNKNOWN")
    return unavailable_contribution(
        feature_id=feature_id,
        label=label,
        reason=f"COVERAGE_UNAVAILABLE:{key}",
        weight=weight,
        coverage_key=key,
        diagnostics=(value,),
    )
