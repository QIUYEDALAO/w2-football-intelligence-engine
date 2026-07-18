import { INTENT_LABELS, MARKET_META, MARKET_ORDER, TENDENCY_LABELS } from "./labels";
import { formatLine, formatOdds, teamCode, translateCompetition, translateReason } from "./formatters";
import { formatAhMainLine, formatAhSideLines } from "./pricingDisplay";
import type {
  BookmakerIntentPayload,
  DashboardCard,
  DashboardStats,
  MarketAnalysis,
  MarketCode,
  ReadinessItem,
  ScoreReference,
} from "../types/dashboard";

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function asArray(value: unknown): unknown[] {
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

export function textValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return fallback;
}

export function numberValue(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

export function booleanValue(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value > 0;
  }
  if (typeof value === "string") {
    return ["true", "ready", "available", "yes", "1"].includes(value.toLowerCase());
  }
  return false;
}

export function cardPayload(payload: unknown): DashboardCard {
  const record = asRecord(payload);
  return asRecord(record.card ?? payload) as DashboardCard;
}

export function fixtureId(item: unknown): string {
  const record = asRecord(item);
  const fixture = asRecord(record.fixture);
  return textValue(record.fixture_id ?? record.id ?? fixture.id);
}

export function isFixtureOnDate(fixture: unknown, selectedDate: string): boolean {
  const record = asRecord(fixture);
  const operationalDate = textValue(record.operational_date_beijing);
  if (operationalDate) {
    return operationalDate === selectedDate;
  }
  return textValue(record.kickoff_beijing).startsWith(selectedDate);
}

export function fixtureTeamName(fixture: unknown, side: "home" | "away"): string {
  const record = asRecord(fixture);
  const teams = asRecord(record.teams);
  const team = asRecord(teams[side]);
  return textValue(
    record[`${side}_team_name`] ?? record[`${side}_name`] ?? record[`${side}_cn`] ?? team.name,
    side === "home" ? "主队" : "客队",
  );
}

export function fixtureCompetition(fixture: unknown): string {
  const record = asRecord(fixture);
  const league = asRecord(record.league);
  const base = textValue(record.competition_name ?? record.competition_cn ?? league.name, "世界杯");
  const round = textValue(league.round);
  return translateCompetition(round && !base.includes(round) ? `${base} · ${round}` : base);
}

export function fixtureKickoff(fixture: unknown): string {
  const record = asRecord(fixture);
  const nested = asRecord(record.fixture);
  return textValue(record.kickoff_utc ?? nested.date);
}

export function fallbackCardFromFixture(fixture: unknown): DashboardCard {
  return {
    fixture_id: fixtureId(fixture),
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

export function normalizeCards(fixtures: unknown[]): DashboardCard[] {
  return fixtures.map(fallbackCardFromFixture);
}

export function marketList(card: DashboardCard): MarketAnalysis[] {
  const rows = asArray(card.markets).map((row) => asRecord(row) as MarketAnalysis);
  return MARKET_ORDER.map((code) => rows.find((row) => row.market === code) ?? { market: code, decision: "SKIP" });
}

export function topMarket(card: DashboardCard): MarketAnalysis | null {
  return marketList(card).find((market) => isMarketPick(market)) ?? null;
}

export function preferredMarket(card: DashboardCard): MarketAnalysis {
  return topMarket(card) ?? marketList(card).find((market) => market.market === "TOTALS") ?? marketList(card)[0];
}

export function isMarketCode(value: unknown): value is MarketCode {
  return MARKET_ORDER.includes(value as MarketCode);
}

export function marketLabel(market: MarketAnalysis): string {
  const code = market.market;
  return isMarketCode(code) ? MARKET_META[code].label : textValue(code, "市场");
}

export function marketShort(market: MarketAnalysis): string {
  const code = market.market;
  return isMarketCode(code) ? MARKET_META[code].short : textValue(code, "市场");
}

export function marketClass(market: MarketAnalysis): string {
  const code = market.market;
  return isMarketCode(code) ? MARKET_META[code].className : "market-neutral";
}

export function isMarketPick(market: MarketAnalysis): boolean {
  return textValue(market.decision) === "PICK" || textValue(market.analysis_decision) === "ANALYSIS_PICK";
}

export function cardStatus(card: DashboardCard): "pick" | "watch" | "skip" | "loading" {
  if (card.loading) {
    return "loading";
  }
  const decision = textValue(card.decision, "SKIP");
  if (decision === "ANALYSIS_PICK" || decision === "PICK" || topMarket(card)) {
    return "pick";
  }
  if (decision === "WATCH") {
    return "watch";
  }
  return "skip";
}

export function isPick(card: DashboardCard): boolean {
  return cardStatus(card) === "pick";
}

export function isWatch(card: DashboardCard): boolean {
  return cardStatus(card) === "watch";
}

export function readinessItems(card: DashboardCard): ReadinessItem[] {
  const readiness = asRecord(card.data_readiness);
  const bookmakers = numberValue(readiness.bookmakers);
  const snapshots = numberValue(readiness.odds_snapshots);
  const oddsReady = bookmakers > 0 || snapshots > 0;
  const xgReady = booleanValue(readiness.xg);
  const xgStatus = textValue(readiness.xg_status);
  const h2hReady = booleanValue(readiness.h2h);
  const lineupsReady = booleanValue(readiness.lineups);
  const xgLabel = (() => {
    if (xgReady) return "已就绪";
    if (xgStatus === "PARTIAL_HISTORY") return "部分覆盖";
    if (xgStatus === "INSUFFICIENT_HISTORY") return "历史不足";
    if (xgStatus === "PROVIDER_EMPTY_OR_UNAVAILABLE") return "源无返回";
    if (xgStatus === "NOT_REQUESTED") return "未请求";
    return "富集中";
  })();
  return [
    {
      key: "odds",
      label: "盘口",
      value: oddsReady ? `${bookmakers || "盘口"}家${snapshots ? ` / ${snapshots}次` : ""}` : "等待采集",
      short: oddsReady ? `盘口 ${bookmakers || snapshots}家` : "盘口等待",
      ready: oddsReady,
    },
    { key: "xg", label: "xG", value: xgLabel, short: `xG ${xgLabel}`, ready: xgReady },
    { key: "h2h", label: "交锋", value: h2hReady ? "已覆盖" : "无交锋", short: h2hReady ? "交锋已覆盖" : "无交锋", ready: h2hReady },
    { key: "lineups", label: "首发", value: lineupsReady ? "已覆盖" : "未出", short: lineupsReady ? "首发已出" : "首发未出", ready: lineupsReady },
  ];
}

export function readinessScore(card: DashboardCard): number {
  return readinessItems(card).filter((item) => item.ready).length;
}

export function readinessLabel(card: DashboardCard): string {
  const status = cardStatus(card);
  if (status === "loading") {
    return "生成中";
  }
  if (status === "pick") {
    return "有分析";
  }
  if (status === "watch") {
    return "观察";
  }
  const score = readinessScore(card);
  if (score >= 3) {
    return "数据较完整";
  }
  if (score >= 1) {
    return "数据补齐中";
  }
  return "数据不足";
}

export function risks(card: DashboardCard): string[] {
  const rows = asArray(card.risks_cn).length ? asArray(card.risks_cn) : asArray(card.risks);
  return rows.map((row) => textValue(row)).filter(Boolean).slice(0, 2);
}

export function currentOdds(
  card: DashboardCard,
  options: { directionalTotals?: boolean; canonicalAhLine?: unknown } = {},
): string[] {
  const directionalTotals = options.directionalTotals ?? true;
  const canonicalAhLine = options.canonicalAhLine;
  const odds = asRecord(card.current_odds);
  const ah = asRecord(odds.ah);
  const ou = asRecord(odds.ou);
  const rows: string[] = [];
  if (Object.keys(ah).length) {
    const hasHomePrice = textValue(ah.home_price) !== "";
    const hasAwayPrice = textValue(ah.away_price) !== "";
    const homePrice = formatOdds(ah.home_price);
    const awayPrice = formatOdds(ah.away_price);
    if (hasHomePrice || hasAwayPrice) {
      const sideLines = formatAhSideLines(canonicalAhLine ?? ah.line ?? ah.home_line);
      if (sideLines) {
        rows.push(`让球 ${sideLines.home} @${homePrice || "-"} / ${sideLines.away} @${awayPrice || "-"}`);
      } else {
        const homeLine = formatLine(ah.home_line ?? ah.line);
        const awayLine = formatLine(ah.away_line ?? ah.line);
        rows.push(`让球 主 ${homeLine} @${homePrice || "-"} / 客 ${awayLine} @${awayPrice || "-"}`);
      }
    } else {
      const line = canonicalAhLine ?? ah.line;
      rows.push(`让球 ${formatAhMainLine(line) ?? formatLine(line)} @${formatOdds(ah.price)}`);
    }
  }
  if (Object.keys(ou).length) {
    const hasOverPrice = textValue(ou.over_price) !== "";
    const hasUnderPrice = textValue(ou.under_price) !== "";
    const overPrice = formatOdds(ou.over_price);
    const underPrice = formatOdds(ou.under_price);
    if (hasOverPrice || hasUnderPrice) {
      const line = formatLine(ou.line);
      if (directionalTotals) {
        rows.push(`大小球 大${line} @${overPrice || "-"} / 小${line} @${underPrice || "-"}`);
      } else {
        rows.push(`大小球 ${line} 两侧 @${overPrice || "-"} / @${underPrice || "-"}`);
      }
    } else {
      rows.push(`大小球 ${formatLine(ou.line)} @${formatOdds(ou.price)}`);
    }
  }
  return rows;
}

export function lineMovement(card: DashboardCard): string {
  const payload = bookmakerIntent(card);
  const movement = asRecord(card.line_movement);
  const open = textValue(payload.opening_line) || textValue(movement.ah_open);
  const current = textValue(payload.current_line) || textValue(movement.ah_current);
  if (open && current) {
    return `${open} → ${current}`;
  }
  return "等待初盘与当前盘";
}

export function bookmakerIntent(card: DashboardCard): BookmakerIntentPayload {
  return asRecord(card.bookmaker_intent) as BookmakerIntentPayload;
}

export function intentLabel(card: DashboardCard): string {
  const payload = bookmakerIntent(card);
  const code = textValue(payload.intent, "INSUFFICIENT_DATA");
  return textValue(payload.label_cn, INTENT_LABELS[code] ?? code);
}

export function watchLevel(card: DashboardCard): number {
  return Math.max(0, Math.min(5, Math.round(numberValue(card.watch_level))));
}

export function confidenceDots(value: unknown): number {
  const raw = numberValue(value);
  const normalized = raw > 1 ? raw / 100 : raw;
  return Math.max(0, Math.min(5, Math.round(normalized * 5)));
}

export function signalStrengthLabel(value: unknown): string {
  const count = confidenceDots(value);
  const label = count >= 4 ? "强" : count >= 2 ? "中" : count === 1 ? "弱" : "暂无";
  return `${label}（${count}/5）`;
}

export function leanLabel(market: MarketAnalysis): string {
  const tendency = textValue(market.tendency);
  return textValue(market.lean_cn ?? market.lean ?? TENDENCY_LABELS[tendency] ?? tendency, "等待判断");
}

export function readableReasons(value: unknown, fallback?: unknown): string[] {
  const rows = asArray(value).length ? asArray(value) : asArray(fallback);
  const translated = rows.map(translateReason).filter(Boolean);
  return Array.from(new Set(translated)).slice(0, 2);
}

export function scoreRows(market: MarketAnalysis): ScoreReference[] {
  const references = asArray(market.reference_scores);
  if (references.length) {
    return references
      .map((row) => {
        const record = asRecord(row);
        const probability = numberValue(record.conditional_probability ?? record.probability, Number.NaN);
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

export function homeName(card: DashboardCard): string {
  return textValue(card.home_name ?? card.home_cn ?? card.home_team_name, "主队");
}

export function awayName(card: DashboardCard): string {
  return textValue(card.away_name ?? card.away_cn ?? card.away_team_name, "客队");
}

export function teamBadgeLabel(name: string): string {
  return teamCode(name);
}

export function competitionName(card: DashboardCard): string {
  return translateCompetition(card.competition_cn ?? card.competition_name);
}

export function computeStats(cards: DashboardCard[]): DashboardStats {
  const picks = cards.filter(isPick).length;
  const watch = cards.filter(isWatch).length;
  const ready = cards.filter((card) => readinessScore(card) >= 3).length;
  const highWatch = cards.filter((card) => watchLevel(card) >= 3).length;
  return {
    total: cards.length,
    picks,
    watch,
    skips: cards.length - picks - watch,
    ready,
    highWatch,
  };
}
