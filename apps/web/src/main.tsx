import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type LoadStatus = "LOADING" | "SUCCESS" | "EMPTY" | "ERROR" | "STALE";

type Resource<T> = {
  status: LoadStatus;
  endpoint: string;
  data: T | null;
  requestId: string | null;
  errorCode: string | null;
  message: string | null;
};

type Fixture = {
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

type FixtureDetail = Fixture & {
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
  ah_ladder?: unknown[];
  ou_ladder?: unknown[];
  all_market_ranking?: unknown[];
  one_x_two_ranking?: unknown[];
  btts_ranking?: unknown[];
  secondary_market_direction?: Record<string, unknown> | null;
  source_snapshot_id?: string | null;
  source_captured_at?: string | null;
  source_phase?: string | null;
  valuation_generated_at?: string | null;
  projector_generated_at?: string | null;
  temporal_status?: string | null;
  integrity_status?: string | null;
};

type FixtureList = {
  request_id: string;
  items: Fixture[];
  meta?: Record<string, unknown>;
};

type ScoreReference = {
  scoreline: string;
  conditional_probability: number | null;
};

type AnalysisMarketCard = {
  market: string;
  label_cn: string;
  decision: "PICK" | "SKIP" | string;
  analysis_decision?: string;
  lean_cn?: string | null;
  confidence: number;
  reason_cn?: string | null;
  reasons?: string[];
  risks_cn?: string[];
  reference_scores?: ScoreReference[];
  candidate: boolean;
  formal_recommendation: boolean;
};

type AnalysisCard = {
  fixture_id: string;
  kickoff_utc?: string | null;
  competition_cn?: string | null;
  home_cn?: string | null;
  away_cn?: string | null;
  decision: "ANALYSIS_PICK" | "SKIP" | "WATCH" | string;
  watch_level?: number;
  bookmaker_intent: {
    intent: string;
    label_cn?: string | null;
    opening_line?: string | null;
    current_line?: string | null;
    confidence?: number;
    reason?: string | null;
  };
  markets: AnalysisMarketCard[];
  risks_cn?: string[];
  disclaimer_cn?: string;
  disclaimer?: string;
  candidate: boolean;
  formal_recommendation: boolean;
  source?: string;
};

type AnalysisCardResponse = {
  request_id: string;
  fixture_id: string;
  card: AnalysisCard;
};

type AnalysisDashboardData = {
  fixtures: Fixture[];
  cards: AnalysisCard[];
};

type Matchday = {
  request_id: string;
  date: string;
  total: number;
  items: Array<Record<string, unknown>>;
};

type MatchdayCoverage = {
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

type MarketRanking = {
  request_id: string;
  fixture_id: string;
  items: Array<Record<string, unknown>>;
};

type Integrity = {
  request_id: string;
  fixture_id: string;
  integrity: Record<string, unknown>;
};

type ForwardStatus = {
  request_id: string;
  status: string;
  locks: number;
  market_comparable: number;
  current_settled_n: number;
  target_n: number;
};

type ProviderStatus = {
  request_id: string;
  provider: string;
  status: string;
  remaining_quota: number | null;
  credential_status: string;
  last_request_status: number | null;
};

type DataHealth = {
  request_id: string;
  stale_data_count: number;
  provider_status: string;
  forward_cycle_age_seconds: number | null;
  generated_at: string;
  gate4_progress: Record<string, unknown>;
};

type Probability = {
  request_id: string;
  probability_type: string;
  probabilities: Record<string, number>;
  source: string;
  quality: string;
  as_of_time: string | null;
};

type OpsList = {
  request_id: string;
  items: Array<{ key: string; status: string; payload: Record<string, unknown> }>;
};

type WorldCupReadiness = {
  request_id: string;
  competition_id: string;
  profile_version: string;
  fixture_coverage_count: number;
  data_coverage: Record<string, string>;
  phase_count_per_fixture: number;
  gate_status: string;
  strategy_version: string;
  production_deployment: string;
  shadow_runtime: string;
  blockers: string[];
};

type LeagueSummary = {
  competition_id: string;
  name: string;
  country: string;
  results_status: string;
  market_status: Record<string, string>;
  latest_season: string | null;
  blocker: string | null;
};

type LeagueList = {
  request_id: string;
  items: LeagueSummary[];
};

type OperationsLatest = {
  request_id: string;
  latest: {
    kind?: string;
    status?: string;
    checkpoint?: string;
    BLOCKER?: string[];
    WARN_ONLY?: string[];
  };
};

type ReleaseReadiness = {
  request_id: string;
  approval_status: string;
  production_release: string;
  dependency_blocker: string | null;
};

type RetentionStatus = {
  request_id: string;
  status: string;
  policy: Record<string, unknown>;
};

type ShadowStrategyStatus = {
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

const staleMs = 15 * 60 * 1000;

function emptyResource<T>(endpoint: string): Resource<T> {
  return {
    status: "LOADING",
    endpoint,
    data: null,
    requestId: null,
    errorCode: null,
    message: null,
  };
}

function isEmptyPayload(payload: unknown): boolean {
  if (payload === null || payload === undefined) {
    return true;
  }
  if (Array.isArray(payload)) {
    return payload.length === 0;
  }
  if (typeof payload === "object") {
    const maybeItems = (payload as { items?: unknown }).items;
    return Array.isArray(maybeItems) && maybeItems.length === 0;
  }
  return false;
}

function isStale(payload: unknown): boolean {
  const maybeTime =
    (payload as { generated_at?: string; as_of_time?: string; updated_at?: string })?.generated_at ??
    (payload as { generated_at?: string; as_of_time?: string; updated_at?: string })?.as_of_time ??
    (payload as { generated_at?: string; as_of_time?: string; updated_at?: string })?.updated_at;
  if (!maybeTime) {
    return false;
  }
  const timestamp = Date.parse(maybeTime);
  return Number.isFinite(timestamp) && Date.now() - timestamp > staleMs;
}

async function loadJson<T>(endpoint: string): Promise<Resource<T>> {
  const requestId = crypto.randomUUID();
  try {
    const response = await fetch(endpoint, {
      headers: { Accept: "application/json", "X-Request-ID": requestId },
    });
    const text = await response.text();
    const payload = text ? (JSON.parse(text) as T & { request_id?: string; code?: string; message?: string }) : null;
    if (!response.ok) {
      return {
        status: "ERROR",
        endpoint,
        data: null,
        requestId: payload?.request_id ?? requestId,
        errorCode: payload?.code ?? String(response.status),
        message: payload?.message ?? response.statusText,
      };
    }
    return {
      status: isEmptyPayload(payload) ? "EMPTY" : isStale(payload) ? "STALE" : "SUCCESS",
      endpoint,
      data: payload as T,
      requestId: payload?.request_id ?? requestId,
      errorCode: null,
      message: null,
    };
  } catch (error) {
    return {
      status: "ERROR",
      endpoint,
      data: null,
      requestId,
      errorCode: error instanceof SyntaxError ? "JSON_PARSE_ERROR" : "FETCH_FAILED",
      message: error instanceof Error ? error.message : "Request failed",
    };
  }
}

function StatePanel<T>({
  title,
  resource,
  onRetry,
  children,
}: {
  title: string;
  resource: Resource<T>;
  onRetry: () => void;
  children: (data: T) => React.ReactNode;
}) {
  return (
    <section className={`panel state-${resource.status.toLowerCase()}`}>
      <div className="panel-title">
        <h2>{title}</h2>
        <span>{resource.status}</span>
      </div>
      {resource.status === "LOADING" ? <p className="muted">Loading {resource.endpoint}</p> : null}
      {resource.status === "EMPTY" ? <p className="muted">No read-model records available for {resource.endpoint}.</p> : null}
      {resource.status === "ERROR" ? (
        <div className="error-box">
          <p>Endpoint: {resource.endpoint}</p>
          <p>request_id: {resource.requestId}</p>
          <p>error: {resource.errorCode}</p>
          <button type="button" onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : null}
      {resource.status === "STALE" ? <p className="warning">Data is stale; showing last read-model snapshot.</p> : null}
      {(resource.status === "SUCCESS" || resource.status === "STALE") && resource.data ? children(resource.data) : null}
    </section>
  );
}

function ProbabilityTable({ title, resource, onRetry }: { title: string; resource: Resource<Probability>; onRetry: () => void }) {
  return (
    <StatePanel title={title} resource={resource} onRetry={onRetry}>
      {(data) => {
        const rows = Object.entries(data.probabilities);
        return (
          <>
            {rows.length ? (
              <table>
                <tbody>
                  {rows.map(([label, value]) => (
                    <tr key={label}>
                      <th>{label}</th>
                      <td>{(value * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">Probability read model is empty.</p>
            )}
            <p className="source">{data.probability_type} · {data.source}</p>
          </>
        );
      }}
    </StatePanel>
  );
}

const worldCupCompetitionIds = new Set(["1", "world_cup_2026", "fifa_world_cup_2026"]);

function isWorldCupFixture(fixture: Fixture): boolean {
  const name = `${fixture.competition_name} ${fixture.competition_id}`.toLowerCase();
  return worldCupCompetitionIds.has(String(fixture.competition_id)) || name.includes("world cup") || name.includes("世界杯");
}

function isFixtureOnDate(fixture: Fixture, selectedDate: string): boolean {
  if (fixture.operational_date_beijing) {
    return fixture.operational_date_beijing === selectedDate;
  }
  if (fixture.kickoff_beijing) {
    return fixture.kickoff_beijing.startsWith(selectedDate);
  }
  return false;
}

function apiFixturesEndpoint(selectedDate: string): string {
  const params = new URLSearchParams({
    competition_id: "1",
    page_size: "80",
    status: "NS",
    timezone: "Asia/Shanghai",
    operational_date: selectedDate,
  });
  return `/api/v1/fixtures?${params.toString()}`;
}

async function loadAnalysisDashboard(selectedDate: string): Promise<Resource<AnalysisDashboardData>> {
  const fixturesEndpoint = apiFixturesEndpoint(selectedDate);
  const fixtures = await loadJson<FixtureList>(fixturesEndpoint);
  if (fixtures.status === "ERROR") {
    return {
      ...fixtures,
      data: null,
    };
  }
  const todayFixtures = (fixtures.data?.items ?? [])
    .filter((fixture) => isWorldCupFixture(fixture))
    .filter((fixture) => isFixtureOnDate(fixture, selectedDate));
  if (!todayFixtures.length) {
    return {
      ...fixtures,
      status: "EMPTY",
      data: { fixtures: [], cards: [] },
    };
  }
  const cards = await Promise.all(
    todayFixtures.map((fixture) => loadJson<AnalysisCardResponse>(`/api/v1/fixtures/${fixture.fixture_id}/analysis-card`)),
  );
  return {
    status: cards.some((card) => card.status === "STALE") ? "STALE" : "SUCCESS",
    endpoint: fixturesEndpoint,
    data: {
      fixtures: todayFixtures,
      cards: todayFixtures.map((fixture, index) => {
        const loaded = cards[index];
        return loaded.data?.card ?? fallbackAnalysisCard(fixture, loaded.errorCode ?? "ANALYSIS_CARD_UNAVAILABLE");
      }),
    },
    requestId: fixtures.requestId,
    errorCode: null,
    message: null,
  };
}

function fallbackAnalysisCard(fixture: Fixture, reason: string): AnalysisCard {
  const marketReasons: Record<string, string> = {
    ASIAN_HANDICAP: reason,
    TOTALS: reason,
    FIRST_HALF_GOALS: reason,
    SCORE: reason,
  };
  return {
    fixture_id: fixture.fixture_id,
    kickoff_utc: fixture.kickoff_utc,
    competition_cn: fixture.competition_name,
    home_cn: fixture.home_team_name ?? fixture.home_team_id,
    away_cn: fixture.away_team_name ?? fixture.away_team_id,
    decision: "SKIP",
    watch_level: 0,
    bookmaker_intent: {
      intent: "INSUFFICIENT_DATA",
      label_cn: "数据不足",
      opening_line: null,
      current_line: null,
      confidence: 0,
      reason,
    },
    markets: ["ASIAN_HANDICAP", "TOTALS", "FIRST_HALF_GOALS", "SCORE"].map((market) => ({
      market,
      label_cn: market === "ASIAN_HANDICAP" ? "让球" : market === "TOTALS" ? "大小球" : market === "FIRST_HALF_GOALS" ? "半场进球" : "比分",
      decision: "SKIP",
      analysis_decision: "SKIP",
      lean_cn: null,
      confidence: 0,
      reason_cn: marketReasons[market],
      risks_cn: ["数据不足时保持 SKIP。"],
      reference_scores: [],
      candidate: false,
      formal_recommendation: false,
    })),
    risks_cn: ["analysis-card 暂不可用，保持 SKIP。"],
    disclaimer_cn: "分析参考·非稳赢",
    disclaimer: "分析参考·非稳赢",
    candidate: false,
    formal_recommendation: false,
    source: "frontend_analysis_card_fallback",
  };
}

function confidenceDots(confidence: number): boolean[] {
  const filled = Math.max(0, Math.min(5, Math.round(confidence * 5)));
  return Array.from({ length: 5 }, (_, index) => index < filled);
}

function marketTone(market: string): string {
  if (market === "ASIAN_HANDICAP") {
    return "tone-ah";
  }
  if (market === "TOTALS") {
    return "tone-ou";
  }
  if (market === "FIRST_HALF_GOALS") {
    return "tone-half";
  }
  if (market === "SCORE") {
    return "tone-score";
  }
  return "tone-neutral";
}

function ConfidenceDots({ confidence }: { confidence: number }) {
  return (
    <span aria-label={`confidence ${Math.round(confidence * 100)} percent`} className="confidence-dots">
      {confidenceDots(confidence).map((filled, index) => (
        <span className={filled ? "dot filled" : "dot"} key={index} />
      ))}
    </span>
  );
}

function WatchLevel({ level }: { level: number }) {
  const value = Math.max(0, Math.min(4, level));
  return <span className="watch-level">关注度 {value ? "★".repeat(value) : "0"}</span>;
}

function AnalysisMarketRow({ market }: { market: AnalysisMarketCard }) {
  const tone = marketTone(market.market);
  const isSkip = market.decision === "SKIP";
  return (
    <div className={isSkip ? "analysis-market skip" : "analysis-market"}>
      <div className="market-main">
        <div className="market-name">
          <span>{market.label_cn}</span>
          <small>{market.market}</small>
        </div>
        {isSkip ? (
          <span className="skip-chip">{market.label_cn} · SKIP</span>
        ) : (
          <>
            <span className={`lean-badge ${tone}`}>{market.lean_cn ?? "倾向待确认"}</span>
            <ConfidenceDots confidence={market.confidence ?? 0} />
          </>
        )}
      </div>
      {market.market === "SCORE" && market.reference_scores?.length ? (
        <div className="score-row">
          {market.reference_scores.slice(0, 2).map((score) => (
            <span className="score-chip" key={score.scoreline}>
              {score.scoreline}
              {score.conditional_probability !== null && score.conditional_probability !== undefined
                ? ` · ${(score.conditional_probability * 100).toFixed(1)}%`
                : ""}
            </span>
          ))}
          <small>方向一致的条件概率 · 非精确比分预测</small>
        </div>
      ) : null}
      <p>理由：{market.reason_cn ?? "数据不足，等待盘口快照与 xG 富集。"}</p>
    </div>
  );
}

function AnalysisFixtureCard({ card }: { card: AnalysisCard }) {
  const marketsByName = new Map(card.markets.map((market) => [market.market, market]));
  const orderedMarkets = ["ASIAN_HANDICAP", "TOTALS", "FIRST_HALF_GOALS", "SCORE"].flatMap((market) => {
    const row = marketsByName.get(market);
    return row ? [row] : [];
  });
  const isSkip = card.decision === "SKIP";
  const intent = card.bookmaker_intent ?? { intent: "INSUFFICIENT_DATA", label_cn: "数据不足" };
  const opening = intent.opening_line ?? null;
  const current = intent.current_line ?? null;
  return (
    <article className={isSkip ? "analysis-card skip-card" : "analysis-card"}>
      <header className="analysis-card-head">
        <div>
          <span>{card.kickoff_utc ?? "kickoff pending"} · {card.competition_cn ?? "世界杯"}</span>
          <h2>{card.home_cn ?? "主队"} vs {card.away_cn ?? "客队"}</h2>
        </div>
        <strong>{card.decision}</strong>
      </header>
      <div className={isSkip ? "intent-strip insufficient" : "intent-strip"}>
        {isSkip
          ? `数据不足（${intent.intent}）`
          : `庄家意图：${intent.label_cn ?? intent.intent} · 盘口 ${opening ?? "n/a"}→${current ?? "n/a"}`}
      </div>
      <div className="analysis-markets">
        {orderedMarkets.map((market) => (
          <AnalysisMarketRow key={market.market} market={market} />
        ))}
      </div>
      {isSkip ? (
        <p className="skip-note">暂不推荐：等盘口快照与 xG 富集到位后自动更新。</p>
      ) : (
        <footer className="analysis-card-foot">
          <span>风险：{card.risks_cn?.length ? card.risks_cn.join("、") : "暂无额外风险"}</span>
          <WatchLevel level={card.watch_level ?? 0} />
        </footer>
      )}
    </article>
  );
}

function AnalysisDashboard({
  resource,
  selectedDate,
  onDateChange,
  onRetry,
}: {
  resource: Resource<AnalysisDashboardData>;
  selectedDate: string;
  onDateChange: (value: string) => void;
  onRetry: () => void;
}) {
  const cards = resource.data?.cards ?? [];
  return (
    <section className="analysis-dashboard">
      <header className="analysis-topbar">
        <div>
          <p className="kicker">W2 足球分析</p>
          <h1>W2 足球分析 · 今日比赛</h1>
        </div>
        <strong className="analysis-pill">分析参考·非稳赢</strong>
      </header>

      <div className="analysis-filter">
        <button type="button" onClick={() => onDateChange(beijingToday())}>今日</button>
        <span>世界杯</span>
        <label>
          时间
          <input type="date" value={selectedDate} onChange={(event) => onDateChange(event.target.value)} />
        </label>
      </div>

      {resource.status === "LOADING" ? <p className="muted">Loading analysis cards from {resource.endpoint}</p> : null}
      {resource.status === "ERROR" ? (
        <div className="error-box">
          <p>Endpoint: {resource.endpoint}</p>
          <p>request_id: {resource.requestId}</p>
          <p>error: {resource.errorCode}</p>
          <button type="button" onClick={onRetry}>Retry</button>
        </div>
      ) : null}
      {resource.status === "EMPTY" ? (
        <div className="analysis-card skip-card">
          <p className="muted">今日没有白名单世界杯比赛可展示。</p>
        </div>
      ) : null}
      {(resource.status === "SUCCESS" || resource.status === "STALE") ? (
        <div className="analysis-list">
          {cards.map((card) => (
            <AnalysisFixtureCard card={card} key={card.fixture_id} />
          ))}
        </div>
      ) : null}
      <footer className="analysis-disclaimer">本页为分析参考，非投注建议，分析参考·非稳赢 · 数据不足时一律 SKIP</footer>
    </section>
  );
}

function beijingToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function matchdayFixture(item: Record<string, unknown>): Fixture {
  return {
    fixture_id: String(item.fixture_id),
    competition_id: String(item.competition_id),
    competition_name: String(item.competition_name),
    kickoff_utc: String(item.kickoff_utc),
    kickoff_beijing: item.kickoff_beijing ? String(item.kickoff_beijing) : null,
    operational_date_beijing: item.operational_date_beijing ? String(item.operational_date_beijing) : null,
    kickoff_display: String(item.kickoff_beijing ?? item.kickoff_utc),
    status: String(item.status),
    home_team_id: String(item.home_team_id),
    home_team_name: item.home_team_name ? String(item.home_team_name) : null,
    away_team_id: String(item.away_team_id),
    away_team_name: item.away_team_name ? String(item.away_team_name) : null,
    lifecycle_state: String(item.action ?? item.lifecycle_state ?? "SKIP"),
    data_state: String(item.data_health ?? item.data_state ?? "CAPTURED_AT"),
    published_grade: item.published_grade ? String(item.published_grade) : null,
    primary_market: item.primary_market ? String(item.primary_market) : null,
    primary_line: item.primary_line ? String(item.primary_line) : null,
    primary_odds: item.primary_odds ? String(item.primary_odds) : null,
    last_captured: item.last_captured ? String(item.last_captured) : null,
  };
}

function App() {
  const [selectedDate, setSelectedDate] = useState<string>(beijingToday());
  const [analysis, setAnalysis] = useState<Resource<AnalysisDashboardData>>(emptyResource(apiFixturesEndpoint(beijingToday())));
  const [fixtures, setFixtures] = useState<Resource<FixtureList>>(emptyResource(`/api/v1/matchday/${beijingToday()}`));
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Resource<FixtureDetail>>(emptyResource("/api/v1/fixtures/none"));
  const [forward, setForward] = useState<Resource<ForwardStatus>>(emptyResource("/api/v1/forward-holdout/status"));
  const [provider, setProvider] = useState<Resource<ProviderStatus>>(emptyResource("/api/v1/providers/status"));
  const [health, setHealth] = useState<Resource<DataHealth>>(emptyResource("/api/v1/data-health"));
  const [market, setMarket] = useState<Resource<Probability>>(emptyResource("/api/v1/fixtures/none/market-probabilities"));
  const [model, setModel] = useState<Resource<Probability>>(emptyResource("/api/v1/fixtures/none/model-probabilities"));
  const [matchday, setMatchday] = useState<Resource<Matchday>>(emptyResource("/api/v1/matchday"));
  const [next36, setNext36] = useState<Resource<Matchday>>(emptyResource("/api/v1/matchday/next-36-hours"));
  const [coverage, setCoverage] = useState<Resource<MatchdayCoverage>>(emptyResource("/api/ops/matchday-coverage"));
  const [ranking, setRanking] = useState<Resource<MarketRanking>>(emptyResource("/api/v1/fixtures/none/market-ranking"));
  const [integrity, setIntegrity] = useState<Resource<Integrity>>(emptyResource("/api/v1/fixtures/none/integrity"));
  const [tasks, setTasks] = useState<Resource<OpsList>>(emptyResource("/api/ops/tasks"));
  const [alerts, setAlerts] = useState<Resource<OpsList>>(emptyResource("/api/ops/alerts"));
  const [worldCup, setWorldCup] = useState<Resource<WorldCupReadiness>>(emptyResource("/api/ops/world-cup-readiness"));
  const [leagues, setLeagues] = useState<Resource<LeagueList>>(emptyResource("/api/v1/leagues"));
  const [operations, setOperations] = useState<Resource<OperationsLatest>>(emptyResource("/api/ops/operations/latest"));
  const [release, setRelease] = useState<Resource<ReleaseReadiness>>(emptyResource("/api/ops/releases/readiness"));
  const [retention, setRetention] = useState<Resource<RetentionStatus>>(emptyResource("/api/ops/retention/status"));
  const [shadowStrategy, setShadowStrategy] = useState<Resource<ShadowStrategyStatus>>(emptyResource("/api/ops/shadow-strategy/status"));
  const [gate5, setGate5] = useState<Resource<OpsList>>(emptyResource("/api/ops/gates/5-preflight"));
  const [w1w2, setW1w2] = useState<Resource<OpsList>>(emptyResource("/api/ops/w1-w2-shadow-comparison"));

  const loadFixtures = useCallback(() => {
    const endpoint = `/api/v1/matchday/${selectedDate}`;
    setFixtures(emptyResource(endpoint));
    loadJson<Matchday>(endpoint).then((payload) => {
      const fixturePayload: Resource<FixtureList> = {
        ...payload,
        data: payload.data
          ? {
              request_id: payload.data.request_id,
              items: payload.data.items.map(matchdayFixture),
            }
          : null,
      };
      setFixtures(fixturePayload);
      const first = fixturePayload.data?.items?.[0]?.fixture_id ?? null;
      setSelected((current) => current ?? first);
    });
  }, [selectedDate]);

  const loadAnalysis = useCallback(() => {
    setAnalysis(emptyResource(apiFixturesEndpoint(selectedDate)));
    loadAnalysisDashboard(selectedDate).then(setAnalysis);
  }, [selectedDate]);

  const loadCommon = useCallback(() => {
    loadJson<ForwardStatus>("/api/v1/forward-holdout/status").then(setForward);
    loadJson<ProviderStatus>("/api/v1/providers/status").then(setProvider);
    loadJson<DataHealth>("/api/v1/data-health").then(setHealth);
    loadJson<OpsList>("/api/ops/tasks").then(setTasks);
    loadJson<OpsList>("/api/ops/alerts").then(setAlerts);
    loadJson<WorldCupReadiness>("/api/ops/world-cup-readiness").then(setWorldCup);
    loadJson<LeagueList>("/api/v1/leagues").then(setLeagues);
    loadJson<OperationsLatest>("/api/ops/operations/latest").then(setOperations);
    loadJson<ReleaseReadiness>("/api/ops/releases/readiness").then(setRelease);
    loadJson<RetentionStatus>("/api/ops/retention/status").then(setRetention);
    loadJson<ShadowStrategyStatus>("/api/ops/shadow-strategy/status").then(setShadowStrategy);
    loadJson<OpsList>("/api/ops/gates/5-preflight").then(setGate5);
    loadJson<OpsList>("/api/ops/w1-w2-shadow-comparison").then(setW1w2);
    loadJson<Matchday>("/api/v1/matchday").then(setMatchday);
    loadJson<Matchday>("/api/v1/matchday/next-36-hours").then(setNext36);
    loadJson<MatchdayCoverage>("/api/ops/matchday-coverage").then(setCoverage);
  }, []);

  useEffect(() => {
    loadAnalysis();
    loadFixtures();
    loadCommon();
  }, [loadAnalysis, loadCommon, loadFixtures]);

  useEffect(() => {
    if (!selected) {
      return;
    }
    const detailEndpoint = `/api/v1/fixtures/${selected}`;
    const marketEndpoint = `/api/v1/fixtures/${selected}/market-probabilities`;
    const modelEndpoint = `/api/v1/fixtures/${selected}/model-probabilities`;
    const rankingEndpoint = `/api/v1/fixtures/${selected}/market-ranking`;
    const integrityEndpoint = `/api/v1/fixtures/${selected}/integrity`;
    setDetail(emptyResource(detailEndpoint));
    setMarket(emptyResource(marketEndpoint));
    setModel(emptyResource(modelEndpoint));
    setRanking(emptyResource(rankingEndpoint));
    setIntegrity(emptyResource(integrityEndpoint));
    loadJson<FixtureDetail>(detailEndpoint).then(setDetail);
    loadJson<Probability>(marketEndpoint).then(setMarket);
    loadJson<Probability>(modelEndpoint).then(setModel);
    loadJson<MarketRanking>(rankingEndpoint).then(setRanking);
    loadJson<Integrity>(integrityEndpoint).then(setIntegrity);
  }, [selected]);

  const fixtureItems = fixtures.data?.items ?? [];
  const selectedFixture = useMemo(
    () => fixtureItems.find((fixture) => fixture.fixture_id === selected),
    [fixtureItems, selected],
  );

  return (
    <main className="shell">
      <AnalysisDashboard
        resource={analysis}
        selectedDate={selectedDate}
        onDateChange={setSelectedDate}
        onRetry={loadAnalysis}
      />

      <header className="topbar ops-topbar">
        <div>
          <p className="kicker">W2 Operations Console</p>
          <h1>Live read-model dashboard</h1>
        </div>
        <strong className="banner">正式推荐尚未启用，当前仅为研究与前瞻验证。</strong>
      </header>

      <section className="grid three">
        <StatePanel title="Forward Holdout" resource={forward} onRetry={loadCommon}>
          {(data) => (
            <div className="metric">
              <strong>{data.status}</strong>
              <p>{data.current_settled_n}/{data.target_n} settled · market comparable {data.market_comparable}</p>
            </div>
          )}
        </StatePanel>
        <StatePanel title="Provider" resource={provider} onRetry={loadCommon}>
          {(data) => (
            <div className="metric">
              <strong>{data.status}</strong>
              <p>{data.provider} · quota {data.remaining_quota ?? "unknown"} · last {data.last_request_status ?? "n/a"}</p>
            </div>
          )}
        </StatePanel>
        <StatePanel title="Data Health" resource={health} onRetry={loadCommon}>
          {(data) => (
            <div className="metric">
              <strong>{data.provider_status}</strong>
              <p>{data.stale_data_count} stale · generated {data.generated_at}</p>
            </div>
          )}
        </StatePanel>
      </section>

      <section className="grid main-grid">
        <StatePanel title="今日比赛（北京时间）" resource={fixtures} onRetry={loadFixtures}>
          {(data) => (
            <>
              <label className="date-control">
                北京时间日期
                <input type="date" value={selectedDate} onChange={(event) => setSelectedDate(event.target.value)} />
              </label>
              <p className="source">窗口：北京时间 00:00:00 至次日 00:00:00，左闭右开。</p>
              <div className="fixture-list">
                {data.items.map((fixture) => (
                  <button
                    className={fixture.fixture_id === selected ? "fixture active" : "fixture"}
                    key={fixture.fixture_id}
                    onClick={() => setSelected(fixture.fixture_id)}
                    type="button"
                  >
                    <span>{fixture.competition_name}</span>
                    <strong>{fixture.home_team_name ?? fixture.home_team_id} vs {fixture.away_team_name ?? fixture.away_team_id}</strong>
                    <small>北京时间 {fixture.kickoff_beijing ?? fixture.kickoff_display}</small>
                    <small>UTC {fixture.kickoff_utc} · {fixture.status} · {fixture.lifecycle_state}</small>
                    <small>
                      {fixture.primary_market ?? "NO_MARKET"} {fixture.primary_line ?? ""} · {fixture.primary_odds ?? "n/a"}
                    </small>
                  </button>
                ))}
              </div>
            </>
          )}
        </StatePanel>

        <StatePanel title="Fixture Detail" resource={detail} onRetry={() => selected && loadJson<FixtureDetail>(`/api/v1/fixtures/${selected}`).then(setDetail)}>
          {(data) => (
            <dl className="facts">
              <div><dt>Fixture</dt><dd>{selectedFixture?.fixture_id ?? data.fixture_id}</dd></div>
              <div><dt>Competition</dt><dd>{data.competition_name}</dd></div>
              <div><dt>Kickoff 北京时间</dt><dd>{data.kickoff_beijing ?? data.kickoff_display}</dd></div>
              <div><dt>Kickoff UTC</dt><dd>{data.kickoff_utc}</dd></div>
              <div><dt>Operational date</dt><dd>{data.operational_date_beijing ?? "n/a"}</dd></div>
              <div><dt>Bookmakers</dt><dd>{data.bookmaker_count}</dd></div>
              <div><dt>Coverage</dt><dd>{JSON.stringify(data.market_coverage)}</dd></div>
              <div><dt>Research status</dt><dd>{data.forward_decision}</dd></div>
              <div><dt>Primary market</dt><dd>{data.primary_market ?? "NO_BET"} {data.primary_selection ?? ""} {data.primary_line ?? ""}</dd></div>
              <div><dt>Executable / HK</dt><dd>{data.primary_executable_odds ?? "n/a"} / {data.primary_hong_kong_odds ?? "n/a"}</dd></div>
              <div><dt>Model fair odds</dt><dd>{data.primary_model_fair_odds ?? "n/a"}</dd></div>
              <div><dt>Risk-adjusted EV</dt><dd>{data.primary_risk_adjusted_ev ?? "n/a"}</dd></div>
              <div><dt>Research grade</dt><dd>{data.research_grade ?? "D"} · 正式推荐尚未启用</dd></div>
              <div><dt>AH / OU ladder</dt><dd>{data.ah_ladder?.length ?? 0} AH · {data.ou_ladder?.length ?? 0} OU</dd></div>
              <div><dt>1X2 / BTTS ranking</dt><dd>{data.one_x_two_ranking?.length ?? 0} 1X2 · {data.btts_ranking?.length ?? 0} BTTS</dd></div>
              <div><dt>All-market ranking</dt><dd>{data.all_market_ranking?.length ?? 0} markets evaluated</dd></div>
              <div><dt>Source captured</dt><dd>{data.source_captured_at ?? "n/a"} · {data.source_phase ?? "n/a"}</dd></div>
              <div><dt>Recompute time</dt><dd>{data.valuation_generated_at ?? "n/a"}</dd></div>
              <div><dt>Temporal / integrity</dt><dd>{data.temporal_status ?? "UNKNOWN"} · {data.integrity_status ?? "UNKNOWN"}</dd></div>
              <div><dt>Risk notes</dt><dd>{data.risk_notes.length ? data.risk_notes.join(", ") : "None"}</dd></div>
              {data.temporal_status === "POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH" ? (
                <div><dt>Notice</dt><dd>基于赛前锁定数据的赛后重算，不代表赛前实时发布。</dd></div>
              ) : null}
            </dl>
          )}
        </StatePanel>
      </section>

      <section className="grid two">
        <StatePanel title="Daily Matchday" resource={matchday} onRetry={loadCommon}>
          {(data) => (
            <div className="fixture-list">
              <strong>{data.date} 北京时间 · {data.total} fixtures</strong>
              {data.items.map((item) => (
                <div className="fixture" key={String(item.fixture_id)}>
                  <span>{String(item.competition_name ?? item.fixture_id)}</span>
                  <strong>{String(item.home_team_name ?? "")} vs {String(item.away_team_name ?? "")}</strong>
                  <small>北京时间 {String(item.kickoff_beijing ?? item.kickoff_utc)}</small>
                  <small>{String(item.primary_market ?? "NO_MARKET")} {String(item.primary_line ?? "")} · grade {String(item.published_grade ?? "X")}</small>
                </div>
              ))}
            </div>
          )}
        </StatePanel>
        <StatePanel title="未来36小时" resource={next36} onRetry={loadCommon}>
          {(data) => (
            <div className="fixture-list">
              <strong>NEXT_36_HOURS · {data.total} fixtures</strong>
              {data.items.map((item) => (
                <div className="fixture" key={String(item.fixture_id)}>
                  <span>{String(item.competition_name ?? item.fixture_id)}</span>
                  <strong>{String(item.home_team_name ?? "")} vs {String(item.away_team_name ?? "")}</strong>
                  <small>北京时间 {String(item.kickoff_beijing ?? item.kickoff_utc)}</small>
                </div>
              ))}
            </div>
          )}
        </StatePanel>
      </section>

      <section className="grid two">
        <StatePanel title="Coverage Audit" resource={coverage} onRetry={loadCommon}>
          {(data) => (
            <div className={data.coverage_status === "READY" ? "metric" : "error-box"}>
              <strong>{data.coverage_status}</strong>
              <p>{data.requested_date_beijing} · {data.timezone}</p>
              <p>Provider/read model/displayed: {data.authoritative_count}/{data.read_model_count}/{data.displayed_count}</p>
              <p>Window UTC: {data.window_start_utc} → {data.window_end_utc}</p>
              <pre>{JSON.stringify(data.reason_distribution, null, 2)}</pre>
            </div>
          )}
        </StatePanel>
        <StatePanel title="Market Ranking / Integrity" resource={ranking} onRetry={() => selected && loadJson<MarketRanking>(`/api/v1/fixtures/${selected}/market-ranking`).then(setRanking)}>
          {(data) => (
            <div>
              <p>{data.items.length} market rows · 正式推荐尚未启用</p>
              <pre>{JSON.stringify(data.items.slice(0, 5), null, 2)}</pre>
              {integrity.data ? <pre>{JSON.stringify(integrity.data.integrity, null, 2)}</pre> : null}
            </div>
          )}
        </StatePanel>
      </section>

      <section className="grid two">
        <ProbabilityTable title="Market fair probabilities" resource={market} onRetry={() => selected && loadJson<Probability>(`/api/v1/fixtures/${selected}/market-probabilities`).then(setMarket)} />
        <ProbabilityTable title="Independent model probabilities" resource={model} onRetry={() => selected && loadJson<Probability>(`/api/v1/fixtures/${selected}/model-probabilities`).then(setModel)} />
      </section>

      <section className="grid two">
        <StatePanel title="Shadow Strategy" resource={shadowStrategy} onRetry={loadCommon}>
          {(data) => (
            <dl className="facts">
              <div><dt>Status</dt><dd>{data.status}</dd></div>
              <div><dt>Version</dt><dd>{data.strategy_version}</dd></div>
              <div><dt>Locks</dt><dd>{data.locks} shadow locks · {data.decisions} decisions</dd></div>
              <div><dt>Gate</dt><dd>{data.gate4_status} · {data.gate5_status}</dd></div>
              <div><dt>Published mode</dt><dd>{data.formal_recommendation ? "BLOCKED" : "WATCH/SKIP only"}</dd></div>
              <div><dt>Latest replay</dt><dd>{data.latest_run_id ?? "not available"}</dd></div>
              <div><dt>Notice</dt><dd>影子策略，正式推荐尚未启用。</dd></div>
            </dl>
          )}
        </StatePanel>
        <StatePanel title="Tasks" resource={tasks} onRetry={loadCommon}>
          {(data) => <pre>{JSON.stringify(data.items, null, 2)}</pre>}
        </StatePanel>
      </section>

      <section className="grid two">
        <StatePanel title="Gate 5 Preflight" resource={gate5} onRetry={loadCommon}>
          {(data) => (
            <div>
              <p>Gate4 remains prerequisite; Gate5 cannot close from this panel.</p>
              <pre>{JSON.stringify(data.items, null, 2)}</pre>
            </div>
          )}
        </StatePanel>
        <StatePanel title="W1/W2 Shadow Comparison" resource={w1w2} onRetry={loadCommon}>
          {(data) => (
            <div>
              <p>Read-only frozen comparison; missing W1 fields remain NOT_AVAILABLE.</p>
              <pre>{JSON.stringify(data.items, null, 2)}</pre>
            </div>
          )}
        </StatePanel>
      </section>

      <section className="grid two">
        <StatePanel title="World Cup Readiness" resource={worldCup} onRetry={loadCommon}>
          {(data) => (
            <dl className="facts">
              <div><dt>Profile</dt><dd>{data.profile_version}</dd></div>
              <div><dt>Fixture coverage</dt><dd>{data.fixture_coverage_count}</dd></div>
              <div><dt>Gate</dt><dd>{data.gate_status}</dd></div>
              <div><dt>Strategy</dt><dd>{data.strategy_version}</dd></div>
              <div><dt>Blockers</dt><dd>{data.blockers.length ? data.blockers.join(", ") : "None"}</dd></div>
            </dl>
          )}
        </StatePanel>
        <StatePanel title="League Readiness" resource={leagues} onRetry={loadCommon}>
          {(data) => (
            <div className="league-grid">
              {data.items.map((league) => (
                <article className="league-card" key={league.competition_id}>
                  <h3>{league.name}</h3>
                  <span>{league.country}</span>
                  <p>{league.results_status} · {league.latest_season ?? "review"}</p>
                  <small>{JSON.stringify(league.market_status)}</small>
                </article>
              ))}
            </div>
          )}
        </StatePanel>
      </section>

      <section className="grid two">
        <StatePanel title="Alerts" resource={alerts} onRetry={loadCommon}>
          {(data) => <pre>{JSON.stringify(data.items, null, 2)}</pre>}
        </StatePanel>
      </section>

      <section className="panel readiness">
        <div className="panel-title">
          <h2>Operations Governance</h2>
          <span>{operations.data?.latest.status ?? operations.status}</span>
        </div>
        <div className="readiness-grid">
          <div><span>Forward progress</span><strong>{forward.data ? `${forward.data.current_settled_n}/${forward.data.target_n}` : forward.status}</strong></div>
          <div><span>Dependency risk</span><strong>{release.data?.dependency_blocker ?? release.status}</strong></div>
          <div><span>Backups / retention</span><strong>{retention.data?.status ?? retention.status}</strong></div>
          <div><span>Gate</span><strong>GATE_4_PENDING</strong></div>
        </div>
        <p className="warning">正式推荐与生产发布尚未启用。</p>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
