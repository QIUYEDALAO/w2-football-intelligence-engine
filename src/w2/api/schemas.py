from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


class VersionResponse(BaseModel):
    request_id: str
    service: str
    environment: str
    api_git_sha: str
    api_build_time: str | None = None
    release_id: str | None = None
    data_profile: str
    data_source: str
    database_ready: bool
    read_model_fixture_count: int
    matchday_card_count: int
    result_event_count: int
    release_identity: dict[str, Any]
    capability_manifest: dict[str, Any]
    generated_at: datetime


class DashboardResponse(BaseModel):
    request_id: str
    generated_at: datetime
    date: str
    selected_date: str
    selected_football_day: str
    selected_date_has_data: bool
    next_available_date: str | None = None
    football_day_timezone: str
    football_day_cutoff_hour: int
    football_day_start_utc: str
    football_day_end_utc: str
    timezone: str
    window: str
    data_profile: str
    data_source: str
    version: dict[str, Any]
    debug: dict[str, Any]
    performance: dict[str, Any]
    recommendations: list[dict[str, Any]]
    upcoming: list[dict[str, Any]]
    finished: list[dict[str, Any]]
    all: list[dict[str, Any]]


class DashboardDayViewResponse(BaseModel):
    request_id: str
    generated_at: datetime | str | None = None
    date: str
    football_day: str
    selected_football_day: str
    environment: str
    environment_policy: dict[str, Any]
    timezone: str
    window: str
    source: str
    version: dict[str, Any]
    checkpoint_key: str
    would_write_checkpoint: bool
    provider_calls: int
    db_writes: int
    counts: dict[str, Any]
    freshness: dict[str, Any]
    navigation: dict[str, Any]
    degradation: dict[str, Any]
    performance: dict[str, Any] | None = None
    cards: list[dict[str, Any]]


class DashboardSummaryResponse(BaseModel):
    request_id: str
    generated_at: datetime
    date: str
    timezone: str
    window: str
    data_profile: str
    data_source: str
    version: dict[str, Any]
    totals: dict[str, int]
    performance: dict[str, Any]


class ValidationSummaryResponse(BaseModel):
    request_id: str
    generated_at: datetime
    date: str
    timezone: str
    window: str
    data_profile: str
    data_source: str
    version: dict[str, Any]
    validation: dict[str, Any]


class FormalTrackingSummaryResponse(BaseModel):
    request_id: str
    generated_at: datetime | str | None = None
    status: str
    label: str
    min_bucket_samples_for_rate: int
    snapshot_count: int
    settlement_count: int
    sample_count: int
    win_count: int
    win_rate: float | None = None
    roi: float | None = None
    buckets: dict[str, Any]
    not_a_formal_gate: bool = True
    posthoc_only: bool = True


class PerformanceReliabilityBin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lower: float
    upper: float
    count: int = Field(ge=0)
    mean_confidence: float | None
    accuracy: float | None


class PerformanceBootstrap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "INSUFFICIENT"]
    sample_count: int = Field(ge=0)
    metric: str | None = None
    delta: float | None = None
    ci95: list[float] | None = Field(default=None, min_length=2, max_length=2)
    iterations: int | None = Field(default=None, ge=1)
    seed: int | None = None


class PerformanceWindowProjection(BaseModel):
    model_config = ConfigDict(extra="allow")

    finished_result_count: int = Field(ge=0)
    fixture_checkpoint_count: int = Field(ge=0)
    scored_count: int = Field(ge=0)
    not_scorable_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    not_scorable_by_reason: dict[str, int]
    model_log_loss: float | None
    market_log_loss: float | None
    model_minus_market_log_loss: float | None
    model_ece: float | None
    market_ece: float | None
    model_reliability_bins: list[PerformanceReliabilityBin]
    market_reliability_bins: list[PerformanceReliabilityBin]
    paired_log_loss_bootstrap: PerformanceBootstrap
    clv_sample_count: int = Field(ge=0)
    clv_population: Literal["SCORABLE_FINISHED_WITH_CANONICAL_CLV"]
    clv_mean: float | None
    clv_median: float | None
    clv_positive_count: int = Field(ge=0)
    clv_positive_share: float | None
    clv_ci95: list[float] | None = Field(default=None, min_length=2, max_length=2)
    clv_method: str
    canonical_settled_count: int = Field(ge=0)
    canonical_hit_count: int = Field(ge=0)
    canonical_miss_count: int = Field(ge=0)
    canonical_push_count: int = Field(ge=0)
    canonical_void_count: int = Field(ge=0)
    canonical_decisive_count: int = Field(ge=0)
    canonical_hit_rate: float | None
    canonical_hit_rate_status: Literal["AVAILABLE", "INSUFFICIENT_SAMPLE"]
    sample_target: int = Field(gt=0)
    sample_progress: float = Field(ge=0, le=1)
    sample_progress_status: Literal["ACCUMULATING", "TARGET_REACHED"]


class PerformanceCohortProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["w2.performance_projection.v2"]
    projection_version: Literal["eval-01c.v2"]
    checkpoint_key: str
    scoring_window_anchor: datetime
    windows: dict[Literal["7d", "30d", "90d"], PerformanceWindowProjection]
    business_projection_hash: str


class PerformanceFixtureProjection(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: Literal["w2.performance_projection.v2"]
    projection_version: Literal["eval-01c.v2"]
    status: Literal["SCORED", "NOT_SCORABLE", "BLOCKED"]
    fixture_id: str
    kickoff_utc: datetime
    league: str
    evaluation_tier: Literal["STRICT", "ADVISORY", "UNKNOWN"]
    clv_status: str
    clv_decimal: float | None
    canonical_pick_status: Literal[
        "AVAILABLE",
        "NOT_APPLICABLE_NO_CANONICAL_PICK",
        "SETTLEMENT_MISSING",
        "CANONICAL_PICK_CONFLICT",
    ]
    canonical_settlement_outcome: Literal["HIT", "MISS", "PUSH", "VOID"] | None
    canonical_decisive: bool | None
    canonical_exclusion_reason: str | None


class PerformanceClvPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    kickoff_utc: datetime
    league: str
    evaluation_tier: Literal["STRICT", "ADVISORY", "UNKNOWN"]
    clv_decimal: float


class PerformanceClvResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clv_population: Literal["SCORABLE_FINISHED_WITH_CANONICAL_CLV"]
    sample_count: int = Field(ge=0)
    mean: float | None
    median: float | None
    ci95: list[float] | None = Field(default=None, min_length=2, max_length=2)
    positive_count: int = Field(ge=0)
    positive_share: float | None
    method: str
    points: list[PerformanceClvPoint]


class PerformanceCalibrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scored_count: int = Field(ge=0)
    model_log_loss: float | None
    market_log_loss: float | None
    model_minus_market_log_loss: float | None
    model_ece: float | None
    market_ece: float | None
    model_reliability_bins: list[PerformanceReliabilityBin]
    market_reliability_bins: list[PerformanceReliabilityBin]
    paired_log_loss_bootstrap: PerformanceBootstrap


class PerformanceTierRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: Literal["STRICT", "ADVISORY"]
    finished_result_count: int = Field(ge=0)
    scored_count: int = Field(ge=0)
    canonical_settled_count: int = Field(ge=0)
    canonical_hit_rate: float | None
    canonical_hit_rate_status: Literal["AVAILABLE", "INSUFFICIENT_SAMPLE"]
    clv_mean: float | None
    clv_positive_share: float | None


class PerformanceTierComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    STRICT: PerformanceTierRow
    ADVISORY: PerformanceTierRow


class PerformanceSampleProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: int = Field(ge=0)
    target: int = Field(gt=0)
    ratio: float = Field(ge=0, le=1)
    status: Literal["ACCUMULATING", "TARGET_REACHED"]


class PerformanceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finished_result_count: int = Field(ge=0)
    fixture_checkpoint_count: int = Field(ge=0)
    scored_count: int = Field(ge=0)
    not_scorable_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    not_scorable_by_reason: dict[str, int]


class PerformanceCheckpointMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_key: str
    source_hash: str
    created_at: datetime


class PerformanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    projection_version: Literal["eval-01c.v2"]
    scoring_window_anchor: datetime
    selected_window: Literal["7d", "30d", "90d"]
    selected_league: str | None
    selected_tier: Literal["ALL", "STRICT", "ADVISORY"]
    clv: PerformanceClvResponse
    calibration: PerformanceCalibrationResponse
    tier_comparison: PerformanceTierComparison
    sample_progress: PerformanceSampleProgress
    coverage: PerformanceCoverage
    checkpoint_metadata: PerformanceCheckpointMetadata


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
    quota_policy: dict[str, Any] = Field(default_factory=dict)


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
