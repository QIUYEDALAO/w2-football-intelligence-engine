export type LoadStatus = "LOADING" | "SUCCESS" | "EMPTY" | "ERROR" | "STALE";

export type Resource<T> = {
  status: LoadStatus;
  endpoint: string;
  data: T | null;
  requestId: string | null;
  errorCode: string | null;
  message: string | null;
};

export type Fixture = {
  fixture_id: string;
  competition_id: string;
  competition_name: string;
  kickoff_utc: string;
  kickoff_beijing?: string | null;
  operational_date_beijing?: string | null;
  kickoff_display: string;
  status: string;
  home_team_id: string;
  home_team_name?: string | null;
  away_team_id: string;
  away_team_name?: string | null;
  lifecycle_state: string;
  data_state: string;
  published_grade?: string | null;
  primary_market?: string | null;
  primary_line?: string | null;
  primary_odds?: string | null;
  last_captured?: string | null;
};

export type FixtureDetail = Fixture & {
  venue: string | null;
  bookmaker_count: number;
  market_coverage: Record<string, boolean>;
  forward_decision: string;
  provenance: Record<string, string>;
  risk_notes: string[];
  primary_market?: string | null;
  primary_selection?: string | null;
  primary_line?: string | null;
  primary_executable_odds?: string | null;
  primary_hong_kong_odds?: string | null;
  primary_model_fair_odds?: string | null;
  primary_risk_adjusted_ev?: string | null;
  research_grade?: string | null;
  ah_ladder?: Array<Record<string, unknown>>;
  ou_ladder?: Array<Record<string, unknown>>;
  all_market_ranking?: Array<Record<string, unknown>>;
  one_x_two_ranking?: Array<Record<string, unknown>>;
  btts_ranking?: Array<Record<string, unknown>>;
  secondary_market_direction?: Record<string, unknown> | null;
  source_snapshot_id?: string | null;
  source_captured_at?: string | null;
  source_phase?: string | null;
  valuation_generated_at?: string | null;
  projector_generated_at?: string | null;
  temporal_status?: string | null;
  integrity_status?: string | null;
};

export type FixtureList = {
  request_id: string;
  items: Fixture[];
};

export type Matchday = {
  request_id: string;
  date: string;
  total: number;
  items: Array<Record<string, unknown>>;
};

export type MatchdayCoverage = {
  request_id: string;
  requested_date_beijing: string;
  timezone: string;
  window_start_beijing: string;
  window_end_beijing: string;
  window_start_utc: string;
  window_end_utc: string;
  authoritative_count: number;
  discovered_count: number;
  eligible_count: number;
  card_count: number;
  read_model_count: number;
  displayed_count: number;
  missing_count: number;
  reason_distribution: Record<string, number>;
  coverage_status: "READY" | "PARTIAL" | "BLOCKED";
};

export type MarketRanking = {
  request_id: string;
  fixture_id: string;
  items: Array<Record<string, unknown>>;
};

export type Integrity = {
  request_id: string;
  fixture_id: string;
  integrity: Record<string, unknown>;
};

export type ForwardStatus = {
  request_id: string;
  status: string;
  locks: number;
  market_comparable: number;
  current_settled_n: number;
  target_n: number;
};

export type ProviderStatus = {
  request_id: string;
  provider: string;
  status: string;
  remaining_quota: number | null;
  credential_status: string;
  last_request_status: number | null;
};

export type DataHealth = {
  request_id: string;
  stale_data_count: number;
  provider_status: string;
  forward_cycle_age_seconds: number | null;
  generated_at: string;
  gate4_progress: Record<string, unknown>;
};

export type Probability = {
  request_id: string;
  probability_type: string;
  probabilities: Record<string, number>;
  source: string;
  quality: string;
  as_of_time: string | null;
};

export type OpsList = {
  request_id: string;
  items: Array<{ key: string; status: string; payload: Record<string, unknown> }>;
};

export type ShadowStrategyStatus = {
  request_id: string;
  status: string;
  strategy_version: string;
  gate4_status: string;
  gate5_status: string;
  formal_recommendation: boolean;
  decisions: number;
  locks: number;
  latest_run_id: string | null;
};
