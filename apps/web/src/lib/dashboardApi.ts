import { API_BASE } from "./labels";
import { asArray, asRecord, numberValue, textValue } from "./normalize";
import type {
  ApiVersion,
  DataRefreshStatus,
  DashboardDayView,
  DashboardDayViewCard,
  DashboardDayViewCounts,
  DashboardDebug,
  DashboardMatchCard,
  DashboardMode,
  DashboardPerformance,
  FormalTrackingSummary,
  LockedPreMatchRecommendation,
  DashboardView,
  MatchResult,
  MatchStatus,
  PricingShadow,
  PricingShadowFactor,
  RecommendationPick,
  ReleaseMeta,
  ReleaseSyncState,
  ValidationSummary,
} from "../types/dashboard";

const REQUEST_TIMEOUT_MS = 20000;
const DASHBOARD_CACHE_VERSION = "dashboard-v12-future-default-dayview-required";
const DASHBOARD_CACHE_TTL_MS = 60_000;

interface DashboardCacheEntry {
  version: string;
  stored_at: string;
  view: DashboardView;
}

interface FetchDashboardArgs {
  date: string;
  mode: DashboardMode;
  includeDebug?: boolean;
}

async function getJSON(
  url: string,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<unknown> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    signal: controller.signal,
  }).finally(() => {
    window.clearTimeout(timeout);
  });
  if (!response.ok) {
    throw new Error(`${url} -> HTTP ${response.status}`);
  }
  return response.json() as Promise<unknown>;
}

function explicitDemoMode(): boolean {
  const params = new URLSearchParams(window.location.search);
  return (
    params.get("demo") === "1" ||
    import.meta.env.VITE_DASHBOARD_DATA_MODE === "demo"
  );
}

function shortSha(value: string): string {
  return value && value !== "UNKNOWN" ? value.slice(0, 7) : "UNKNOWN";
}

function normalizeMeta(payload: unknown): ReleaseMeta {
  const record = asRecord(payload);
  return {
    web_git_sha: textValue(record.web_git_sha, "UNKNOWN"),
    web_build_time: textValue(record.web_build_time) || null,
    release_id: textValue(record.release_id) || null,
    data_mode: textValue(record.data_mode, "api"),
  };
}

function normalizeVersion(payload: unknown): ApiVersion {
  const record = asRecord(payload);
  return {
    service: textValue(record.service),
    environment: textValue(record.environment),
    api_git_sha: textValue(record.api_git_sha, "UNKNOWN"),
    api_build_time: textValue(record.api_build_time) || null,
    release_id: textValue(record.release_id) || null,
    data_profile: textValue(record.data_profile, "empty"),
    data_source: textValue(record.data_source, "empty"),
    database_ready: Boolean(record.database_ready),
    read_model_fixture_count: numberValue(record.read_model_fixture_count),
    matchday_card_count: numberValue(record.matchday_card_count),
    result_event_count: numberValue(record.result_event_count),
    release_identity: asRecord(record.release_identity),
    generated_at: textValue(record.generated_at),
  };
}

function normalizeDebug(payload: unknown): DashboardDebug {
  const record = asRecord(payload);
  return {
    read_model_fixture_count: numberValue(record.read_model_fixture_count),
    matchday_card_count: numberValue(record.matchday_card_count),
    future_fixture_count: numberValue(record.future_fixture_count),
    future_fixture_in_window_count: numberValue(
      record.future_fixture_in_window_count,
    ),
    future_fixture_parse_error_count: numberValue(
      record.future_fixture_parse_error_count,
    ),
    future_fixture_status_distribution: asRecord(
      record.future_fixture_status_distribution,
    ) as Record<string, number>,
    future_fixture_date_distribution: asRecord(
      record.future_fixture_date_distribution,
    ) as Record<string, number>,
    future_fixture_min_kickoff_utc:
      textValue(record.future_fixture_min_kickoff_utc) || null,
    future_fixture_max_kickoff_utc:
      textValue(record.future_fixture_max_kickoff_utc) || null,
    result_event_count: numberValue(record.result_event_count),
    selected_date: textValue(record.selected_date),
    selected_date_has_data: Boolean(record.selected_date_has_data),
    next_available_date: textValue(record.next_available_date) || null,
    empty_reason: textValue(record.empty_reason) || null,
    empty_detail: textValue(record.empty_detail) || null,
    suggested_actions: asArray(record.suggested_actions)
      .map((item) => textValue(item))
      .filter(Boolean),
  };
}

function normalizePerformance(payload: unknown): DashboardPerformance {
  const record = asRecord(payload);
  const scoreExact = asRecord(record.score_exact);
  const official = asRecord(record.official);
  const analysisShadow = asRecord(record.analysis_shadow);
  const forwardLedger = asRecord(record.forward_ledger);
  const forwardClv = asRecord(forwardLedger.clv);
  const performanceCohort = asRecord(forwardLedger.performance_cohort);
  const cohortOutcomes = asRecord(performanceCohort.outcomes);
  const cohortClv = asRecord(performanceCohort.clv);
  const validationOutcomes = asRecord(forwardLedger.outcomes_validation);
  const canonicalOutcomes = asRecord(forwardLedger.outcomes_canonical);
  const officialOutcomes = asRecord(forwardLedger.outcomes);
  const shadowOutcomes = asRecord(forwardLedger.outcomes_shadow);
  const evidenceWindow = asRecord(forwardLedger.evidence_window);
  const bucket = (row: Record<string, unknown>) => ({
    sample_size: numberValue(row.sample_size),
    hit_count: numberValue(row.hit_count),
    miss_count: numberValue(row.miss_count),
    push_count: numberValue(row.push_count),
    void_count: numberValue(row.void_count),
    hit_rate: typeof row.hit_rate === "number" ? row.hit_rate : null,
  });
  const outcomeSummary = (row: Record<string, unknown>) => ({
    settled_sample_count: numberValue(row.settled_sample_count),
    hit_count: numberValue(row.hit_count),
    miss_count: numberValue(row.miss_count),
    push_count: numberValue(row.push_count),
    void_count: numberValue(row.void_count),
    hit_rate: typeof row.hit_rate === "number" ? row.hit_rate : null,
  });
  const clvSummary = (row: Record<string, unknown>) => ({
    sample_count: numberValue(row.sample_count),
    candidate_count: numberValue(row.candidate_count),
    missing_count: numberValue(row.missing_count),
    median_decimal:
      typeof row.median_decimal === "number" ? row.median_decimal : null,
    positive_count: numberValue(row.positive_count),
    negative_count: numberValue(row.negative_count),
    push_count: numberValue(row.push_count),
    line_changed_count: numberValue(row.line_changed_count),
    stale_closing_count: numberValue(row.stale_closing_count),
    insufficient_snapshot_count: numberValue(row.insufficient_snapshot_count),
    method: textValue(row.method) || undefined,
  });
  const cohortOutcomeSummary = (row: Record<string, unknown>) => ({
    ...outcomeSummary(row),
    decisive_count: numberValue(row.decisive_count),
  });
  return {
    today_count: numberValue(record.today_count),
    next36_count: numberValue(record.next36_count),
    formal_count: numberValue(record.formal_count),
    candidate_count: numberValue(record.candidate_count),
    analysis_pick_count: numberValue(record.analysis_pick_count),
    watch_count: numberValue(record.watch_count),
    no_recommendation_count: numberValue(record.no_recommendation_count),
    analysis_ready_count: numberValue(record.analysis_ready_count),
    analysis_partial_count: numberValue(record.analysis_partial_count),
    analysis_blocked_count: numberValue(record.analysis_blocked_count),
    analysis_unknown_count: numberValue(record.analysis_unknown_count),
    analysis_actionable_count: numberValue(record.analysis_actionable_count),
    analysis_readiness_rate:
      typeof record.analysis_readiness_rate === "number"
        ? record.analysis_readiness_rate
        : null,
    analysis_blocker_distribution: asRecord(
      record.analysis_blocker_distribution,
    ) as Record<string, number>,
    finished_count: numberValue(record.finished_count),
    average_confidence:
      typeof record.average_confidence === "number"
        ? record.average_confidence
        : undefined,
    data_health_status: textValue(record.data_health_status, "READ_ONLY"),
    sample_size: numberValue(record.sample_size),
    hit_count: numberValue(record.hit_count),
    miss_count: numberValue(record.miss_count),
    push_count: numberValue(record.push_count),
    void_count: numberValue(record.void_count),
    hit_rate: typeof record.hit_rate === "number" ? record.hit_rate : null,
    market_hit_rate:
      typeof record.market_hit_rate === "number"
        ? record.market_hit_rate
        : null,
    score_hit_rate:
      typeof record.score_hit_rate === "number" ? record.score_hit_rate : null,
    official: bucket(official),
    analysis_shadow: bucket(analysisShadow),
    by_market: asArray(record.by_market).map((item) => {
      const row = asRecord(item);
      return {
        market: textValue(row.market, "市场"),
        sample_size: numberValue(row.sample_size),
        hit_rate: typeof row.hit_rate === "number" ? row.hit_rate : null,
      };
    }),
    score_exact: {
      sample_size: numberValue(scoreExact.sample_size),
      hit_count: numberValue(scoreExact.hit_count),
      hit_rate:
        typeof scoreExact.hit_rate === "number" ? scoreExact.hit_rate : null,
    },
    forward_ledger: Object.keys(forwardLedger).length
      ? {
          schema_version: textValue(forwardLedger.schema_version) || undefined,
          source: textValue(forwardLedger.source) || undefined,
          sample_target: numberValue(forwardLedger.sample_target),
          record_count: numberValue(forwardLedger.record_count),
          fixture_count: numberValue(forwardLedger.fixture_count),
          settled_sample_count: numberValue(forwardLedger.settled_sample_count),
          hit_count: numberValue(forwardLedger.hit_count),
          miss_count: numberValue(forwardLedger.miss_count),
          push_count: numberValue(forwardLedger.push_count),
          void_count: numberValue(forwardLedger.void_count),
          hit_rate:
            typeof forwardLedger.hit_rate === "number"
              ? forwardLedger.hit_rate
              : null,
          validation_fixture_count: numberValue(
            forwardLedger.validation_fixture_count,
          ),
          validation_settled_fixture_count: numberValue(
            forwardLedger.validation_settled_fixture_count,
          ),
          validation_pending_fixture_count: numberValue(
            forwardLedger.validation_pending_fixture_count,
          ),
          validation_pending_status: (() => {
            const status = asRecord(forwardLedger.validation_pending_status);
            return {
              waiting_finish_count: numberValue(status.waiting_finish_count),
              postponed_count: numberValue(status.postponed_count),
              result_missing_count: numberValue(status.result_missing_count),
              settlement_error_count: numberValue(
                status.settlement_error_count,
              ),
              details: Array.isArray(status.details)
                ? status.details.map((item) => {
                    const detail = asRecord(item);
                    return {
                      fixture_id: textValue(detail.fixture_id),
                      category: textValue(detail.category),
                      last_checked_at_utc:
                        textValue(detail.last_checked_at_utc) || null,
                      next_check_at_utc:
                        textValue(detail.next_check_at_utc) || null,
                    };
                  })
                : [],
            };
          })(),
          outcomes_validation: outcomeSummary(validationOutcomes),
          outcomes_canonical: outcomeSummary(canonicalOutcomes),
          performance_cohort: {
            validation_count: numberValue(performanceCohort.validation_count),
            processed_count: numberValue(performanceCohort.processed_count),
            eligible_count: numberValue(performanceCohort.eligible_count),
            excluded_count: numberValue(performanceCohort.excluded_count),
            recovered_count: numberValue(performanceCohort.recovered_count),
            pending_count: numberValue(performanceCohort.pending_count),
            outcomes: cohortOutcomeSummary(cohortOutcomes),
            clv: clvSummary(cohortClv),
            by_league: asArray(performanceCohort.by_league).map((item) => {
              const row = asRecord(item);
              return {
                competition_id: textValue(row.competition_id) || null,
                league: textValue(row.league, "UNKNOWN"),
                processed_count: numberValue(row.processed_count),
                eligible_count: numberValue(row.eligible_count),
                excluded_count: numberValue(row.excluded_count),
                decisive_count: numberValue(row.decisive_count),
                outcomes: cohortOutcomeSummary(asRecord(row.outcomes)),
                clv: clvSummary(asRecord(row.clv)),
                rate_status:
                  textValue(row.rate_status) === "AVAILABLE"
                    ? ("AVAILABLE" as const)
                    : ("INSUFFICIENT" as const),
              };
            }),
            exclusions: asArray(performanceCohort.exclusions).map((item) => {
              const row = asRecord(item);
              return {
                fixture_id: textValue(row.fixture_id),
                competition_id: textValue(row.competition_id) || null,
                league: textValue(row.league, "UNKNOWN"),
                home_team_name: textValue(row.home_team_name),
                away_team_name: textValue(row.away_team_name),
                kickoff_utc: textValue(row.kickoff_utc),
                settlement_outcome: textValue(row.settlement_outcome),
                reason_code: textValue(row.reason_code),
                reason_label: textValue(
                  row.reason_label,
                  "不符合当前统计身份契约",
                ),
              };
            }),
            recoveries: asArray(performanceCohort.recoveries).map((item) => {
              const row = asRecord(item);
              return {
                fixture_id: textValue(row.fixture_id),
                competition_id: textValue(row.competition_id) || null,
                league: textValue(row.league, "UNKNOWN"),
                home_team_name: textValue(row.home_team_name),
                away_team_name: textValue(row.away_team_name),
                kickoff_utc: textValue(row.kickoff_utc),
                settlement_outcome: textValue(row.settlement_outcome),
                recovery_code: textValue(row.recovery_code),
                recovery_label: textValue(
                  row.recovery_label,
                  "经唯一历史快照审计恢复",
                ),
              };
            }),
            invariants: asRecord(performanceCohort.invariants) as Record<
              string,
              boolean | string
            >,
          },
          outcomes: outcomeSummary(officialOutcomes),
          outcomes_shadow: outcomeSummary(shadowOutcomes),
          canonical_settled_fixture_count: numberValue(
            forwardLedger.canonical_settled_fixture_count,
          ),
          canonical_excluded_count: numberValue(
            forwardLedger.canonical_excluded_count,
          ),
          canonical_excluded_by_reason: asRecord(
            forwardLedger.canonical_excluded_by_reason,
          ) as Record<string, number>,
          validation_excluded_count: numberValue(
            forwardLedger.validation_excluded_count,
          ),
          validation_excluded_by_reason: asRecord(
            forwardLedger.validation_excluded_by_reason,
          ) as Record<string, number>,
          evidence_window: {
            first_capture_at:
              textValue(evidenceWindow.first_capture_at) || null,
            latest_capture_at:
              textValue(evidenceWindow.latest_capture_at) || null,
            latest_outcome_at:
              textValue(evidenceWindow.latest_outcome_at) || null,
          },
          accumulation_label: textValue(
            forwardLedger.accumulation_label,
            "积累中 0/200",
          ),
          clv: clvSummary(forwardClv),
          by_league: asArray(forwardLedger.by_league).map((item) => {
            const row = asRecord(item);
            return {
              league: textValue(row.league, "UNKNOWN"),
              record_count: numberValue(row.record_count),
              fixture_count: numberValue(row.fixture_count),
              settled_sample_count: numberValue(row.settled_sample_count),
              hit_count: numberValue(row.hit_count),
              miss_count: numberValue(row.miss_count),
              push_count: numberValue(row.push_count),
              void_count: numberValue(row.void_count),
              hit_rate: typeof row.hit_rate === "number" ? row.hit_rate : null,
              clv_sample_count: numberValue(row.clv_sample_count),
              clv_median_decimal:
                typeof row.clv_median_decimal === "number"
                  ? row.clv_median_decimal
                  : null,
            };
          }),
          by_league_validation: asArray(forwardLedger.by_league_validation).map(
            (item) => {
              const row = asRecord(item);
              return {
                competition_id: textValue(row.competition_id) || null,
                league: textValue(row.league, "UNKNOWN"),
                validation_fixture_count: numberValue(
                  row.validation_fixture_count,
                ),
                validation_settled_fixture_count: numberValue(
                  row.validation_settled_fixture_count,
                ),
                canonical_settled_fixture_count: numberValue(
                  row.canonical_settled_fixture_count,
                ),
                canonical_excluded_count: numberValue(
                  row.canonical_excluded_count,
                ),
                hit_count: numberValue(row.hit_count),
                miss_count: numberValue(row.miss_count),
                push_count: numberValue(row.push_count),
                void_count: numberValue(row.void_count),
                hit_rate:
                  typeof row.hit_rate === "number" ? row.hit_rate : null,
                clv_sample_count: numberValue(row.clv_sample_count),
                clv_median_decimal:
                  typeof row.clv_median_decimal === "number"
                    ? row.clv_median_decimal
                    : null,
              };
            },
          ),
          mock_data: Boolean(forwardLedger.mock_data),
        }
      : undefined,
  };
}

function normalizeFormalTracking(
  payload: unknown,
): FormalTrackingSummary | null {
  const record = asRecord(payload);
  const status = textValue(record.status);
  if (!status) return null;
  return {
    status,
    label: textValue(record.label, "观察中 · 0/30"),
    min_bucket_samples_for_rate:
      numberValue(record.min_bucket_samples_for_rate) || 30,
    snapshot_count: numberValue(record.snapshot_count),
    settlement_count: numberValue(record.settlement_count),
    sample_count: numberValue(record.sample_count),
    win_count: numberValue(record.win_count),
    win_rate: typeof record.win_rate === "number" ? record.win_rate : null,
    roi: typeof record.roi === "number" ? record.roi : null,
    not_a_formal_gate: record.not_a_formal_gate === true,
    posthoc_only: record.posthoc_only === true,
  };
}

function normalizeAnalysisReadiness(payload: unknown) {
  const record = asRecord(payload);
  const available = asRecord(record.available_inputs);
  return {
    status: textValue(record.status, "UNKNOWN") as
      | "READY"
      | "PARTIAL"
      | "BLOCKED"
      | "UNKNOWN",
    blockers: asArray(record.blockers)
      .map((item) => textValue(item))
      .filter(Boolean),
    available_inputs: {
      market_observations: numberValue(available.market_observations),
      bookmakers: numberValue(available.bookmakers),
      odds_snapshots: numberValue(available.odds_snapshots),
      xg: Boolean(available.xg),
      score_matrix: Boolean(available.score_matrix),
      model_probabilities: Boolean(available.model_probabilities),
      market_probabilities: Boolean(available.market_probabilities),
      current_odds: Boolean(available.current_odds),
      line_movement: Boolean(available.line_movement),
    },
    next_action: textValue(record.next_action, "INVESTIGATE_DATA_PIPELINE"),
  };
}

function normalizeDataRefresh(payload: unknown): DataRefreshStatus | null {
  const record = asRecord(payload);
  const status = textValue(record.status);
  if (!status) return null;
  return {
    status,
    status_label: textValue(record.status_label),
    provider: textValue(record.provider),
    source: textValue(record.source),
    odds_status: textValue(record.odds_status),
    lineups_status: textValue(record.lineups_status),
    lineups_status_label: textValue(record.lineups_status_label),
    xg_status: textValue(record.xg_status),
    xg_status_label: textValue(record.xg_status_label),
    statistics_status: textValue(record.statistics_status),
    lineups_captured_at: textValue(record.lineups_captured_at) || null,
    statistics_captured_at: textValue(record.statistics_captured_at) || null,
    last_refresh_hint: textValue(record.last_refresh_hint) || null,
  };
}

function nullableNumber(payload: unknown): number | null {
  return typeof payload === "number" && Number.isFinite(payload)
    ? payload
    : null;
}

function normalizePricingShadowFactor(payload: unknown): PricingShadowFactor {
  const record = asRecord(payload);
  return {
    id: textValue(record.id, "UNKNOWN_FACTOR"),
    side: textValue(record.side, "UNKNOWN"),
    weight: nullableNumber(record.weight) ?? 0,
    score: nullableNumber(record.score),
    status: textValue(record.status, "UNKNOWN"),
    source: textValue(record.source) || null,
    source_group: textValue(record.source_group) || null,
    is_independent_signal: record.is_independent_signal === true,
    proxy_of: textValue(record.proxy_of) || null,
    collection_status: textValue(record.collection_status) || null,
  };
}

function normalizeFactorSourceSummary(
  payload: unknown,
): PricingShadow["factor_source_summary"] {
  const record = asRecord(payload);
  return Object.fromEntries(
    Object.entries(record).map(([key, value]) => {
      const row = asRecord(value);
      return [
        key,
        {
          source: textValue(row.source) || null,
          source_group: textValue(row.source_group) || null,
          is_independent_signal: row.is_independent_signal === true,
          proxy_of: textValue(row.proxy_of) || null,
          collection_status: textValue(row.collection_status) || null,
        },
      ];
    }),
  );
}

function normalizePricingShadow(payload: unknown): PricingShadow | null {
  const record = asRecord(payload);
  const status = textValue(record.status);
  if (!status) return null;
  const s2Gate = asRecord(record.s2_gate);
  const teamScore = asRecord(record.team_score);
  return {
    fixture_id: textValue(record.fixture_id),
    status,
    model_version: textValue(record.model_version) || null,
    calibration_version: textValue(record.calibration_version) || null,
    factors: asArray(record.factors).map(normalizePricingShadowFactor),
    team_score: {
      home: nullableNumber(teamScore.home),
      away: nullableNumber(teamScore.away),
    },
    fair_ah: nullableNumber(record.fair_ah),
    fair_ou: nullableNumber(record.fair_ou),
    market_ah: nullableNumber(record.market_ah),
    market_ou: nullableNumber(record.market_ou),
    edge_ah: nullableNumber(record.edge_ah),
    edge_ou: nullableNumber(record.edge_ou),
    coverage: nullableNumber(record.coverage),
    independent_signal_count: numberValue(record.independent_signal_count),
    independent_signal_groups: asArray(record.independent_signal_groups)
      .map((item) => textValue(item))
      .filter(Boolean),
    xg_derived_factor_count: numberValue(record.xg_derived_factor_count),
    missing_independent_sources: asArray(record.missing_independent_sources)
      .map((item) => textValue(item))
      .filter(Boolean),
    factor_source_summary: normalizeFactorSourceSummary(
      record.factor_source_summary,
    ),
    simulation: Object.keys(asRecord(record.simulation)).length
      ? asRecord(record.simulation)
      : null,
    simulation_model_version:
      textValue(record.simulation_model_version) || null,
    simulation_calibration_version:
      textValue(record.simulation_calibration_version) || null,
    simulation_status: textValue(record.simulation_status) || null,
    formal_eligible: record.formal_eligible === true,
    formal_blockers: asArray(record.formal_blockers)
      .map((item) => textValue(item))
      .filter(Boolean),
    ah_mainline_blocker: textValue(record.ah_mainline_blocker) || null,
    canonical_ah_market_blocker:
      textValue(record.canonical_ah_market_blocker) || null,
    asof_market_snapshot_id: textValue(record.asof_market_snapshot_id) || null,
    devig_method: textValue(record.devig_method) || null,
    settlement_outcome: textValue(record.settlement_outcome) || null,
    formal_enabled: record.formal_enabled === true,
    candidate_enabled: record.candidate_enabled === true,
    beats_market: record.beats_market === true,
    s2_gate: {
      n_min: nullableNumber(s2Gate.n_min) ?? undefined,
      beats_market: s2Gate.beats_market === true,
    },
  };
}

function normalizeScorelineReadiness(payload: unknown) {
  const record = asRecord(payload);
  const status = textValue(record.status);
  if (!status) return null;
  return {
    status,
    reason: textValue(record.reason) || null,
    source: textValue(record.source) || null,
    model_version: textValue(record.model_version) || null,
    lambda_home: nullableNumber(record.lambda_home),
    lambda_away: nullableNumber(record.lambda_away),
    fair_ou: nullableNumber(record.fair_ou),
    xg_sample_status: textValue(record.xg_sample_status) || null,
  };
}

function normalizeScorelinePick(payload: unknown) {
  const row = asRecord(payload);
  return {
    scoreline: textValue(row.scoreline),
    home_goals: numberValue(row.home_goals) ?? undefined,
    away_goals: numberValue(row.away_goals) ?? undefined,
    probability:
      typeof row.probability === "number" ? row.probability : undefined,
    probability_label: textValue(row.probability_label),
  };
}

function normalizeScorelineReference(payload: unknown) {
  const record = asRecord(payload);
  const source = textValue(record.source);
  if (
    !source &&
    !record.top_scorelines &&
    !record.direction_top3 &&
    !record.high_total &&
    !record.ah_key_scorelines
  )
    return null;
  return {
    source: source || null,
    label: textValue(record.label) || null,
    top_scorelines: asArray(record.top_scorelines)
      .map(normalizeScorelinePick)
      .filter((row) => row.scoreline),
    direction_top3: asArray(record.direction_top3)
      .map((item) => ({
        ...asRecord(item),
        ...normalizeScorelinePick(item),
      }))
      .filter((row) => row.scoreline),
    high_total: Object.keys(asRecord(record.high_total)).length
      ? asRecord(record.high_total)
      : null,
    very_high_total: Object.keys(asRecord(record.very_high_total)).length
      ? asRecord(record.very_high_total)
      : null,
    ah_key_scorelines: asArray(record.ah_key_scorelines).map((item) =>
      asRecord(item),
    ),
  };
}

function normalizeLockedPreMatchRecommendation(
  payload: unknown,
): LockedPreMatchRecommendation | null {
  const record = asRecord(payload);
  const status = textValue(record.status);
  if (!status) return null;
  const settlement = asRecord(record.settlement);
  const simulationEvidence = asRecord(record.simulation_evidence);
  return {
    status,
    fixture_id: textValue(record.fixture_id) || null,
    snapshot_id: textValue(record.snapshot_id) || null,
    captured_at: textValue(record.captured_at) || null,
    as_of: textValue(record.as_of) || null,
    kickoff_utc: textValue(record.kickoff_utc) || null,
    recommendation: record.recommendation
      ? (asRecord(record.recommendation) as unknown as RecommendationPick)
      : null,
    scoreline_reference: normalizeScorelineReference(
      record.scoreline_reference,
    ),
    simulation_evidence: Object.keys(simulationEvidence).length
      ? {
          simulations:
            numberValue(simulationEvidence.simulations) ??
            (textValue(simulationEvidence.simulations) || null),
          source: textValue(simulationEvidence.source) || null,
          model_version: textValue(simulationEvidence.model_version) || null,
          calibration_version:
            textValue(simulationEvidence.calibration_version) || null,
        }
      : null,
    reason: textValue(record.reason) || null,
    settlement: Object.keys(settlement).length
      ? {
          status: textValue(settlement.status),
          result: asRecord(settlement.result),
          pnl:
            numberValue(settlement.pnl) ?? (textValue(settlement.pnl) || null),
          settlement_outcome: textValue(settlement.settlement_outcome) || null,
          sample_included: settlement.sample_included === true,
          win_included: settlement.win_included === true,
          evaluated_at: textValue(settlement.evaluated_at) || null,
        }
      : null,
  };
}

function normalizeMarketMovement(payload: unknown) {
  const record = asRecord(payload);
  const status = textValue(record.status);
  if (!status) return null;
  return {
    status,
    line_moved: record.line_moved === true,
    line_move_direction: textValue(record.line_move_direction) || null,
    line_move_magnitude: nullableNumber(record.line_move_magnitude),
    water_drift_home: nullableNumber(record.water_drift_home),
    water_drift_away: nullableNumber(record.water_drift_away),
    pattern: textValue(record.pattern) || null,
    timing: textValue(record.timing) || null,
    checkpoints_seen: asArray(record.checkpoints_seen)
      .map((item) => textValue(item))
      .filter(Boolean),
    as_of_latest: textValue(record.as_of_latest) || null,
    source: textValue(record.source) || null,
  };
}

function normalizeMarketDivergence(payload: unknown) {
  const record = asRecord(payload);
  const status = textValue(record.status);
  if (!status) return null;
  return {
    status,
    factor_leader: textValue(record.factor_leader) || "UNKNOWN",
    factor_leader_team: textValue(record.factor_leader_team) || null,
    fair_ah: nullableNumber(record.fair_ah),
    market_open_ah: nullableNumber(record.market_open_ah),
    market_lock_ah: nullableNumber(record.market_lock_ah),
    open_divergence: nullableNumber(record.open_divergence),
    lock_divergence: nullableNumber(record.lock_divergence),
    book_deeper_than_factors: record.book_deeper_than_factors === true,
    book_deeper_side: textValue(record.book_deeper_side) || "UNKNOWN",
    magnitude: nullableNumber(record.magnitude),
    calibration_status: textValue(record.calibration_status) || null,
    direction_allowed: record.direction_allowed === true,
  };
}

function normalizeBookmakerHypothesis(payload: unknown) {
  const record = asRecord(payload);
  const status = textValue(record.status);
  if (!status) return null;
  return {
    status,
    label: textValue(record.label, "盘口假设 · 未验证"),
    hypothesis: textValue(record.hypothesis, "盘口轨迹不足，暂不形成假设"),
    alternative_explanations: asArray(record.alternative_explanations)
      .map((item) => textValue(item))
      .filter(Boolean),
    sample_status: textValue(record.sample_status, "观察中"),
    sample_count: numberValue(record.sample_count) ?? 0,
    verified: record.verified === true,
    direction_allowed: record.direction_allowed === true,
  };
}

function normalizeRecommendationPick(
  payload: unknown,
): RecommendationPick | null {
  const record = asRecord(payload);
  if (!Object.keys(record).length) return null;
  return {
    ...(record as unknown as RecommendationPick),
    tier: textValue(record.tier, "WATCH") as RecommendationPick["tier"],
    market: textValue(record.market, "UNKNOWN"),
    market_label_cn: textValue(record.market_label_cn, "市场"),
    selection: textValue(record.selection, "WATCH"),
    selection_label_cn: textValue(record.selection_label_cn),
    line: textValue(record.line),
    odds: textValue(record.odds),
    hong_kong_odds: textValue(record.hong_kong_odds),
    model_probability: numberValue(record.model_probability) ?? undefined,
    confidence: numberValue(record.confidence) ?? undefined,
    confidence_label: textValue(record.confidence_label),
    reasons: asArray(record.reasons)
      .map((item) => textValue(item))
      .filter(Boolean),
    risks: asArray(record.risks)
      .map((item) => textValue(item))
      .filter(Boolean),
    value_explanation: textValue(record.value_explanation),
    candidate: record.candidate === true,
    formal_recommendation: record.formal_recommendation === true,
  };
}

function normalizeCard(payload: unknown): DashboardMatchCard {
  const record = asRecord(payload);
  return {
    fixture_id: textValue(record.fixture_id, "unknown-fixture"),
    kickoff_utc: textValue(record.kickoff_utc),
    kickoff_beijing: textValue(record.kickoff_beijing),
    operational_date_beijing: textValue(record.operational_date_beijing),
    competition_id: textValue(record.competition_id),
    competition_name: textValue(record.competition_name, "世界杯"),
    home_team_name: textValue(record.home_team_name, "主队"),
    away_team_name: textValue(record.away_team_name, "客队"),
    status: textValue(record.status, "UPCOMING") as MatchStatus,
    raw_status: textValue(record.raw_status),
    data_state: textValue(record.data_state),
    lifecycle_state: textValue(record.lifecycle_state),
    watch_level: numberValue(record.watch_level),
    data_readiness: asRecord(record.data_readiness),
    data_refresh: normalizeDataRefresh(record.data_refresh),
    analysis_readiness: normalizeAnalysisReadiness(record.analysis_readiness),
    recommendation: normalizeRecommendationPick(record.recommendation),
    candidate: record.candidate === true,
    formal_recommendation: record.formal_recommendation === true,
    formal_suppressed: record.formal_suppressed === true,
    formal_suppressed_reason:
      textValue(record.formal_suppressed_reason) || null,
    locked_pre_match_recommendation: normalizeLockedPreMatchRecommendation(
      record.locked_pre_match_recommendation,
    ),
    scoreline_picks: asArray(record.scoreline_picks)
      .map(normalizeScorelinePick)
      .filter((row) => row.scoreline),
    scoreline_reference: normalizeScorelineReference(
      record.scoreline_reference,
    ),
    scoreline_readiness: normalizeScorelineReadiness(
      record.scoreline_readiness,
    ),
    result: record.result
      ? (asRecord(record.result) as unknown as MatchResult)
      : null,
    validation: record.validation
      ? (asRecord(record.validation) as unknown as ValidationSummary)
      : null,
    current_odds: asRecord(record.current_odds),
    last_known_odds: asRecord(record.last_known_odds),
    odds_movement: asRecord(record.odds_movement),
    market_strip: asArray(record.market_strip).map((item) => asRecord(item)),
    bookmaker_intent: asRecord(record.bookmaker_intent),
    market_movement: normalizeMarketMovement(record.market_movement),
    market_divergence: normalizeMarketDivergence(record.market_divergence),
    bookmaker_hypothesis: normalizeBookmakerHypothesis(
      record.bookmaker_hypothesis,
    ),
    pricing_shadow: normalizePricingShadow(record.pricing_shadow),
    missing_inputs: asArray(record.missing_inputs)
      .map((item) => textValue(item))
      .filter(Boolean),
  };
}

function normalizeRelease(
  meta: ReleaseMeta,
  version: ApiVersion,
  dashboard: Record<string, unknown>,
  demo: boolean,
): ReleaseSyncState {
  const apiSha = textValue(
    asRecord(dashboard.version).api_git_sha,
    version.api_git_sha,
  );
  const webSha = meta.web_git_sha;
  return {
    web_git_sha: webSha,
    api_git_sha: apiSha,
    release_id: textValue(
      asRecord(dashboard.version).release_id,
      version.release_id ?? undefined,
    ),
    data_profile: textValue(dashboard.data_profile, version.data_profile),
    data_source: textValue(dashboard.data_source, version.data_source),
    updated_at: textValue(dashboard.generated_at, new Date().toISOString()),
    demo,
    mismatch:
      shortSha(webSha) !== "UNKNOWN" &&
      shortSha(apiSha) !== "UNKNOWN" &&
      shortSha(webSha) !== shortSha(apiSha),
  };
}

function demoDashboard(date: string, meta: ReleaseMeta): DashboardView {
  const card: DashboardMatchCard = {
    fixture_id: "demo-tur-usa",
    kickoff_utc: `${date}T02:00:00Z`,
    competition_name: "世界杯",
    home_team_name: "Türkiye",
    away_team_name: "USA",
    status: "UPCOMING",
    watch_level: 4,
    data_readiness: {
      bookmakers: 12,
      odds_snapshots: 12,
      xg: false,
      h2h: false,
      lineups: false,
    },
    analysis_readiness: {
      status: "PARTIAL",
      blockers: ["MISSING_XG"],
      available_inputs: {
        market_observations: 12,
        bookmakers: 12,
        odds_snapshots: 12,
        xg: false,
      },
      next_action: "WAIT_XG",
    },
    recommendation: {
      tier: "ANALYSIS_PICK",
      market: "TOTALS",
      market_label_cn: "大小球",
      selection: "OVER",
      selection_label_cn: "大 3.5",
      line: "3.5",
      odds: "1.03",
      confidence: 0.78,
      reasons: ["DEMO DATA：盘口初盘到临场有变化，综合倾向大球。"],
      risks: ["天气、红牌、阵容临场变化可能改变判断。"],
    },
    scoreline_picks: [],
    result: null,
    validation: null,
    current_odds: {
      ah: { line: "-1.5", price: "7.5" },
      ou: { line: "3.5", price: "1.03" },
    },
    odds_movement: { ah_open: "-1.75", ah_current: "-1.5" },
    market_strip: [
      {
        market: "TOTALS",
        decision: "PICK",
        label_cn: "大小球",
        lean_cn: "大 3.5",
        signal_strength: 0.78,
      },
      {
        market: "ASIAN_HANDICAP",
        decision: "SKIP",
        label_cn: "让球",
        lean_cn: "数据不足",
      },
    ],
    bookmaker_intent: {
      intent: "CONFLICTED",
      label_cn: "分歧较大",
      opening_line: "-1.75",
      current_line: "-1.5",
      signal_strength: 0.4,
    },
    missing_inputs: ["xG", "交锋", "首发"],
  };
  return {
    date,
    generated_at: new Date().toISOString(),
    data_profile: "demo",
    data_source: "explicit-demo",
    release: {
      web_git_sha: meta.web_git_sha,
      api_git_sha: "DEMO",
      release_id: meta.release_id,
      data_profile: "demo",
      data_source: "explicit-demo",
      updated_at: new Date().toISOString(),
      demo: true,
      mismatch: false,
    },
    debug: {
      read_model_fixture_count: 0,
      matchday_card_count: 0,
      future_fixture_count: 0,
      result_event_count: 0,
      selected_date: date,
      selected_date_has_data: true,
      next_available_date: date,
      empty_reason: null,
      suggested_actions: [],
    },
    performance: normalizePerformance({
      today_count: 1,
      next36_count: 1,
      candidate_count: 0,
      analysis_pick_count: 1,
      finished_count: 0,
      data_health_status: "DEMO",
    }),
    formal_tracking: null,
    recommendations: [card],
    upcoming: [card],
    finished: [],
    all: [card],
    errors: [],
  };
}

function cacheKey(date: string, mode: DashboardMode): string {
  return `${DASHBOARD_CACHE_VERSION}:${date}:${mode}`;
}

export function getCachedDashboardView(
  date: string,
  mode: DashboardMode,
): DashboardView | null {
  try {
    const raw = window.localStorage.getItem(cacheKey(date, mode));
    if (!raw) return null;
    const entry = JSON.parse(raw) as Partial<DashboardCacheEntry>;
    if (
      entry.version !== DASHBOARD_CACHE_VERSION ||
      !entry.stored_at ||
      !entry.view
    )
      return null;
    if (Date.now() - Date.parse(entry.stored_at) > DASHBOARD_CACHE_TTL_MS)
      return null;
    if (!entry.view.day_view) return null;
    return entry.view;
  } catch {
    return null;
  }
}

export function clearCachedDashboardView(
  date: string,
  mode: DashboardMode,
): void {
  try {
    window.localStorage.removeItem(cacheKey(date, mode));
    for (let index = window.localStorage.length - 1; index >= 0; index -= 1) {
      const key = window.localStorage.key(index);
      if (key?.startsWith("dashboard-v")) {
        window.localStorage.removeItem(key);
      }
    }
  } catch {
    // Cache is best-effort; clearing it must not block a manual refresh.
  }
}

function storeCachedDashboardView(
  date: string,
  mode: DashboardMode,
  view: DashboardView,
): void {
  try {
    const entry: DashboardCacheEntry = {
      version: DASHBOARD_CACHE_VERSION,
      stored_at: new Date().toISOString(),
      view,
    };
    window.localStorage.setItem(cacheKey(date, mode), JSON.stringify(entry));
  } catch {
    // Cache is best-effort; private browsing or quota limits should not break the dashboard.
  }
}

async function fetchDashboardPayload(
  date: string,
  mode: DashboardMode,
  includeDebug: boolean,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<unknown> {
  const params = new URLSearchParams({
    date,
    window: mode,
    timezone: "Asia/Shanghai",
    include_debug: includeDebug ? "true" : "false",
  });
  return getJSON(`${API_BASE}/dashboard?${params.toString()}`, timeoutMs);
}

async function fetchDashboardDayViewPayload(
  date: string,
  mode: DashboardMode,
): Promise<unknown> {
  const params = new URLSearchParams({
    date,
    window: mode,
    timezone: "Asia/Shanghai",
  });
  return getJSON(`${API_BASE}/dashboard/day-view?${params.toString()}`);
}

async function fetchDashboardDayViewPayloadRequired(
  date: string,
  mode: DashboardMode,
): Promise<unknown> {
  try {
    return await fetchDashboardDayViewPayload(date, mode);
  } catch {
    return fetchDashboardDayViewPayload(date, mode);
  }
}

function normalizeCounts(payload: unknown): DashboardDayViewCounts {
  const record = asRecord(payload);
  const byDecision = asRecord(record.by_decision_tier);
  const byData = asRecord(record.by_data_status);
  const byLifecycle = asRecord(record.by_lifecycle_status);
  return {
    total: numberValue(record.total),
    lock_eligible: numberValue(record.lock_eligible),
    outcome_tracked: numberValue(record.outcome_tracked),
    legacy_fallback: numberValue(record.legacy_fallback),
    analysis_pick: numberValue(record.analysis_pick),
    recommend: numberValue(record.recommend),
    watch: numberValue(record.watch),
    not_ready: numberValue(record.not_ready),
    skip: numberValue(record.skip),
    ready: numberValue(record.ready),
    partial: numberValue(record.partial),
    stale: numberValue(record.stale),
    blocked: numberValue(record.blocked),
    by_decision_tier: Object.fromEntries(
      Object.entries(byDecision).map(([key, value]) => [
        key,
        numberValue(value),
      ]),
    ),
    by_data_status: Object.fromEntries(
      Object.entries(byData).map(([key, value]) => [key, numberValue(value)]),
    ),
    by_lifecycle_status: Object.fromEntries(
      Object.entries(byLifecycle).map(([key, value]) => [
        key,
        numberValue(value),
      ]),
    ),
  };
}

function normalizeDayViewCard(payload: unknown): DashboardDayViewCard {
  const record = asRecord(payload);
  const nonPick = asRecord(record.non_pick);
  const pick = asRecord(record.pick);
  const decisionTier = textValue(
    record.decision_tier,
    "SKIP",
  ) as DashboardDayViewCard["decision_tier"];
  const dataStatus = textValue(
    record.data_status,
    "PARTIAL",
  ) as DashboardDayViewCard["data_status"];
  const actionable =
    dataStatus === "READY" &&
    ["RECOMMEND", "ANALYSIS_PICK"].includes(decisionTier);
  return {
    fixture_id: textValue(record.fixture_id, "unknown-fixture"),
    kickoff_utc: textValue(record.kickoff_utc) || null,
    kickoff_beijing: textValue(record.kickoff_beijing) || null,
    competition_id: textValue(record.competition_id) || null,
    competition_name: textValue(record.competition_name) || null,
    home_team_name: textValue(record.home_team_name) || null,
    away_team_name: textValue(record.away_team_name) || null,
    status: textValue(record.status) || null,
    source: textValue(record.source) || null,
    decision_tier: decisionTier,
    data_status: dataStatus,
    lifecycle_status: textValue(
      record.lifecycle_status,
      "DRAFT",
    ) as DashboardDayViewCard["lifecycle_status"],
    outcome_tracked: actionable && Boolean(record.outcome_tracked),
    lock_eligible: actionable && Boolean(record.lock_eligible),
    recommendation_id: actionable
      ? textValue(record.recommendation_id) || null
      : null,
    reason_code:
      textValue(record.reason_code) || textValue(nonPick.reason_code) || null,
    action: textValue(record.action) || textValue(nonPick.action) || null,
    next_eval_at:
      textValue(record.next_eval_at) || textValue(nonPick.next_eval_at) || null,
    provider_budget_status: textValue(record.provider_budget_status) || null,
    missing_fields: asArray(record.missing_fields)
      .map((item) => textValue(item))
      .filter(Boolean),
    stale_fields: asArray(record.stale_fields)
      .map((item) => textValue(item))
      .filter(Boolean),
    data_readiness: asRecord(record.data_readiness),
    data_refresh: normalizeDataRefresh(record.data_refresh),
    analysis_readiness: asRecord(record.analysis_readiness),
    current_odds: dataStatus === "READY" ? asRecord(record.current_odds) : {},
    last_known_odds: asRecord(record.last_known_odds),
    market_probabilities: asRecord(record.market_probabilities),
    odds_movement: asRecord(record.odds_movement),
    probability_source: textValue(record.probability_source) || null,
    model_market_divergence: asRecord(record.model_market_divergence),
    market_strip: asArray(record.market_strip).map((item) => asRecord(item)),
    missing_inputs: asArray(record.missing_inputs)
      .map((item) => textValue(item))
      .filter(Boolean),
    scoreline_picks: asArray(record.scoreline_picks)
      .map(normalizeScorelinePick)
      .filter((row) => row.scoreline),
    scoreline_reference: normalizeScorelineReference(
      record.scoreline_reference,
    ),
    scoreline_readiness: normalizeScorelineReadiness(
      record.scoreline_readiness,
    ),
    scoreline_simulations: numberValue(record.scoreline_simulations) || null,
    pick:
      actionable && Object.keys(pick).length
        ? {
            market: textValue(pick.market) || null,
            selection: textValue(pick.selection) || null,
            line: textValue(pick.line) || null,
            odds: textValue(pick.odds) || null,
            disclaimer: textValue(pick.disclaimer) || null,
          }
        : null,
    secondary_picks: actionable
      ? asArray(record.secondary_picks)
          .slice(0, 1)
          .map((item) => {
            const secondary = asRecord(item);
            return {
              market: textValue(secondary.market) || null,
              tendency: textValue(secondary.tendency) || null,
              lean: textValue(secondary.lean) || null,
              line: textValue(secondary.line) || null,
              odds: textValue(secondary.odds) || null,
              decision_score: numberValue(secondary.decision_score),
            };
          })
      : [],
    market_selection_audit: asArray(record.market_selection_audit).map((item) =>
      asRecord(item),
    ),
    lineup_provenance: asRecord(record.lineup_provenance),
    non_pick: Object.keys(nonPick).length ? nonPick : null,
    one_liner: textValue(record.one_liner) || null,
    card_hash: textValue(record.card_hash) || null,
    diagnostics: asRecord(record.diagnostics),
  };
}

function normalizeDashboardDayView(payload: unknown): DashboardDayView {
  const record = asRecord(payload);
  const freshness = asRecord(record.freshness);
  const staleness = asRecord(freshness.staleness);
  return {
    request_id: textValue(record.request_id) || undefined,
    generated_at: textValue(record.generated_at, new Date().toISOString()),
    date: textValue(record.date),
    football_day: textValue(
      record.football_day,
      textValue(record.selected_football_day),
    ),
    selected_football_day: textValue(
      record.selected_football_day,
      textValue(record.football_day),
    ),
    environment: textValue(record.environment, "unknown"),
    environment_policy: asRecord(record.environment_policy),
    timezone: textValue(record.timezone, "Asia/Shanghai"),
    window: textValue(record.window, "today"),
    source: textValue(record.source, "dashboard_read_model"),
    checkpoint_key: textValue(record.checkpoint_key) || undefined,
    would_write_checkpoint: Boolean(record.would_write_checkpoint),
    provider_calls: numberValue(record.provider_calls),
    db_writes: numberValue(record.db_writes),
    counts: normalizeCounts(record.counts),
    freshness: {
      page_updated_at: textValue(freshness.page_updated_at) || null,
      odds_last_confirmed_at:
        textValue(freshness.odds_last_confirmed_at) || null,
      last_refresh: textValue(freshness.last_refresh) || null,
      next_refresh_tick: textValue(freshness.next_refresh_tick) || null,
      provider_budget_status:
        textValue(freshness.provider_budget_status) || null,
      refreshing: Boolean(freshness.refreshing),
      staleness: {
        stale_cards: numberValue(staleness.stale_cards),
        blocked_cards: numberValue(staleness.blocked_cards),
        stale_or_blocked_cards: numberValue(staleness.stale_or_blocked_cards),
      },
      data_status_summary: Object.fromEntries(
        Object.entries(asRecord(freshness.data_status_summary)).map(
          ([key, value]) => [key, numberValue(value)],
        ),
      ),
    },
    navigation: asRecord(record.navigation),
    degradation: asRecord(record.degradation),
    cards: asArray(record.cards).map(normalizeDayViewCard),
  };
}

export async function fetchDashboardView({
  date,
  mode,
  includeDebug = false,
}: FetchDashboardArgs): Promise<DashboardView> {
  const metaPromise = getJSON("/meta.json");
  if (explicitDemoMode()) {
    const meta = normalizeMeta(await metaPromise);
    return demoDashboard(date, meta);
  }
  const [metaPayload, versionPayload, formalTrackingPayload, dayViewPayload] =
    await Promise.all([
      metaPromise,
      getJSON(`${API_BASE}/version`),
      getJSON(`${API_BASE}/formal/tracking/summary`).catch(() => null),
      fetchDashboardDayViewPayloadRequired(date, mode),
    ]);
  const dayView = dayViewPayload
    ? normalizeDashboardDayView(dayViewPayload)
    : null;
  let dashboardPayload: unknown | null = null;
  let dashboardError: unknown = null;
  if (!dayView) {
    dashboardPayload = await fetchDashboardPayload(
      date,
      mode,
      includeDebug,
      REQUEST_TIMEOUT_MS,
    );
  }
  let dashboard = asRecord(dashboardPayload);
  if (!includeDebug && !dayView && asArray(dashboard.all).length === 0) {
    try {
      dashboardPayload = await fetchDashboardPayload(
        date,
        mode,
        true,
        REQUEST_TIMEOUT_MS,
      );
      dashboard = asRecord(dashboardPayload);
    } catch (error) {
      dashboardError = dashboardError ?? error;
      throw error;
    }
  }
  const meta = normalizeMeta(metaPayload);
  const version = normalizeVersion(versionPayload);
  const release = normalizeRelease(meta, version, dashboard, false);
  const dayViewRecord = asRecord(dayViewPayload);
  const all = asArray(dashboard.all).map(normalizeCard);
  const view = {
    date: textValue(dashboard.date, dayView?.date || date),
    selected_date:
      textValue(dashboard.selected_date) ||
      textValue(dashboard.date) ||
      dayView?.selected_football_day ||
      date,
    selected_football_day:
      textValue(dashboard.selected_football_day) ||
      textValue(dashboard.selected_date) ||
      textValue(dashboard.date) ||
      dayView?.selected_football_day ||
      date,
    selected_date_has_data: dashboardPayload
      ? Boolean(dashboard.selected_date_has_data)
      : Boolean(dayView?.cards.length),
    next_available_date:
      textValue(dashboard.next_available_date) ||
      normalizeDebug(dashboard.debug).next_available_date ||
      dayView?.selected_football_day ||
      null,
    football_day_timezone:
      textValue(dashboard.football_day_timezone) || "Asia/Shanghai",
    football_day_cutoff_hour:
      numberValue(dashboard.football_day_cutoff_hour) ?? 12,
    football_day_start_utc:
      textValue(dashboard.football_day_start_utc) || undefined,
    football_day_end_utc:
      textValue(dashboard.football_day_end_utc) || undefined,
    generated_at: textValue(dashboard.generated_at, new Date().toISOString()),
    data_profile: release.data_profile,
    data_source: release.data_source,
    release,
    debug: normalizeDebug(dashboard.debug),
    performance: normalizePerformance(
      dayView ? dayViewRecord.performance : dashboard.performance,
    ),
    formal_tracking: normalizeFormalTracking(formalTrackingPayload),
    day_view: dayView,
    recommendations: asArray(dashboard.recommendations).map(normalizeCard),
    upcoming: asArray(dashboard.upcoming).map(normalizeCard),
    finished: asArray(dashboard.finished).map(normalizeCard),
    all,
    errors: dashboardError
      ? ["legacy dashboard payload timed out; Boss View rendered from DayView"]
      : [],
  };
  storeCachedDashboardView(date, mode, view);
  return view;
}
