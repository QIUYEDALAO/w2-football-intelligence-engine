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
