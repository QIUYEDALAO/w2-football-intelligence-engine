import { API_BASE } from "./labels";
import { asArray, asRecord, numberValue, textValue } from "./normalize";
import type {
  ApiVersion,
  DashboardDebug,
  DashboardMatchCard,
  DashboardMode,
  DashboardPerformance,
  DashboardView,
  MatchResult,
  MatchStatus,
  RecommendationPick,
  ReleaseMeta,
  ReleaseSyncState,
  ValidationSummary,
} from "../types/dashboard";

const REQUEST_TIMEOUT_MS = 20000;

interface FetchDashboardArgs {
  date: string;
  mode: DashboardMode;
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
    recommendation: record.recommendation ? (asRecord(record.recommendation) as unknown as RecommendationPick) : null,
    scoreline_picks: asArray(record.scoreline_picks).map((item) => asRecord(item)).map((row) => ({
      scoreline: textValue(row.scoreline),
      probability: typeof row.probability === "number" ? row.probability : undefined,
      probability_label: textValue(row.probability_label),
    })).filter((row) => row.scoreline),
    result: record.result ? (asRecord(record.result) as unknown as MatchResult) : null,
    validation: record.validation ? (asRecord(record.validation) as unknown as ValidationSummary) : null,
    current_odds: asRecord(record.current_odds),
    odds_movement: asRecord(record.odds_movement),
    market_strip: asArray(record.market_strip).map((item) => asRecord(item)),
    bookmaker_intent: asRecord(record.bookmaker_intent),
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

export async function fetchDashboardView({ date, mode }: FetchDashboardArgs): Promise<DashboardView> {
  const meta = normalizeMeta(await getJSON("/meta.json"));
  if (explicitDemoMode()) {
    return demoDashboard(date, meta);
  }
  const [versionPayload, dashboardPayload] = await Promise.all([
    getJSON(`${API_BASE}/version`),
    getJSON(`${API_BASE}/dashboard?date=${encodeURIComponent(date)}&window=${encodeURIComponent(mode)}&timezone=Asia%2FShanghai&include_debug=true`),
  ]);
  const version = normalizeVersion(versionPayload);
  const dashboard = asRecord(dashboardPayload);
  const release = normalizeRelease(meta, version, dashboard, false);
  const all = asArray(dashboard.all).map(normalizeCard);
  return {
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
}
