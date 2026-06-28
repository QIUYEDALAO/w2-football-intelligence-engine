import { API_BASE } from "./labels";
import { asArray, asRecord, numberValue, textValue } from "./normalize";
import type {
  ApiVersion,
  DataRefreshStatus,
  DashboardDebug,
  DashboardMatchCard,
  DashboardMode,
  DashboardPerformance,
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
const DASHBOARD_CACHE_VERSION = "dashboard-v2";

interface FetchDashboardArgs {
  date: string;
  mode: DashboardMode;
  includeDebug?: boolean;
}

async function getJSON(url: string, timeoutMs = REQUEST_TIMEOUT_MS): Promise<unknown> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const response = await fetch(url, { headers: { Accept: "application/json" }, signal: controller.signal }).finally(() => {
    window.clearTimeout(timeout);
  });
  if (!response.ok) {
    throw new Error(`${url} -> HTTP ${response.status}`);
  }
  return response.json() as Promise<unknown>;
}

function explicitDemoMode(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.get("demo") === "1" || import.meta.env.VITE_DASHBOARD_DATA_MODE === "demo";
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
    generated_at: textValue(record.generated_at),
  };
}

function normalizeDebug(payload: unknown): DashboardDebug {
  const record = asRecord(payload);
  return {
    read_model_fixture_count: numberValue(record.read_model_fixture_count),
    matchday_card_count: numberValue(record.matchday_card_count),
    future_fixture_count: numberValue(record.future_fixture_count),
    future_fixture_in_window_count: numberValue(record.future_fixture_in_window_count),
    future_fixture_parse_error_count: numberValue(record.future_fixture_parse_error_count),
    future_fixture_status_distribution: asRecord(record.future_fixture_status_distribution) as Record<string, number>,
    future_fixture_date_distribution: asRecord(record.future_fixture_date_distribution) as Record<string, number>,
    future_fixture_min_kickoff_utc: textValue(record.future_fixture_min_kickoff_utc) || null,
    future_fixture_max_kickoff_utc: textValue(record.future_fixture_max_kickoff_utc) || null,
    result_event_count: numberValue(record.result_event_count),
    selected_date: textValue(record.selected_date),
    selected_date_has_data: Boolean(record.selected_date_has_data),
    next_available_date: textValue(record.next_available_date) || null,
    empty_reason: textValue(record.empty_reason) || null,
    empty_detail: textValue(record.empty_detail) || null,
    suggested_actions: asArray(record.suggested_actions).map((item) => textValue(item)).filter(Boolean),
  };
}

function normalizePerformance(payload: unknown): DashboardPerformance {
  const record = asRecord(payload);
  const scoreExact = asRecord(record.score_exact);
  const official = asRecord(record.official);
  const analysisShadow = asRecord(record.analysis_shadow);
  const bucket = (row: Record<string, unknown>) => ({
    sample_size: numberValue(row.sample_size),
    hit_count: numberValue(row.hit_count),
    miss_count: numberValue(row.miss_count),
    push_count: numberValue(row.push_count),
    void_count: numberValue(row.void_count),
    hit_rate: typeof row.hit_rate === "number" ? row.hit_rate : null,
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
    analysis_readiness_rate: typeof record.analysis_readiness_rate === "number" ? record.analysis_readiness_rate : null,
    analysis_blocker_distribution: asRecord(record.analysis_blocker_distribution) as Record<string, number>,
    finished_count: numberValue(record.finished_count),
    average_confidence: typeof record.average_confidence === "number" ? record.average_confidence : undefined,
    data_health_status: textValue(record.data_health_status, "READ_ONLY"),
    sample_size: numberValue(record.sample_size),
    hit_count: numberValue(record.hit_count),
    miss_count: numberValue(record.miss_count),
    push_count: numberValue(record.push_count),
    void_count: numberValue(record.void_count),
    hit_rate: typeof record.hit_rate === "number" ? record.hit_rate : null,
    market_hit_rate: typeof record.market_hit_rate === "number" ? record.market_hit_rate : null,
    score_hit_rate: typeof record.score_hit_rate === "number" ? record.score_hit_rate : null,
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
      hit_rate: typeof scoreExact.hit_rate === "number" ? scoreExact.hit_rate : null,
    },
  };
}

function normalizeAnalysisReadiness(payload: unknown) {
  const record = asRecord(payload);
  const available = asRecord(record.available_inputs);
  return {
    status: textValue(record.status, "UNKNOWN") as "READY" | "PARTIAL" | "BLOCKED" | "UNKNOWN",
    blockers: asArray(record.blockers).map((item) => textValue(item)).filter(Boolean),
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
  return typeof payload === "number" && Number.isFinite(payload) ? payload : null;
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

function normalizeFactorSourceSummary(payload: unknown): PricingShadow["factor_source_summary"] {
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
    independent_signal_groups: asArray(record.independent_signal_groups).map((item) => textValue(item)).filter(Boolean),
    xg_derived_factor_count: numberValue(record.xg_derived_factor_count),
    missing_independent_sources: asArray(record.missing_independent_sources).map((item) => textValue(item)).filter(Boolean),
    factor_source_summary: normalizeFactorSourceSummary(record.factor_source_summary),
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
    checkpoints_seen: asArray(record.checkpoints_seen).map((item) => textValue(item)).filter(Boolean),
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
    alternative_explanations: asArray(record.alternative_explanations).map((item) => textValue(item)).filter(Boolean),
    sample_status: textValue(record.sample_status, "观察中"),
    sample_count: numberValue(record.sample_count) ?? 0,
    verified: record.verified === true,
    direction_allowed: record.direction_allowed === true,
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
    recommendation: record.recommendation ? (asRecord(record.recommendation) as unknown as RecommendationPick) : null,
    scoreline_picks: asArray(record.scoreline_picks).map((item) => asRecord(item)).map((row) => ({
      scoreline: textValue(row.scoreline),
      probability: typeof row.probability === "number" ? row.probability : undefined,
      probability_label: textValue(row.probability_label),
    })).filter((row) => row.scoreline),
    scoreline_readiness: normalizeScorelineReadiness(record.scoreline_readiness),
    result: record.result ? (asRecord(record.result) as unknown as MatchResult) : null,
    validation: record.validation ? (asRecord(record.validation) as unknown as ValidationSummary) : null,
    current_odds: asRecord(record.current_odds),
    odds_movement: asRecord(record.odds_movement),
    market_strip: asArray(record.market_strip).map((item) => asRecord(item)),
    bookmaker_intent: asRecord(record.bookmaker_intent),
    market_movement: normalizeMarketMovement(record.market_movement),
    market_divergence: normalizeMarketDivergence(record.market_divergence),
    bookmaker_hypothesis: normalizeBookmakerHypothesis(record.bookmaker_hypothesis),
    pricing_shadow: normalizePricingShadow(record.pricing_shadow),
    missing_inputs: asArray(record.missing_inputs).map((item) => textValue(item)).filter(Boolean),
  };
}

function normalizeRelease(meta: ReleaseMeta, version: ApiVersion, dashboard: Record<string, unknown>, demo: boolean): ReleaseSyncState {
  const apiSha = textValue(asRecord(dashboard.version).api_git_sha, version.api_git_sha);
  const webSha = meta.web_git_sha;
  return {
    web_git_sha: webSha,
    api_git_sha: apiSha,
    release_id: textValue(asRecord(dashboard.version).release_id, version.release_id ?? undefined),
    data_profile: textValue(dashboard.data_profile, version.data_profile),
    data_source: textValue(dashboard.data_source, version.data_source),
    updated_at: textValue(dashboard.generated_at, new Date().toISOString()),
    demo,
    mismatch: shortSha(webSha) !== "UNKNOWN" && shortSha(apiSha) !== "UNKNOWN" && shortSha(webSha) !== shortSha(apiSha),
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
    data_readiness: { bookmakers: 12, odds_snapshots: 12, xg: false, h2h: false, lineups: false },
    analysis_readiness: {
      status: "PARTIAL",
      blockers: ["MISSING_XG"],
      available_inputs: { market_observations: 12, bookmakers: 12, odds_snapshots: 12, xg: false },
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
    current_odds: { ah: { line: "-1.5", price: "7.5" }, ou: { line: "3.5", price: "1.03" } },
    odds_movement: { ah_open: "-1.75", ah_current: "-1.5" },
    market_strip: [
      { market: "TOTALS", decision: "PICK", label_cn: "大小球", lean_cn: "大 3.5", confidence: 0.78 },
      { market: "ASIAN_HANDICAP", decision: "SKIP", label_cn: "让球", lean_cn: "数据不足" },
    ],
    bookmaker_intent: { intent: "CONFLICTED", label_cn: "分歧较大", opening_line: "-1.75", current_line: "-1.5" },
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
    performance: normalizePerformance({ today_count: 1, next36_count: 1, candidate_count: 0, analysis_pick_count: 1, finished_count: 0, data_health_status: "DEMO" }),
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

export function getCachedDashboardView(date: string, mode: DashboardMode): DashboardView | null {
  try {
    const raw = window.localStorage.getItem(cacheKey(date, mode));
    if (!raw) return null;
    return JSON.parse(raw) as DashboardView;
  } catch {
    return null;
  }
}

function storeCachedDashboardView(date: string, mode: DashboardMode, view: DashboardView): void {
  try {
    window.localStorage.setItem(cacheKey(date, mode), JSON.stringify(view));
  } catch {
    // Cache is best-effort; private browsing or quota limits should not break the dashboard.
  }
}

async function fetchDashboardPayload(date: string, mode: DashboardMode, includeDebug: boolean): Promise<unknown> {
  const params = new URLSearchParams({
    date,
    window: mode,
    timezone: "Asia/Shanghai",
    include_debug: includeDebug ? "true" : "false",
  });
  return getJSON(`${API_BASE}/dashboard?${params.toString()}`);
}

export async function fetchDashboardView({ date, mode, includeDebug = false }: FetchDashboardArgs): Promise<DashboardView> {
  const metaPromise = getJSON("/meta.json");
  if (explicitDemoMode()) {
    const meta = normalizeMeta(await metaPromise);
    return demoDashboard(date, meta);
  }
  let [metaPayload, versionPayload, dashboardPayload] = await Promise.all([
    metaPromise,
    getJSON(`${API_BASE}/version`),
    fetchDashboardPayload(date, mode, includeDebug),
  ]);
  let dashboard = asRecord(dashboardPayload);
  if (!includeDebug && asArray(dashboard.all).length === 0) {
    dashboardPayload = await fetchDashboardPayload(date, mode, true);
    dashboard = asRecord(dashboardPayload);
  }
  const meta = normalizeMeta(metaPayload);
  const version = normalizeVersion(versionPayload);
  const release = normalizeRelease(meta, version, dashboard, false);
  const all = asArray(dashboard.all).map(normalizeCard);
  const view = {
    date: textValue(dashboard.date, date),
    generated_at: textValue(dashboard.generated_at, new Date().toISOString()),
    data_profile: release.data_profile,
    data_source: release.data_source,
    release,
    debug: normalizeDebug(dashboard.debug),
    performance: normalizePerformance(dashboard.performance),
    recommendations: asArray(dashboard.recommendations).map(normalizeCard),
    upcoming: asArray(dashboard.upcoming).map(normalizeCard),
    finished: asArray(dashboard.finished).map(normalizeCard),
    all,
    errors: [],
  };
  storeCachedDashboardView(date, mode, view);
  return view;
}
