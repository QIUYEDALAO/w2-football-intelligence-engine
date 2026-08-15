from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from w2.dashboard.results import (
    normalize_match_status,
    outcome_public_cause,
    selected_day_outcome_cause,
    selected_day_record_kind,
)

IntelligenceState = Literal[
    "COLLECTION_INCIDENT",
    "DATA_INCOMPLETE",
    "MODEL_DIAGNOSTIC_WARNING",
    "MARKET_ANOMALY",
    "MODEL_MARKET_DISAGREEMENT",
    "MARKET_MOVEMENT",
    "MARKET_STABLE",
]
DashboardPriorityReason = Literal["MARKET_MOVEMENT", "MODEL_DIAGNOSTIC"]


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
    date_strip: list[dict[str, Any]] = Field(min_length=15, max_length=15)
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
    market_price_attention_threshold_ratio: float = Field(ge=0.02, le=0.02)
    candidate: Literal["OFF", "SHADOW_ONLY"]
    formal: Literal["OFF"]
    lock: Literal["OFF"]
    production: Literal["OFF"]


class WorkspaceRiskDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: Literal["EVENT_RISK", "DATA_RISK", "MODEL_RISK", "COLLECTION_RISK"]
    status: Literal["OK", "ATTENTION", "INCIDENT"]
    reason_codes: list[str]
    explanation: str
    assessment_status: (
        Literal["ASSESSED_CURRENT", "ASSESSED_INCIDENT", "STALE", "UNASSESSED"] | None
    ) = None
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
    affected_domains: list[Literal["EVENT", "DATA", "MODEL", "COLLECTION", "MARKET"]] = Field(
        min_length=1
    )
    factual_summary: str = Field(min_length=1)
    readiness_status: str
    readiness_context: WorkspaceAttentionReadinessContext
    next_eval_at: datetime | str | None
    risks: WorkspaceRisks


class WorkspaceTimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_id: str | None
    checkpoint: str | None
    captured_at: datetime | str | None
    canonical_line: str | None
    bookmaker_count: int = Field(ge=0)
    prices: dict[str, Any]
    probabilities: dict[str, Any]


class WorkspaceMovement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "INSUFFICIENT",
        "STABLE",
        "PRICE_MOVEMENT",
        "LINE_MOVEMENT",
        "LINE_AND_PRICE_MOVEMENT",
    ]
    reason_code: str | None = None
    from_captured_at: datetime | str | None = None
    to_captured_at: datetime | str | None = None
    line_delta: str | None = None
    price_delta: dict[str, float] | None = None
    probability_delta: dict[str, float] | None = None

    @model_validator(mode="after")
    def movement_evidence_is_visible(self) -> WorkspaceMovement:
        if self.status != "INSUFFICIENT" and any(
            value is None
            for value in (
                self.from_captured_at,
                self.to_captured_at,
                self.line_delta,
                self.price_delta,
                self.probability_delta,
            )
        ):
            raise ValueError("movement status requires visible from/to and delta evidence")
        return self


class WorkspaceMarketEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_status: Literal["AVAILABLE", "INSUFFICIENT"]
    trend_evidence_status: Literal["AVAILABLE", "INSUFFICIENT"]
    cross_sectional_comparison_status: Literal["AVAILABLE", "INSUFFICIENT"]
    model_diagnostic_status: str
    candidate_quote_lock_status: Literal["READY", "NOT_READY"]
    candidate_model_status: Literal["READY", "NOT_READY"]
    candidate_eligibility_status: Literal["READY", "NOT_READY"]
    blockers: list[str]


class WorkspaceMarket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: Literal["ASIAN_HANDICAP", "TOTALS"]
    status: Literal["READY", "INSUFFICIENT"]
    source_status: str
    snapshot_state: Literal[
        "NO_TIMELINE_EVIDENCE",
        "ONE_OBSERVATION_NOT_A_TREND",
        "DISCRETE_REAL_PATH",
    ]
    snapshot_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    bookmaker_pair_count: int = Field(ge=0)
    quote_row_count: int = Field(ge=0)
    main_line: str | None
    bookmaker_count: int = Field(ge=0)
    prices: dict[str, Any]
    probabilities: dict[str, Any]
    quote_age_seconds: int | None = Field(default=None, ge=0)
    timeline_points: list[WorkspaceTimelinePoint]
    movement: WorkspaceMovement
    reason_codes: list[str]
    trend_evidence_status: Literal["AVAILABLE", "INSUFFICIENT"]
    cross_sectional_comparison_status: Literal["AVAILABLE", "INSUFFICIENT"]
    latest_snapshot_at: datetime | str | None
    eligibility: WorkspaceMarketEligibility

    @model_validator(mode="after")
    def preserves_quote_rows(self) -> WorkspaceMarket:
        if self.status == "READY" and self.latest_snapshot_at is None:
            raise ValueError("READY market evidence requires a persisted snapshot")
        if self.quote_row_count != self.observation_count:
            raise ValueError("quote_row_count must preserve observation_count")
        if self.quote_row_count != self.bookmaker_pair_count * 2:
            raise ValueError("each bookmaker pair must preserve two quote rows")
        return self


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
    market_aggregate_status: Literal["READY", "PARTIAL", "NOT_READY"]
    market_evidence_status: Literal["AVAILABLE", "NOT_READY"]
    candidate_input_status: Literal["READY", "NOT_READY"]


class WorkspacePublicSemantics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["MATCH", "SELECTED_DAY", "CROSS_DAY_CUMULATIVE", "GLOBAL"]
    cause: (
        Literal[
            "NOT_YET_DUE",
            "AWAITING_COLLECTION",
            "INSUFFICIENT",
            "UNAVAILABLE",
            "UNASSESSED",
            "LABEL_MISSING",
            "IDENTITY_UNRESOLVED",
            "AMBIGUOUS",
        ]
        | None
    )


class WorkspacePublicTeamLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)
    state: Literal[
        "CHINESE_LABEL_READY",
        "CANONICAL_IDENTITY_READY_LABEL_MISSING",
        "IDENTITY_UNRESOLVED",
        "AMBIGUOUS",
    ]
    canonical_team_id: str | None
    provider_team_id: str | None
    public_semantics: WorkspacePublicSemantics
    technical: dict[Literal["raw_provider_name"], str | None]

    @model_validator(mode="after")
    def semantics_match_identity_state(self) -> WorkspacePublicTeamLabel:
        expected = {
            "CHINESE_LABEL_READY": None,
            "CANONICAL_IDENTITY_READY_LABEL_MISSING": "LABEL_MISSING",
            "IDENTITY_UNRESOLVED": "IDENTITY_UNRESOLVED",
            "AMBIGUOUS": "AMBIGUOUS",
        }[self.state]
        if self.public_semantics.scope != "MATCH" or self.public_semantics.cause != expected:
            raise ValueError("team label semantics must derive from identity state")
        return self


class WorkspaceMarketFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["READY", "INSUFFICIENT"]
    source_status: str
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
    market_quote_age_seconds: int | None = Field(default=None, ge=0)
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


class WorkspaceShadowCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ACTIVE", "NOT_READY", "OFF"]
    mode: Literal["SHADOW_ONLY"]
    authority: Literal["RECOMMENDATION_DECISION_V4"]
    decision_tier: Literal["NOT_READY", "NO_EDGE", "ANALYSIS_PICK", "FORMAL_RECOMMEND"]
    reason_code: str | None
    reason_message: str | None
    market: Literal["ASIAN_HANDICAP", "TOTALS"] | None
    selection: Literal["HOME", "AWAY", "OVER", "UNDER"] | None
    exact_line: str | None
    decimal_odds: float | None = Field(default=None, gt=1)
    captured_at: datetime | str | None
    decision_hash: str | None
    recommendation_scope: Literal["VALIDATION", "NONE"]
    outcome_tracked: bool
    formal_status: Literal["OFF"]
    lock_status: Literal["OFF"]
    production_action_allowed: Literal[False]
    real_money_allowed: Literal[False]

    @model_validator(mode="after")
    def active_candidate_is_complete(self) -> WorkspaceShadowCandidate:
        selected = (
            self.market,
            self.selection,
            self.exact_line,
            self.decimal_odds,
            self.captured_at,
            self.decision_hash,
        )
        if self.status == "ACTIVE":
            if self.decision_tier != "ANALYSIS_PICK" or any(value is None for value in selected):
                raise ValueError("active shadow candidate requires complete V4 identity")
            if self.recommendation_scope != "VALIDATION" or not self.outcome_tracked:
                raise ValueError("active shadow candidate must enter forward validation")
        elif any(value is not None for value in selected):
            raise ValueError("inactive shadow candidate cannot expose a selection")
        return self


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

    status: Literal["READY", "INSUFFICIENT"]
    source_status: str
    main_line: str | None
    bookmaker_count: int = Field(ge=0)
    quote_age_seconds: int | None = Field(default=None, ge=0)


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


class WorkspaceMatchOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_finished: bool
    is_tracked: bool
    is_recorded: bool
    public_semantics: WorkspacePublicSemantics

    @model_validator(mode="after")
    def semantics_follow_outcome_facts(self) -> WorkspaceMatchOutcome:
        if self.is_recorded and not self.is_finished:
            raise ValueError("an unfinished match cannot have a recorded outcome")
        if self.public_semantics.scope != "MATCH":
            raise ValueError("match outcome semantics must derive from outcome facts")
        if self.is_finished:
            expected_cause = outcome_public_cause(
                status="FINISHED",
                kickoff_utc=None,
                as_of=None,
                is_tracked=self.is_tracked,
                is_recorded=self.is_recorded,
            )
            if self.public_semantics.cause != expected_cause:
                raise ValueError("match outcome semantics must derive from outcome facts")
        elif self.public_semantics.cause not in {
            "NOT_YET_DUE",
            "AWAITING_COLLECTION",
            "UNASSESSED",
        }:
            raise ValueError("unfinished outcome semantics require a temporal cause")
        return self


class WorkspaceMarketCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latest_snapshot_at: datetime | str | None
    latest_snapshot_checkpoint: str | None
    target_checkpoint: str | None
    scheduled_at: datetime | str | None
    window_end_at: datetime | str | None
    overdue: bool
    public_semantics: WorkspacePublicSemantics

    @model_validator(mode="after")
    def collection_window_is_exact(self) -> WorkspaceMarketCollection:
        if self.public_semantics.scope != "MATCH":
            raise ValueError("market collection semantics must describe one match")
        cause = self.public_semantics.cause
        if cause not in {None, "NOT_YET_DUE", "AWAITING_COLLECTION", "UNASSESSED"}:
            raise ValueError("market collection cause is not temporal")
        if cause in {"NOT_YET_DUE", "AWAITING_COLLECTION"} and any(
            value is None
            for value in (self.target_checkpoint, self.scheduled_at, self.window_end_at)
        ):
            raise ValueError("scheduled market collection requires checkpoint and window")
        if self.overdue and cause != "AWAITING_COLLECTION":
            raise ValueError("only an awaiting collection window can be overdue")
        return self


class WorkspaceLineupCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_checkpoint: str | None
    scheduled_at: datetime | str | None
    window_end_at: datetime | str | None
    overdue: bool
    public_semantics: WorkspacePublicSemantics

    @model_validator(mode="after")
    def collection_window_is_exact(self) -> WorkspaceLineupCollection:
        if self.public_semantics.scope != "MATCH":
            raise ValueError("lineup collection semantics must describe one match")
        cause = self.public_semantics.cause
        if cause not in {None, "NOT_YET_DUE", "AWAITING_COLLECTION", "UNASSESSED"}:
            raise ValueError("lineup collection cause is not temporal")
        if cause in {"NOT_YET_DUE", "AWAITING_COLLECTION"} and any(
            value is None
            for value in (self.target_checkpoint, self.scheduled_at, self.window_end_at)
        ):
            raise ValueError("scheduled lineup collection requires checkpoint and window")
        if self.overdue and cause != "AWAITING_COLLECTION":
            raise ValueError("only an awaiting lineup window can be overdue")
        return self


class WorkspaceFactorTrackState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["READY", "BLOCKED"]
    blocking_factor_ids: list[str]

    @model_validator(mode="after")
    def blockers_follow_state(self) -> WorkspaceFactorTrackState:
        if (self.state == "READY") != (not self.blocking_factor_ids):
            raise ValueError("factor track state must follow blockers")
        return self


class WorkspaceShadowFactorTrack(WorkspaceFactorTrackState):
    per_market: dict[Literal["ASIAN_HANDICAP", "TOTALS"], WorkspaceFactorTrackState]


class WorkspaceFixtureFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_id: str
    display_name_zh: str = Field(min_length=1)
    market: Literal["ASIAN_HANDICAP", "TOTALS"] | None = None
    role_model_forecast: Literal["HARD_GATE", "ENHANCEMENT", "NOT_APPLICABLE", "POLICY_DISABLED"]
    role_shadow_candidate: Literal["HARD_GATE", "ENHANCEMENT", "NOT_APPLICABLE", "POLICY_DISABLED"]
    factor_lifecycle: str | None
    numeric_effect_enabled: bool
    state: Literal["READY", "PARTIAL", "MISSING", "WAITING", "DISABLED"]
    cause: (
        Literal[
            "NOT_YET_DUE",
            "AWAITING_COLLECTION",
            "COLLECTION_WINDOW_MISSED",
            "UNDER_SAMPLED",
            "PROVIDER_NOT_AVAILABLE",
            "POLICY_DISABLED",
            "NOT_MATERIALIZED",
            "SOURCE_NOT_CONFIGURED",
            "IDENTITY_UNRESOLVED",
            "NO_MATERIALIZED_HISTORY",
        ]
        | None
    )
    permanence: Literal[
        "TRANSIENT",
        "SELF_RESOLVING",
        "STRUCTURAL_PERMANENT",
        "UNKNOWN",
        "NOT_APPLICABLE",
    ]
    next_window_at: datetime | str | None
    evidence: dict[str, Any]

    @model_validator(mode="after")
    def missing_semantics_are_explicit(self) -> WorkspaceFixtureFactor:
        if (self.state == "READY") != (self.cause is None):
            raise ValueError("only READY factor rows may omit cause")
        if self.cause == "PROVIDER_NOT_AVAILABLE" and self.permanence != "STRUCTURAL_PERMANENT":
            raise ValueError("provider unavailable must be structural permanent")
        if self.cause == "POLICY_DISABLED" and self.state != "DISABLED":
            raise ValueError("policy disabled must use disabled state")
        if (self.state == "WAITING") != (self.cause == "NOT_YET_DUE"):
            raise ValueError("not-yet-due factors must use waiting state")
        if self.permanence == "SELF_RESOLVING" and not (
            self.next_window_at is not None
            or int(self.evidence.get("shortfall") or 0) > 0
        ):
            raise ValueError("self-resolving factors require a concrete recovery condition")
        return self


class WorkspaceModelForecastFourFieldXgFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["READY"]
    identity_hash: str = Field(min_length=64, max_length=64)
    home_snapshot_identity: str = Field(min_length=1)
    away_snapshot_identity: str = Field(min_length=1)
    home_match_count: int = Field(ge=3)
    away_match_count: int = Field(ge=3)


class WorkspaceModelForecastLedgerFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["NOT_CAPTURED", "CAPTURED", "SETTLED"]
    capture_identity_hash: str | None = None
    captured_at: datetime | str | None = None
    lead_time_seconds: int | None = Field(default=None, ge=0)
    lead_time_bucket: Literal["LT_6H", "H6_TO_LT_24H", "D1_TO_D3", "GT_3D"] | None = None
    capture_policy: Literal["FIRST_ELIGIBLE_FREEZE_IMMUTABLE"] | None = None
    model_family: str | None = None
    model_version: str | None = None
    calibration_version: str | None = None
    calibration_status: str | None = None
    four_field_xg: WorkspaceModelForecastFourFieldXgFact | None = None
    settled_at: datetime | str | None = None
    brier: float | None = None
    log_loss: float | None = None
    rps: float | None = None

    @model_validator(mode="after")
    def fields_follow_state(self) -> WorkspaceModelForecastLedgerFact:
        captured = (
            self.capture_identity_hash,
            self.captured_at,
            self.lead_time_seconds,
            self.lead_time_bucket,
            self.capture_policy,
            self.model_family,
            self.model_version,
        )
        settled = (self.settled_at, self.brier, self.log_loss, self.rps)
        if self.state == "NOT_CAPTURED" and any(
            value is not None for value in (*captured, *settled)
        ):
            raise ValueError("not-captured ledger facts cannot contain capture or outcome fields")
        if self.state in {"CAPTURED", "SETTLED"} and any(value is None for value in captured):
            raise ValueError(
                "captured ledger facts require persisted capture identity and model fields"
            )
        if self.state in {"CAPTURED", "SETTLED"} and self.four_field_xg is None:
            raise ValueError("captured ledger facts require persisted four-field xG identity")
        if self.state == "NOT_CAPTURED" and self.four_field_xg is not None:
            raise ValueError("not-captured ledger facts cannot contain four-field xG identity")
        if self.state == "SETTLED" and any(value is None for value in settled):
            raise ValueError("settled ledger facts require persisted probability metrics")
        if self.state == "CAPTURED" and any(value is not None for value in settled):
            raise ValueError("unsettled capture cannot contain outcome metrics")
        return self


class WorkspaceEnhancementQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["READY", "DEGRADED"]
    missing_factor_ids: list[str]


class WorkspaceFixtureFactorChecklist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    competition_id: str | None
    kickoff_utc: datetime | str | None
    as_of: datetime | str | None
    conclusion_zh: str = Field(min_length=1)
    market_identity_note_zh: str = Field(min_length=1)
    ledger_fact: WorkspaceModelForecastLedgerFact
    enhancement_quality: WorkspaceEnhancementQuality
    track_model_forecast: WorkspaceFactorTrackState
    track_shadow_candidate: WorkspaceShadowFactorTrack
    factors: list[WorkspaceFixtureFactor]


class WorkspaceMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    competition_id: str | None
    competition_name: str | None
    kickoff_utc: datetime | str | None
    home_team_name: str | None
    away_team_name: str | None
    home_team_label: WorkspacePublicTeamLabel
    away_team_label: WorkspacePublicTeamLabel
    public_semantics: WorkspacePublicSemantics
    status: str | None
    outcome: WorkspaceMatchOutcome
    market_collection: WorkspaceMarketCollection
    lineup_collection: WorkspaceLineupCollection
    intelligence_state: IntelligenceState
    intelligence_reason_codes: list[str]
    priority_reason_primary: DashboardPriorityReason | None
    priority_reason_secondary: list[str]
    factual_summary: str = Field(min_length=1)
    risks: WorkspaceRisks
    readiness: WorkspaceReadiness
    market_fact: WorkspaceMarketFact
    w2_analysis: WorkspaceW2Analysis
    shadow_candidate: WorkspaceShadowCandidate
    factor_checklist: WorkspaceFixtureFactorChecklist
    formal_recommendation: WorkspaceFormalRecommendation
    market_radar: WorkspaceMarketRadar
    model_lab: WorkspaceModelLab
    scoreline_reference: WorkspaceScorelineReference
    evidence: WorkspaceEvidence

    @model_validator(mode="after")
    def market_readiness_is_consistent(self) -> WorkspaceMatch:
        expected_finished = normalize_match_status(self.status) == "FINISHED"
        if self.outcome.is_finished != expected_finished:
            raise ValueError("match outcome finished fact must derive from fixture status")
        for name, market in self.market_radar.markets.items():
            summary = self.model_lab.market.get(name)
            if summary is None or (summary.status, summary.source_status) != (
                market.status,
                market.source_status,
            ):
                raise ValueError("market readiness must match across radar and model lab")
        if self.market_fact.main_line is not None and not any(
            market.main_line == self.market_fact.main_line
            and (market.status, market.source_status)
            == (self.market_fact.status, self.market_fact.source_status)
            for market in self.market_radar.markets.values()
        ):
            raise ValueError("market fact must use canonical market readiness")
        eligibility = [market.eligibility for market in self.market_radar.markets.values()]
        expected = (
            "READY"
            if eligibility
            and all(item.candidate_eligibility_status == "READY" for item in eligibility)
            else "PARTIAL"
            if any(item.candidate_eligibility_status == "READY" for item in eligibility)
            else "NOT_READY"
        )
        if self.readiness.market_aggregate_status != expected:
            raise ValueError("match market aggregate must derive from per-market eligibility")
        expected_market_evidence = (
            "AVAILABLE"
            if any(item.observation_status == "AVAILABLE" for item in eligibility)
            else "NOT_READY"
        )
        if self.readiness.market_evidence_status != expected_market_evidence:
            raise ValueError("match market evidence must derive from per-market observations")
        expected_candidate_input = (
            "READY"
            if any(item.candidate_eligibility_status == "READY" for item in eligibility)
            else "NOT_READY"
        )
        if self.readiness.candidate_input_status != expected_candidate_input:
            raise ValueError("match candidate input must derive from per-market eligibility")
        if (
            "lineups" in self.readiness.missing_fields
            and self.lineup_collection.public_semantics.cause == "NOT_YET_DUE"
        ):
            data_risk = self.risks.data_risk
            if "待补齐：首发" in data_risk.explanation:
                raise ValueError("not-yet-due lineups cannot be an anomalous missing input")
            if set(self.readiness.missing_fields) == {"lineups"} and data_risk.status != "OK":
                raise ValueError("not-yet-due lineups alone cannot make data risk abnormal")
        if self.shadow_candidate.status == "ACTIVE":
            selected = self.market_radar.markets.get(str(self.shadow_candidate.market))
            if selected is None or selected.eligibility.candidate_eligibility_status != "READY":
                raise ValueError("active shadow candidate requires selected-market eligibility")
        return self


class WorkspaceTodaySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_count: int = Field(ge=0)
    competition_count: int = Field(ge=0)
    priority_match_count: int = Field(ge=0)
    priority_group_count: int = Field(ge=0)
    primary_reason_counts: dict[str, int]

    @model_validator(mode="after")
    def primary_counts_do_not_double_count(self) -> WorkspaceTodaySummary:
        if sum(self.primary_reason_counts.values()) != self.priority_match_count:
            raise ValueError("primary reason counts must count each priority match once")
        if self.priority_group_count != len(self.primary_reason_counts):
            raise ValueError("priority group count must match primary reason groups")
        return self


class WorkspaceGlobalFocus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str
    factual_summary: str = Field(min_length=1)
    affected_fixture_count: int = Field(ge=0)
    affected_competition_count: int = Field(ge=0)
    source_as_of: datetime | str | None
    next_eval_at: datetime | str | None = None
    recovery_condition: str | None = None
    public_semantics: WorkspacePublicSemantics

    @model_validator(mode="after")
    def semantics_are_selected_day(self) -> WorkspaceGlobalFocus:
        if self.public_semantics.scope != "SELECTED_DAY":
            raise ValueError("global focus public semantics must describe the selected day")
        return self


class WorkspaceModelQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "STALE", "INCOMPLETE", "NOT_AVAILABLE"]
    checkpoint_key: str | None
    checkpoint_generated_at: datetime | str | None
    freshness_max_age_seconds: int = Field(ge=0)
    model_log_loss: float | None
    market_log_loss: float | None
    model_brier: float | None
    market_brier: float | None
    model_calibration_error: float | None
    sample_count: int = Field(ge=0)

    @model_validator(mode="after")
    def unavailable_quality_has_no_metrics(self) -> WorkspaceModelQuality:
        metrics = (
            self.model_log_loss,
            self.market_log_loss,
            self.model_brier,
            self.market_brier,
            self.model_calibration_error,
        )
        if self.status != "AVAILABLE" and any(value is not None for value in metrics):
            raise ValueError("non-current model quality must fail closed")
        if self.status == "AVAILABLE" and (
            self.checkpoint_generated_at is None or any(value is None for value in metrics)
        ):
            raise ValueError("available model quality requires a timestamp and complete metrics")
        return self


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
    only_record_reason: Literal["PROBABILITY_QUALITY_NOT_READY", "SAMPLE_INSUFFICIENT"] | None


class WorkspaceLeaguePerformance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    league: str
    source_league: str
    source_aliases: list[str]
    source_checkpoint_keys: list[str]
    scope_group: str
    aggregation_status: Literal["SOURCE_CHECKPOINT", "FIXTURE_RECONSTRUCTED", "CONFLICT"]
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
    only_record_reason: (
        Literal["PROBABILITY_QUALITY_NOT_READY", "SAMPLE_INSUFFICIENT", "AGGREGATION_CONFLICT"]
        | None
    )
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
    public_semantics: WorkspacePublicSemantics

    @model_validator(mode="after")
    def semantics_are_cumulative(self) -> WorkspaceForwardValidationRecords:
        if self.public_semantics.scope != "CROSS_DAY_CUMULATIVE":
            raise ValueError("forward validation records must remain cross-day cumulative")
        return self


class WorkspaceReplayDecisionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cards: int = Field(ge=0)
    lock_eligible_count: int = Field(ge=0)
    by_decision_tier: dict[str, int]
    by_data_status: dict[str, int]


class WorkspaceOutcomeTrackingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracked_count: int = Field(ge=0)
    matched_outcome_count: int = Field(ge=0)
    missing_outcome_count: int = Field(ge=0)
    tracked_fixture_ids: list[str]
    matched_fixture_ids: list[str]
    missing_outcome_fixture_ids: list[str]

    @model_validator(mode="after")
    def counts_and_fixture_sets_agree(self) -> WorkspaceOutcomeTrackingSummary:
        tracked = set(self.tracked_fixture_ids)
        matched = set(self.matched_fixture_ids)
        missing = set(self.missing_outcome_fixture_ids)
        if len(tracked) != len(self.tracked_fixture_ids):
            raise ValueError("tracked outcome fixture ids must be unique")
        if len(matched) != len(self.matched_fixture_ids):
            raise ValueError("matched outcome fixture ids must be unique")
        if len(missing) != len(self.missing_outcome_fixture_ids):
            raise ValueError("missing outcome fixture ids must be unique")
        if self.tracked_count != len(tracked):
            raise ValueError("tracked outcome count must match fixture ids")
        if self.matched_outcome_count != len(matched):
            raise ValueError("matched outcome count must match fixture ids")
        if self.missing_outcome_count != len(missing):
            raise ValueError("missing outcome count must match fixture ids")
        if not (matched | missing).issubset(tracked):
            raise ValueError("matched and missing outcomes must be tracked")
        if matched & missing:
            raise ValueError("an outcome cannot be both matched and missing")
        return self


class WorkspaceHistoryReplay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    known_at: dict[str, Any]
    decision_summary: WorkspaceReplayDecisionSummary
    reason_summary: list[dict[str, Any]]
    outcome_tracking_summary: WorkspaceOutcomeTrackingSummary
    card_hash_checks: list[dict[str, Any]]
    replay_gaps: list[str]
    record_kind: Literal["FORWARD_RECORD", "REPLAY", "MIXED_RECORD", "EMPTY"]
    public_semantics: WorkspacePublicSemantics

    @model_validator(mode="after")
    def semantics_match_selected_day_record_kind(self) -> WorkspaceHistoryReplay:
        if self.public_semantics.scope != "SELECTED_DAY":
            raise ValueError("history/replay records must remain selected-day scoped")
        has_missing_status = self.status == "MISSING_OUTCOMES"
        has_missing_gap = "MISSING_OUTCOMES" in self.replay_gaps
        if self.record_kind == "EMPTY":
            if self.public_semantics.cause is not None:
                raise ValueError("empty selected-day records cannot claim a gap cause")
            if self.status != "EMPTY" or self.replay_gaps:
                raise ValueError("empty selected-day records cannot claim replay gaps")
            return self
        if self.record_kind == "FORWARD_RECORD":
            if self.public_semantics.cause not in {
                "NOT_YET_DUE",
                "AWAITING_COLLECTION",
                "UNASSESSED",
            }:
                raise ValueError("forward records require a temporal cause")
            if self.status != "FORWARD_RECORD":
                raise ValueError("forward records must use FORWARD_RECORD status")
            if has_missing_status or has_missing_gap:
                raise ValueError("forward records cannot claim missing outcomes")
            return self
        if self.public_semantics.cause == "NOT_YET_DUE":
            raise ValueError("replay records cannot be NOT_YET_DUE")
        if has_missing_status != has_missing_gap:
            raise ValueError("missing outcome status and gap must agree")
        if has_missing_status:
            if self.public_semantics.cause != "AWAITING_COLLECTION":
                raise ValueError("missing replay outcomes must await collection")
        else:
            if self.record_kind == "REPLAY" and self.public_semantics.cause is not None:
                raise ValueError("complete replay records cannot claim a gap cause")
            if self.record_kind == "REPLAY" and self.status != "READY":
                raise ValueError("complete replay records must use READY status")
            if self.record_kind == "MIXED_RECORD" and self.status != "READY":
                raise ValueError("complete mixed records must use READY status")
        return self


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


class WorkspaceDateStripEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    football_day: str
    fixture_count: int = Field(ge=0)
    competition_count: int = Field(ge=0)
    finished_fixture_count: int = Field(ge=0)
    upcoming_fixture_count: int = Field(ge=0)
    persisted_inventory_status: Literal[
        "PERSISTED_FIXTURES_AVAILABLE",
        "EMPTY_PERSISTED_DAY",
    ]
    persisted_competition_coverage_count: int = Field(ge=0, le=13)
    active_whitelist_count: Literal[13]
    market_collection_window_status: Literal[
        "EMPTY_PERSISTED_DAY",
        "MARKET_EVIDENCE_AVAILABLE",
        "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW",
        "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY",
        "MARKET_COLLECTION_PLAN_NOT_PERSISTED",
    ]
    market_evidence_fixture_count: int = Field(ge=0)
    public_semantics: WorkspacePublicSemantics

    @model_validator(mode="after")
    def counts_are_consistent(self) -> WorkspaceDateStripEntry:
        if self.finished_fixture_count + self.upcoming_fixture_count != self.fixture_count:
            raise ValueError("date strip fixture counts must reconcile")
        if self.market_evidence_fixture_count > self.fixture_count:
            raise ValueError("date strip market evidence cannot exceed fixtures")
        has_full_evidence = (
            self.fixture_count > 0
            and self.market_evidence_fixture_count == self.fixture_count
        )
        if (
            self.market_collection_window_status == "MARKET_EVIDENCE_AVAILABLE"
        ) != has_full_evidence:
            raise ValueError("market evidence availability must equal full fixture coverage")
        if self.market_collection_window_status == "EMPTY_PERSISTED_DAY" and (
            self.fixture_count != 0 or self.market_evidence_fixture_count != 0
        ):
            raise ValueError("empty date strip entries cannot claim fixtures or evidence")
        if self.persisted_competition_coverage_count != self.competition_count:
            raise ValueError("date strip coverage must use persisted competition count")
        expected_cause = {
            "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW": "NOT_YET_DUE",
            "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY": "AWAITING_COLLECTION",
            "MARKET_COLLECTION_PLAN_NOT_PERSISTED": "UNASSESSED",
        }.get(self.market_collection_window_status)
        if (
            self.public_semantics.scope != "SELECTED_DAY"
            or self.public_semantics.cause != expected_cause
        ):
            raise ValueError("date strip semantics must derive from collection-window status")
        return self


class DashboardIntelligenceWorkspaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    schema_version: Literal["w2.dashboard-intelligence-workspace.v1"]
    generated_at: datetime | str | None
    date: str
    timezone: str
    window: Literal["today"]
    football_day_timezone: str
    football_day_cutoff_hour: int = Field(ge=0, le=23)
    football_day_start_utc: datetime | str | None
    football_day_end_utc: datetime | str | None
    source: Literal["dashboard_day_view+performance_checkpoint+replay_front_door"]
    selected_fixture_id: str | None
    today_summary: WorkspaceTodaySummary
    global_focus: WorkspaceGlobalFocus | None
    global_model_quality: WorkspaceModelQuality
    read_contract: WorkspaceReadContract
    runtime: WorkspaceRuntime
    navigation: dict[str, Any]
    date_strip: list[WorkspaceDateStripEntry] = Field(min_length=15, max_length=15)
    attention: list[WorkspaceAttentionItem]
    matches: list[WorkspaceMatch]
    validation: WorkspaceValidation
    external_intelligence: WorkspaceExternalIntelligence
    freshness: WorkspaceFreshness
    data_operations: WorkspaceDataOperations

    @model_validator(mode="after")
    def focus_and_date_strip_are_exact(self) -> DashboardIntelligenceWorkspaceResponse:
        fixture_ids = {match.fixture_id for match in self.matches}
        competition_ids = {
            match.competition_id for match in self.matches if match.competition_id
        }
        if self.today_summary.match_count != len(self.matches):
            raise ValueError("selected-day match count must equal projected matches")
        if self.today_summary.competition_count != len(competition_ids):
            raise ValueError("selected-day competition count must equal projected matches")
        if self.selected_fixture_id is not None:
            if self.selected_fixture_id not in fixture_ids:
                raise ValueError("selected fixture must exist in matches")
            if self.global_focus is not None:
                raise ValueError("selected fixture cannot coexist with global focus")
        elif self.global_focus is None:
            raise ValueError("missing selected fixture requires a factual global focus")
        days = [date.fromisoformat(item.football_day) for item in self.date_strip]
        if days != [days[0] + timedelta(days=index) for index in range(15)]:
            raise ValueError("date strip must contain 15 consecutive football days")
        if date.fromisoformat(self.date) != days[7]:
            raise ValueError("selected football day must be centered in date strip")
        selected_day = self.date_strip[7]
        if (
            selected_day.fixture_count != self.today_summary.match_count
            or selected_day.competition_count != self.today_summary.competition_count
        ):
            raise ValueError("selected date strip counts must match selected-day summary")
        for match in self.matches:
            expected_cause = outcome_public_cause(
                status=match.status,
                kickoff_utc=match.kickoff_utc,
                as_of=self.generated_at,
                is_tracked=match.outcome.is_tracked,
                is_recorded=match.outcome.is_recorded,
            )
            if match.outcome.public_semantics.cause != expected_cause:
                raise ValueError("match outcome cause must derive from status and time")
        finished = [match.outcome.is_finished for match in self.matches]
        expected_record_kind = selected_day_record_kind(finished)
        if self.validation.history_replay.record_kind != expected_record_kind:
            raise ValueError("history/replay record kind must derive from match outcomes")
        outcome_summary = self.validation.history_replay.outcome_tracking_summary
        tracked_ids = {match.fixture_id for match in self.matches if match.outcome.is_tracked}
        matched_ids = {
            match.fixture_id
            for match in self.matches
            if match.outcome.is_tracked and match.outcome.is_recorded
        }
        missing_ids = {
            match.fixture_id
            for match in self.matches
            if match.outcome.is_tracked
            and match.outcome.is_finished
            and not match.outcome.is_recorded
        }
        if set(outcome_summary.tracked_fixture_ids) != tracked_ids:
            raise ValueError("tracked replay fixtures must match per-match outcome facts")
        if set(outcome_summary.matched_fixture_ids) != matched_ids:
            raise ValueError("matched replay fixtures must match per-match outcome facts")
        if set(outcome_summary.missing_outcome_fixture_ids) != missing_ids:
            raise ValueError("missing replay fixtures must match per-match outcome facts")
        outcome_causes = [
            match.outcome.public_semantics.cause for match in self.matches
        ]
        expected_record_cause = selected_day_outcome_cause(
            finished, outcome_causes
        )
        if (
            self.validation.history_replay.public_semantics.cause
            != expected_record_cause
        ):
            raise ValueError("history/replay cause must derive from match outcomes")
        return self


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
