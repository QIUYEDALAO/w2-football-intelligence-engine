import { todayShanghai, translateCompetition } from "./formatters";
import { API_BASE, COMPETITION_ID } from "./labels";
import {
  asArray,
  asRecord,
  booleanValue,
  cardPayload,
  fixtureCompetition,
  fixtureId,
  fixtureKickoff,
  fixtureTeamName,
  isMarketPick,
  leanLabel,
  marketLabel,
  marketList,
  numberValue,
  preferredMarket,
  readinessItems,
  readableReasons,
  scoreRows,
  textValue,
} from "./normalize";
import type {
  DashboardMatchCard,
  DashboardMode,
  DashboardPerformance,
  DashboardView,
  MatchResult,
  MatchStatus,
  MarketAnalysis,
  RecommendationPick,
  RecommendationTier,
  ScorelinePick,
  SettlementStatus,
  ValidationSummary,
} from "../types/dashboard";

const REQUEST_TIMEOUT_MS = 20000;
const FIXTURE_LIMIT = 50;
const POOL_LIMIT = 6;

interface FetchDashboardArgs {
  date: string;
  mode: DashboardMode;
}

interface EndpointResult<T> {
  value?: T;
  error?: string;
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

async function safeJSON<T>(url: string, label: string, timeoutMs = REQUEST_TIMEOUT_MS): Promise<EndpointResult<T>> {
  try {
    return { value: (await getJSON(url, timeoutMs)) as T };
  } catch (error) {
    return { error: `${label}: ${error instanceof Error ? error.message : "unknown error"}` };
  }
}

async function promisePool<T, R>(items: T[], worker: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = [];
  let cursor = 0;
  async function run() {
    for (;;) {
      const index = cursor;
      cursor += 1;
      if (index >= items.length) return;
      results[index] = await worker(items[index]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(POOL_LIMIT, items.length) }, run));
  return results;
}

export function fetchMatchday(date: string): Promise<EndpointResult<unknown>> {
  return safeJSON(`${API_BASE}/matchday?date=${encodeURIComponent(date)}&competition_id=${COMPETITION_ID}`, "matchday");
}

export function fetchNext36Hours(): Promise<EndpointResult<unknown>> {
  return safeJSON(`${API_BASE}/matchday/next-36-hours`, "next36");
}

export function fetchBacktestLatest(): Promise<EndpointResult<unknown>> {
  return safeJSON(`${API_BASE}/backtests/latest`, "backtests");
}

export function fetchForwardHoldoutStatus(): Promise<EndpointResult<unknown>> {
  return safeJSON(`${API_BASE}/forward-holdout/status`, "forward-holdout");
}

export function fetchFixtureAnalysis(fixtureIdValue: string): Promise<EndpointResult<unknown>> {
  return safeJSON(`${API_BASE}/fixtures/${encodeURIComponent(fixtureIdValue)}/analysis-card`, `analysis-card:${fixtureIdValue}`, 60000);
}

export function fetchFixtureDetail(fixtureIdValue: string): Promise<EndpointResult<unknown>> {
  return safeJSON(`${API_BASE}/fixtures/${encodeURIComponent(fixtureIdValue)}?timezone=Asia/Shanghai`, `fixture:${fixtureIdValue}`);
}

export function fetchFixtureMarketRanking(fixtureIdValue: string): Promise<EndpointResult<unknown>> {
  return safeJSON(`${API_BASE}/fixtures/${encodeURIComponent(fixtureIdValue)}/market-ranking`, `market-ranking:${fixtureIdValue}`);
}

export function fetchFixtureModelProbabilities(fixtureIdValue: string): Promise<EndpointResult<unknown>> {
  return safeJSON(`${API_BASE}/fixtures/${encodeURIComponent(fixtureIdValue)}/model-probabilities`, `model-probabilities:${fixtureIdValue}`);
}

export function fetchFixtureOddsTimeline(fixtureIdValue: string): Promise<EndpointResult<unknown>> {
  return safeJSON(`${API_BASE}/fixtures/${encodeURIComponent(fixtureIdValue)}/odds-timeline`, `odds-timeline:${fixtureIdValue}`);
}

function payloadItems(payload: unknown): unknown[] {
  return asArray(asRecord(payload).items ?? payload);
}

function fixtureFromMatchday(row: unknown): unknown {
  const record = asRecord(row);
  const fixture = asRecord(record.fixture);
  return fixture.fixture_id ? fixture : row;
}

function fixtureKey(row: unknown): string {
  const record = asRecord(row);
  return textValue(record.fixture_id ?? asRecord(record.fixture).fixture_id ?? fixtureId(row));
}

function statusFromRaw(value: unknown): MatchStatus {
  const raw = textValue(value).toUpperCase();
  if (["NS", "TBD"].includes(raw)) return "UPCOMING";
  if (["1H", "2H", "HT", "ET", "BT", "P", "LIVE"].includes(raw)) return "LIVE";
  if (["FT", "AET", "PEN", "FINISHED"].includes(raw)) return "FINISHED";
  if (["CANC", "CANCELLED"].includes(raw)) return "CANCELLED";
  if (["PST", "POSTPONED"].includes(raw)) return "POSTPONED";
  return raw ? "UNKNOWN" : "UPCOMING";
}

function fixtureStatus(row: unknown, detail: unknown): MatchStatus {
  const source = asRecord(detail);
  const fixtureStatusPayload = asRecord(asRecord(source.fixture).status);
  const raw = source.status ?? fixtureStatusPayload.short ?? asRecord(row).status;
  return statusFromRaw(raw);
}

function resultFromPayload(detail: unknown, status: MatchStatus): MatchResult | null {
  const record = asRecord(detail);
  const goals = asRecord(record.goals);
  const fulltime = asRecord(asRecord(record.score).fulltime);
  const home = numberValue(record.home_goals ?? goals.home ?? fulltime.home, Number.NaN);
  const away = numberValue(record.away_goals ?? goals.away ?? fulltime.away, Number.NaN);
  if (!Number.isFinite(home) || !Number.isFinite(away)) {
    return status === "FINISHED" ? { status, result_source: "status_without_score" } : null;
  }
  return {
    status,
    home_goals: home,
    away_goals: away,
    final_score: `${home}-${away}`,
    total_goals: home + away,
    result_source: textValue(record.result_source, "read-model"),
    settled_at: textValue(record.settled_at),
  };
}

function recommendationTier(card: unknown, market: MarketAnalysis | null): RecommendationTier {
  const payload = asRecord(card);
  if (booleanValue(payload.formal_recommendation)) return "FORMAL";
  if (booleanValue(payload.candidate)) return "CANDIDATE";
  if (market && isMarketPick(market)) return "CANDIDATE";
  if (textValue(payload.decision) === "WATCH") return "WATCH";
  return "NO_RECOMMENDATION";
}

function probabilityLabel(value: unknown): string | undefined {
  const numeric = numberValue(value, Number.NaN);
  if (!Number.isFinite(numeric)) return undefined;
  const normalized = numeric > 1 ? numeric : numeric * 100;
  return `${Math.round(normalized)}%`;
}

function parseScoreline(scoreline: string): { home: number; away: number } | null {
  const match = scoreline.match(/^(\d+)\s*[-:]\s*(\d+)$/);
  if (!match) return null;
  return { home: Number(match[1]), away: Number(match[2]) };
}

function annotateScoreHit(pick: ScorelinePick, result: MatchResult | null): ScorelinePick {
  if (!result || result.home_goals === undefined || result.away_goals === undefined) return pick;
  const parsed = parseScoreline(pick.scoreline);
  if (!parsed) return pick;
  const pickDirection = Math.sign(parsed.home - parsed.away);
  const actualDirection = Math.sign(result.home_goals - result.away_goals);
  return {
    ...pick,
    hit: parsed.home === result.home_goals && parsed.away === result.away_goals,
    direction_hit: pickDirection === actualDirection,
  };
}

function scorelinePicks(card: unknown, modelProbabilities: unknown, result: MatchResult | null): ScorelinePick[] {
  const scoreMarket = marketList(cardPayload(card)).find((market) => market.market === "SCORE");
  const fromCard = scoreMarket ? scoreRows(scoreMarket).map((row) => ({ scoreline: row.scoreline, probability_label: row.probability })) : [];
  const probabilities = asRecord(modelProbabilities).probabilities;
  const probabilityRows = Array.isArray(probabilities) ? probabilities.map((row) => asRecord(row)) : [];
  const fromModel: ScorelinePick[] = probabilityRows
    .map((row): ScorelinePick | null => {
      const scoreline = textValue(row.scoreline ?? row.score);
      if (!scoreline) return null;
      return {
        scoreline,
        probability: numberValue(row.probability, Number.NaN),
        probability_label: probabilityLabel(row.probability),
      };
    })
    .filter((row): row is ScorelinePick => row !== null && Number.isFinite(row.probability ?? Number.NaN))
    .slice(0, 3);
  const source: ScorelinePick[] = fromCard.length ? fromCard : fromModel;
  return source.slice(0, 3).map((pick) => annotateScoreHit(pick, result));
}

function currentOddsRecord(card: unknown, detail: unknown): Record<string, unknown> {
  const payload = asRecord(cardPayload(card));
  const detailRecord = asRecord(detail);
  if (payload.current_odds) return asRecord(payload.current_odds);
  if (detailRecord.primary_line || detailRecord.primary_executable_odds) {
    return { ah: { line: detailRecord.primary_line, price: detailRecord.primary_executable_odds } };
  }
  return {};
}

function recommendationFromCard(card: unknown, detail: unknown): RecommendationPick | null {
  const payload = cardPayload(card);
  const market = preferredMarket(payload);
  const tier = recommendationTier(payload, market);
  if (tier === "NO_RECOMMENDATION") return null;
  const detailRecord = asRecord(detail);
  const reasons = readableReasons(market.reasons, market.reason ?? market.reason_cn);
  const riskRows = asArray(market.risks_cn).length ? asArray(market.risks_cn) : asArray(market.risks);
  return {
    tier,
    market: textValue(market.market, "UNKNOWN"),
    market_label_cn: marketLabel(market),
    selection: textValue(market.tendency ?? market.lean ?? market.lean_cn, "WATCH"),
    selection_label_cn: leanLabel(market),
    line: textValue(market.line ?? detailRecord.primary_line),
    odds: textValue(market.odds ?? detailRecord.primary_executable_odds),
    hong_kong_odds: textValue(detailRecord.primary_hong_kong_odds),
    model_probability: numberValue(market.model_probability ?? market.confidence, Number.NaN),
    fair_odds: textValue(market.fair_odds ?? detailRecord.primary_model_fair_odds),
    risk_adjusted_ev: textValue(market.risk_adjusted_ev ?? detailRecord.primary_risk_adjusted_ev),
    confidence: numberValue(market.confidence, 0),
    reasons: reasons.length ? reasons : ["多因素输入仍在补齐，保持候选/观察口径。"],
    risks: riskRows.map((row) => textValue(row)).filter(Boolean).slice(0, 2),
    generated_at: textValue(asRecord(payload.temporal).valuation_generated_at ?? payload.generated_at),
    locked_before_kickoff: booleanValue(asRecord(payload.temporal).locked_before_kickoff ?? detailRecord.temporal_status),
    is_live_line: false,
  };
}

function settleTotals(recommendation: RecommendationPick, result: MatchResult): SettlementStatus {
  const line = numberValue(recommendation.line, Number.NaN);
  if (!Number.isFinite(line) || result.total_goals === undefined) return "UNKNOWN";
  const selection = `${recommendation.selection} ${recommendation.selection_label_cn ?? ""}`.toUpperCase();
  if (result.total_goals === line) return "PUSH";
  if (selection.includes("UNDER") || selection.includes("小")) return result.total_goals < line ? "HIT" : "MISS";
  return result.total_goals > line ? "HIT" : "MISS";
}

function settleAsianHandicap(recommendation: RecommendationPick, result: MatchResult): SettlementStatus {
  const line = numberValue(recommendation.line, Number.NaN);
  if (!Number.isFinite(line) || result.home_goals === undefined || result.away_goals === undefined) return "UNKNOWN";
  const selection = `${recommendation.selection} ${recommendation.selection_label_cn ?? ""}`.toUpperCase();
  const isAway = selection.includes("AWAY") || selection.includes("客");
  const margin = isAway ? result.away_goals - result.home_goals : result.home_goals - result.away_goals;
  const adjusted = margin + line;
  if (adjusted > 0) return "HIT";
  if (adjusted < 0) return "MISS";
  return "PUSH";
}

function settleScore(scorePicks: ScorelinePick[]): Pick<ValidationSummary, "score_exact_hit" | "score_direction_hit"> {
  return {
    score_exact_hit: scorePicks.some((pick) => pick.hit),
    score_direction_hit: scorePicks.some((pick) => pick.direction_hit),
  };
}

function validationFor(recommendation: RecommendationPick | null, result: MatchResult | null, scorePicks: ScorelinePick[]): ValidationSummary | null {
  if (!recommendation) return result?.status === "FINISHED" ? { settlement: "NO_BET", validation_notes: ["无推荐，不计入命中率。"] } : null;
  if (!result || result.status !== "FINISHED") return { settlement: "PENDING", validation_notes: ["等待完场比分。"] };
  let settlement: SettlementStatus = "UNKNOWN";
  if (recommendation.market === "TOTALS") settlement = settleTotals(recommendation, result);
  if (recommendation.market === "ASIAN_HANDICAP") settlement = settleAsianHandicap(recommendation, result);
  const odds = numberValue(recommendation.odds, Number.NaN);
  const profit =
    Number.isFinite(odds) && settlement === "HIT" ? odds - 1 : settlement === "MISS" ? -1 : settlement === "PUSH" ? 0 : undefined;
  return {
    settlement,
    market_hit: settlement === "HIT",
    total_goals_hit: recommendation.market === "TOTALS" ? settlement === "HIT" : undefined,
    profit_units: profit,
    closing_line_value: textValue(recommendation.risk_adjusted_ev),
    validation_notes: [recommendation.locked_before_kickoff ? "LOCKED_BEFORE_KICKOFF" : "推荐锁状态待确认"],
    ...settleScore(scorePicks),
  };
}

function missingInputs(card: DashboardMatchCard): string[] {
  return readinessItems({ data_readiness: card.data_readiness })
    .filter((row) => !row.ready)
    .map((row) => `缺${row.label}`);
}

function normalizeFixtureCard(row: unknown, analysis: unknown, detail: unknown, modelProbabilities: unknown, ranking: unknown, oddsTimeline: unknown): DashboardMatchCard {
  const fixture = fixtureFromMatchday(row);
  const payload = cardPayload(analysis);
  const status = fixtureStatus(fixture, detail);
  const result = resultFromPayload(detail, status);
  const recommendation = recommendationFromCard(payload, detail);
  const scores = scorelinePicks(payload, modelProbabilities, result);
  const validation = validationFor(recommendation, result, scores);
  const fixtureRecord = asRecord(fixture);
  const id = fixtureKey(fixture) || textValue(payload.fixture_id, "unknown-fixture");
  const card: DashboardMatchCard = {
    fixture_id: id,
    kickoff_utc: textValue(payload.kickoff_utc ?? fixtureRecord.kickoff_utc ?? fixtureKickoff(fixture)),
    kickoff_beijing: textValue(fixtureRecord.kickoff_beijing),
    operational_date_beijing: textValue(fixtureRecord.operational_date_beijing),
    competition_id: textValue(fixtureRecord.competition_id),
    competition_name: translateCompetition(payload.competition_cn ?? payload.competition_name ?? fixtureCompetition(fixture)),
    home_team_name: textValue(payload.home_cn ?? payload.home_name ?? fixtureTeamName(fixture, "home"), "主队"),
    away_team_name: textValue(payload.away_cn ?? payload.away_name ?? fixtureTeamName(fixture, "away"), "客队"),
    status,
    raw_status: textValue(fixtureRecord.status),
    data_state: textValue(fixtureRecord.data_state),
    lifecycle_state: textValue(fixtureRecord.lifecycle_state),
    watch_level: numberValue(payload.watch_level ?? fixtureRecord.watch_level, 0),
    data_readiness: asRecord(payload.data_readiness),
    recommendation,
    scoreline_picks: scores,
    result,
    validation,
    current_odds: currentOddsRecord(payload, detail),
    odds_movement: asRecord(payload.line_movement ?? { items: payloadItems(oddsTimeline) }),
    market_strip: payloadItems(ranking).map((item) => asRecord(item)),
    bookmaker_intent: asRecord(payload.bookmaker_intent),
    missing_inputs: [],
  };
  return { ...card, missing_inputs: missingInputs(card) };
}

function dedupeFixtures(rows: unknown[]): unknown[] {
  const seen = new Set<string>();
  const deduped: unknown[] = [];
  rows.forEach((row) => {
    const key = fixtureKey(fixtureFromMatchday(row));
    if (!key || seen.has(key)) return;
    seen.add(key);
    deduped.push(row);
  });
  return deduped;
}

function recommendationRank(card: DashboardMatchCard): number {
  const tier = card.recommendation?.tier;
  if (tier === "FORMAL") return 0;
  if (tier === "CANDIDATE") return 1;
  if (tier === "WATCH") return 2;
  return 3;
}

function performance(all: DashboardMatchCard[], next36Count: number, backtests: unknown, holdout: unknown): DashboardPerformance {
  const recommended = all.filter((card) => card.recommendation?.tier === "FORMAL" || card.recommendation?.tier === "CANDIDATE");
  const settled = recommended.filter((card) => card.validation && ["HIT", "MISS", "PUSH", "VOID"].includes(card.validation.settlement));
  const hits = settled.filter((card) => card.validation?.settlement === "HIT").length;
  const misses = settled.filter((card) => card.validation?.settlement === "MISS").length;
  const pushes = settled.filter((card) => card.validation?.settlement === "PUSH").length;
  const voids = settled.filter((card) => card.validation?.settlement === "VOID").length;
  const confidenceRows = recommended.map((card) => card.recommendation?.confidence ?? 0).filter((value) => value > 0);
  const marketMap = new Map<string, { sample: number; hit: number }>();
  settled.forEach((card) => {
    const market = card.recommendation?.market_label_cn ?? card.recommendation?.market ?? "市场";
    const current = marketMap.get(market) ?? { sample: 0, hit: 0 };
    current.sample += 1;
    if (card.validation?.settlement === "HIT") current.hit += 1;
    marketMap.set(market, current);
  });
  const scoreSample = settled.filter((card) => card.scoreline_picks.length).length;
  const scoreHit = settled.filter((card) => card.validation?.score_exact_hit).length;
  return {
    today_count: all.filter((card) => card.operational_date_beijing === todayShanghai() || card.status !== "FINISHED").length || all.length,
    next36_count: next36Count,
    candidate_count: recommended.length,
    finished_count: all.filter((card) => card.status === "FINISHED").length,
    average_confidence: confidenceRows.length ? confidenceRows.reduce((sum, value) => sum + value, 0) / confidenceRows.length : undefined,
    data_health_status: textValue(asRecord(holdout).status ?? asRecord(backtests).status, "READ_ONLY"),
    sample_size: settled.length,
    hit_count: hits,
    miss_count: misses,
    push_count: pushes,
    void_count: voids,
    hit_rate: settled.length ? hits / settled.length : undefined,
    by_market: Array.from(marketMap.entries()).map(([market, value]) => ({
      market,
      sample_size: value.sample,
      hit_rate: value.sample ? value.hit / value.sample : undefined,
    })),
    score_exact: {
      sample_size: scoreSample,
      hit_count: scoreHit,
      hit_rate: scoreSample ? scoreHit / scoreSample : undefined,
    },
  };
}

export async function fetchDashboardView({ date, mode }: FetchDashboardArgs): Promise<DashboardView> {
  const [todayResult, next36Result, backtestResult, holdoutResult] = await Promise.all([
    fetchMatchday(date),
    fetchNext36Hours(),
    fetchBacktestLatest(),
    fetchForwardHoldoutStatus(),
  ]);
  const errors = [todayResult.error, next36Result.error, backtestResult.error, holdoutResult.error].filter((error): error is string => Boolean(error));
  const todayRows = payloadItems(todayResult.value);
  const nextRows = payloadItems(next36Result.value);
  const sourceRows = mode === "next36" ? nextRows : mode === "today" ? todayRows : [...todayRows, ...nextRows];
  const rows = dedupeFixtures(sourceRows).slice(0, FIXTURE_LIMIT);
  const enriched = await promisePool(rows, async (row) => {
    const id = fixtureKey(fixtureFromMatchday(row));
    if (!id) return normalizeFixtureCard(row, {}, {}, {}, {}, {});
    const [analysis, detail, ranking, model, timeline] = await Promise.all([
      fetchFixtureAnalysis(id),
      fetchFixtureDetail(id),
      fetchFixtureMarketRanking(id),
      fetchFixtureModelProbabilities(id),
      fetchFixtureOddsTimeline(id),
    ]);
    [analysis.error, detail.error, ranking.error, model.error, timeline.error].forEach((error) => {
      if (error) errors.push(error);
    });
    return normalizeFixtureCard(row, analysis.value ?? {}, detail.value ?? row, model.value ?? {}, ranking.value ?? {}, timeline.value ?? {});
  });
  const recommendations = enriched
    .filter((card) => card.recommendation?.tier === "FORMAL" || card.recommendation?.tier === "CANDIDATE")
    .sort((left, right) => recommendationRank(left) - recommendationRank(right));
  const upcoming = enriched.filter((card) => card.status === "UPCOMING" || card.status === "LIVE");
  const finished = enriched.filter((card) => card.status === "FINISHED");
  return {
    date,
    generated_at: new Date().toISOString(),
    performance: performance(enriched, nextRows.length, backtestResult.value, holdoutResult.value),
    recommendations,
    upcoming,
    finished,
    all: enriched,
    errors,
  };
}
