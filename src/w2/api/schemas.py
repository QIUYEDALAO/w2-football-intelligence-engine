from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

IntelligenceState = Literal[
    "COLLECTION_INCIDENT",
    "DATA_INCOMPLETE",
    "MODEL_DIAGNOSTIC_WARNING",
    "MARKET_ANOMALY",
    "MODEL_MARKET_DISAGREEMENT",
    "MARKET_MOVEMENT",
    "MARKET_STABLE",
]


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
    football_day_timezone: str
    football_day_cutoff_hour: int
    football_day_start_utc: str | None
    football_day_end_utc: str | None
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


class WorkspaceReadContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_calls: Literal[0]
    db_writes: Literal[0]
    would_write_checkpoint: Literal[False]
    no_call_on_read: Literal[True]


class WorkspaceRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: Literal["FOOTBALL_MARKET_INTELLIGENCE_PLUS_MODEL_DIAGNOSTICS"]
    public_dashboard_authority: Literal["NEW_INTELLIGENCE_WORKSPACE_ONLY"]
    active_whitelist_count: Literal[13]
    free_bridge_mode: Literal["SHADOW_ONLY"]
    candidate: Literal["OFF"]
    formal: Literal["OFF"]
    lock: Literal["OFF"]
    production: Literal["OFF"]


class WorkspaceRiskDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: Literal["EVENT_RISK", "DATA_RISK", "MODEL_RISK", "COLLECTION_RISK"]
    status: Literal["OK", "ATTENTION", "INCIDENT"]
    reason_codes: list[str]
    explanation: str
    assessment_status: Literal[
        "ASSESSED_CURRENT", "ASSESSED_INCIDENT", "STALE", "UNASSESSED"
    ] | None = None
    evidence_basis: str | None = None
    source_as_of: datetime | str | None = None


class WorkspaceRisks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_risk: WorkspaceRiskDimension = Field(alias="EVENT_RISK")
    data_risk: WorkspaceRiskDimension = Field(alias="DATA_RISK")
    model_risk: WorkspaceRiskDimension = Field(alias="MODEL_RISK")
    collection_risk: WorkspaceRiskDimension = Field(alias="COLLECTION_RISK")

    @model_validator(mode="after")
    def dimensions_match_axes(self) -> WorkspaceRisks:
        axes = {
            "EVENT_RISK": self.event_risk,
            "DATA_RISK": self.data_risk,
            "MODEL_RISK": self.model_risk,
            "COLLECTION_RISK": self.collection_risk,
        }
        if any(dimension.dimension != name for name, dimension in axes.items()):
            raise ValueError("risk dimension must match its axis")
        return self


class WorkspaceAttentionReadinessContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str | None
    missing_fields: list[str]
    stale_fields: list[str]
    action: str | None


class WorkspaceAttentionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    kickoff_utc: datetime | str | None
    intelligence_state: IntelligenceState
    reason_codes: list[str]
    affected_domains: list[
        Literal["EVENT", "DATA", "MODEL", "COLLECTION", "MARKET"]
    ] = Field(min_length=1)
    factual_summary: str = Field(min_length=1)
    readiness_status: str
    readiness_context: WorkspaceAttentionReadinessContext
    next_eval_at: datetime | str | None
    risks: WorkspaceRisks


class WorkspaceTimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_id: str | None
    captured_at: datetime | str | None
    canonical_line: str | None
    bookmaker_count: int = Field(ge=0)
    prices: dict[str, Any]
    probabilities: dict[str, Any]


class WorkspaceMarket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: Literal["ASIAN_HANDICAP", "TOTALS"]
    status: str
    snapshot_state: Literal[
        "NO_TIMELINE_EVIDENCE",
        "ONE_OBSERVATION_NOT_A_TREND",
        "DISCRETE_REAL_PATH",
    ]
    snapshot_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    main_line: str | None
    bookmaker_count: int = Field(ge=0)
    prices: dict[str, Any]
    probabilities: dict[str, Any]
    freshness: dict[str, Any]
    timeline_points: list[WorkspaceTimelinePoint]
    movement: dict[str, Any]
    reason_codes: list[str]


class WorkspaceReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    reason_code: str | None
    reason_codes: list[str]
    missing_fields: list[str]
    stale_fields: list[str]
    action: str | None
    next_eval_at: datetime | str | None
    provider_budget_status: str | None
    lineup_status: str | None
    lineup_expectation: str | None


class WorkspaceMarketFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    main_line: str | None
    current_odds: dict[str, Any]
    market_probabilities: dict[str, Any]
    price_reference: Literal["LAST_AVAILABLE_PREMATCH_SNAPSHOT"]
    canonical_close_status: Literal["NOT_OBTAINABLE_FROM_CURRENT_PROVIDER"]


class WorkspaceModelView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    source_status: str
    model_version: str | None
    calibration_version: str | None
    calibration_status: str | None
    simulations_completed: int | None = Field(default=None, ge=1)


class WorkspaceModelRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: Literal["ASIAN_HANDICAP", "TOTALS"]
    status: str
    canonical_line: str | None
    bookmaker_count: int = Field(ge=0)
    freshness_status: str | None
    diagnostics: list[dict[str, Any]]
    blockers: list[str]


class WorkspaceW2Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ANALYSIS_REFERENCE"]
    proof_status: Literal["NOT_PROVEN"]
    decision_tier: str
    analysis_state: str
    reason_codes: list[str]
    model_view: WorkspaceModelView
    model_market_relation: dict[str, WorkspaceModelRelation]


class WorkspaceFormalRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["OFF"]
    reason: Literal["PRODUCT_AUTHORITY_DISABLED"]


class WorkspaceMarketRadar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    markets: dict[str, WorkspaceMarket]


class WorkspaceModelSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    source_status: str
    model_version: str | None
    calibration_status: str | None


class WorkspaceMarketSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    main_line: str | None
    bookmaker_count: int = Field(ge=0)
    freshness: dict[str, Any]


class WorkspaceApiFootballPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["NOT_AVAILABLE"]
    role: Literal["EXTERNAL_MODEL_BENCHMARK"]
    reason_code: Literal["API_FOOTBALL_PREDICTION_NOT_PROJECTED"]


class WorkspaceModelLab(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    w2_model: WorkspaceModelSummary
    market: dict[str, WorkspaceMarketSummary]
    api_football_prediction: WorkspaceApiFootballPrediction
    relation: dict[str, WorkspaceModelRelation]
    historical_validation: dict[str, Any]


class WorkspaceScoreline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scoreline: str
    unconditional_probability: float = Field(ge=0, le=1)
    sample_count: int = Field(ge=0)


class WorkspaceScorelineReferenceBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Literal["MODEL_SCORELINE_REFERENCE"]
    proof_status: Literal["NOT_PROVEN"]


class WorkspaceReadyScorelineReference(WorkspaceScorelineReferenceBase):
    status: Literal["READY"]
    simulations_completed: Literal[10_000]
    top3: list[WorkspaceScoreline] = Field(min_length=1, max_length=3)


class WorkspaceUnavailableScorelineReference(WorkspaceScorelineReferenceBase):
    status: Literal["UNAVAILABLE"]
    simulations_completed: int | None = Field(default=None, ge=1)
    top3: list[WorkspaceScoreline] = Field(max_length=0)


WorkspaceScorelineReference = Annotated[
    WorkspaceReadyScorelineReference | WorkspaceUnavailableScorelineReference,
    Field(discriminator="status"),
]


class WorkspaceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_hash: str | None
    artifact_hash: str | None
    source: str | None
    source_event_at: str | None
    decision_role: Literal["DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY"]


class WorkspaceMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    competition_id: str | None
    competition_name: str | None
    kickoff_utc: datetime | str | None
    home_team_name: str | None
    away_team_name: str | None
    status: str | None
    intelligence_state: IntelligenceState
    intelligence_reason_codes: list[str]
    risks: WorkspaceRisks
    readiness: WorkspaceReadiness
    market_fact: WorkspaceMarketFact
    w2_analysis: WorkspaceW2Analysis
    formal_recommendation: WorkspaceFormalRecommendation
    market_radar: WorkspaceMarketRadar
    model_lab: WorkspaceModelLab
    scoreline_reference: WorkspaceScorelineReference
    evidence: WorkspaceEvidence


class WorkspaceProbabilityValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "SAMPLE_BUILDING", "INSUFFICIENT"]
    sample_count: int = Field(ge=0)
    model_brier: float | None
    market_brier: float | None
    model_minus_market_brier: float | None
    model_log_loss: float | None
    market_log_loss: float | None
    model_minus_market_log_loss: float | None
    model_calibration_error: float | None
    market_calibration_error: float | None
    model_reliability_bins: list[dict[str, Any]]
    market_reliability_bins: list[dict[str, Any]]
    checkpoint_metadata: dict[str, Any]


class WorkspaceDirectionalValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "SAMPLE_BUILDING", "INSUFFICIENT"]
    source_status: Literal["AVAILABLE", "SAMPLE_BUILDING", "INSUFFICIENT"]
    probability_evidence_ready: bool
    validation_n: int = Field(ge=0)
    decisive_n: int = Field(ge=0)
    correct: int = Field(ge=0)
    wrong: int = Field(ge=0)
    push: int = Field(ge=0)
    void: int = Field(ge=0)
    direction_accuracy: float | None
    effective_n: int = Field(ge=0)
    market_direction_benchmark: Literal["NOT_DEFINED"]
    only_record_reason: Literal[
        "PROBABILITY_QUALITY_NOT_READY", "SAMPLE_INSUFFICIENT"
    ] | None


class WorkspaceLeaguePerformance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    league: str
    source_league: str
    source_aliases: list[str]
    source_checkpoint_keys: list[str]
    scope_group: str
    aggregation_status: Literal[
        "SOURCE_CHECKPOINT", "FIXTURE_RECONSTRUCTED", "CONFLICT"
    ]
    competition_id: str
    canonical_competition_id: str | None
    competition_name: str | None
    identity_status: Literal["RESOLVED", "UNRESOLVED"]
    validation_n: int = Field(ge=0)
    decisive_n: int = Field(ge=0)
    correct: int = Field(ge=0)
    wrong: int = Field(ge=0)
    push: int = Field(ge=0)
    void: int = Field(ge=0)
    direction_accuracy: float | None
    brier: float | None
    log_loss: float | None
    calibration: float | None
    statistical_status: Literal["AVAILABLE", "SAMPLE_BUILDING", "INSUFFICIENT"]
    source_statistical_status: Literal["AVAILABLE", "SAMPLE_BUILDING", "INSUFFICIENT"]
    probability_evidence_ready: bool
    only_record_reason: Literal[
        "PROBABILITY_QUALITY_NOT_READY", "SAMPLE_INSUFFICIENT", "AGGREGATION_CONFLICT"
    ] | None
    market_direction_benchmark: Literal["NOT_DEFINED"]


class WorkspaceForwardValidationRecords(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "INSUFFICIENT"]
    validation_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    excluded_share: float = Field(ge=0, le=1)
    excluded_by_reason: dict[str, int]
    pending_count: int = Field(ge=0)
    outcomes: dict[str, Any]
    checkpoint_metadata: dict[str, Any]


class WorkspaceReplayDecisionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cards: int = Field(ge=0)
    lock_eligible_count: int = Field(ge=0)
    by_decision_tier: dict[str, int]
    by_data_status: dict[str, int]


class WorkspaceHistoryReplay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    known_at: dict[str, Any]
    decision_summary: WorkspaceReplayDecisionSummary
    reason_summary: list[dict[str, Any]]
    outcome_tracking_summary: dict[str, Any]
    card_hash_checks: list[dict[str, Any]]
    replay_gaps: list[str]


class WorkspaceValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probability: WorkspaceProbabilityValidation
    directional: WorkspaceDirectionalValidation
    league_performance: list[WorkspaceLeaguePerformance]
    tournament_performance: list[WorkspaceLeaguePerformance]
    forward_validation_records: WorkspaceForwardValidationRecords
    history_replay: WorkspaceHistoryReplay


class WorkspaceExternalSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["NOT_CONNECTED"]
    affects_match_readiness: Literal[False]


class WorkspaceExternalIntelligence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weather: WorkspaceExternalSource
    news: WorkspaceExternalSource
    sentiment: WorkspaceExternalSource
    advanced_xg: WorkspaceExternalSource


class WorkspaceFreshnessDomain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    availability: str
    status: str
    source: str
    source_as_of: datetime | str | None
    provider_refresh_authority: str
    readiness_semantics: Literal[
        "SOURCE_VALUE_ONLY",
        "SOURCE_AS_OF_NOT_PROJECTED",
    ]
    no_call_on_read: Literal[True]


class WorkspaceFreshness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domains: dict[str, WorkspaceFreshnessDomain]


class WorkspaceDataOperations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read_model_source: str
    checkpoint_key: str
    degradation: dict[str, Any]
    counts: dict[str, Any]
    system_health: str
    provider_budget_status: str


class DashboardIntelligenceWorkspaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    schema_version: Literal["w2.dashboard-intelligence-workspace.v1"]
    generated_at: datetime | str | None
    date: str
    timezone: str
    window: str
    football_day_timezone: str
    football_day_cutoff_hour: int = Field(ge=0, le=23)
    football_day_start_utc: datetime | str | None
    football_day_end_utc: datetime | str | None
    source: Literal["dashboard_day_view+performance_checkpoint+replay_front_door"]
    selected_fixture_id: str | None
    read_contract: WorkspaceReadContract
    runtime: WorkspaceRuntime
    navigation: dict[str, Any]
    attention: list[WorkspaceAttentionItem]
    matches: list[WorkspaceMatch]
    validation: WorkspaceValidation
    external_intelligence: WorkspaceExternalIntelligence
    freshness: WorkspaceFreshness
    data_operations: WorkspaceDataOperations


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
    model_brier: float | None = None
    market_brier: float | None = None
    model_minus_market_brier: float | None = None
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
    blind_spot_attribution_sample_count: int = Field(ge=0)
    rotation_associated_miss_count: int = Field(ge=0)
    non_rotation_residual_miss_count: int = Field(ge=0)
    insufficient_attribution_count: int = Field(ge=0)
    high_rotation_prior_fixture_count: int = Field(ge=0)
    lineup_unobservable_fixture_count: int = Field(ge=0)


class PerformanceCohortProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["w2.performance_projection.v3"]
    projection_version: Literal["eval-02a.v1"]
    checkpoint_key: str
    scoring_window_anchor: datetime
    windows: dict[Literal["7d", "30d", "90d"], PerformanceWindowProjection]
    business_projection_hash: str


class PerformanceFixtureProjection(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: Literal["w2.performance_projection.v3"]
    projection_version: Literal["eval-02a.v1"]
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
    projection_version: Literal["eval-02a.v1"]
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
