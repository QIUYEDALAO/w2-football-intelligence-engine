export type MarketCode = "ASIAN_HANDICAP" | "TOTALS" | "FIRST_HALF_GOALS" | "SCORE";

export type Decision = "PICK" | "SKIP" | "WATCH" | "ANALYSIS_PICK" | string;

export type DecisionTier = "NOT_READY" | "SKIP" | "WATCH" | "ANALYSIS_PICK" | "RECOMMEND";

export type DataStatus = "READY" | "PARTIAL" | "STALE" | "BLOCKED";

export type LifecycleStatus = "DRAFT" | "LOCKED" | "SUPERSEDED" | "VOID" | "SETTLED";

export type FilterMode = "ALL" | "PICK" | "SKIP" | "WATCH";

export type LoadState = "loading" | "ok" | "error" | "empty";

export interface MarketAnalysis {
  market?: MarketCode | string;
  decision?: Decision;
  analysis_decision?: Decision;
  tendency?: string | null;
  lean?: string | null;
  lean_cn?: string | null;
  confidence?: number | string | null;
  line?: string | number | null;
  odds?: string | number | null;
  model_probability?: number | string | null;
  fair_odds?: string | number | null;
  risk_adjusted_ev?: string | number | null;
  reasons?: unknown;
  reason?: unknown;
  reason_cn?: unknown;
  risks?: unknown;
  risks_cn?: unknown;
  reference_scores?: unknown;
  scores?: unknown;
}

export interface ReadinessPayload {
  bookmakers?: number | string | null;
  odds_snapshots?: number | string | null;
  xg?: boolean | string | number | null;
  h2h?: boolean | string | number | null;
  lineups?: boolean | string | number | null;
}

export type AnalysisReadinessStatus = "READY" | "PARTIAL" | "BLOCKED" | "UNKNOWN";

export interface AnalysisReadiness {
  status: AnalysisReadinessStatus;
  blockers: string[];
  available_inputs: {
    market_observations?: number;
    bookmakers?: number;
    odds_snapshots?: number;
    xg?: boolean;
    score_matrix?: boolean;
    model_probabilities?: boolean;
    market_probabilities?: boolean;
    current_odds?: boolean;
    line_movement?: boolean;
  };
  next_action: string;
}

export interface BookmakerIntentPayload {
  intent?: string | null;
  label_cn?: string | null;
  opening_line?: string | number | null;
  current_line?: string | number | null;
  confidence?: number | string | null;
}

export interface MarketMovementPayload {
  status?: "READY" | "PARTIAL" | "INSUFFICIENT" | string;
  line_moved?: boolean;
  line_move_direction?: string | null;
  line_move_magnitude?: number | null;
  water_drift_home?: number | null;
  water_drift_away?: number | null;
  pattern?: string | null;
  timing?: string | null;
  checkpoints_seen?: string[];
  as_of_latest?: string | null;
  source?: string | null;
}

export interface MarketDivergencePayload {
  status?: "READY" | "INSUFFICIENT" | "UNVALIDATED" | string;
  factor_leader?: "HOME" | "AWAY" | "NEUTRAL" | "UNKNOWN" | string;
  factor_leader_team?: string | null;
  fair_ah?: number | null;
  market_open_ah?: number | null;
  market_lock_ah?: number | null;
  open_divergence?: number | null;
  lock_divergence?: number | null;
  book_deeper_than_factors?: boolean;
  book_deeper_side?: "HOME" | "AWAY" | "UNKNOWN" | string;
  magnitude?: number | null;
  calibration_status?: string | null;
  direction_allowed?: boolean;
}

export interface BookmakerHypothesisPayload {
  status?: "READY" | "PARTIAL" | "INSUFFICIENT" | string;
  label?: string;
  hypothesis?: string;
  alternative_explanations?: string[];
  sample_status?: string;
  sample_count?: number;
  verified?: boolean;
  direction_allowed?: boolean;
}

export interface AhOddsPayload {
  line?: string | number | null;
  home_line?: string | number | null;
  away_line?: string | number | null;
  home_price?: string | number | null;
  away_price?: string | number | null;
  price?: string | number | null;
  display_line_cn?: string | null;
  home_display_line_cn?: string | null;
  away_display_line_cn?: string | null;
  source?: string | null;
  as_of?: string | null;
  selection_policy?: string | null;
  selection_warning?: string | null;
  candidate_lines?: unknown;
  rejected_lines?: unknown;
}

export interface CurrentOddsPayload {
  ah?: AhOddsPayload | null;
  ou?: unknown;
}

export interface DataRefreshStatus {
  status?: string;
  status_label?: string;
  provider?: string;
  source?: string;
  odds_status?: string;
  lineups_status?: string;
  lineups_status_label?: string;
  xg_status?: string;
  xg_status_label?: string;
  statistics_status?: string;
  lineups_captured_at?: string | null;
  statistics_captured_at?: string | null;
  last_refresh_hint?: string | null;
}

export interface LineMovementPayload {
  ah_open?: string | number | null;
  ah_current?: string | number | null;
  ou_open?: string | number | null;
  ou_current?: string | number | null;
}

export interface DashboardCard {
  fixture_id?: string | number | null;
  kickoff_utc?: string | null;
  kickoff_beijing?: string | null;
  competition_name?: string | null;
  competition_cn?: string | null;
  home_name?: string | null;
  away_name?: string | null;
  home_cn?: string | null;
  away_cn?: string | null;
  home_team_name?: string | null;
  away_team_name?: string | null;
  home_team_name_zh?: string | null;
  away_team_name_zh?: string | null;
  home_team_display_name?: string | null;
  away_team_display_name?: string | null;
  home_team_provider_name?: string | null;
  away_team_provider_name?: string | null;
  decision?: Decision;
  loading?: boolean;
  watch_level?: number | string | null;
  bookmaker_intent?: BookmakerIntentPayload | Record<string, unknown> | null;
  market_movement?: MarketMovementPayload | Record<string, unknown> | null;
  market_divergence?: MarketDivergencePayload | Record<string, unknown> | null;
  bookmaker_hypothesis?: BookmakerHypothesisPayload | Record<string, unknown> | null;
  markets?: unknown;
  data_readiness?: ReadinessPayload | Record<string, unknown> | null;
  risks_cn?: unknown;
  risks?: unknown;
  candidate?: false | boolean;
  formal_recommendation?: false | boolean;
  line_movement?: LineMovementPayload | Record<string, unknown> | null;
  current_odds?: CurrentOddsPayload | Record<string, unknown> | null;
  ai_summary?: string | null;
  explain?: unknown;
  probability_distribution?: unknown;
  timeline?: unknown;
  temporal?: unknown;
  generated_at?: string | null;
}

export interface ReadinessItem {
  key: "odds" | "xg" | "h2h" | "lineups";
  label: string;
  value: string;
  ready: boolean;
  short: string;
}

export interface ScoreReference {
  scoreline: string;
  probability: string;
}

export interface DashboardStats {
  total: number;
  picks: number;
  skips: number;
  watch: number;
  ready: number;
  highWatch: number;
}

export type MatchStatus = "UPCOMING" | "LIVE" | "FINISHED" | "POSTPONED" | "CANCELLED" | "UNKNOWN";

export type RecommendationTier = "FORMAL" | "CANDIDATE" | "ANALYSIS_PICK" | "WATCH" | "NO_RECOMMENDATION";

export type SettlementStatus = "PENDING" | "HIT" | "MISS" | "PUSH" | "VOID" | "NO_BET" | "UNKNOWN";

export type DashboardMode = "today" | "next36" | "future" | "results" | "all";

export interface ScorelinePick {
  scoreline: string;
  home_goals?: number;
  away_goals?: number;
  probability?: number;
  probability_label?: string;
  hit?: boolean;
  direction_hit?: boolean;
  probability_type?: "UNCONDITIONAL_FILTERED_BY_SETTLEMENT" | string;
  selection?: string;
  line?: number;
  outcome?: string;
  source?: string;
}

export interface ScorelineReference {
  source?: string | null;
  estimate_id?: string | null;
  label?: string | null;
  top_scorelines?: ScorelinePick[];
  direction_scorelines?: ScorelinePick[];
  high_total?: {
    threshold?: number;
    probability?: number | null;
    probability_label?: string | null;
    representative_scoreline?: (ScorelinePick & { source?: string | null }) | null;
  } | null;
  very_high_total?: {
    threshold?: number;
    probability?: number | null;
    probability_label?: string | null;
  } | null;
  ah_key_scorelines?: Array<{
    outcome?: string;
    label?: string;
    scoreline?: string;
    home_goals?: number;
    away_goals?: number;
    representative_probability?: number | null;
    representative_probability_label?: string | null;
    settlement_probability?: number | null;
    settlement_probability_label?: string | null;
    source?: string | null;
  }>;
  market_settlement?: {
    market?: string;
    selection?: string;
    line?: number;
    source?: string;
    probabilities?: Record<string, number>;
    probability_labels?: Record<string, string>;
  } | null;
  distribution_provenance?: {
    model_family?: string | null;
    artifact_hash?: string | null;
    artifact_version?: string | null;
    train_cutoff?: string | null;
    feature_as_of?: string | null;
    home_mu?: number | null;
    away_mu?: number | null;
  } | null;
}

export interface ScorelineReadiness {
  status: "READY" | "INSUFFICIENT_INDEPENDENT_XG" | string;
  reason?: string | null;
  source?: string | null;
  model_version?: string | null;
  lambda_home?: number | null;
  lambda_away?: number | null;
  fair_ou?: number | null;
  xg_sample_status?: string | null;
}

export interface RecommendationPick {
  tier: RecommendationTier;
  market: string;
  market_label_cn: string;
  selection: string;
  selection_label_cn?: string;
  line?: string;
  odds?: string;
  hong_kong_odds?: string;
  model_probability?: number;
  fair_odds?: string;
  risk_adjusted_ev?: string;
  confidence?: number;
  confidence_label?: string;
  reasons: string[];
  risks: string[];
  value_explanation?: string;
  reverse_factor_value?: boolean;
  devig_probability?: number;
  generated_at?: string;
  locked_before_kickoff?: boolean;
  is_live_line?: boolean;
  candidate?: boolean;
  formal_recommendation?: boolean;
}

export type LockedPreMatchStatus = "LOCKED" | "NO_PREMATCH_FORMAL" | string;
export type LockedSettlementStatus = "PENDING" | "SETTLED" | "WAITING_RESULT" | "NO_BET" | string;

export interface LockedPreMatchRecommendation {
  status: LockedPreMatchStatus;
  fixture_id?: string | number | null;
  snapshot_id?: string | null;
  captured_at?: string | null;
  as_of?: string | null;
  kickoff_utc?: string | null;
  recommendation?: RecommendationPick | null;
  scoreline_reference?: ScorelineReference | null;
  simulation_evidence?: {
    simulations?: number | string | null;
    source?: string | null;
    model_version?: string | null;
    calibration_version?: string | null;
  } | null;
  reason?: string | null;
  settlement?: {
    status?: LockedSettlementStatus;
    result?: MatchResult | Record<string, unknown> | null;
    pnl?: string | number | null;
    settlement_outcome?: string | null;
    sample_included?: boolean | null;
    win_included?: boolean | null;
    evaluated_at?: string | null;
  } | null;
}

export type PricingShadowStatus = "RULE_BASED_UNCALIBRATED" | "INSUFFICIENT_INDEPENDENT_FACTORS" | "WATCH" | string;

export interface PricingShadowFactor {
  id: string;
  side: "HOME" | "AWAY" | "NEUTRAL" | "UNKNOWN" | string;
  weight: number;
  score: number | null;
  status: string;
  source?: string | null;
  source_group?: string | null;
  is_independent_signal?: boolean;
  proxy_of?: string | null;
  collection_status?: string | null;
}

export interface PricingShadow {
  fixture_id?: string;
  status: PricingShadowStatus;
  model_version?: string | null;
  calibration_version?: string | null;
  factors: PricingShadowFactor[];
  team_score?: {
    home?: number | null;
    away?: number | null;
  } | null;
  fair_ah?: number | null;
  fair_ou?: number | null;
  market_ah?: number | null;
  market_ou?: number | null;
  edge_ah?: number | null;
  edge_ou?: number | null;
  coverage?: number | null;
  independent_signal_count?: number;
  independent_signal_groups?: string[];
  xg_derived_factor_count?: number;
  missing_independent_sources?: string[];
  factor_source_summary?: Record<string, {
    source?: string | null;
    source_group?: string | null;
    is_independent_signal?: boolean;
    proxy_of?: string | null;
    collection_status?: string | null;
  }>;
  simulation?: Record<string, unknown> | null;
  simulation_model_version?: string | null;
  simulation_calibration_version?: string | null;
  simulation_status?: string | null;
  formal_eligible?: boolean;
  formal_blockers?: string[];
  ah_mainline_blocker?: string | null;
  canonical_ah_market_blocker?: string | null;
  asof_market_snapshot_id?: string | null;
  devig_method?: string | null;
  settlement_outcome?: string | null;
  formal_enabled?: false | boolean;
  candidate_enabled?: false | boolean;
  beats_market?: false | boolean;
  s2_gate?: {
    n_min?: number;
    beats_market?: false | boolean;
  };
}

export interface MatchResult {
  status: MatchStatus;
  home_goals?: number;
  away_goals?: number;
  final_score?: string;
  total_goals?: number;
  result_source?: string;
  settled_at?: string;
}

export interface ValidationSummary {
  settlement: SettlementStatus;
  market_hit?: boolean;
  score_exact_hit?: boolean;
  score_direction_hit?: boolean;
  total_goals_hit?: boolean;
  profit_units?: number;
  closing_line_value?: string;
  validation_notes?: string[];
  tier?: RecommendationTier;
  counted_in_official?: boolean;
  counted_in_analysis_shadow?: boolean;
}

export interface PerformanceBucket {
  sample_size: number;
  hit_count: number;
  miss_count: number;
  push_count: number;
  void_count: number;
  hit_rate?: number | null;
}

export interface OptionalEnrichmentItem {
  status?: string | null;
  affects_estimate?: boolean;
  adjustment?: number | null;
  source?: string | null;
  as_of?: string | null;
}

export interface OptionalEnrichment {
  lineups?: OptionalEnrichmentItem;
  player_value?: OptionalEnrichmentItem;
}

export interface DashboardMatchCard {
  fixture_id: string;
  kickoff_utc: string;
  kickoff_beijing?: string;
  operational_date_beijing?: string;
  competition_id?: string;
  competition_name: string;
  home_team_name: string;
  away_team_name: string;
  home_team_id?: string | null;
  away_team_id?: string | null;
  home_team_name_zh?: string | null;
  away_team_name_zh?: string | null;
  home_team_display_name?: string | null;
  away_team_display_name?: string | null;
  home_team_provider_name?: string | null;
  away_team_provider_name?: string | null;
  home_team_localization_status?: string | null;
  away_team_localization_status?: string | null;
  home_team_code?: string;
  away_team_code?: string;
  status: MatchStatus;
  raw_status?: string;
  data_state?: string;
  lifecycle_state?: string;
  watch_level?: number;
  data_readiness?: Record<string, unknown>;
  data_refresh?: DataRefreshStatus | null;
  analysis_readiness?: AnalysisReadiness;
  recommendation?: RecommendationPick | null;
  candidate?: boolean;
  formal_recommendation?: boolean;
  formal_suppressed?: boolean;
  formal_suppressed_reason?: string | null;
  locked_pre_match_recommendation?: LockedPreMatchRecommendation | null;
  scoreline_picks: ScorelinePick[];
  scoreline_reference?: ScorelineReference | null;
  scoreline_readiness?: ScorelineReadiness | null;
  result?: MatchResult | null;
  validation?: ValidationSummary | null;
  current_odds?: Record<string, unknown>;
  odds_movement?: Record<string, unknown>;
  market_strip?: Array<Record<string, unknown>>;
  bookmaker_intent?: Record<string, unknown>;
  market_movement?: MarketMovementPayload | null;
  market_divergence?: MarketDivergencePayload | null;
  bookmaker_hypothesis?: BookmakerHypothesisPayload | null;
  pricing_shadow?: PricingShadow | null;
  missing_inputs: string[];
}

export interface DashboardPerformance {
  today_count: number;
  next36_count: number;
  formal_count?: number;
  candidate_count: number;
  analysis_pick_count?: number;
  watch_count?: number;
  no_recommendation_count?: number;
  analysis_ready_count?: number;
  analysis_partial_count?: number;
  analysis_blocked_count?: number;
  analysis_unknown_count?: number;
  analysis_actionable_count?: number;
  analysis_readiness_rate?: number | null;
  analysis_blocker_distribution?: Record<string, number>;
  finished_count: number;
  average_confidence?: number;
  data_health_status: string;
  sample_size: number;
  hit_count: number;
  miss_count: number;
  push_count: number;
  void_count: number;
  hit_rate?: number | null;
  market_hit_rate?: number | null;
  score_hit_rate?: number | null;
  official?: PerformanceBucket;
  analysis_shadow?: PerformanceBucket;
  by_market: Array<{
    market: string;
    sample_size: number;
    hit_rate?: number | null;
  }>;
  score_exact: {
    sample_size: number;
    hit_count: number;
    hit_rate?: number | null;
  };
  forward_ledger?: ForwardLedgerPerformance;
}

export interface ForwardLedgerLeaguePerformance {
  league: string;
  record_count: number;
  fixture_count: number;
  double_snapshot_fixture_count: number;
  settled_sample_count: number;
  hit_count: number;
  miss_count: number;
  push_count: number;
  void_count: number;
  hit_rate?: number | null;
  clv_sample_count: number;
  clv_median_decimal?: number | null;
  clv_shadow_sample_count: number;
  clv_shadow_median_decimal?: number | null;
}

export interface ForwardLedgerPerformance {
  schema_version?: string;
  source?: string;
  sample_target: number;
  record_count: number;
  fixture_count: number;
  double_snapshot_fixture_count: number;
  validation_fixture_count: number;
  validation_settled_fixture_count: number;
  validation_pending_fixture_count: number;
  settled_sample_count: number;
  hit_count: number;
  miss_count: number;
  push_count: number;
  void_count: number;
  hit_rate?: number | null;
  outcomes_validation: ForwardLedgerOutcomeSummary;
  outcomes_shadow: ForwardLedgerOutcomeSummary;
  accumulation_label: string;
  clv: {
    sample_count: number;
    median_decimal?: number | null;
    positive_count: number;
    negative_count: number;
    push_count: number;
    line_changed_count: number;
    method?: string;
  };
  clv_shadow: {
    sample_count: number;
    median_decimal?: number | null;
    positive_count: number;
    negative_count: number;
    push_count: number;
    line_changed_count: number;
    line_clv_sample_count?: number;
    median_line_clv?: number | null;
    method?: string;
  };
  by_league: ForwardLedgerLeaguePerformance[];
  mock_data?: boolean;
}

export interface ForwardLedgerOutcomeSummary {
  settled_sample_count: number;
  hit_count: number;
  miss_count: number;
  push_count: number;
  void_count: number;
  hit_rate?: number | null;
}

export interface FormalTrackingSummary {
  status: string;
  label: string;
  min_bucket_samples_for_rate: number;
  snapshot_count: number;
  settlement_count: number;
  sample_count: number;
  win_count: number;
  win_rate?: number | null;
  roi?: number | null;
  not_a_formal_gate: boolean;
  posthoc_only: boolean;
}

export interface ReleaseMeta {
  web_git_sha: string;
  web_build_time?: string | null;
  release_id?: string | null;
  data_mode: string;
}

export interface ApiVersion {
  service?: string;
  environment?: string;
  api_git_sha: string;
  api_build_time?: string | null;
  release_id?: string | null;
  data_profile: string;
  data_source: string;
  database_ready?: boolean;
  read_model_fixture_count: number;
  matchday_card_count: number;
  result_event_count: number;
  generated_at?: string;
}

export interface DashboardDebug {
  read_model_fixture_count: number;
  matchday_card_count: number;
  future_fixture_count: number;
  future_fixture_in_window_count?: number;
  future_fixture_parse_error_count?: number;
  future_fixture_status_distribution?: Record<string, number>;
  future_fixture_date_distribution?: Record<string, number>;
  future_fixture_min_kickoff_utc?: string | null;
  future_fixture_max_kickoff_utc?: string | null;
  result_event_count: number;
  selected_date?: string;
  selected_date_has_data?: boolean;
  next_available_date?: string | null;
  empty_reason?: string | null;
  empty_detail?: string | null;
  suggested_actions?: string[];
}

export interface ReleaseSyncState {
  web_git_sha: string;
  api_git_sha: string;
  release_id?: string | null;
  data_profile: string;
  data_source: string;
  updated_at: string;
  demo: boolean;
  mismatch: boolean;
}

export interface DashboardDayViewCounts {
  total: number;
  lock_eligible: number;
  outcome_tracked: number;
  legacy_fallback: number;
  analysis_pick: number;
  recommend: number;
  watch: number;
  not_ready: number;
  skip: number;
  ready: number;
  partial: number;
  stale: number;
  blocked: number;
  by_decision_tier?: Record<string, number>;
  by_data_status?: Record<string, number>;
  by_lifecycle_status?: Record<string, number>;
}

export interface DashboardDayViewFreshness {
  last_refresh?: string | null;
  next_refresh_tick?: string | null;
  provider_budget_status?: string | null;
  refreshing?: boolean;
  staleness?: {
    stale_cards?: number;
    blocked_cards?: number;
    stale_or_blocked_cards?: number;
  };
  data_status_summary?: Record<string, number>;
}

export interface DashboardDayViewCard {
  fixture_id: string;
  kickoff_utc?: string | null;
  kickoff_beijing?: string | null;
  competition_id?: string | null;
  competition_name?: string | null;
  home_team_name?: string | null;
  away_team_name?: string | null;
  home_team_id?: string | null;
  away_team_id?: string | null;
  home_team_name_zh?: string | null;
  away_team_name_zh?: string | null;
  home_team_display_name?: string | null;
  away_team_display_name?: string | null;
  home_team_provider_name?: string | null;
  away_team_provider_name?: string | null;
  home_team_localization_status?: string | null;
  away_team_localization_status?: string | null;
  status?: string | null;
  source?: string | null;
  decision_tier: DecisionTier;
  data_status: DataStatus;
  lifecycle_status: LifecycleStatus;
  outcome_tracked: boolean;
  lock_eligible: boolean;
  recommendation_id?: string | null;
  reason_code?: string | null;
  action?: string | null;
  next_eval_at?: string | null;
  provider_budget_status?: string | null;
  missing_fields: string[];
  stale_fields: string[];
  data_readiness?: Record<string, unknown>;
  data_refresh?: DataRefreshStatus | null;
  analysis_readiness?: Record<string, unknown>;
  current_odds?: Record<string, unknown>;
  market_probabilities?: Record<string, unknown>;
  odds_movement?: Record<string, unknown>;
  probability_source?: string | null;
  model_market_divergence?: Record<string, unknown>;
  fair_market_estimates?: Array<Record<string, unknown>>;
  fair_market_estimate_ids?: string[];
  fair_market_estimate_snapshots?: Array<Record<string, unknown>>;
  analysis_gate_v2_shadow?: Record<string, unknown>;
  analysis_gate_v2_shadows?: Array<Record<string, unknown>>;
  optional_enrichment?: OptionalEnrichment;
  player_impact_estimate?: Record<string, unknown>;
  analysis_gate?: Record<string, unknown>;
  analysis_gates?: Array<Record<string, unknown>>;
  market_strip?: Array<Record<string, unknown>>;
  missing_inputs?: string[];
  pricing_shadow?: PricingShadow | null;
  scoreline_picks: ScorelinePick[];
  scoreline_reference?: ScorelineReference | null;
  scoreline_readiness?: ScorelineReadiness | null;
  pick?: {
    market?: string | null;
    selection?: string | null;
    line?: string | number | null;
    odds?: string | number | null;
    disclaimer?: string | null;
  } | null;
  non_pick?: Record<string, unknown> | null;
  one_liner?: string | null;
  card_hash?: string | null;
  diagnostics?: Record<string, unknown>;
}

export interface DashboardDayView {
  request_id?: string;
  generated_at: string;
  date: string;
  football_day: string;
  selected_football_day: string;
  environment: string;
  active_whitelist_count?: number | null;
  environment_policy?: Record<string, unknown>;
  timezone: string;
  window: string;
  source: string;
  checkpoint_key?: string;
  would_write_checkpoint: boolean;
  provider_calls: number;
  db_writes: number;
  counts: DashboardDayViewCounts;
  freshness: DashboardDayViewFreshness;
  navigation?: Record<string, unknown>;
  degradation?: Record<string, unknown>;
  cards: DashboardDayViewCard[];
}

export interface DashboardView {
  date: string;
  selected_date?: string;
  selected_football_day?: string;
  selected_date_has_data?: boolean;
  next_available_date?: string | null;
  football_day_timezone?: string;
  football_day_cutoff_hour?: number;
  football_day_start_utc?: string;
  football_day_end_utc?: string;
  generated_at: string;
  data_profile: string;
  data_source: string;
  release: ReleaseSyncState;
  debug: DashboardDebug;
  performance: DashboardPerformance;
  formal_tracking?: FormalTrackingSummary | null;
  day_view?: DashboardDayView | null;
  recommendations: DashboardMatchCard[];
  upcoming: DashboardMatchCard[];
  finished: DashboardMatchCard[];
  all: DashboardMatchCard[];
  errors: string[];
}
