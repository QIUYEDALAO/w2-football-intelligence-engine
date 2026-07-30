export type PerformanceWindow = "7d" | "30d" | "90d";
export type PerformanceTier = "ALL" | "STRICT" | "ADVISORY";

export interface ReliabilityBin {
  lower: number;
  upper: number;
  count: number;
  mean_confidence: number | null;
  accuracy: number | null;
}

export interface PerformanceTierRow {
  tier: "STRICT" | "ADVISORY";
  finished_result_count: number;
  scored_count: number;
  canonical_settled_count: number;
  canonical_hit_rate: number | null;
  canonical_hit_rate_status: "AVAILABLE" | "INSUFFICIENT_SAMPLE";
  clv_mean: number | null;
  clv_positive_share: number | null;
}

export interface PerformancePayload {
  request_id: string;
  projection_version: "eval-01c.v2";
  scoring_window_anchor: string;
  selected_window: PerformanceWindow;
  selected_league: string | null;
  selected_tier: PerformanceTier;
  clv: {
    clv_population: "SCORABLE_FINISHED_WITH_CANONICAL_CLV";
    sample_count: number;
    mean: number | null;
    median: number | null;
    ci95: [number, number] | null;
    positive_count: number;
    positive_share: number | null;
    method: string;
    points: Array<{
      fixture_id: string;
      kickoff_utc: string;
      league: string;
      evaluation_tier: "STRICT" | "ADVISORY" | "UNKNOWN";
      clv_decimal: number;
    }>;
  };
  calibration: {
    scored_count: number;
    model_log_loss: number | null;
    market_log_loss: number | null;
    model_minus_market_log_loss: number | null;
    model_ece: number | null;
    market_ece: number | null;
    model_reliability_bins: ReliabilityBin[];
    market_reliability_bins: ReliabilityBin[];
    paired_log_loss_bootstrap: {
      status: "AVAILABLE" | "INSUFFICIENT";
      sample_count: number;
      metric?: string | null;
      delta?: number | null;
      ci95?: [number, number] | null;
      iterations?: number | null;
      seed?: number | null;
    };
  };
  tier_comparison: {
    STRICT: PerformanceTierRow;
    ADVISORY: PerformanceTierRow;
  };
  sample_progress: {
    current: number;
    target: number;
    ratio: number;
    status: "ACCUMULATING" | "TARGET_REACHED";
  };
  coverage: {
    finished_result_count: number;
    fixture_checkpoint_count: number;
    scored_count: number;
    not_scorable_count: number;
    blocked_count: number;
    not_scorable_by_reason: Record<string, number>;
  };
  checkpoint_metadata: {
    checkpoint_key: string;
    source_hash: string;
    created_at: string;
  };
}
