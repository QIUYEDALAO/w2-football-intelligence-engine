export type IntelligenceState =
  | "COLLECTION_INCIDENT"
  | "DATA_INCOMPLETE"
  | "MODEL_DIAGNOSTIC_WARNING"
  | "MARKET_ANOMALY"
  | "MODEL_MARKET_DISAGREEMENT"
  | "MARKET_MOVEMENT"
  | "MARKET_STABLE";

export type RiskAxisName =
  | "EVENT_RISK"
  | "DATA_RISK"
  | "MODEL_RISK"
  | "COLLECTION_RISK";

export interface RiskAxis {
  dimension: RiskAxisName;
  status: string;
  reason_codes: string[];
  explanation: string;
  assessment_status?: "ASSESSED_CURRENT" | "ASSESSED_INCIDENT" | "STALE" | "UNASSESSED" | null;
  evidence_basis?: string | null;
  source_as_of?: string | null;
}

export type WorkspaceRisks = Record<RiskAxisName, RiskAxis>;

export type PublicStatusScope = "MATCH" | "SELECTED_DAY" | "CROSS_DAY_CUMULATIVE" | "GLOBAL";
export type PublicStatusCause =
  | "NOT_YET_DUE"
  | "AWAITING_COLLECTION"
  | "INSUFFICIENT"
  | "UNAVAILABLE"
  | "UNASSESSED"
  | "LABEL_MISSING"
  | "IDENTITY_UNRESOLVED"
  | "AMBIGUOUS"
  | null;

export interface PublicStatusSemantics {
  scope: PublicStatusScope;
  cause: PublicStatusCause;
}

export interface WorkspaceAttentionItem {
  fixture_id: string;
  kickoff_utc: string | null;
  intelligence_state: IntelligenceState;
  reason_codes: string[];
  affected_domains: string[];
  factual_summary: string;
  readiness_status: string;
  readiness_context: {
    reason_code: string | null;
    missing_fields: string[];
    stale_fields: string[];
    action: string | null;
  };
  next_eval_at: string | null;
  risks: WorkspaceRisks;
}

export interface WorkspaceTimelinePoint {
  capture_id: string | null;
  captured_at: string | null;
  canonical_line: string | null;
  bookmaker_count: number;
  prices: Record<string, unknown>;
  probabilities: Record<string, unknown>;
}

export interface WorkspaceMarket {
  market: "ASIAN_HANDICAP" | "TOTALS";
  status: "READY" | "STALE" | "INSUFFICIENT";
  source_status: string;
  snapshot_state:
    | "NO_TIMELINE_EVIDENCE"
    | "ONE_OBSERVATION_NOT_A_TREND"
    | "DISCRETE_REAL_PATH";
  snapshot_count: number;
  observation_count: number;
  bookmaker_pair_count: number;
  quote_row_count: number;
  main_line: string | null;
  bookmaker_count: number;
  prices: Record<string, unknown>;
  probabilities: Record<string, unknown>;
  freshness: Record<string, unknown>;
  timeline_points: WorkspaceTimelinePoint[];
  movement: {
    status?: string;
    reason_code?: string | null;
    from_captured_at?: string | null;
    to_captured_at?: string | null;
    line_delta?: string | null;
    price_delta?: Record<string, number> | null;
    probability_delta?: Record<string, number> | null;
  };
  reason_codes: string[];
  trend_evidence_status: "AVAILABLE" | "INSUFFICIENT";
  cross_sectional_comparison_status: "AVAILABLE" | "INSUFFICIENT" | "PAUSED_STALE";
  latest_snapshot_at: string | null;
  freshness_max_age_seconds: number | null;
  eligibility: {
    observation_status: "AVAILABLE" | "STALE" | "INSUFFICIENT";
    trend_evidence_status: "AVAILABLE" | "INSUFFICIENT";
    cross_sectional_comparison_status: "AVAILABLE" | "INSUFFICIENT" | "PAUSED_STALE";
    model_diagnostic_status: string;
    candidate_quote_identity_status: "READY" | "NOT_READY";
    candidate_model_status: "READY" | "NOT_READY";
    candidate_eligibility_status: "READY" | "NOT_READY";
    blockers: string[];
  };
}

export interface WorkspacePublicTeamLabel {
  display_name: string;
  state:
    | "CHINESE_LABEL_READY"
    | "CANONICAL_IDENTITY_READY_LABEL_MISSING"
    | "IDENTITY_UNRESOLVED"
    | "AMBIGUOUS";
  canonical_team_id: string | null;
  provider_team_id: string | null;
  public_semantics: PublicStatusSemantics;
  technical: { raw_provider_name: string | null };
}

export interface WorkspaceDateStripEntry {
  football_day: string;
  fixture_count: number;
  competition_count: number;
  finished_fixture_count: number;
  upcoming_fixture_count: number;
  persisted_inventory_status: "PERSISTED_FIXTURES_AVAILABLE" | "EMPTY_PERSISTED_DAY";
  persisted_competition_coverage_count: number;
  active_whitelist_count: 13;
  market_collection_window_status:
    | "EMPTY_PERSISTED_DAY"
    | "MARKET_EVIDENCE_AVAILABLE"
    | "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW"
    | "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY"
    | "MARKET_COLLECTION_PLAN_NOT_PERSISTED";
  market_evidence_fixture_count: number;
  public_semantics: PublicStatusSemantics;
}

export interface WorkspaceModelRelation {
  market: "ASIAN_HANDICAP" | "TOTALS";
  status: string;
  canonical_line: string | null;
  bookmaker_count: number;
  freshness_status: string | null;
  diagnostics: Record<string, unknown>[];
  blockers: string[];
}

export interface WorkspaceMatch {
  fixture_id: string;
  competition_id: string | null;
  competition_name: string | null;
  kickoff_utc: string | null;
  home_team_name: string | null;
  away_team_name: string | null;
  home_team_label: WorkspacePublicTeamLabel;
  away_team_label: WorkspacePublicTeamLabel;
  public_semantics: PublicStatusSemantics;
  status: string | null;
  outcome: {
    is_finished: boolean;
    is_tracked: boolean;
    is_recorded: boolean;
    public_semantics: PublicStatusSemantics;
  };
  intelligence_state: IntelligenceState;
  intelligence_reason_codes: string[];
  priority_reason_primary: string | null;
  priority_reason_secondary: string[];
  factual_summary: string;
  risks: WorkspaceRisks;
  readiness: {
    status: string;
    reason_code: string | null;
    reason_codes: string[];
    missing_fields: string[];
    stale_fields: string[];
    action: string | null;
    next_eval_at: string | null;
    provider_budget_status: string | null;
    lineup_status: string | null;
    lineup_expectation: string | null;
    market_aggregate_status: "READY" | "PARTIAL" | "NOT_READY";
    market_evidence_status: "AVAILABLE" | "NOT_READY";
    candidate_input_status: "READY" | "NOT_READY";
  };
  market_fact: {
    status: "READY" | "STALE" | "INSUFFICIENT";
    source_status: string;
    main_line: string | null;
    current_odds: Record<string, unknown>;
    market_probabilities: Record<string, unknown>;
    price_reference: "LAST_AVAILABLE_PREMATCH_SNAPSHOT";
    canonical_close_status: "NOT_OBTAINABLE_FROM_CURRENT_PROVIDER";
  };
  w2_analysis: {
    status: "ANALYSIS_REFERENCE";
    proof_status: "NOT_PROVEN";
    decision_tier: string;
    analysis_state: string;
    reason_codes: string[];
    model_view: {
      status: string;
      source_status: string;
      model_version: string | null;
      calibration_version: string | null;
      calibration_status: string | null;
      simulations_completed: number | null;
    };
    model_market_relation: Record<string, WorkspaceModelRelation>;
  };
  shadow_candidate: {
    status: "ACTIVE" | "NOT_READY" | "OFF";
    mode: "SHADOW_ONLY";
    authority: "RECOMMENDATION_DECISION_V4";
    decision_tier: string;
    reason_code: string | null;
    reason_message: string | null;
    market: "ASIAN_HANDICAP" | "TOTALS" | null;
    selection: "HOME" | "AWAY" | "OVER" | "UNDER" | null;
    exact_line: string | null;
    decimal_odds: number | null;
    captured_at: string | null;
    decision_hash: string | null;
    recommendation_scope: "VALIDATION" | "NONE";
    outcome_tracked: boolean;
    formal_status: "OFF";
    lock_status: "OFF";
    production_action_allowed: false;
    real_money_allowed: false;
  };
  formal_recommendation: {
    status: "OFF";
    reason: "PRODUCT_AUTHORITY_DISABLED";
  };
  market_radar: {
    schema_version: string;
    markets: Record<"ASIAN_HANDICAP" | "TOTALS", WorkspaceMarket>;
  };
  model_lab: {
    schema_version: string;
    w2_model: {
      status: string;
      source_status: string;
      model_version: string | null;
      calibration_status: string | null;
    };
    market: Record<string, {
      status: "READY" | "STALE" | "INSUFFICIENT";
      source_status: string;
      main_line: string | null;
      bookmaker_count: number;
      freshness: Record<string, unknown>;
    }>;
    api_football_prediction: {
      status: "NOT_AVAILABLE";
      role: "EXTERNAL_MODEL_BENCHMARK";
      reason_code: "API_FOOTBALL_PREDICTION_NOT_PROJECTED";
    };
    relation: Record<string, WorkspaceModelRelation>;
    historical_validation: Record<string, unknown>;
  };
  scoreline_reference: {
    label: "MODEL_SCORELINE_REFERENCE";
    proof_status: "NOT_PROVEN";
    status: "READY" | "UNAVAILABLE";
    simulations_completed: number | null;
    top3: Array<{
      scoreline: string;
      unconditional_probability: number;
      sample_count: number;
    }>;
  };
  evidence: {
    card_hash: string | null;
    artifact_hash: string | null;
    source: string | null;
    source_event_at: string | null;
    decision_role: "DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY";
  };
}

export interface WorkspaceCompetitionPerformance {
  league: string;
  source_league: string;
  source_aliases: string[];
  source_checkpoint_keys: string[];
  scope_group: string;
  aggregation_status: "SOURCE_CHECKPOINT" | "FIXTURE_RECONSTRUCTED" | "CONFLICT";
  competition_id: string;
  canonical_competition_id: string | null;
  competition_name: string | null;
  identity_status: "RESOLVED" | "UNRESOLVED";
  validation_n: number;
  decisive_n: number;
  correct: number;
  wrong: number;
  push: number;
  void: number;
  direction_accuracy: number | null;
  brier: number | null;
  log_loss: number | null;
  calibration: number | null;
  statistical_status: "AVAILABLE" | "SAMPLE_BUILDING" | "INSUFFICIENT";
  source_statistical_status: "AVAILABLE" | "SAMPLE_BUILDING" | "INSUFFICIENT";
  probability_evidence_ready: boolean;
  only_record_reason: "PROBABILITY_QUALITY_NOT_READY" | "SAMPLE_INSUFFICIENT" | "AGGREGATION_CONFLICT" | null;
  market_direction_benchmark: "NOT_DEFINED";
}

export interface WorkspaceValidation {
  probability: {
    status: "AVAILABLE" | "SAMPLE_BUILDING" | "INSUFFICIENT";
    sample_count: number;
    model_brier: number | null;
    market_brier: number | null;
    model_minus_market_brier: number | null;
    model_log_loss: number | null;
    market_log_loss: number | null;
    model_minus_market_log_loss: number | null;
    model_calibration_error: number | null;
    market_calibration_error: number | null;
    model_reliability_bins: Record<string, unknown>[];
    market_reliability_bins: Record<string, unknown>[];
    checkpoint_metadata: Record<string, unknown>;
  };
  directional: {
    status: "AVAILABLE" | "SAMPLE_BUILDING" | "INSUFFICIENT";
    source_status: "AVAILABLE" | "SAMPLE_BUILDING" | "INSUFFICIENT";
    probability_evidence_ready: boolean;
    validation_n: number;
    decisive_n: number;
    correct: number;
    wrong: number;
    push: number;
    void: number;
    direction_accuracy: number | null;
    effective_n: number;
    market_direction_benchmark: "NOT_DEFINED";
    only_record_reason: "PROBABILITY_QUALITY_NOT_READY" | "SAMPLE_INSUFFICIENT" | null;
  };
  league_performance: WorkspaceCompetitionPerformance[];
  tournament_performance: WorkspaceCompetitionPerformance[];
  forward_validation_records: {
    status: "AVAILABLE" | "INSUFFICIENT";
    validation_count: number;
    eligible_count: number;
    excluded_count: number;
    excluded_share: number;
    excluded_by_reason: Record<string, number>;
    pending_count: number;
    outcomes: Record<string, unknown>;
    checkpoint_metadata: Record<string, unknown>;
    public_semantics: PublicStatusSemantics;
  };
  history_replay: {
    status: string;
    known_at: Record<string, unknown>;
    decision_summary: {
      total_cards: number;
      lock_eligible_count: number;
      by_decision_tier: Record<string, number>;
      by_data_status: Record<string, number>;
    };
    reason_summary: Record<string, unknown>[];
    outcome_tracking_summary: {
      tracked_count: number;
      matched_outcome_count: number;
      missing_outcome_count: number;
      tracked_fixture_ids: string[];
      matched_fixture_ids: string[];
      missing_outcome_fixture_ids: string[];
    };
    card_hash_checks: Record<string, unknown>[];
    replay_gaps: string[];
    record_kind: "FORWARD_RECORD" | "REPLAY" | "MIXED_RECORD" | "EMPTY";
    public_semantics: PublicStatusSemantics;
  };
}

export interface IntelligenceWorkspace {
  request_id: string;
  schema_version: "w2.dashboard-intelligence-workspace.v1";
  generated_at: string | null;
  date: string;
  timezone: string;
  window: "today";
  football_day_timezone: string;
  football_day_cutoff_hour: number;
  football_day_start_utc: string | null;
  football_day_end_utc: string | null;
  source: "dashboard_day_view+performance_checkpoint+replay_front_door";
  selected_fixture_id: string | null;
  today_summary: {
    match_count: number;
    competition_count: number;
    priority_match_count: number;
    priority_group_count: number;
    primary_reason_counts: Record<string, number>;
  };
  global_focus: {
    reason_code: string;
    factual_summary: string;
    affected_fixture_count: number;
    affected_competition_count: number;
    source_as_of: string | null;
    next_eval_at: string | null;
    recovery_condition: string | null;
    public_semantics: PublicStatusSemantics;
  } | null;
  global_model_quality: {
    status: "AVAILABLE" | "STALE" | "INCOMPLETE" | "NOT_AVAILABLE";
    checkpoint_key: string | null;
    checkpoint_generated_at: string | null;
    freshness_max_age_seconds: number;
    model_log_loss: number | null;
    market_log_loss: number | null;
    model_brier: number | null;
    market_brier: number | null;
    model_calibration_error: number | null;
    sample_count: number;
  };
  read_contract: {
    provider_calls: number;
    db_writes: number;
    would_write_checkpoint: boolean;
    no_call_on_read: true;
  };
  runtime: {
    product: string;
    public_dashboard_authority: "NEW_INTELLIGENCE_WORKSPACE_ONLY";
    active_whitelist_count: 13;
    free_bridge_mode: "SHADOW_ONLY";
    market_price_attention_threshold_ratio: 0.02;
    candidate: "OFF" | "SHADOW_ONLY";
    formal: "OFF";
    lock: "OFF";
    production: "OFF";
  };
  navigation: Record<string, unknown>;
  date_strip: WorkspaceDateStripEntry[];
  attention: WorkspaceAttentionItem[];
  matches: WorkspaceMatch[];
  validation: WorkspaceValidation;
  external_intelligence: Record<string, {
    status: "NOT_CONNECTED";
    affects_match_readiness: false;
  }>;
  freshness: {
    domains: Record<string, {
      domain: string;
      availability: string;
      status: string;
      source: string;
      source_as_of: string | null;
      provider_refresh_authority: string;
      readiness_semantics: "SOURCE_VALUE_ONLY" | "SOURCE_AS_OF_NOT_PROJECTED";
      no_call_on_read: true;
    }>;
  };
  data_operations: {
    read_model_source: string;
    checkpoint_key: string;
    degradation: Record<string, unknown>;
    counts: Record<string, unknown>;
    system_health: string;
    provider_budget_status: string;
  };
}
