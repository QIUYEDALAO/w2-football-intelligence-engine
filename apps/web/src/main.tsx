import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = "/v1";
const COMPETITION_ID = "1";
const MARKET_ORDER = ["ASIAN_HANDICAP", "TOTALS", "FIRST_HALF_GOALS", "SCORE"] as const;

type FilterMode = "ALL" | "PICK" | "SKIP";
type LoadState = "loading" | "ok" | "error" | "empty";

type AnalysisCard = Record<string, unknown>;

type ReadinessItem = {
  key: string;
  label: string;
  value: string;
  ready: boolean;
};

const MARKET_META: Record<string, { label: string; short: string; tone: string }> = {
  ASIAN_HANDICAP: { label: "亚洲让球", short: "让球", tone: "tone-ah" },
  TOTALS: { label: "大小球", short: "大小", tone: "tone-ou" },
  FIRST_HALF_GOALS: { label: "半场进球", short: "半场", tone: "tone-half" },
  SCORE: { label: "比分参考", short: "比分", tone: "tone-score" },
};

const INTENT_LABELS: Record<string, string> = {
  HOME_LEAN: "偏主队",
  AWAY_LEAN: "偏客队",
  OVER_LEAN: "偏大球",
  UNDER_LEAN: "偏小球",
  CONFLICTED: "信号分歧",
  INSUFFICIENT_DATA: "数据不足",
  LEAKAGE_BLOCKED: "as-of 拦截",
};

const TENDENCY_LABELS: Record<string, string> = {
  HOME_AH: "主队方向",
  AWAY_AH: "客队方向",
  NO_SIDE_EDGE: "暂无边向",
  OVER: "大球方向",
  UNDER: "小球方向",
  "1H_OVER": "半场有球",
  "1H_UNDER": "半场谨慎",
  HOME: "主胜方向",
  AWAY: "客胜方向",
  DRAW: "平局方向",
};

const COMPETITION_TRANSLATIONS: Array<[RegExp, string]> = [
  [/World Cup/i, "世界杯"],
  [/Group Stage/i, "小组赛"],
  [/Round of 16/i, "16 强"],
  [/Quarter[- ]final/i, "四分之一决赛"],
  [/Semi[- ]final/i, "半决赛"],
  [/Final/i, "决赛"],
];

const REASON_TRANSLATIONS: Array<[RegExp, string]> = [
  [/^F9_TRUE_XG:/, "滚动 xG 已纳入对比。"],
  [/^F1_MARKET_MOVEMENT:/, "盘口从初盘到当前有可用变化。"],
  [/^F2_BOOKMAKER_DISAGREEMENT:/, "多家庄家分歧已纳入。"],
  [/^F3_REST:/, "体能与休息差已纳入。"],
  [/^F4_MATCH_IMPORTANCE:/, "赛事阶段重要性已纳入。"],
  [/^F5_SETTLED_AH_FORM:/, "近期赢盘表现已纳入，权重较低。"],
  [/^F6_H2H:/, "历史交锋已纳入。"],
  [/^F7_STRENGTH_FORM:/, "球队强度与近期状态已纳入。"],
  [/^F8_SQUAD_VALUE:/, "球队身价差异已纳入，权重较低。"],
  [/^FEATURES_INSUFFICIENT$/, "多因素输入不足。"],
  [/^AH_ANALYSIS_INPUT_UNAVAILABLE$/, "让球分析输入不足。"],
  [/^AH_MARKET_UNAVAILABLE$/, "让球盘口暂未覆盖。"],
  [/^OU_ANALYSIS_INPUT_UNAVAILABLE$/, "大小球分析输入不足。"],
  [/^OU_MARKET_UNAVAILABLE$/, "大小球盘口暂未覆盖。"],
  [/^HALF_GOAL_INPUT_UNAVAILABLE$/, "半场进球模型输入不足。"],
  [/^SCORE_MATRIX_UNAVAILABLE$/, "比分矩阵暂不可用。"],
  [/^BOOKMAKER_INTENT_INPUT_UNAVAILABLE$/, "庄家意图输入不足。"],
  [/^INSUFFICIENT_DATA$/, "数据点不足，暂不输出倾向。"],
  [/^CONFLICTED$/, "盘口信号互相冲突，暂不强出方向。"],
  [/^LEAKAGE_BLOCKED$/, "as-of 防泄漏规则拦截。"],
  [/^大小球意图: OVER_LEAN$/, "大小球盘口倾向偏大。"],
  [/^大小球意图: UNDER_LEAN$/, "大小球盘口倾向偏小。"],
  [/^大小球意图: CONFLICTED$/, "大小球盘口方向存在分歧。"],
  [/^庄家意图: HOME_LEAN$/, "庄家意图偏主队方向。"],
  [/^庄家意图: AWAY_LEAN$/, "庄家意图偏客队方向。"],
  [/^半场 Poisson 拆分 P\(1H>0\.5\)=/, "半场进球使用 1H Poisson 拆分估计。"],
  [/^比分使用方向一致条件概率/, "比分只展示与主方向一致的条件概率。"],
];

function todayShanghai(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    return value;
  }
  const record = asRecord(value);
  for (const key of ["items", "fixtures", "data", "results"]) {
    const nested = record[key];
    if (Array.isArray(nested)) {
      return nested;
    }
  }
  return [];
}

function textValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return fallback;
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function booleanValue(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value > 0;
  }
  if (typeof value === "string") {
    return ["true", "ready", "available", "yes"].includes(value.toLowerCase());
  }
  return false;
}

function fxId(item: unknown): string {
  const record = asRecord(item);
  const fixture = asRecord(record.fixture);
  return textValue(record.fixture_id ?? record.id ?? fixture.id);
}

function isFixtureOnDate(fixture: unknown, selectedDate: string): boolean {
  const record = asRecord(fixture);
  const operationalDate = textValue(record.operational_date_beijing);
  if (operationalDate) {
    return operationalDate === selectedDate;
  }
  return textValue(record.kickoff_beijing).startsWith(selectedDate);
}

function cardPayload(payload: unknown): AnalysisCard {
  const record = asRecord(payload);
  return asRecord(record.card ?? payload);
}

function fixtureTeamName(fixture: unknown, side: "home" | "away"): string {
  const record = asRecord(fixture);
  const teams = asRecord(record.teams);
  const team = asRecord(teams[side]);
  return textValue(
    record[`${side}_team_name`] ?? record[`${side}_name`] ?? record[`${side}_cn`] ?? team.name,
    side === "home" ? "主队" : "客队",
  );
}

function fixtureCompetition(fixture: unknown): string {
  const record = asRecord(fixture);
  const league = asRecord(record.league);
  const base = textValue(record.competition_name ?? record.competition_cn ?? league.name, "世界杯");
  const round = textValue(league.round);
  return translateCompetition(round && !base.includes(round) ? `${base} · ${round}` : base);
}

function fixtureKickoff(fixture: unknown): string {
  const record = asRecord(fixture);
  const nested = asRecord(record.fixture);
  return textValue(record.kickoff_utc ?? nested.date);
}

function fmtTime(iso?: unknown): string {
  const raw = textValue(iso);
  if (!raw) {
    return "--:--";
  }
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(raw));
  } catch {
    return "--:--";
  }
}

async function getJSON(url: string, timeoutMs = 20000): Promise<unknown> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const response = await fetch(url, { headers: { Accept: "application/json" }, signal: controller.signal }).finally(() => {
    window.clearTimeout(timeout);
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json() as Promise<unknown>;
}

function fallbackCardFromFixture(fixture: unknown): AnalysisCard {
  return {
    fixture_id: fxId(fixture),
    kickoff_utc: fixtureKickoff(fixture),
    competition_name: fixtureCompetition(fixture),
    competition_cn: fixtureCompetition(fixture),
    home_name: fixtureTeamName(fixture, "home"),
    away_name: fixtureTeamName(fixture, "away"),
    home_cn: fixtureTeamName(fixture, "home"),
    away_cn: fixtureTeamName(fixture, "away"),
    decision: "SKIP",
    loading: true,
    watch_level: 0,
    bookmaker_intent: { intent: "INSUFFICIENT_DATA", label_cn: "数据加载中" },
    markets: MARKET_ORDER.map((market) => ({ market, decision: "SKIP", reasons: ["BOOKMAKER_INTENT_INPUT_UNAVAILABLE"] })),
    data_readiness: { bookmakers: 0, odds_snapshots: 0, xg: false, h2h: false, lineups: false },
    risks_cn: ["盘口快照与多因素数据加载中。"],
    candidate: false,
    formal_recommendation: false,
  };
}

function normalizeCards(fixtures: unknown[]): AnalysisCard[] {
  return fixtures.map(fallbackCardFromFixture);
}

function decision(card: AnalysisCard): string {
  return textValue(card.decision, "SKIP");
}

function isPick(card: AnalysisCard): boolean {
  return ["ANALYSIS_PICK", "WATCH"].includes(decision(card));
}

function marketList(card: AnalysisCard): Record<string, unknown>[] {
  const rows = asArray(card.markets).map(asRecord);
  return MARKET_ORDER.map((code) => rows.find((row) => row.market === code) ?? { market: code, decision: "SKIP" });
}

function translateReason(reason: unknown): string {
  const raw = textValue(reason, "数据不足时保持 SKIP。");
  for (const [pattern, translated] of REASON_TRANSLATIONS) {
    if (pattern.test(raw)) {
      return translated;
    }
  }
  return raw.replace(/_/g, " ").replace(/:/g, "：");
}

function translateCompetition(value: unknown): string {
  let text = textValue(value, "世界杯");
  for (const [pattern, translated] of COMPETITION_TRANSLATIONS) {
    text = text.replace(pattern, translated);
  }
  return text;
}

function readableReasons(value: unknown, fallback?: unknown): string[] {
  const rows = asArray(value).length ? asArray(value) : asArray(fallback);
  const translated = rows.map(translateReason).filter(Boolean);
  return Array.from(new Set(translated)).slice(0, 3);
}

function readinessItems(card: AnalysisCard): ReadinessItem[] {
  const readiness = asRecord(card.data_readiness);
  const bookmakers = numberValue(readiness.bookmakers);
  const snapshots = numberValue(readiness.odds_snapshots);
  return [
    {
      key: "odds",
      label: "盘口快照",
      value: bookmakers > 0 ? `${bookmakers} 家 / ${snapshots} 次` : snapshots > 0 ? `${snapshots} 次` : "等待采集",
      ready: bookmakers > 0 || snapshots > 0,
    },
    { key: "xg", label: "滚动 xG", value: booleanValue(readiness.xg) ? "已就绪" : "富集中", ready: booleanValue(readiness.xg) },
    { key: "h2h", label: "历史交锋", value: booleanValue(readiness.h2h) ? "已覆盖" : "不可用", ready: booleanValue(readiness.h2h) },
    { key: "lineups", label: "首发伤停", value: booleanValue(readiness.lineups) ? "已覆盖" : "未公布", ready: booleanValue(readiness.lineups) },
  ];
}

function readinessScore(card: AnalysisCard): number {
  const items = readinessItems(card);
  return items.filter((item) => item.ready).length;
}

function readinessLabel(card: AnalysisCard): string {
  const score = readinessScore(card);
  if (score >= 3) return "数据较完整";
  if (score >= 1) return "数据补齐中";
  return "数据不足";
}

function topMarket(card: AnalysisCard): Record<string, unknown> | null {
  return marketList(card).find((market) => textValue(market.decision) === "PICK") ?? null;
}

function leanLabel(market: Record<string, unknown>): string {
  return textValue(market.lean_cn ?? market.lean ?? TENDENCY_LABELS[textValue(market.tendency)] ?? market.tendency, "等待判断");
}

function confidenceLabel(value: unknown): string {
  const percent = Math.round(numberValue(value) * 100);
  if (percent <= 0) return "未成形";
  return `${percent}%`;
}

function watchLevel(card: AnalysisCard): number {
  return Math.max(0, Math.min(4, Math.round(numberValue(card.watch_level))));
}

function risks(card: AnalysisCard): string[] {
  const rows = asArray(card.risks_cn).length ? asArray(card.risks_cn) : asArray(card.risks);
  return rows.map((row) => textValue(row)).filter(Boolean).slice(0, 4);
}

function intent(card: AnalysisCard): Record<string, unknown> {
  return asRecord(card.bookmaker_intent);
}

function intentLabel(card: AnalysisCard): string {
  const payload = intent(card);
  const code = textValue(payload.intent, "INSUFFICIENT_DATA");
  return textValue(payload.label_cn, INTENT_LABELS[code] ?? code);
}

function lineMovement(card: AnalysisCard): string {
  const payload = intent(card);
  const movement = asRecord(card.line_movement);
  const open = textValue(payload.opening_line) || textValue(movement.ah_open);
  const current = textValue(payload.current_line) || textValue(movement.ah_current);
  if (open && current) {
    return `${open} → ${current}`;
  }
  return "等待初盘与当前盘";
}

function currentOdds(card: AnalysisCard): string[] {
  const odds = asRecord(card.current_odds);
  const ah = asRecord(odds.ah);
  const ou = asRecord(odds.ou);
  const rows: string[] = [];
  if (Object.keys(ah).length) {
    rows.push(`让球 ${textValue(ah.line, "-")} @${textValue(ah.price, "-")}`);
  }
  if (Object.keys(ou).length) {
    rows.push(`大小 ${textValue(ou.line, "-")} @${textValue(ou.price, "-")}`);
  }
  return rows;
}

function scoreRows(market: Record<string, unknown>): Array<{ scoreline: string; probability: string }> {
  const references = asArray(market.reference_scores);
  if (references.length) {
    return references
      .map((row) => {
        const record = asRecord(row);
        const probability = numberValue(record.conditional_probability ?? record.probability, NaN);
        return {
          scoreline: textValue(record.scoreline),
          probability: Number.isFinite(probability) ? `${Math.round(probability * 100)}%` : "",
        };
      })
      .filter((row) => row.scoreline)
      .slice(0, 3);
  }
  return asArray(market.scores)
    .map((row) => ({ scoreline: textValue(row), probability: "" }))
    .filter((row) => row.scoreline)
    .slice(0, 3);
}

function Dots({ value }: { value: unknown }) {
  const n = Math.max(0, Math.min(5, Math.round(numberValue(value) * 5)));
  return (
    <span className="confidence-dots" aria-label={`信心 ${n}/5`}>
      {[0, 1, 2, 3, 4].map((index) => (
        <span className={index < n ? "dot filled" : "dot"} key={index} />
      ))}
    </span>
  );
}

function SkeletonCard() {
  return (
    <article className="match-card skeleton-card">
      <div className="skeleton-line w30" />
      <div className="skeleton-line w60" />
      <div className="skeleton-grid">
        <div />
        <div />
        <div />
        <div />
      </div>
    </article>
  );
}

function SummaryMetric({ label, value, sub }: { label: string; value: string | number; sub: string }) {
  return (
    <div className="summary-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function ReadinessStrip({ card }: { card: AnalysisCard }) {
  return (
    <div className="readiness-strip">
      {readinessItems(card).map((item) => (
        <div className={item.ready ? "ready-item ready" : "ready-item"} key={item.key}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}

function MarketPanel({ market }: { market: Record<string, unknown> }) {
  const code = textValue(market.market, "UNKNOWN");
  const meta = MARKET_META[code] ?? { label: code, short: code, tone: "tone-neutral" };
  const pick = textValue(market.decision, "SKIP") === "PICK";
  const reasons = readableReasons(market.reasons, market.reason ?? market.reason_cn);
  const scores = scoreRows(market);

  return (
    <section className={pick ? "market-panel" : "market-panel market-skip"}>
      <div className="market-panel-head">
        <div>
          <span className="market-short">{meta.short}</span>
          <h3>{meta.label}</h3>
        </div>
        {pick ? <span className={`lean-badge ${meta.tone}`}>{leanLabel(market)}</span> : <span className="skip-chip">SKIP</span>}
      </div>

      {pick ? (
        <>
          <div className="confidence-row">
            <Dots value={market.confidence} />
            <span>{confidenceLabel(market.confidence)}</span>
          </div>
          {code === "SCORE" && scores.length ? (
            <div className="score-row">
              {scores.map((score) => (
                <span className="score-chip" key={`${score.scoreline}-${score.probability}`}>
                  {score.scoreline}
                  {score.probability ? <small>{score.probability}</small> : null}
                </span>
              ))}
            </div>
          ) : null}
          <p>{reasons.length ? reasons.join(" ") : "多因素信号已形成，但仍仅作分析参考。"}</p>
        </>
      ) : (
        <p>{reasons.length ? reasons.join(" ") : "数据不足，暂不输出该市场倾向。"}</p>
      )}

      {code === "SCORE" && pick ? <small className="score-note">方向一致的条件概率，不是精确比分预测。</small> : null}
    </section>
  );
}

function MatchCard({ card }: { card: AnalysisCard }) {
  const pick = isPick(card);
  const primary = topMarket(card);
  const watch = watchLevel(card);
  const loading = Boolean(card.loading);
  const home = textValue(card.home_name ?? card.home_cn, "主队");
  const away = textValue(card.away_name ?? card.away_cn, "客队");
  const competition = translateCompetition(card.competition_cn ?? card.competition_name);
  const riskRows = risks(card);
  const oddsRows = currentOdds(card);

  return (
    <article className={pick ? "match-card pick" : "match-card"}>
      <header className="match-header">
        <div>
          <span className={pick ? "status-pill pick" : "status-pill"}>{loading ? "生成中" : pick ? "有分析" : readinessLabel(card)}</span>
          <h2>
            {home} <span>vs</span> {away}
          </h2>
        </div>
        <div className="kickoff">
          <strong>{fmtTime(card.kickoff_utc)}</strong>
          <span>{competition}</span>
        </div>
      </header>

      <section className="decision-band">
        <div>
          <span>本场结论</span>
          <strong>{pick && primary ? `${MARKET_META[textValue(primary.market)]?.short ?? "市场"}：${leanLabel(primary)}` : "暂不强出分析倾向"}</strong>
        </div>
        <div>
          <span>关注度</span>
          <strong className="watch-dots">{"●".repeat(watch)}{"○".repeat(4 - watch)}</strong>
        </div>
        <div>
          <span>数据完整度</span>
          <strong>{readinessScore(card)}/4</strong>
        </div>
      </section>

      <ReadinessStrip card={card} />

      <section className="intent-card">
        <div>
          <span>庄家意图</span>
          <strong>{intentLabel(card)}</strong>
        </div>
        <div>
          <span>盘口演变</span>
          <strong>{lineMovement(card)}</strong>
        </div>
        {oddsRows.length ? (
          <div>
            <span>当前盘口</span>
            <strong>{oddsRows.join(" · ")}</strong>
          </div>
        ) : null}
      </section>

      <div className="market-grid">
        {marketList(card).map((market) => (
          <MarketPanel key={textValue(market.market)} market={market} />
        ))}
      </div>

      <details className="risk-details" open={pick}>
        <summary>原因与风险</summary>
        <div>
          <p>
            {pick
              ? "分析倾向来自盘口变化、庄家分歧、球队状态、xG/阵容等可用因子；缺失因子不会被补写。"
              : loading
                ? "分析卡正在生成，先展示白名单赛程。"
                : "数据还没有达到出卡阈值，系统保持 SKIP。"}
          </p>
          <ul>
            {(riskRows.length ? riskRows : ["阵容、伤停和临场盘口变化可能改变判断。"]).map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
        </div>
      </details>
    </article>
  );
}

function FilterButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button className={active ? "filter-button active" : "filter-button"} onClick={onClick} type="button">
      {children}
    </button>
  );
}

function Dashboard() {
  const [cards, setCards] = useState<AnalysisCard[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [filter, setFilter] = useState<FilterMode>("ALL");
  const [updatedAt, setUpdatedAt] = useState<string>("--");
  const date = todayShanghai();

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setState("loading");
        const list = await getJSON(`${API_BASE}/fixtures?competition_id=${COMPETITION_ID}&page_size=80&status=NS&timezone=Asia/Shanghai&operational_date=${date}`);
        const fixtures = asArray(list).filter((fixture) => isFixtureOnDate(fixture, date));
        const ids = fixtures.map(fxId).filter(Boolean);
        if (!ids.length) {
          if (!cancelled) setState("empty");
          return;
        }
        if (!cancelled) {
          setCards(normalizeCards(fixtures));
          setState("ok");
          setUpdatedAt(new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date()));
        }
        ids.forEach((id, index) => {
          getJSON(`${API_BASE}/fixtures/${id}/analysis-card`, 60000)
            .then((payload) => {
              if (cancelled) return;
              const nextCard = cardPayload(payload);
              setCards((current) => current.map((card, cardIndex) => (cardIndex === index ? nextCard : card)));
              setUpdatedAt(new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date()));
            })
            .catch(() => {
              if (cancelled) return;
              setCards((current) =>
                current.map((card, cardIndex) =>
                  cardIndex === index
                    ? {
                        ...card,
                        loading: false,
                        bookmaker_intent: { intent: "INSUFFICIENT_DATA", label_cn: "数据暂不可用" },
                        risks_cn: ["分析卡暂不可用，保持 SKIP。"],
                      }
                    : card,
                ),
              );
            });
        });
      } catch {
        if (!cancelled) setState("error");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [date]);

  const stats = useMemo(() => {
    const picks = cards.filter(isPick).length;
    const skips = cards.filter((card) => !isPick(card)).length;
    const readiness = cards.length ? Math.round((cards.reduce((sum, card) => sum + readinessScore(card), 0) / (cards.length * 4)) * 100) : 0;
    return { total: cards.length, picks, skips, readiness };
  }, [cards]);

  const visibleCards = useMemo(() => {
    if (filter === "PICK") return cards.filter(isPick);
    if (filter === "SKIP") return cards.filter((card) => !isPick(card));
    return cards;
  }, [cards, filter]);

  return (
    <main className="product-shell">
      <header className="hero-bar">
        <div>
          <p>W2 足球分析</p>
          <h1>W2 足球分析 · 今日比赛</h1>
          <span>只显示白名单赛事。分析参考 · 非稳赢，数据不足时一律 SKIP。</span>
        </div>
        <strong>分析参考 · 非稳赢</strong>
      </header>

      <section className="summary-bar">
        <SummaryMetric label="今日比赛" value={stats.total} sub={date} />
        <SummaryMetric label="有分析" value={stats.picks} sub="四市场择优展示" />
        <SummaryMetric label="数据不足" value={stats.skips} sub="保持 SKIP" />
        <SummaryMetric label="数据完整度" value={`${stats.readiness}%`} sub={`更新 ${updatedAt}`} />
      </section>

      <nav className="toolbar" aria-label="分析卡筛选">
        <div>
          <FilterButton active={filter === "ALL"} onClick={() => setFilter("ALL")}>全部</FilterButton>
          <FilterButton active={filter === "PICK"} onClick={() => setFilter("PICK")}>有分析</FilterButton>
          <FilterButton active={filter === "SKIP"} onClick={() => setFilter("SKIP")}>数据不足</FilterButton>
        </div>
        <span>世界杯 · 北京时间 · {date}</span>
      </nav>

      {state === "loading" ? (
        <div className="card-list">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : null}
      {state === "error" ? <div className="empty-state">加载失败。请确认 API 反代正常后刷新页面。</div> : null}
      {state === "empty" ? <div className="empty-state">今日暂无白名单比赛或数据还未进入 read-model。</div> : null}
      {state === "ok" ? (
        <section className="card-list">
          {visibleCards.length ? visibleCards.map((card) => <MatchCard key={textValue(card.fixture_id) || JSON.stringify(card)} card={card} />) : <div className="empty-state">当前筛选下没有比赛。</div>}
        </section>
      ) : null}

      <footer className="product-disclaimer">本页为分析参考，非投注建议，不承诺盈利 · 数据不足时一律 SKIP，不强出推荐</footer>
    </main>
  );
}

const el = document.getElementById("root");
if (el) {
  createRoot(el).render(<Dashboard />);
}
