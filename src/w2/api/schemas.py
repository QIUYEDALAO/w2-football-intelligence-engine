from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorPayload(BaseModel):
    request_id: str
    code: str
    message: str


class PageMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int


class FixtureSummary(BaseModel):
    fixture_id: str
    competition_id: str
    competition_name: str
    kickoff_utc: datetime
    kickoff_beijing: str | None = None
    operational_date_beijing: str | None = None
    kickoff_display: str
    status: str
    home_team_id: str
    home_team_name: str | None = None
    away_team_id: str
    away_team_name: str | None = None
    lifecycle_state: str
    data_state: str
    published_grade: str | None = None
    primary_market: str | None = None
    primary_line: str | None = None
    primary_odds: str | None = None
    last_captured: datetime | None = None


class FixtureListResponse(BaseModel):
    request_id: str
    meta: PageMeta
    items: list[FixtureSummary]


class FixtureDetailResponse(FixtureSummary):
    request_id: str
    venue: str | None
    bookmaker_count: int
    market_coverage: dict[str, bool]
    forward_decision: str
    provenance: dict[str, str]
    risk_notes: list[str]
    primary_market: str | None = None
    primary_selection: str | None = None
    primary_line: str | None = None
    primary_executable_odds: str | None = None
    primary_hong_kong_odds: str | None = None
    primary_model_fair_odds: str | None = None
    primary_risk_adjusted_ev: str | None = None
    research_grade: str | None = None
    ah_ladder: list[dict[str, Any]] = Field(default_factory=list)
    ou_ladder: list[dict[str, Any]] = Field(default_factory=list)
    all_market_ranking: list[dict[str, Any]] = Field(default_factory=list)
    one_x_two_ranking: list[dict[str, Any]] = Field(default_factory=list)
    btts_ranking: list[dict[str, Any]] = Field(default_factory=list)
    secondary_market_direction: dict[str, Any] | None = None
    source_snapshot_id: str | None = None
    source_captured_at: datetime | None = None
    source_phase: str | None = None
    valuation_generated_at: datetime | None = None
    projector_generated_at: datetime | None = None
    temporal_status: str | None = None
    integrity_status: str | None = None
    analysis_card: dict[str, Any] | None = None


class OddsPoint(BaseModel):
    captured_at: datetime
    snapshot_semantics: str
    market: str
    selection: str
    line: str | None
    decimal_odds: str | None
    bookmaker_count: int
    bookmaker: str | None = None
    first_seen: bool
    closing: bool


class OddsTimelineResponse(BaseModel):
    request_id: str
    fixture_id: str
    items: list[OddsPoint]


class ProbabilityResponse(BaseModel):
    request_id: str
    fixture_id: str
    probability_type: str
    probabilities: dict[str, float]
    calibrated: bool = False
    source: str
    as_of_time: datetime | None = None
    quality: str


class MatchdayResponse(BaseModel):
    request_id: str
    date: str
    total: int
    items: list[dict[str, Any]]


class MatchdayCoverageResponse(BaseModel):
    request_id: str
    requested_date_beijing: str
    timezone: str
    window_start_beijing: str
    window_end_beijing: str
    window_start_utc: str
    window_end_utc: str
    authoritative_count: int
    discovered_count: int
    eligible_count: int
    card_count: int
    read_model_count: int
    displayed_count: int
    missing_count: int
    reason_distribution: dict[str, int]
    coverage_status: str


class ResearchCardResponse(BaseModel):
    request_id: str
    fixture_id: str
    card: dict[str, Any]


class AnalysisCardResponse(BaseModel):
    request_id: str
    fixture_id: str
    card: dict[str, Any]


class MarketRankingResponse(BaseModel):
    request_id: str
    fixture_id: str
    items: list[dict[str, Any]]


class IntegrityResponse(BaseModel):
    request_id: str
    fixture_id: str
    integrity: dict[str, Any]


class DataHealthResponse(BaseModel):
    request_id: str
    stale_data_count: int
    provider_status: str
    forward_cycle_age_seconds: int | None
    gate4_progress: dict[str, Any]
    generated_at: datetime


class ProviderStatusResponse(BaseModel):
    request_id: str
    provider: str
    status: str
    remaining_quota: int | None
    credential_status: str
    last_request_status: int | None
    blockers: list[str] = Field(default_factory=list)


class BacktestLatestResponse(BaseModel):
    request_id: str
    status: str
    gate4_national_1x2: str
    metrics: dict[str, Any]


class ForwardHoldoutStatusResponse(BaseModel):
    request_id: str
    status: str
    locks: int
    market_comparable: int
    current_settled_n: int
    target_n: int


class OperationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    status: str
    payload: dict[str, Any]


class OperationListResponse(BaseModel):
    request_id: str
    items: list[OperationItem]


class CompetitionOperationsProfileResponse(BaseModel):
    request_id: str
    competition_id: str
    version: str
    season: str
    hosts: list[str]
    neutral_site_policy: str
    stages: list[dict[str, Any]]
    groups: list[dict[str, Any]]
    knockout_rounds: list[dict[str, Any]]
    operations_schedule: dict[str, Any]
    strategy_version: str
    freeze_policy: dict[str, Any]


class WorldCupReadinessResponse(BaseModel):
    request_id: str
    competition_id: str
    profile_version: str
    fixture_coverage_count: int
    data_coverage: dict[str, Any]
    phase_count_per_fixture: int
    gate_status: str
    strategy_version: str
    production_deployment: str
    shadow_runtime: str
    blockers: list[str]


class LeagueSummary(BaseModel):
    competition_id: str
    name: str
    country: str
    results_status: str
    market_status: dict[str, str]
    latest_season: str | None
    blocker: str | None


class LeagueListResponse(BaseModel):
    request_id: str
    items: list[LeagueSummary]


class LeagueReadinessResponse(BaseModel):
    request_id: str
    competition_id: str
    audit: dict[str, Any]
    rollover: dict[str, Any]
    checklist: dict[str, str]
    model_scope_policy: dict[str, Any]


class LeagueOnboardingResponse(BaseModel):
    request_id: str
    items: list[LeagueReadinessResponse]


class OperationsCycleResponse(BaseModel):
    request_id: str
    items: list[dict[str, Any]]


class OperationsLatestResponse(BaseModel):
    request_id: str
    latest: dict[str, Any]


class ReleaseReadinessResponse(BaseModel):
    request_id: str
    approval_status: str
    production_release: str
    dependency_blocker: str | None


class RetentionStatusResponse(BaseModel):
    request_id: str
    status: str
    policy: dict[str, Any]


class ShadowStrategyStatusResponse(BaseModel):
    request_id: str
    status: str
    strategy_version: str
    gate4_status: str
    gate5_status: str
    formal_recommendation: bool
    candidate: bool
    decisions: int
    locks: int
    latest_run_id: str | None
