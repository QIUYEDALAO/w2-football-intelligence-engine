export type MarketCode = "ASIAN_HANDICAP" | "TOTALS" | "FIRST_HALF_GOALS" | "SCORE";

export type Decision = "PICK" | "SKIP" | "WATCH" | "ANALYSIS_PICK" | string;

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

export interface BookmakerIntentPayload {
  intent?: string | null;
  label_cn?: string | null;
  opening_line?: string | number | null;
  current_line?: string | number | null;
  confidence?: number | string | null;
}

export interface CurrentOddsPayload {
  ah?: unknown;
  ou?: unknown;
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
  decision?: Decision;
  loading?: boolean;
  watch_level?: number | string | null;
  bookmaker_intent?: BookmakerIntentPayload | Record<string, unknown> | null;
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

export type DashboardMode = "today" | "next36" | "results" | "all";

export interface ScorelinePick {
  scoreline: string;
  home_goals?: number;
  away_goals?: number;
  probability?: number;
  probability_label?: string;
  hit?: boolean;
  direction_hit?: boolean;
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
  reasons: string[];
  risks: string[];
  generated_at?: string;
  locked_before_kickoff?: boolean;
  is_live_line?: boolean;
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
  home_team_code?: string;
  away_team_code?: string;
  status: MatchStatus;
  raw_status?: string;
  data_state?: string;
  lifecycle_state?: string;
  watch_level?: number;
  data_readiness?: Record<string, unknown>;
  recommendation?: RecommendationPick | null;
  scoreline_picks: ScorelinePick[];
  result?: MatchResult | null;
  validation?: ValidationSummary | null;
  current_odds?: Record<string, unknown>;
  odds_movement?: Record<string, unknown>;
  market_strip?: Array<Record<string, unknown>>;
  bookmaker_intent?: Record<string, unknown>;
  missing_inputs: string[];
}

export interface DashboardPerformance {
  today_count: number;
  next36_count: number;
  candidate_count: number;
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
  result_event_count: number;
  selected_date?: string;
  selected_date_has_data?: boolean;
  next_available_date?: string | null;
  empty_reason?: string | null;
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

export interface DashboardView {
  date: string;
  generated_at: string;
  data_profile: string;
  data_source: string;
  release: ReleaseSyncState;
  debug: DashboardDebug;
  performance: DashboardPerformance;
  recommendations: DashboardMatchCard[];
  upcoming: DashboardMatchCard[];
  finished: DashboardMatchCard[];
  all: DashboardMatchCard[];
  errors: string[];
}
