import { useMemo, useState } from "react";
import {
  fmtTime,
  formatLine,
  formatOdds,
  translateCompetition,
  translateTeam,
} from "../lib/formatters";
import { asRecord, textValue } from "../lib/normalize";
import type {
  DashboardDayView,
  DashboardDayViewCard,
  DashboardMatchCard,
  DashboardPerformance,
  ReleaseSyncState,
} from "../types/dashboard";
import { RecommendationCard } from "./RecommendationCard";

const TIER_LABELS: Record<string, string> = {
  RECOMMEND: "正式可锁",
  ANALYSIS_PICK: "分析参考",
  WATCH: "观察",
  NOT_READY: "未就绪",
  SKIP: "跳过",
};

const DATA_STATUS_LABELS: Record<string, string> = {
  READY: "数据齐",
  PARTIAL: "部分就绪",
  STALE: "缺少最新数据",
  BLOCKED: "数据阻塞",
};

const REASON_LABELS: Record<string, string> = {
  LINEUPS_PENDING: "首发未出",
  MARKET_UNAVAILABLE: "盘口未齐",
  ODDS_UNAVAILABLE: "赔率未返回",
  DATA_STALE_ODDS: "赔率过期",
  PROVIDER_BUDGET_EXHAUSTED: "provider 预算耗尽",
  MARKET_INCOMPLETE: "盘口不完整",
  XG_PENDING: "xG 待刷新",
  CONTRACT_BLOCKED_BY_DATA_STATUS: "数据状态阻塞",
  EDGE_INSUFFICIENT: "优势不足",
  NO_SUPPORTED_MARKET: "无可支持市场",
  FIXTURE_NOT_UPCOMING: "非赛前窗口",
  LINEUP_SNAPSHOT_INCOMPLETE: "正式首发尚未完整",
  LINEUP_NOT_CONFIRMED: "正式首发尚未确认",
  STARTING_XI_INCOMPLETE: "双方首发不足 11 人",
  PLAYER_IDENTITY_INCOMPLETE: "首发球员身份尚未匹配完整",
  VALUATION_INCOMPLETE: "首发球员身价覆盖不足",
  FORMATION_INCOMPLETE: "阵型数据尚未完整",
  QUOTE_NOT_COMPLETE_OR_FRESH: "临场赔率尚未齐全或已过期",
};

const ACTION_LABELS: Record<string, string> = {
  WAIT_LINEUPS: "等首发",
  WAIT_MARKET: "等盘口",
  WAIT_ODDS: "等赔率",
  WAIT_NEXT_REFRESH: "等下一次刷新",
  REVIEW_DATA_PIPELINE: "检查数据链路",
  KEEP_WATCHING: "继续观察",
};

const MARKET_ANCHOR_DISPLAY_ENABLED =
  import.meta.env.VITE_W2_MARKET_ANCHOR_DISPLAY_ENABLED === "true";
const MARKET_ANCHOR_MIN_DIVERGENCE = Number(
  import.meta.env.VITE_W2_MARKET_ANCHOR_MIN_DIVERGENCE ?? 0.05,
);

type ScheduleFilter = "all" | "recommended" | "hide-not-ready";

interface LeaguePerformanceRow {
  key: string;
  label: string;
  sampleSize: number;
  hitCount: number;
  missCount: number;
  pushCount: number;
  voidCount: number;
  roiUnits: number;
}

function tierLabel(value: string): string {
  return TIER_LABELS[value] ?? "未判定";
}

function dataStatusLabel(value: string): string {
  return DATA_STATUS_LABELS[value] ?? "数据待确认";
}

function reasonLabel(value?: string | null): string {
  if (!value) return "暂无阻塞原因";
  return REASON_LABELS[value] ?? "未就绪原因";
}

function effectiveReasonCode(card: DashboardDayViewCard): string | null {
  return (
    card.reason_code ?? (textValue(asRecord(card.non_pick).reason_code) || null)
  );
}

function actionLabel(value?: string | null): string {
  if (!value) return "等待下一次刷新";
  return ACTION_LABELS[value] ?? "继续观察";
}

function isWaitingForScheduledRefresh(
  card: DashboardDayViewCard,
  now = new Date(),
): boolean {
  if (!(card.data_status === "STALE" || card.data_status === "BLOCKED"))
    return false;
  const reasonCode = effectiveReasonCode(card);
  if (
    !(reasonCode === "DATA_STALE_ODDS" || reasonCode === "MARKET_UNAVAILABLE")
  )
    return false;
  const next = card.next_eval_at ? new Date(card.next_eval_at) : null;
  const kickoff = card.kickoff_utc ? new Date(card.kickoff_utc) : null;
  return Boolean(
    next &&
    kickoff &&
    !Number.isNaN(next.getTime()) &&
    !Number.isNaN(kickoff.getTime()) &&
    next.getTime() > now.getTime() &&
    next.getTime() < kickoff.getTime(),
  );
}

function lastKnownOdds(card: DashboardDayViewCard): Record<string, unknown> {
  return asRecord(card.last_known_odds);
}

function hasLastKnownOdds(card: DashboardDayViewCard): boolean {
  return Object.keys(asRecord(lastKnownOdds(card).markets)).length > 0;
}

function lastKnownCapturedLabel(card: DashboardDayViewCard): string {
  const capturedAt = textValue(lastKnownOdds(card).captured_at);
  if (!capturedAt) return "较早快照";
  const parsed = new Date(capturedAt);
  if (Number.isNaN(parsed.getTime())) return "较早快照";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed);
}

function nextRefreshLabel(card: DashboardDayViewCard): string {
  return card.next_eval_at ? fmtTime(card.next_eval_at) : "下一次计划采集";
}

function staleOddsExplanation(card: DashboardDayViewCard): string {
  const existing = hasLastKnownOdds(card)
    ? `当前只有 ${lastKnownCapturedLabel(card)} 的早盘`
    : "当前没有可执行赔率";
  return `缺少开赛前 30 分钟内的最新赔率；${existing}，${nextRefreshLabel(card)} 刷新后重新判断是否形成推荐`;
}

function visibleDataStatusLabel(
  card: DashboardDayViewCard,
  now = new Date(),
): string {
  if (effectiveReasonCode(card) === "DATA_STALE_ODDS") {
    return `缺临场赔率·${nextRefreshLabel(card)}更新`;
  }
  if (isWaitingForScheduledRefresh(card, now)) {
    return hasLastKnownOdds(card) ? "已有早盘·待临场更新" : "等待首轮盘口";
  }
  return dataStatusLabel(card.data_status);
}

function visibleReasonLabel(
  card: DashboardDayViewCard,
  now = new Date(),
): string {
  if (effectiveReasonCode(card) === "DATA_STALE_ODDS")
    return "缺少开赛前 30 分钟内的最新赔率";
  if (isWaitingForScheduledRefresh(card, now)) {
    return hasLastKnownOdds(card)
      ? "已有早盘，待临场更新"
      : "尚无盘口，等待首轮采集";
  }
  const lineup = asRecord(card.lineup_provenance);
  const blockers = Array.isArray(lineup.blockers) ? lineup.blockers : [];
  const lineupReason = blockers
    .map((value) => REASON_LABELS[String(value)])
    .find(Boolean);
  return lineupReason ?? reasonLabel(effectiveReasonCode(card));
}

function isWorldCup(dayView: DashboardDayView): boolean {
  return dayView.cards.some(
    (card) =>
      card.competition_id === "world_cup_2026" ||
      (card.competition_name ?? "").toLowerCase().includes("world cup"),
  );
}

function l1OneLiner(card: DashboardDayViewCard): string {
  if (effectiveReasonCode(card) === "DATA_STALE_ODDS")
    return `${staleOddsExplanation(card)}。`;
  if (isWaitingForScheduledRefresh(card)) {
    if (hasLastKnownOdds(card)) {
      return `已有 ${lastKnownCapturedLabel(card)} 早盘；仅供参考，${card.next_eval_at ? fmtTime(card.next_eval_at) : "下一时点"}更新临场盘口。`;
    }
    return `目前尚无盘口；${card.next_eval_at ? fmtTime(card.next_eval_at) : "下一时点"}执行首轮采集。`;
  }
  const oneLiner = (card.one_liner ?? "").trim();
  if (
    oneLiner &&
    !oneLiner.includes("缺少人话解释") &&
    !/[A-Z0-9_]{6,}/.test(oneLiner)
  ) {
    return oneLiner;
  }
  if (card.decision_tier === "ANALYSIS_PICK" && card.pick) {
    return `${tierLabel(card.decision_tier)}：${marketPickLabel(card)}；分析参考·非稳赢。`;
  }
  return `${reasonLabel(effectiveReasonCode(card))}，${actionLabel(card.action)}。`;
}

function scorelineSimulationSummary(card: DashboardDayViewCard): string {
  if (
    !card.pick ||
    !["ANALYSIS_PICK", "RECOMMEND"].includes(card.decision_tier)
  ) {
    if (effectiveReasonCode(card) === "DATA_STALE_ODDS") {
      return `暂无推荐比分：缺临场赔率，${nextRefreshLabel(card)}刷新后再判断`;
    }
    return "尚未形成推荐盘口，暂无推荐比分";
  }
  const scores = card.scoreline_reference?.direction_top3?.slice(0, 3) ?? [];
  if (card.scoreline_readiness?.status === "READY" && scores.length > 0) {
    return `推荐比分：${scores.map((pick) => pick.scoreline).join(" · ")}`;
  }
  return "已有推荐盘口，推荐比分暂不可用";
}

function oddsSummary(card: DashboardDayViewCard): string | null {
  return oddsPayloadSummary(asRecord(card.current_odds));
}

function lastKnownOddsSummary(card: DashboardDayViewCard): string | null {
  return oddsPayloadSummary(asRecord(lastKnownOdds(card).markets));
}

function oddsPayloadSummary(odds: Record<string, unknown>): string | null {
  const ah = asRecord(odds.ah);
  const ou = asRecord(odds.ou);
  const rows: string[] = [];
  if (Object.keys(ah).length) {
    const homeLine =
      textValue(ah.home_display_line_cn) || signedLine("主", ah.home_line);
    const awayLine =
      textValue(ah.away_display_line_cn) || signedLine("客", ah.away_line);
    const homePrice = formatOdds(ah.home_price);
    const awayPrice = formatOdds(ah.away_price);
    rows.push(`让球 ${homeLine} @${homePrice} / ${awayLine} @${awayPrice}`);
  }
  if (Object.keys(ou).length) {
    const line =
      textValue(ou.line) || textValue(ou.over_line) || textValue(ou.under_line);
    const overPrice = formatOdds(ou.over_price);
    const underPrice = formatOdds(ou.under_price);
    rows.push(`大小 ${formatLine(line)} 大@${overPrice} / 小@${underPrice}`);
  }
  return rows.length ? rows.join(" · ") : null;
}

function marketProbabilitySummary(card: DashboardDayViewCard): string | null {
  const preferredMarkets = probabilityMarketOrder(card);
  const markets = asRecord(card.market_probabilities);
  for (const market of preferredMarkets) {
    const summary = probabilitySummaryForMarket(card, markets, market);
    if (summary) return summary;
  }
  return null;
}

function probabilityMarketOrder(card: DashboardDayViewCard): string[] {
  const pickMarket = card.pick?.market;
  if (pickMarket === "TOTALS") return ["ou", "ah", "one_x_two"];
  if (pickMarket === "ASIAN_HANDICAP") return ["ah", "ou", "one_x_two"];
  if (pickMarket === "ONE_X_TWO") return ["one_x_two", "ah", "ou"];
  return ["ah", "ou", "one_x_two"];
}

function probabilitySummaryForMarket(
  card: DashboardDayViewCard,
  markets: Record<string, unknown>,
  market: string,
): string | null {
  if (market === "ah") {
    return ahProbabilitySummary(card, markets);
  }
  if (market === "ou") {
    return ouProbabilitySummary(markets);
  }
  if (market === "one_x_two") {
    return oneXTwoProbabilitySummary(markets);
  }
  return null;
}

function ahProbabilitySummary(
  card: DashboardDayViewCard,
  markets: Record<string, unknown>,
): string | null {
  const ah = asRecord(markets.ah);
  const ahProbabilities = asRecord(ah.probabilities);
  if (Object.keys(ahProbabilities).length) {
    const home = probabilityPercent(ahProbabilities.HOME_AH);
    const away = probabilityPercent(ahProbabilities.AWAY_AH);
    const odds = asRecord(card.current_odds);
    const ahOdds = asRecord(odds.ah);
    const homeLine = displayLineForTeam(
      translateTeam(card.home_team_name),
      ahOdds.home_line,
      textValue(ahOdds.home_display_line_cn),
    );
    const awayLine = displayLineForTeam(
      translateTeam(card.away_team_name),
      ahOdds.away_line,
      textValue(ahOdds.away_display_line_cn),
    );
    return `市场概率 ${homeLine} ${home} / ${awayLine} ${away}`;
  }
  return null;
}

function ouProbabilitySummary(markets: Record<string, unknown>): string | null {
  const ou = asRecord(markets.ou);
  const ouProbabilities = asRecord(ou.probabilities);
  if (Object.keys(ouProbabilities).length) {
    const over = probabilityPercent(ouProbabilities.OVER);
    const under = probabilityPercent(ouProbabilities.UNDER);
    return `市场概率 大小 大 ${over} / 小 ${under}`;
  }
  return null;
}

function oneXTwoProbabilitySummary(
  markets: Record<string, unknown>,
): string | null {
  const oneXTwo = asRecord(markets.one_x_two);
  const oneXTwoProbabilities = asRecord(oneXTwo.probabilities);
  if (Object.keys(oneXTwoProbabilities).length) {
    const home = probabilityPercent(oneXTwoProbabilities.HOME);
    const draw = probabilityPercent(oneXTwoProbabilities.DRAW);
    const away = probabilityPercent(oneXTwoProbabilities.AWAY);
    return `市场概率 胜 ${home} / 平 ${draw} / 负 ${away}`;
  }
  return null;
}

function probabilityPercent(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value * 100)}%`
    : "--";
}

function trustSignalSummary(card: DashboardDayViewCard): string {
  if (isWaitingForScheduledRefresh(card) && hasLastKnownOdds(card)) {
    return `已有早盘（${lastKnownCapturedLabel(card)}，不可执行） · 临场盘口与分析待更新`;
  }
  const refresh = card.data_refresh ?? {};
  const odds = textValue(
    refresh.odds_status,
    Object.keys(asRecord(card.current_odds)).length ? "READY" : "WAITING",
  );
  const lineups = textValue(
    refresh.lineups_status,
    textValue(asRecord(card.data_readiness).lineups_status, "UNKNOWN"),
  );
  const xg = textValue(
    refresh.xg_status,
    textValue(asRecord(card.data_readiness).xg_status, "UNKNOWN"),
  );
  const lineupLabel =
    textValue(refresh.lineups_status_label) ||
    (lineups === "NOT_REQUESTED" ? "未到采集时间" : statusCn(lineups));
  return `盘口 ${statusCn(odds)} · 首发 ${lineupLabel} · xG ${statusCn(xg)}`;
}

function applicabilityLabel(card: DashboardDayViewCard): string {
  const diagnostics = asRecord(card.diagnostics);
  const explicit =
    textValue(diagnostics.model_applicability) ||
    textValue(asRecord(card.model_market_divergence).calibration_status);
  if (explicit === "UNVALIDATED") return "模型未验证";
  if (explicit === "INSUFFICIENT") return "样本不足";
  if (explicit) return explicit.replace(/_/g, " ");
  if ((card.competition_id ?? "").includes("world_cup"))
    return "国际赛未独立验证";
  return "按联赛校准状态";
}

function probabilitySourceLabel(card: DashboardDayViewCard): string {
  if (card.probability_source === "MARKET_DEVIG") return "市场锚定";
  if (card.probability_source === "MODEL_FALLBACK") return "模型回退";
  return "概率来源待确认";
}

function marketSourceLabel(card: DashboardDayViewCard): string {
  if (
    hasLastKnownOdds(card) &&
    !Object.keys(asRecord(card.current_odds)).length
  ) {
    return `最近盘口 ${lastKnownCapturedLabel(card)} · 已过期，仅参考`;
  }
  if (card.probability_source !== "MARKET_DEVIG") return "无盘口概率";
  const odds = asRecord(card.current_odds);
  const preferred =
    card.pick?.market === "TOTALS" ? asRecord(odds.ou) : asRecord(odds.ah);
  const source = textValue(preferred.source) || textValue(preferred.bookmaker);
  if (source) return `${source} · 去水市场概率`;
  return "Pinnacle 优先 · 共识主线去水";
}

function divergenceLabel(card: DashboardDayViewCard): string {
  const divergence = asRecord(card.model_market_divergence);
  const magnitude =
    typeof divergence.magnitude === "number" ? divergence.magnitude : null;
  const status = textValue(divergence.status, "UNKNOWN");
  if (magnitude != null) return `模型与市场差 ${magnitude.toFixed(2)}`;
  if (status === "INSUFFICIENT") return "模型分歧不足";
  if (status === "UNVALIDATED") return "模型未验证";
  if (status === "READY") return "分歧可读";
  return "分歧待确认";
}

function signedLine(prefix: string, value: unknown): string {
  const line = formatLine(value);
  if (line === "-") return `${prefix} --`;
  const numeric = typeof value === "number" ? value : Number(value);
  return `${prefix} ${Number.isFinite(numeric) && numeric > 0 ? `+${line}` : line}`;
}

function statusCn(value: string): string {
  const status = value.toUpperCase();
  if (status === "READY") return "已就绪";
  if (status === "STALE") return "已过期";
  if (status === "WAITING") return "等待";
  if (status === "PROVIDER_EMPTY") return "数据源空返";
  if (status === "INSUFFICIENT_HISTORY") return "样本不足";
  if (status === "NOT_REQUESTED") return "未到采集时间";
  if (status === "UNKNOWN") return "未知";
  return value;
}

function marketPickLabel(card: DashboardDayViewCard): string {
  if (!card.pick) return "等待盘口";
  const market = card.pick.market ? marketLabel(card.pick.market) : "市场";
  const selection = card.pick.selection
    ? pickSelectionLabel(card.pick.selection)
    : "方向待确认";
  const line = displayableLine(card.pick.line)
    ? ` ${formatLine(card.pick.line)}`
    : "";
  const odds = card.pick.odds != null ? ` @${formatOdds(card.pick.odds)}` : "";
  return `${market} ${selection}${line}${odds}`.trim();
}

function displayableLine(value: string | number | null | undefined): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "string") return false;
  return /^[-+]?\d+(?:\.\d+)?$/.test(value.trim());
}

function marketLabel(value: string): string {
  if (value === "ASIAN_HANDICAP") return "让球";
  if (value === "TOTALS") return "大小球";
  if (value === "ONE_X_TWO") return "胜平负";
  return "市场";
}

function selectionLabel(value: string): string {
  if (value === "HOME") return "主队";
  if (value === "AWAY") return "客队";
  if (value === "HOME_AH") return "主队";
  if (value === "AWAY_AH") return "客队";
  if (value === "OVER") return "大";
  if (value === "UNDER") return "小";
  if (value === "DRAW") return "平";
  return "方向";
}

function pickSelectionLabel(value: string): string {
  if (value === "HOME_AH") return "主";
  if (value === "AWAY_AH") return "客";
  return selectionLabel(value);
}

function displayLineForTeam(
  team: string,
  line: unknown,
  fallback?: string | null,
): string {
  if (fallback) {
    return fallback.replace("主队", team).replace("客队", team);
  }
  const formatted = formatLine(line);
  return formatted === "-" ? team : `${team} ${formatted}`;
}

function teamLabel(card: DashboardDayViewCard): string {
  const home = translateTeam(card.home_team_name);
  const away = translateTeam(card.away_team_name);
  return `${home} vs ${away}`;
}

function competitionLabel(card: DashboardDayViewCard): string {
  return translateCompetition(
    card.competition_name || card.competition_id || "比赛",
  );
}

function byFixtureId(
  matches: DashboardMatchCard[],
): Map<string, DashboardMatchCard> {
  return new Map(matches.map((match) => [String(match.fixture_id), match]));
}

function referenceTime(dayView: DashboardDayView): Date {
  const raw = dayView.generated_at || dayView.freshness.last_refresh;
  const parsed = raw ? new Date(raw) : new Date();
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
}

function isSameShanghaiDate(
  left?: string | null,
  right?: string | null,
): boolean {
  if (!left || !right) return false;
  const format = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return format.format(new Date(left)) === format.format(new Date(right));
}

function minutesUntil(card: DashboardDayViewCard, now: Date): number | null {
  if (!card.kickoff_utc) return null;
  const kickoff = new Date(card.kickoff_utc);
  if (Number.isNaN(kickoff.getTime())) return null;
  return Math.round((kickoff.getTime() - now.getTime()) / 60000);
}

function isPreMatch(card: DashboardDayViewCard): boolean {
  const status = (card.status ?? "").toUpperCase();
  return !["FT", "AET", "PEN", "FINISHED", "CANCELLED", "POSTPONED"].includes(
    status,
  );
}

function isLiveOrRecentlyStarted(
  card: DashboardDayViewCard,
  now: Date,
): boolean {
  if (!isPreMatch(card)) return false;
  const status = (card.status ?? "").toUpperCase();
  if (["LIVE", "1H", "2H", "HT", "ET", "BT", "P"].includes(status)) return true;
  const minutes = minutesUntil(card, now);
  return minutes != null && minutes <= 0 && minutes >= -150;
}

function isReadyRecommendation(card: DashboardDayViewCard): boolean {
  const pickTier = ["RECOMMEND", "ANALYSIS_PICK"].includes(card.decision_tier);
  if (!pickTier || card.data_status !== "READY") return false;
  if (!MARKET_ANCHOR_DISPLAY_ENABLED || card.decision_tier === "RECOMMEND")
    return true;
  return hasActionableMarketDivergence(card);
}

function hasActionableMarketDivergence(card: DashboardDayViewCard): boolean {
  if (card.probability_source !== "MARKET_DEVIG") return false;
  const divergence = asRecord(card.model_market_divergence);
  const status = textValue(divergence.status, "UNKNOWN").toUpperCase();
  const directionAllowed =
    divergence.direction_allowed === true ||
    textValue(divergence.direction_allowed).toLowerCase() === "true";
  const magnitude =
    typeof divergence.magnitude === "number"
      ? Math.abs(divergence.magnitude)
      : null;
  return (
    ["READY", "SIGNIFICANT", "ACTIONABLE"].includes(status) &&
    directionAllowed &&
    magnitude != null &&
    magnitude >= MARKET_ANCHOR_MIN_DIVERGENCE
  );
}

function orderedByKickoff(
  cards: DashboardDayViewCard[],
): DashboardDayViewCard[] {
  return [...cards].sort((left, right) => {
    return (left.kickoff_utc ?? "").localeCompare(right.kickoff_utc ?? "");
  });
}

function orderedForTriage(
  cards: DashboardDayViewCard[],
): DashboardDayViewCard[] {
  const priority: Record<string, number> = {
    RECOMMEND: 0,
    ANALYSIS_PICK: 1,
    WATCH: 2,
    NOT_READY: 3,
    SKIP: 4,
  };
  return [...cards].sort((left, right) => {
    const tierDelta =
      (priority[left.decision_tier] ?? 9) -
      (priority[right.decision_tier] ?? 9);
    if (tierDelta) return tierDelta;
    return (left.kickoff_utc ?? "").localeCompare(right.kickoff_utc ?? "");
  });
}

function filterScheduleCards(
  cards: DashboardDayViewCard[],
  filter: ScheduleFilter,
): DashboardDayViewCard[] {
  if (filter === "recommended") return cards.filter(isReadyRecommendation);
  if (filter === "hide-not-ready")
    return cards.filter(
      (card) => !["NOT_READY", "SKIP"].includes(card.decision_tier),
    );
  return cards;
}

function settledMatches(matches: DashboardMatchCard[]): DashboardMatchCard[] {
  return matches
    .filter((match) => {
      const settlement =
        match.validation?.settlement ??
        match.locked_pre_match_recommendation?.settlement?.status;
      return (
        settlement &&
        !["PENDING", "WAITING_RESULT", "NO_BET", "UNKNOWN"].includes(
          String(settlement),
        )
      );
    })
    .sort((left, right) =>
      (right.kickoff_utc ?? "").localeCompare(left.kickoff_utc ?? ""),
    );
}

function settlementLabel(value?: string | null): string {
  if (value === "HIT" || value === "SETTLED") return "命中";
  if (value === "MISS") return "未中";
  if (value === "PUSH") return "走水";
  if (value === "VOID") return "作废";
  return "待追踪";
}

function buildLeaguePerformanceRows(
  matches: DashboardMatchCard[],
): LeaguePerformanceRow[] {
  const rows = new Map<string, LeaguePerformanceRow>();
  for (const match of matches) {
    const validation = match.validation;
    if (
      !validation ||
      !["HIT", "MISS", "PUSH", "VOID"].includes(validation.settlement)
    )
      continue;
    const key = match.competition_id || match.competition_name || "unknown";
    const row = rows.get(key) ?? {
      key,
      label: translateCompetition(
        match.competition_name || match.competition_id || "联赛",
      ),
      sampleSize: 0,
      hitCount: 0,
      missCount: 0,
      pushCount: 0,
      voidCount: 0,
      roiUnits: 0,
    };
    row.sampleSize += 1;
    if (validation.settlement === "HIT") row.hitCount += 1;
    if (validation.settlement === "MISS") row.missCount += 1;
    if (validation.settlement === "PUSH") row.pushCount += 1;
    if (validation.settlement === "VOID") row.voidCount += 1;
    row.roiUnits +=
      typeof validation.profit_units === "number" ? validation.profit_units : 0;
    rows.set(key, row);
  }
  return [...rows.values()].sort(
    (left, right) =>
      right.sampleSize - left.sampleSize ||
      left.label.localeCompare(right.label),
  );
}

function percent(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return "样本不足";
  return `${Math.round(value * 100)}%`;
}

function shortSha(value?: string | null): string {
  return value && value !== "UNKNOWN" ? value.slice(0, 7) : "UNKNOWN";
}

function units(value: number): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}u`;
}

function clvUnits(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return "CLV 积累中";
  return `${value > 0 ? "+" : ""}${value.toFixed(3)}`;
}

function performanceStatus(sampleSize: number): string {
  if (sampleSize >= 50) return "已验证";
  if (sampleSize >= 10) return "观察中";
  return "样本不足";
}

function nextEvalLabel(card: DashboardDayViewCard): string {
  if (!card.next_eval_at) return "待定";
  return fmtTime(card.next_eval_at);
}

function countdownLabel(card: DashboardDayViewCard, now: Date): string {
  const minutes = minutesUntil(card, now);
  if (minutes == null) return "时间待定";
  if (minutes < 0) return `已开赛 ${Math.abs(minutes)} 分钟`;
  if (minutes < 60) return `还有 ${minutes} 分钟`;
  if (minutes < 1440) return `还有 ${Math.floor(minutes / 60)} 小时`;
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  return `还有 ${days} 天${hours ? ` ${hours} 小时` : ""}`;
}

function rowMarketSummary(card: DashboardDayViewCard): string {
  if (card.pick) return `推荐盘口：${marketPickLabel(card)}`;
  const odds = oddsSummary(card);
  if (odds) return `当前市场盘口（非推荐）：${odds.split(" · ")[0] ?? odds}`;
  const historical = lastKnownOddsSummary(card);
  if (historical)
    return `市场早盘（非推荐）：${historical.split(" · ")[0] ?? historical}`;
  return visibleReasonLabel(card);
}

function secondaryMarketSummary(card: DashboardDayViewCard): string | null {
  const pick = card.secondary_picks?.[0];
  if (!pick) return null;
  const market =
    pick.market === "TOTALS"
      ? "大小球"
      : pick.market === "ASIAN_HANDICAP"
        ? "让球"
        : pick.market;
  const direction = pick.tendency ?? pick.lean;
  const parts = [
    market,
    direction,
    pick.line,
    pick.odds ? `@${pick.odds}` : null,
  ].filter(Boolean);
  return parts.length ? `严格次推：${parts.join(" ")}` : null;
}

function reasonSummary(
  cards: DashboardDayViewCard[],
): Array<{ label: string; count: number }> {
  const counter = new Map<string, number>();
  for (const card of cards) {
    const label = visibleReasonLabel(card);
    if (label === "暂无阻塞原因") continue;
    counter.set(label, (counter.get(label) ?? 0) + 1);
  }
  return [...counter.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort(
      (left, right) =>
        right.count - left.count || left.label.localeCompare(right.label),
    );
}

function diagnosticRows(card: DashboardDayViewCard): Array<[string, string]> {
  const diagnostics = asRecord(card.diagnostics);
  const readiness = asRecord(diagnostics.data_readiness_summary);
  const missingFields = card.missing_fields ?? [];
  const staleFields = card.stale_fields ?? [];
  return [
    ["decision", tierLabel(card.decision_tier)],
    ["data", dataStatusLabel(card.data_status)],
    ["reason", reasonLabel(effectiveReasonCode(card))],
    ["action", actionLabel(card.action)],
    ["next_eval_at", textValue(card.next_eval_at, "-")],
    ["probability_source", probabilitySourceLabel(card)],
    ["model_market_divergence", divergenceLabel(card)],
    ["model_applicability", applicabilityLabel(card)],
    ["card_hash", textValue(card.card_hash, "-").slice(0, 16)],
    ["missing", missingFields.join(", ") || "-"],
    ["stale", staleFields.join(", ") || "-"],
    ["readiness", textValue(readiness.data_status, "-")],
  ];
}

function evidenceStatements(card: DashboardDayViewCard): string[] {
  const waitingWithEarlyMarket =
    isWaitingForScheduledRefresh(card) && hasLastKnownOdds(card);
  return [
    `盘口源:${marketSourceLabel(card)}`,
    `决策:${tierLabel(card.decision_tier)}; ${l1OneLiner(card)}`,
    effectiveReasonCode(card) === "DATA_STALE_ODDS"
      ? `数据:${staleOddsExplanation(card)}`
      : `数据:${visibleDataStatusLabel(card)}; ${trustSignalSummary(card)}`,
    waitingWithEarlyMarket
      ? "模型:等待临场盘口更新后重新确认"
      : `模型:${applicabilityLabel(card)}; ${divergenceLabel(card)}`,
    `下一步:${actionLabel(card.action)}; ${card.next_eval_at ? fmtTime(card.next_eval_at) : "待定"}再看`,
  ];
}

function nextVisibleKickoff(cards: DashboardDayViewCard[]): string | null {
  return (
    cards
      .filter((card) => card.kickoff_utc && isPreMatch(card))
      .sort((left, right) =>
        (left.kickoff_utc ?? "").localeCompare(right.kickoff_utc ?? ""),
      )[0]?.kickoff_utc ?? null
  );
}

export function MatchdayHeader({
  dayView,
  release,
}: {
  dayView: DashboardDayView;
  release?: ReleaseSyncState;
}) {
  const upcoming = dayView.cards.filter(isPreMatch).length;
  const readyRecommendations = orderedForTriage(
    dayView.cards.filter(isReadyRecommendation),
  ).length;
  return (
    <header className="boss-commandbar">
      <div className="boss-brand">
        <strong>FOOTBALL</strong>
        <span>INTELLIGENCE</span>
      </div>
      <span className="boss-view-select">只读决策台</span>
      <div className="boss-command-meta">
        <span>
          日期 <strong>{dayView.football_day}</strong>
        </span>
        <span>
          环境 <strong>{dayView.environment}</strong>
        </span>
        <span className="boss-time-pair">
          <span className="boss-time-line">
            页面更新{" "}
            <strong>
              {dayView.freshness.page_updated_at
                ? fmtTime(dayView.freshness.page_updated_at)
                : "--:--"}
            </strong>
          </span>
          <span className="boss-time-line">
            全局赔率确认{" "}
            <strong>
              {dayView.freshness.odds_last_confirmed_at
                ? fmtTime(dayView.freshness.odds_last_confirmed_at)
                : "暂无"}
            </strong>
          </span>
        </span>
        <span>
          下次采集{" "}
          <strong>
            {dayView.freshness.next_refresh_tick
              ? fmtTime(dayView.freshness.next_refresh_tick)
              : "待定"}
          </strong>
        </span>
        <span>
          未来待赛 <strong>{upcoming}</strong>
        </span>
        <span>
          已出推荐 <strong>{readyRecommendations}</strong>
        </span>
      </div>
      <div className="boss-command-release">
        Web {shortSha(release?.web_git_sha)} · API{" "}
        {shortSha(release?.api_git_sha)}
      </div>
    </header>
  );
}

export function DecisionCounts({
  dayView,
  performance,
}: {
  dayView: DashboardDayView;
  performance?: DashboardPerformance;
}) {
  const lockLabel =
    dayView.environment === "production" ? "正式可锁" : "可锁审批";
  const readyRecommendations = dayView.cards.filter(
    isReadyRecommendation,
  ).length;
  const cohort = performance?.forward_ledger?.performance_cohort;
  const metrics = [
    [lockLabel, dayView.counts.lock_eligible, "审批候选由 DecisionCard 给出"],
    ["已出推荐", readyRecommendations, "数据齐全后才置顶"],
    [
      "纳入统计",
      cohort?.eligible_count ?? 0,
      `有效输赢命中率 ${percent(cohort?.outcomes.hit_rate)}`,
    ],
    [
      "今日待评估",
      dayView.counts.not_ready + dayView.counts.watch + dayView.counts.skip,
      "按开球时间继续观察",
    ],
  ] as const;
  return (
    <section className="decision-counts" aria-label="今日决策计数">
      {metrics.map(([label, value, hint]) => (
        <div className="decision-count" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{hint}</small>
        </div>
      ))}
    </section>
  );
}

export function EvidencePanel({
  cards,
  selectedCard,
  settledCount,
}: {
  cards: DashboardDayViewCard[];
  selectedCard?: DashboardDayViewCard;
  settledCount: number;
}) {
  const reasons = reasonSummary(cards);
  if (selectedCard) {
    return (
      <aside className="evidence-panel" aria-label="选中比赛证据预览">
        <span>选中比赛证据</span>
        <h2>{teamLabel(selectedCard)}</h2>
        <p>
          {lastKnownOddsSummary(selectedCard) ??
            marketSourceLabel(selectedCard)}
        </p>
        <div className="trust-grid">
          {evidenceStatements(selectedCard).map((statement) => (
            <strong key={statement}>{statement}</strong>
          ))}
        </div>
        <div className="tracking-note">
          <span>赛后追踪</span>
          <strong>
            {selectedCard.outcome_tracked
              ? "已纳入验证追踪"
              : "本场尚未产生验证推荐"}
          </strong>
          <small>
            {selectedCard.outcome_tracked
              ? "结算后会进入赛后验证，并计入对应联赛样本。"
              : "只有赛前形成分析参考或正式推荐，完场后才计入验证样本。"}
          </small>
        </div>
      </aside>
    );
  }
  return (
    <aside className="evidence-panel" aria-label="今日聚合证据">
      <span>今日聚合</span>
      <h2>{cards.length ? `${cards.length} 场待赛` : "当前无待赛比赛"}</h2>
      <p>
        {reasons.length
          ? reasons
              .slice(0, 3)
              .map((reason) => `${reason.label} × ${reason.count}`)
              .join(" · ")
          : "没有阻塞原因时，继续按时间轴观察下一次刷新。"}
      </p>
      <div className="tracking-note">
        <span>赛后验证</span>
        <strong>
          {settledCount
            ? `已有 ${settledCount} 条结算样本`
            : "暂无可展示结算样本"}
        </strong>
        <small>命中率必须和 ROI、样本量一起看。</small>
      </div>
    </aside>
  );
}

export function DecisionRow({
  card,
  selected,
  legacyMatch,
  now,
  onSelect,
}: {
  card: DashboardDayViewCard;
  selected: boolean;
  legacyMatch?: DashboardMatchCard;
  now: Date;
  onSelect: () => void;
}) {
  const tierClass = `tier-${card.decision_tier.toLowerCase().replace("_", "-")}`;
  const muted =
    card.decision_tier === "NOT_READY" ||
    card.decision_tier === "SKIP" ||
    card.data_status === "BLOCKED";
  return (
    <article
      className={`decision-row ${tierClass}${selected ? " is-selected" : ""}${muted ? " is-muted" : ""}`}
    >
      <button
        className="decision-row-button"
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
      >
        <div className="decision-cell decision-time">
          <strong>{fmtTime(card.kickoff_utc)}</strong>
          <span>{countdownLabel(card, now)}</span>
        </div>
        <div className="decision-cell decision-league">
          <span>{competitionLabel(card)}</span>
        </div>
        <div className="decision-cell decision-teams">
          <strong>{teamLabel(card)}</strong>
          <span>{scorelineSimulationSummary(card)}</span>
        </div>
        <div className="decision-cell decision-market">
          <span>{rowMarketSummary(card)}</span>
          <small>
            {secondaryMarketSummary(card) ??
              marketProbabilitySummary(card) ??
              marketSourceLabel(card)}
          </small>
        </div>
        <div className="decision-cell decision-data">
          <span>{visibleDataStatusLabel(card, now)}</span>
          <i aria-hidden="true" />
        </div>
        <div className="decision-cell decision-tier">
          <span className={`tier-badge ${tierClass}`}>
            {tierLabel(card.decision_tier)}
          </span>
        </div>
        <div className="decision-cell decision-next">
          <span>{nextEvalLabel(card)}</span>
        </div>
      </button>
      <details className="l2-diagnostics-drawer">
        <summary>L2 技术诊断</summary>
        <div className="l2-diagnostics-body">
          {legacyMatch ? <RecommendationCard match={legacyMatch} /> : null}
          <dl className="l2-diagnostics-grid">
            {diagnosticRows(card).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </details>
    </article>
  );
}

function HealthStrip({ dayView }: { dayView: DashboardDayView }) {
  const waiting = dayView.cards.filter((card) =>
    isWaitingForScheduledRefresh(card),
  ).length;
  const withEarlyMarket = dayView.cards.filter(
    (card) => isWaitingForScheduledRefresh(card) && hasLastKnownOdds(card),
  ).length;
  const competitionCount = new Set(
    dayView.cards
      .map((card) => card.competition_id || card.competition_name)
      .filter(Boolean),
  ).size;
  const blocked = dayView.cards.filter(
    (card) =>
      (card.data_status === "BLOCKED" || card.data_status === "STALE") &&
      !isWaitingForScheduledRefresh(card),
  ).length;
  const staleOdds = dayView.cards.filter(
    (card) => effectiveReasonCode(card) === "DATA_STALE_ODDS",
  );
  const staleOddsNext = staleOdds
    .map((card) => card.next_eval_at)
    .filter((value): value is string => Boolean(value))
    .sort()[0];
  return (
    <section
      className={`health-strip${blocked ? " has-warning" : ""}`}
      aria-label="白名单健康状态"
    >
      <strong>
        {staleOdds.length
          ? "缺少最新临场赔率"
          : blocked
            ? "部分数据需处理"
            : waiting
              ? "赛前数据持续更新"
              : "当前窗口正常"}
      </strong>
      <span>
        {competitionCount} 个联赛 · 待赛{" "}
        {dayView.cards.filter(isPreMatch).length} 场
      </span>
      {staleOdds.length ? (
        <small>
          {staleOdds.length} 场当前只有过期早盘；
          {staleOddsNext ? fmtTime(staleOddsNext) : "下一计划时点"}
          采集后重新判断能否形成推荐。
        </small>
      ) : blocked ? (
        <small>异常比赛已保留在赛程中，并显示真实原因。</small>
      ) : waiting ? (
        <small>
          {withEarlyMarket} 场已有早盘；{waiting - withEarlyMarket}{" "}
          场待首轮盘口，均按计划更新。
        </small>
      ) : (
        <small>覆盖诊断只在异常时展开。</small>
      )}
    </section>
  );
}

function FilterControls({
  filter,
  onFilterChange,
}: {
  filter: ScheduleFilter;
  onFilterChange: (filter: ScheduleFilter) => void;
}) {
  const filters: Array<[ScheduleFilter, string]> = [
    ["all", "全部赛程"],
    ["recommended", "只看已形成建议"],
    ["hide-not-ready", "隐藏未就绪"],
  ];
  return (
    <div className="schedule-controls" aria-label="赛程筛选">
      {filters.map(([id, label]) => (
        <button
          key={id}
          type="button"
          className={filter === id ? "is-active" : ""}
          onClick={() => onFilterChange(id)}
          aria-pressed={filter === id}
        >
          {label}
        </button>
      ))}
      <span>推荐置顶；其余严格按开球时间</span>
    </div>
  );
}

function ScheduleSection({
  title,
  hint,
  cards,
  empty,
  selectedFixtureId,
  legacyById,
  now,
  onSelect,
  collapsed,
}: {
  title: string;
  hint: string;
  cards: DashboardDayViewCard[];
  empty: string;
  selectedFixtureId?: string | null;
  legacyById: Map<string, DashboardMatchCard>;
  now: Date;
  onSelect: (fixtureId: string) => void;
  collapsed?: boolean;
}) {
  return (
    <section
      className={`schedule-section${collapsed ? " is-collapsed" : ""}${cards.length ? "" : " is-empty"}`}
      aria-label={title}
    >
      <header className="schedule-section-heading">
        <div>
          <span>{title}</span>
          <p>{hint}</p>
        </div>
        <strong>{cards.length}</strong>
      </header>
      {cards.length ? (
        <div className="schedule-row-list">
          <div className="schedule-table-head" aria-hidden="true">
            <span>开球时间</span>
            <span>联赛</span>
            <span>对阵</span>
            <span>盘口 / 市场概率</span>
            <span>数据就绪</span>
            <span>决策</span>
            <span>下一次评估</span>
          </div>
          {cards.map((card) => (
            <DecisionRow
              key={card.fixture_id}
              card={card}
              selected={card.fixture_id === selectedFixtureId}
              legacyMatch={legacyById.get(card.fixture_id)}
              now={now}
              onSelect={() => onSelect(card.fixture_id)}
            />
          ))}
        </div>
      ) : (
        <div className="inline-empty">{empty}</div>
      )}
    </section>
  );
}

function TrustStrip({
  performance,
  leagueRows,
}: {
  performance?: DashboardPerformance;
  leagueRows: LeaguePerformanceRow[];
}) {
  const forwardLedger = performance?.forward_ledger;
  const cohort = forwardLedger?.performance_cohort;
  const bestLeagues = leagueRows
    .filter((row) => row.sampleSize >= 10)
    .slice(0, 2)
    .map((row) => row.label)
    .join(" / ");
  const bestForwardLeagues = cohort?.by_league
    ?.filter((row) => row.eligible_count > 0)
    .slice(0, 2)
    .map((row) => translateCompetition(row.league))
    .join(" / ");
  const validationCount = cohort?.validation_count ?? 0;
  const settled = cohort?.eligible_count ?? 0;
  const pending = cohort?.pending_count ?? 0;
  const firstCapture = forwardLedger?.evidence_window.first_capture_at?.slice(
    5,
    10,
  );
  const latestCapture = forwardLedger?.evidence_window.latest_capture_at?.slice(
    5,
    10,
  );
  const evidenceRange =
    firstCapture && latestCapture
      ? `${firstCapture} 至 ${latestCapture}`
      : "积累中";
  return (
    <section className="trust-strip" aria-label="赛后信任摘要">
      <strong>真实前向 {evidenceRange}</strong>
      <span>验证推荐 {validationCount} 场</span>
      <span>
        纳入统计 {settled} · 待处理 {pending}
      </span>
      <span>
        命中率 {settled ? percent(cohort?.outcomes.hit_rate) : "积累中"}
      </span>
      <span>
        CLV{" "}
        {cohort?.clv.sample_count
          ? clvUnits(cohort.clv.median_decimal)
          : "积累中"}
      </span>
      <span>联赛表现 {bestForwardLeagues || bestLeagues || "积累中"}</span>
    </section>
  );
}

function VerificationPreview({
  matches,
  performance,
}: {
  matches: DashboardMatchCard[];
  performance?: DashboardPerformance;
}) {
  const forwardLedger = performance?.forward_ledger;
  if (forwardLedger) {
    const cohort = forwardLedger.performance_cohort;
    const settled = cohort.eligible_count;
    const pending = cohort.pending_count;
    const outcomes = cohort.outcomes;
    const decisive = outcomes.decisive_count;
    const pendingStatus = forwardLedger.validation_pending_status;
    const pendingBreakdown = [
      pendingStatus?.waiting_finish_count
        ? `等待完赛 ${pendingStatus.waiting_finish_count}`
        : "",
      pendingStatus?.postponed_count
        ? `延期 ${pendingStatus.postponed_count}`
        : "",
      pendingStatus?.result_missing_count
        ? `缺少赛果 ${pendingStatus.result_missing_count}`
        : "",
      pendingStatus?.settlement_error_count
        ? `结算异常 ${pendingStatus.settlement_error_count}`
        : "",
    ]
      .filter(Boolean)
      .join(" · ");
    return (
      <section className="verification-preview" aria-label="赛后验证预览">
        <header>
          <span>赛后验证</span>
          <strong>纳入统计 {settled} 场</strong>
        </header>
        {settled ? (
          <div className="verification-list">
            <div>
              <span>验证推荐与赛果</span>
              <strong>
                命中 {outcomes.hit_count} · 未中 {outcomes.miss_count} · 走水{" "}
                {outcomes.push_count}
                {outcomes.void_count ? ` · 作废 ${outcomes.void_count}` : ""}
              </strong>
              <small>
                有效输赢 {decisive} 场 · 命中率{" "}
                {decisive ? percent(outcomes.hit_rate) : "暂无有效分母"}
                {cohort.recovered_count
                  ? ` · 其中 ${cohort.recovered_count} 场经唯一历史快照审计恢复`
                  : ""}
                {pending
                  ? ` · ${pendingBreakdown || `待处理 ${pending} 场`}`
                  : ""}
              </small>
            </div>
            {cohort.recovered_count ? (
              <details className="verification-recoveries">
                <summary>查看 {cohort.recovered_count} 场恢复明细</summary>
                <div className="verification-recovery-list">
                  {cohort.recoveries.map((row) => (
                    <article key={row.fixture_id}>
                      <strong>
                        {translateTeam(row.home_team_name)} vs{" "}
                        {translateTeam(row.away_team_name)}
                      </strong>
                      <span>
                        {translateCompetition(row.league)} ·{" "}
                        {fmtTime(row.kickoff_utc)} ·{" "}
                        {settlementLabel(row.settlement_outcome)}
                      </span>
                      <small>
                        {row.recovery_label} · {row.recovery_code}
                      </small>
                    </article>
                  ))}
                </div>
              </details>
            ) : null}
            {cohort.excluded_count ? (
              <details className="verification-exclusions">
                <summary>
                  另有 {cohort.excluded_count}{" "}
                  场赛果已处理，因历史身份链缺失未纳入
                </summary>
                <div className="verification-exclusion-list">
                  {cohort.exclusions.map((row) => (
                    <article key={row.fixture_id}>
                      <strong>
                        {translateTeam(row.home_team_name)} vs{" "}
                        {translateTeam(row.away_team_name)}
                      </strong>
                      <span>
                        {translateCompetition(row.league)} ·{" "}
                        {fmtTime(row.kickoff_utc)} ·{" "}
                        {settlementLabel(row.settlement_outcome)}
                      </span>
                      <small>
                        {row.reason_label} · {row.reason_code}
                      </small>
                    </article>
                  ))}
                </div>
              </details>
            ) : null}
          </div>
        ) : (
          <p>
            真实前向卡已进入 ledger,但 outcome
            仍在积累中；暂不显示命中率,不制造战绩。
          </p>
        )}
      </section>
    );
  }
  const settled = settledMatches(matches).slice(0, 5);
  return (
    <section className="verification-preview" aria-label="赛后验证预览">
      <header>
        <span>赛后验证</span>
        <strong>
          {settled.length ? `最近 ${settled.length} 条` : "暂无结算样本"}
        </strong>
      </header>
      {settled.length ? (
        <div className="verification-list">
          {settled.map((match) => (
            <div key={match.fixture_id}>
              <span>
                {fmtTime(match.kickoff_utc)} ·{" "}
                {translateCompetition(match.competition_name)}
              </span>
              <strong>
                {translateTeam(match.home_team_name)} vs{" "}
                {translateTeam(match.away_team_name)}
              </strong>
              <small>
                {settlementLabel(match.validation?.settlement)} ·{" "}
                {match.result?.final_score ?? "比分待同步"} ·{" "}
                {match.validation?.closing_line_value ?? "CLV 待接入"}
              </small>
            </div>
          ))}
        </div>
      ) : (
        <p>完场并结算后，推荐会在这里显示命中、走水、作废和原因码。</p>
      )}
    </section>
  );
}

function LeaguePerformancePreview({
  rows,
  performance,
}: {
  rows: LeaguePerformanceRow[];
  performance?: DashboardPerformance;
}) {
  const forwardLedger = performance?.forward_ledger;
  if (forwardLedger) {
    const visibleForwardRows = forwardLedger.performance_cohort.by_league;
    return (
      <section className="league-performance-preview" aria-label="联赛表现预览">
        <header>
          <span>联赛表现</span>
          <strong>
            {visibleForwardRows.length ? "验证样本" : "验证样本积累中"}
          </strong>
        </header>
        {visibleForwardRows.length ? (
          <div className="league-performance-table">
            <div className="league-performance-head">
              <span>联赛</span>
              <span>纳入统计</span>
              <span>结果</span>
              <span title="推荐赔率减去开赛前 30 分钟内的同盘口赔率">
                临场 CLV
              </span>
              <span>统计状态</span>
            </div>
            {visibleForwardRows.map((row) => (
              <div key={row.competition_id || row.league}>
                <span data-label="联赛">
                  {translateCompetition(row.league)}
                </span>
                <span data-label="纳入统计">{row.eligible_count} 场</span>
                <span data-label="结果">
                  {row.outcomes.hit_count}-{row.outcomes.miss_count}-
                  {row.outcomes.push_count}
                </span>
                <span data-label="临场 CLV">
                  {row.clv.sample_count
                    ? `${clvUnits(row.clv.median_decimal)}（n=${row.clv.sample_count}）`
                    : "暂无临场盘（n=0）"}
                </span>
                <span data-label="统计状态">
                  {row.rate_status === "AVAILABLE"
                    ? `${percent(row.outcomes.hit_rate)}（有效输赢 ${row.decisive_count}）`
                    : `样本不足（${row.decisive_count}）`}
                </span>
              </div>
            ))}
            <p className="league-clv-note">
              临场 CLV＝推荐赔率－开赛前 30 分钟内的同盘口赔率；正数更优，n
              为有效临场样本。
            </p>
          </div>
        ) : (
          <p>还没有形成验证推荐；未产生验证身份的比赛不计入联赛表现。</p>
        )}
      </section>
    );
  }
  const visibleRows = rows.slice(0, 6);
  return (
    <section className="league-performance-preview" aria-label="联赛表现预览">
      <header>
        <span>联赛表现</span>
        <strong>{visibleRows.length ? "按样本量排序" : "样本不足"}</strong>
      </header>
      {visibleRows.length ? (
        <div className="league-performance-table">
          <div className="league-performance-head">
            <span>联赛</span>
            <span>样本</span>
            <span>命中率</span>
            <span>ROI</span>
            <span>状态</span>
          </div>
          {visibleRows.map((row) => (
            <div key={row.key}>
              <span>{row.label}</span>
              <span>{row.sampleSize}</span>
              <span>
                {percent(row.sampleSize ? row.hitCount / row.sampleSize : null)}
              </span>
              <span>{units(row.roiUnits)}</span>
              <span>{performanceStatus(row.sampleSize)}</span>
            </div>
          ))}
        </div>
      ) : (
        <p>
          联赛命中率必须等有足够结算样本后展示；当前只保留占位，不制造胜率。
        </p>
      )}
    </section>
  );
}

function CoverageFoldout({ dayView }: { dayView: DashboardDayView }) {
  const reasons = reasonSummary(dayView.cards);
  const nextKickoff = nextVisibleKickoff(dayView.cards);
  return (
    <details className="coverage-foldout">
      <summary>
        <strong>未来 / 覆盖解释</strong>
        <span>
          {nextKickoff ? `下一场 ${fmtTime(nextKickoff)}` : "当前没有下一场"}
        </span>
      </summary>
      <div className="coverage-foldout-body">
        <p>
          白名单比赛只有进入 DayView/DecisionCard
          后才展示；未就绪不会被删掉,会带着原因和下一次评估时间留在赛程里。
        </p>
        <div>
          {reasons.slice(0, 4).map((reason) => (
            <span key={reason.label}>
              {reason.label} × {reason.count}
            </span>
          ))}
          {!reasons.length ? <span>暂无阻塞原因</span> : null}
        </div>
      </div>
    </details>
  );
}

export function BossDecisionView({
  dayView,
  legacyMatches,
  performance,
  release,
}: {
  dayView: DashboardDayView;
  legacyMatches: DashboardMatchCard[];
  performance?: DashboardPerformance;
  release?: ReleaseSyncState;
}) {
  const legacyById = byFixtureId(legacyMatches);
  const now = useMemo(() => referenceTime(dayView), [dayView]);
  const [scheduleFilter, setScheduleFilter] = useState<ScheduleFilter>("all");
  const scheduleDay =
    dayView.selected_football_day ||
    dayView.football_day ||
    dayView.generated_at;
  const activeCards = useMemo(
    () => orderedByKickoff(dayView.cards.filter(isPreMatch)),
    [dayView.cards],
  );
  const worthWatching = useMemo(
    () => orderedForTriage(activeCards.filter(isReadyRecommendation)),
    [activeCards],
  );
  const worthWatchingIds = useMemo(
    () => new Set(worthWatching.map((card) => card.fixture_id)),
    [worthWatching],
  );
  const liveCards = useMemo(
    () =>
      orderedByKickoff(
        activeCards.filter(
          (card) =>
            isLiveOrRecentlyStarted(card, now) &&
            !worthWatchingIds.has(card.fixture_id),
        ),
      ),
    [activeCards, now, worthWatchingIds],
  );
  const liveIds = useMemo(
    () => new Set(liveCards.map((card) => card.fixture_id)),
    [liveCards],
  );
  const todaySchedule = useMemo(
    () =>
      orderedByKickoff(
        activeCards.filter(
          (card) =>
            isSameShanghaiDate(card.kickoff_utc, scheduleDay) &&
            !worthWatchingIds.has(card.fixture_id) &&
            !liveIds.has(card.fixture_id),
        ),
      ),
    [activeCards, liveIds, scheduleDay, worthWatchingIds],
  );
  const futureSchedule = useMemo(
    () =>
      orderedByKickoff(
        activeCards.filter(
          (card) =>
            !isSameShanghaiDate(card.kickoff_utc, scheduleDay) &&
            !worthWatchingIds.has(card.fixture_id) &&
            !liveIds.has(card.fixture_id),
        ),
      ),
    [activeCards, liveIds, scheduleDay, worthWatchingIds],
  );
  const filteredTodaySchedule = useMemo(
    () => filterScheduleCards(todaySchedule, scheduleFilter),
    [scheduleFilter, todaySchedule],
  );
  const filteredFutureSchedule = useMemo(
    () => filterScheduleCards(futureSchedule, scheduleFilter),
    [futureSchedule, scheduleFilter],
  );
  const visibleCards = useMemo(
    () => [
      ...worthWatching,
      ...liveCards,
      ...filteredTodaySchedule,
      ...filteredFutureSchedule,
    ],
    [filteredFutureSchedule, filteredTodaySchedule, liveCards, worthWatching],
  );
  const firstCard =
    worthWatching[0] ??
    liveCards[0] ??
    filteredTodaySchedule[0] ??
    filteredFutureSchedule[0];
  const [selectedFixtureId, setSelectedFixtureId] = useState<string | null>(
    firstCard?.fixture_id ?? null,
  );
  const selectedCard =
    visibleCards.find((card) => card.fixture_id === selectedFixtureId) ??
    firstCard;
  const leagueRows = useMemo(
    () => buildLeaguePerformanceRows(legacyMatches),
    [legacyMatches],
  );
  const settledCount = useMemo(
    () => settledMatches(legacyMatches).length,
    [legacyMatches],
  );

  return (
    <section className="boss-dashboard" aria-label="老板视角决策页">
      <MatchdayHeader dayView={dayView} release={release} />
      <TrustStrip performance={performance} leagueRows={leagueRows} />
      <HealthStrip dayView={dayView} />
      {isWorldCup(dayView) ? (
        <aside className="model-caveat">
          世界杯输出按 staging 保守展示：当前拟合模型在五大俱乐部离线验证，尚未对国际赛完成独立验证。
        </aside>
      ) : null}

      <div className="boss-workspace">
        <section className="schedule-board" aria-label="赛前决策与赛程">
          <FilterControls
            filter={scheduleFilter}
            onFilterChange={setScheduleFilter}
          />
          {visibleCards.length ? (
            <>
              <ScheduleSection
                title="已形成建议"
                hint="所有符合完整数据与决策条件的比赛均展示"
                cards={worthWatching}
                empty="现在没有已形成建议的比赛 · 当前分歧门槛未通过"
                selectedFixtureId={selectedCard?.fixture_id}
                legacyById={legacyById}
                now={now}
                onSelect={setSelectedFixtureId}
              />
              <ScheduleSection
                title="赛中 / 刚开赛"
                hint="开球后仍保留在台面，避免临场比赛突然消失"
                cards={liveCards}
                empty="当前没有赛中或刚开赛比赛"
                selectedFixtureId={selectedCard?.fixture_id}
                legacyById={legacyById}
                now={now}
                onSelect={setSelectedFixtureId}
              />
              <ScheduleSection
                title="今日赛程"
                hint="严格按开球时间；未就绪比赛留在原时间位置并说明原因"
                cards={filteredTodaySchedule}
                empty="今日没有符合筛选条件的待赛比赛"
                selectedFixtureId={selectedCard?.fixture_id}
                legacyById={legacyById}
                now={now}
                onSelect={setSelectedFixtureId}
              />
              <ScheduleSection
                title="未来赛程"
                hint="明天及以后先折叠看摘要，临近窗口再进入今日赛程"
                cards={filteredFutureSchedule.slice(0, 8)}
                empty="未来窗口暂无待赛比赛"
                selectedFixtureId={selectedCard?.fixture_id}
                legacyById={legacyById}
                now={now}
                onSelect={setSelectedFixtureId}
                collapsed
              />
              <CoverageFoldout dayView={dayView} />
            </>
          ) : (
            <div className="decision-empty">
              <strong>未来 36 小时暂无比赛</strong>
              <span>
                {nextVisibleKickoff(dayView.cards)
                  ? `下一场 ${fmtTime(nextVisibleKickoff(dayView.cards))} 进入窗口后自动出现。`
                  : "白名单赛程进入 read-model 后会自动显示。"}
              </span>
            </div>
          )}
        </section>
        <aside className="boss-side-rail" aria-label="证据与信任层">
          <EvidencePanel
            cards={visibleCards}
            selectedCard={selectedCard}
            settledCount={settledCount}
          />
          <VerificationPreview
            matches={legacyMatches}
            performance={performance}
          />
          <LeaguePerformancePreview
            rows={leagueRows}
            performance={performance}
          />
        </aside>
      </div>

      <footer className="boss-disclaimer">
        分析参考·非稳赢·不构成投注建议
      </footer>
    </section>
  );
}
