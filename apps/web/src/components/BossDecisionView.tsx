import { useEffect, useMemo, useRef, useState } from "react";
import {
  fmtTime,
  formatLine,
  formatOdds,
  localizedTeamName,
  localizedTeamTitle,
  translateCompetition,
} from "../lib/formatters";
import { asArray, asRecord, textValue } from "../lib/normalize";
import {
  DashboardHttpError,
  fetchFixtureAuditDetails,
  fetchFixtureOddsTimeline,
} from "../lib/dashboardApi";
import type {
  DashboardDayView,
  DashboardDayViewCard,
  DashboardMatchCard,
  DashboardPerformance,
  FixtureAuditDetails,
  ReleaseSyncState,
} from "../types/dashboard";
import { RecommendationCard } from "./RecommendationCard";

const TIER_LABELS: Record<string, string> = {
  RECOMMEND: "正式可锁",
  ANALYSIS_PICK: "验证推荐",
  WATCH: "观察",
  NOT_READY: "未就绪",
  SKIP: "跳过",
};

const DATA_STATUS_LABELS: Record<string, string> = {
  READY: "数据齐",
  PARTIAL: "部分就绪",
  STALE: "数据陈旧",
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
  MODEL_FAIR_LINE_UNAVAILABLE: "模型公平盘不可用",
  NO_EDGE: "模型与市场线差不足",
  FORWARD_EVIDENCE_ACCUMULATING: "前向证据积累中",
  NO_SUPPORTED_MARKET: "无可支持市场",
  FIXTURE_NOT_UPCOMING: "非赛前窗口",
};

const ACTION_LABELS: Record<string, string> = {
  WAIT_LINEUPS: "等首发",
  WAIT_MARKET: "等盘口",
  WAIT_ODDS: "等赔率",
  WAIT_NEXT_REFRESH: "等下一次刷新",
  REVIEW_DATA_PIPELINE: "检查数据链路",
  KEEP_WATCHING: "继续观察",
};

const BLOCKER_LABELS: Record<string, string> = {
  MISSING_ANALYSIS_CARD: "缺少分析卡",
  ALL_MARKETS_SKIP: "所有市场均为跳过",
  MISSING_MARKET_OBSERVATIONS: "盘口观察不足",
  MISSING_BOOKMAKER_QUOTES: "bookmaker 报价不足",
  MISSING_ODDS_TIMELINE: "赔率时间线不足",
  MISSING_XG: "xG/独立信号不足",
  MISSING_LINEUPS: "首发未出",
  MISSING_SCORE_MATRIX: "比分矩阵不足",
  MISSING_MODEL_PROBABILITIES: "模型概率缺失",
  MISSING_MARKET_PROBABILITIES: "市场概率缺失",
  SCORE_MARKET_UNAVAILABLE: "比分市场不可用",
  ODDS_UNAVAILABLE: "赔率未返回",
  FIXTURE_NOT_UPCOMING: "非赛前窗口",
  UNSUPPORTED_MARKET: "不支持的盘口",
  DATA_MISSING_XG: "缺关键 xG",
  PROVIDER_EMPTY_OR_UNAVAILABLE: "模型历史特征尚未物化",
  MODEL_FAIR_LINE_UNAVAILABLE: "模型公平盘不可用",
  NO_EDGE: "模型与市场线差不足 0.25 球",
  FORWARD_EVIDENCE_ACCUMULATING: "该联赛该市场的前向证据积累中",
};

const MARKET_ANCHOR_MIN_DIVERGENCE = Number(import.meta.env.VITE_W2_MARKET_ANCHOR_MIN_DIVERGENCE ?? 0.25);

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

function actionLabel(value?: string | null): string {
  if (!value) return "等待下一次刷新";
  return ACTION_LABELS[value] ?? "继续观察";
}

function blockerLabel(value?: string | null): string {
  if (!value) return "";
  return BLOCKER_LABELS[value] ?? REASON_LABELS[value] ?? value.replace(/_/g, " ").toLowerCase();
}

function analysisGateLabel(value: string): string {
  return {
    ELIGIBLE: "分析资格已满足",
    ACCUMULATING: "前向证据积累中",
    NO_EDGE: "线差不足",
    BLOCKED: "分析资格受阻",
  }[value] ?? "待评估";
}

function analysisMarketLabel(value: string): string {
  return value === "ASIAN_HANDICAP" ? "让球" : value === "TOTALS" ? "大小球" : "市场待定";
}

function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function uniqueItems(items: string[]): string[] {
  return [...new Set(items.map((item) => item.trim()).filter(Boolean))];
}

function isWorldCup(dayView: DashboardDayView): boolean {
  return dayView.cards.some((card) => card.competition_id === "world_cup_2026" || (card.competition_name ?? "").toLowerCase().includes("world cup"));
}

function l1OneLiner(card: DashboardDayViewCard): string {
  const oneLiner = (card.one_liner ?? "").trim();
  if (oneLiner && !oneLiner.includes("缺少人话解释") && !/[A-Z0-9_]{6,}/.test(oneLiner)) {
    return oneLiner;
  }
  if (card.decision_tier === "ANALYSIS_PICK" && card.pick) {
    return `${tierLabel(card.decision_tier)}：${marketPickLabel(card)}。`;
  }
  return nonRecommendationReasons(card)[0] ?? `${reasonLabel(card.reason_code)}，${actionLabel(card.action)}。`;
}

function nonRecommendationReasons(card: DashboardDayViewCard): string[] {
  if (["RECOMMEND", "ANALYSIS_PICK"].includes(card.decision_tier)) {
    return card.decision_tier === "RECOMMEND"
      ? ["已达到正式推荐口径，等待赛后结算验证。"]
      : ["当前是分析推荐，尚未开放为正式推荐；赛后结果会进入前向验证。"];
  }
  const reasons: string[] = [];
  const analysisGate = asRecord(card.analysis_gate);
  const gateBlockers = asArray(analysisGate.blockers)
    .map((value) => textValue(value))
    .filter(Boolean);
  const analysis = asRecord(card.analysis_readiness);
  const blockers = [
    ...asArray(analysis.blockers),
    ...(card.missing_inputs ?? []),
    ...(card.missing_fields ?? []),
  ].map((value) => textValue(value)).filter(Boolean);

  for (const blocker of gateBlockers) {
    reasons.push(blockerLabel(blocker));
  }
  const advisories = asArray(analysisGate.advisories)
    .map((value) => textValue(value))
    .filter(Boolean);
  if (advisories.includes("LINEUPS_PENDING")) {
    reasons.push("首发待公布是可选增强提示；当前球员影响未建模，不会单独阻断或改变分析方向。");
  }

  if (card.reason_code === "EDGE_INSUFFICIENT") {
    reasons.push("模型-市场分歧没有达到高亮门槛，当前不输出方向。");
  }
  if (card.reason_code === "LINEUPS_PENDING") {
    reasons.push("首发待公布不属于分析硬门；请同时查看真正的盘口、模型和数据阻断项。");
  }
  if (card.reason_code && !["EDGE_INSUFFICIENT", "LINEUPS_PENDING"].includes(card.reason_code)) {
    reasons.push(`${reasonLabel(card.reason_code)}，${actionLabel(card.action)}。`);
  }

  for (const blocker of blockers) {
    if (blocker === "MISSING_LINEUPS") {
      reasons.push("首发待公布仅影响信息完整度；当前模型不使用球员影响，因此不改变推荐。");
    } else if (blocker === "MISSING_XG") {
      reasons.push("xG/独立信号不足，模型侧证据不够。");
    } else if (blocker === "MISSING_SCORE_MATRIX") {
      reasons.push("比分矩阵不足，暂时不给比分型结论。");
    } else if (blocker === "MISSING_ODDS_TIMELINE") {
      reasons.push("赔率时间线不足，无法判断开盘到现价的变化质量。");
    } else if (blocker === "MISSING_MARKET_PROBABILITIES") {
      reasons.push("市场概率缺失，不能做市场锚定判断。");
    } else if (blocker === "MISSING_MODEL_PROBABILITIES") {
      reasons.push("模型概率缺失，只能保留观察。");
    } else {
      reasons.push(blockerLabel(blocker));
    }
  }

  const divergence = asRecord(card.model_market_divergence);
  const divergenceStatus = textValue(divergence.status).toUpperCase();
  const directionAllowed = divergence.direction_allowed === true || textValue(divergence.direction_allowed).toLowerCase() === "true";
  const magnitude = numericValue(divergence.magnitude);
  if (divergenceStatus === "INSUFFICIENT") {
    reasons.push("模型与市场没有形成足够分歧，当前只是观察。");
  }
  if (divergenceStatus === "UNVALIDATED") {
    reasons.push("模型适用性未验证，方向只能进入证据积累。");
  }
  if (magnitude != null && magnitude < MARKET_ANCHOR_MIN_DIVERGENCE) {
    reasons.push(`线差 ${magnitude.toFixed(2)} < ${MARKET_ANCHOR_MIN_DIVERGENCE.toFixed(2)}，未达分歧雷达门槛。`);
  }
  if (!directionAllowed && card.probability_source === "MARKET_DEVIG") {
    reasons.push("当前方向继续积累前向证据。");
  }

  const scoreline = scorelineStatusText(card);
  if (!scoreline.hasPicks && scoreline.message !== "比分模拟暂无可展示结果。") {
    reasons.push(scoreline.message);
  }
  if (!reasons.length) {
    reasons.push("没有达到 ANALYSIS_PICK / RECOMMEND 门槛，保留观察。");
  }
  return uniqueItems(reasons).slice(0, 5);
}

function optionalEnrichmentStatements(card: DashboardDayViewCard): string[] {
  const lineups = card.optional_enrichment?.lineups;
  const playerValue = card.optional_enrichment?.player_value;
  const lineupText = lineups?.affects_estimate
    ? "首发增强已应用于估计"
    : lineups?.status === "AVAILABLE_NOT_MODELED"
      ? "首发已获取，仅作信息增强，不参与当前模型"
      : "首发待公布，不阻断当前分析，也不会触发自动改向";
  const playerText = playerValue?.affects_estimate
    ? "球员价值增强已应用于估计"
    : playerValue?.status === "AVAILABLE_NOT_MODELED"
      ? "球队/球员价值已获取，但尚未通过独立验证"
      : "球员影响模型未启用，净调整为 0";
  return [lineupText, playerText];
}

function scorelineItems(card: DashboardDayViewCard): DashboardDayViewCard["scoreline_picks"] {
  if (card.scoreline_reference?.direction_scorelines?.length) return card.scoreline_reference.direction_scorelines;
  if (isReadyRecommendation(card)) return [];
  if (card.scoreline_reference?.top_scorelines?.length) return card.scoreline_reference.top_scorelines;
  return card.scoreline_picks ?? [];
}

function scorelineItemText(pick: { scoreline?: string }): string {
  return `${pick.scoreline}`;
}

function scorelineAuditText(pick: { scoreline?: string; probability_label?: string | null }): string {
  return `${pick.scoreline}${pick.probability_label ? ` ${pick.probability_label}` : ""}`;
}

function scorelineStatusText(card: DashboardDayViewCard): { message: string; hasPicks: boolean } {
  const picks = scorelineItems(card).filter((pick) => pick.scoreline);
  if (picks.length) {
    return {
      hasPicks: true,
      message: `模拟比分参考：${picks.slice(0, 3).map(scorelineItemText).join(" / ")}`,
    };
  }
  const readiness = card.scoreline_readiness;
  const readinessReason = blockerLabel(readiness?.reason);
  if (readinessReason) return { hasPicks: false, message: `比分模拟未显示：${readinessReason}` };
  const shadow = asRecord(card.pricing_shadow);
  const simulation = asRecord(shadow.simulation);
  const simulationStatus = textValue(simulation.status, textValue(shadow.simulation_status));
  if (simulationStatus && simulationStatus !== "READY") {
    return { hasPicks: false, message: `比分模拟未显示：${blockerLabel(simulationStatus) || statusCn(simulationStatus)}` };
  }
  return { hasPicks: false, message: "比分模拟暂无可展示结果。" };
}

function oddsSummary(card: DashboardDayViewCard): string | null {
  const odds = asRecord(card.current_odds);
  const ah = asRecord(odds.ah);
  const ou = asRecord(odds.ou);
  const rows: string[] = [];
  if (Object.keys(ah).length) {
    const homeLine = textValue(ah.home_display_line_cn) || signedLine("主", ah.home_line);
    const awayLine = textValue(ah.away_display_line_cn) || signedLine("客", ah.away_line);
    const homePrice = formatOdds(ah.home_price);
    const awayPrice = formatOdds(ah.away_price);
    rows.push(`让球 ${homeLine} @${homePrice} / ${awayLine} @${awayPrice}`);
  }
  if (Object.keys(ou).length) {
    const line = textValue(ou.line) || textValue(ou.over_line) || textValue(ou.under_line);
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

function probabilitySummaryForMarket(card: DashboardDayViewCard, markets: Record<string, unknown>, market: string): string | null {
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

function ahProbabilitySummary(card: DashboardDayViewCard, markets: Record<string, unknown>): string | null {
  const ah = asRecord(markets.ah);
  const ahProbabilities = asRecord(ah.probabilities);
  if (Object.keys(ahProbabilities).length) {
    const home = probabilityPercent(ahProbabilities.HOME_AH);
    const away = probabilityPercent(ahProbabilities.AWAY_AH);
    const odds = asRecord(card.current_odds);
    const ahOdds = asRecord(odds.ah);
    const homeLine = displayLineForTeam(localizedTeamName(card, "home"), ahOdds.home_line, textValue(ahOdds.home_display_line_cn));
    const awayLine = displayLineForTeam(localizedTeamName(card, "away"), ahOdds.away_line, textValue(ahOdds.away_display_line_cn));
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

function oneXTwoProbabilitySummary(markets: Record<string, unknown>): string | null {
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
  const refresh = card.data_refresh ?? {};
  const odds = textValue(refresh.odds_status, Object.keys(asRecord(card.current_odds)).length ? "READY" : "WAITING");
  const lineups = textValue(refresh.lineups_status, textValue(asRecord(card.data_readiness).lineups_status, "UNKNOWN"));
  const xg = textValue(refresh.xg_status, textValue(asRecord(card.data_readiness).xg_status, "UNKNOWN"));
  return `盘口 ${statusCn(odds)} · 首发 ${statusCn(lineups)} · xG ${statusCn(xg)}`;
}

function applicabilityLabel(card: DashboardDayViewCard): string {
  const gate = asRecord(card.analysis_gate);
  const provenance = card.scoreline_reference?.distribution_provenance;
  if (textValue(gate.status).toUpperCase() === "ELIGIBLE" && provenance?.model_family) {
    return modelFamilyLabel(provenance.model_family);
  }
  const diagnostics = asRecord(card.diagnostics);
  const explicit = textValue(diagnostics.model_applicability) || textValue(asRecord(card.model_market_divergence).calibration_status);
  if (explicit === "UNVALIDATED") return "模型未验证";
  if (explicit === "INSUFFICIENT") return "样本不足";
  if (explicit) return explicit.replace(/_/g, " ");
  if ((card.competition_id ?? "").includes("world_cup")) return "国际赛未独立验证";
  return "按联赛校准状态";
}

function modelFamilyLabel(value: string): string {
  const normalized = value.toUpperCase();
  if (normalized === "R4_1_CALIBRATED") return "联赛校准模型已加载";
  if (normalized === "FITTED_CALIBRATED") return "联赛拟合模型已加载";
  if (normalized === "GOALS_ELO_FALLBACK") return "进球与评分备用模型";
  return "独立模型已加载";
}

function probabilitySourceLabel(card: DashboardDayViewCard): string {
  if (card.probability_source === "MARKET_DEVIG") return "市场锚定";
  if (card.probability_source === "MODEL_FALLBACK") return "模型回退";
  return "概率来源待确认";
}

function marketSourceLabel(card: DashboardDayViewCard): string {
  if (card.probability_source !== "MARKET_DEVIG") return "无盘口概率";
  const odds = asRecord(card.current_odds);
  const preferred = card.pick?.market === "TOTALS" ? asRecord(odds.ou) : asRecord(odds.ah);
  const source = textValue(preferred.source) || textValue(preferred.bookmaker);
  if (source) return `${source} · POWER 去水`;
  return "主线共识盘 · POWER 去水";
}

function divergenceLabel(card: DashboardDayViewCard): string {
  const gate = asRecord(card.analysis_gate);
  const gateStatus = textValue(gate.status).toUpperCase();
  const fairLine = numericValue(gate.fair_line);
  const marketLine = numericValue(gate.market_line);
  if (gateStatus === "ELIGIBLE" && fairLine != null && marketLine != null) {
    return `模型与市场线差 ${Math.abs(fairLine - marketLine).toFixed(2)}`;
  }
  if (gateStatus === "NO_EDGE") return "模型与市场线差不足";
  if (gateStatus === "BLOCKED") return "独立模型或盘口尚未就绪";
  const divergence = asRecord(card.model_market_divergence);
  const magnitude = typeof divergence.magnitude === "number" ? divergence.magnitude : null;
  const status = textValue(divergence.status, "UNKNOWN");
  if (magnitude != null) return `模型与市场线差 ${magnitude.toFixed(2)}`;
  if (status === "INSUFFICIENT") return "模型分歧不足";
  if (status === "UNVALIDATED") return "模型未验证";
  if (status === "READY") return "分歧可读";
  return "分歧待确认";
}

function signedLine(prefix: string, value: unknown): string {
  const line = formatLine(value);
  return line === "-" ? `${prefix} --` : `${prefix} ${line}`;
}

function statusCn(value: string): string {
  const status = value.toUpperCase();
  if (status === "READY") return "已就绪";
  if (status === "WAITING") return "等待";
  if (status === "PROVIDER_EMPTY") return "数据源暂未返回";
  if (status === "INSUFFICIENT_HISTORY") return "样本不足";
  if (status === "NOT_REQUESTED") return "未请求";
  if (status === "UNKNOWN") return "未知";
  return value;
}

function marketPickLabel(card: DashboardDayViewCard): string {
  if (!card.pick) return "等待盘口";
  const market = card.pick.market ? marketLabel(card.pick.market) : "市场";
  const selection = card.pick.selection ? pickSelectionLabel(card, card.pick.selection) : "方向待确认";
  const line = displayableLine(card.pick.line) ? ` ${formatLine(card.pick.line)}` : "";
  const odds = card.pick.odds != null ? ` @ ${formatOdds(card.pick.odds)}` : "";
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

function pickSelectionLabel(card: DashboardDayViewCard, value: string): string {
  if (value === "HOME_AH") return localizedTeamName(card, "home");
  if (value === "AWAY_AH") return localizedTeamName(card, "away");
  return selectionLabel(value);
}

function displayLineForTeam(team: string, line: unknown, fallback?: string | null): string {
  if (fallback) {
    return fallback.replace("主队", team).replace("客队", team);
  }
  const formatted = formatLine(line);
  return formatted === "-" ? team : `${team} ${formatted}`;
}

function teamLabel(card: DashboardDayViewCard): string {
  const home = localizedTeamName(card, "home");
  const away = localizedTeamName(card, "away");
  return `${home} vs ${away}`;
}

function competitionLabel(card: DashboardDayViewCard): string {
  return translateCompetition(card.competition_name || card.competition_id || "比赛");
}

function referenceTime(dayView: DashboardDayView): Date {
  const raw = dayView.generated_at || dayView.freshness.last_refresh;
  const parsed = raw ? new Date(raw) : new Date();
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
}

function isSameShanghaiDate(left?: string | null, right?: string | null): boolean {
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

function kickoffDateLabel(value?: string | null): string {
  if (!value) return "日期待定";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "日期待定";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function isPreMatch(card: DashboardDayViewCard): boolean {
  const status = (card.status ?? "").toUpperCase();
  return !["FT", "AET", "PEN", "FINISHED", "CANCELLED", "POSTPONED"].includes(status);
}

function isLiveOrRecentlyStarted(card: DashboardDayViewCard, now: Date): boolean {
  if (!isPreMatch(card)) return false;
  const status = (card.status ?? "").toUpperCase();
  if (["LIVE", "1H", "2H", "HT", "ET", "BT", "P"].includes(status)) return true;
  const minutes = minutesUntil(card, now);
  return minutes != null && minutes <= 0 && minutes >= -150;
}

function isReadyRecommendation(card: DashboardDayViewCard): boolean {
  return ["RECOMMEND", "ANALYSIS_PICK"].includes(card.decision_tier);
}

function orderedByKickoff(cards: DashboardDayViewCard[]): DashboardDayViewCard[] {
  return [...cards].sort((left, right) => {
    return (left.kickoff_utc ?? "").localeCompare(right.kickoff_utc ?? "");
  });
}

function orderedForTriage(cards: DashboardDayViewCard[]): DashboardDayViewCard[] {
  const priority: Record<string, number> = {
    RECOMMEND: 0,
    ANALYSIS_PICK: 1,
    WATCH: 2,
    NOT_READY: 3,
    SKIP: 4,
  };
  return [...cards].sort((left, right) => {
    const tierDelta = (priority[left.decision_tier] ?? 9) - (priority[right.decision_tier] ?? 9);
    if (tierDelta) return tierDelta;
    return (left.kickoff_utc ?? "").localeCompare(right.kickoff_utc ?? "");
  });
}

function filterScheduleCards(cards: DashboardDayViewCard[], filter: ScheduleFilter): DashboardDayViewCard[] {
  if (filter === "recommended") return cards.filter(isReadyRecommendation);
  if (filter === "hide-not-ready") return cards.filter((card) => !["NOT_READY", "SKIP"].includes(card.decision_tier));
  return cards;
}

function settledMatches(matches: DashboardMatchCard[]): DashboardMatchCard[] {
  return matches
    .filter((match) => {
      const settlement = match.validation?.settlement ?? match.locked_pre_match_recommendation?.settlement?.status;
      return settlement && !["PENDING", "WAITING_RESULT", "NO_BET", "UNKNOWN"].includes(String(settlement));
    })
    .sort((left, right) => (right.kickoff_utc ?? "").localeCompare(left.kickoff_utc ?? ""));
}

function settlementLabel(value?: string | null): string {
  if (value === "HIT" || value === "SETTLED") return "命中";
  if (value === "MISS") return "未中";
  if (value === "PUSH") return "走水";
  if (value === "VOID") return "作废";
  return "待追踪";
}

function buildLeaguePerformanceRows(matches: DashboardMatchCard[]): LeaguePerformanceRow[] {
  const rows = new Map<string, LeaguePerformanceRow>();
  for (const match of matches) {
    const validation = match.validation;
    if (!validation || !["HIT", "MISS", "PUSH", "VOID"].includes(validation.settlement)) continue;
    const key = match.competition_id || match.competition_name || "unknown";
    const row = rows.get(key) ?? {
      key,
      label: translateCompetition(match.competition_name || match.competition_id || "联赛"),
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
    row.roiUnits += typeof validation.profit_units === "number" ? validation.profit_units : 0;
    rows.set(key, row);
  }
  return [...rows.values()].sort((left, right) => right.sampleSize - left.sampleSize || left.label.localeCompare(right.label));
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
  const kickoff = card.kickoff_utc ? new Date(card.kickoff_utc) : null;
  const next = new Date(card.next_eval_at);
  const delta = kickoff && !Number.isNaN(kickoff.getTime()) && !Number.isNaN(next.getTime())
    ? Math.round((next.getTime() - kickoff.getTime()) / 60000)
    : null;
  return `${fmtTime(card.next_eval_at)}${delta != null ? ` (${delta >= 0 ? "+" : ""}${delta})` : ""}`;
}

function rowMarketSummary(card: DashboardDayViewCard): string {
  if (card.pick) return marketPickLabel(card);
  const odds = oddsSummary(card);
  if (odds) return odds.split(" · ")[0] ?? odds;
  return reasonLabel(card.reason_code);
}

function reasonSummary(cards: DashboardDayViewCard[]): Array<{ label: string; count: number }> {
  const counter = new Map<string, number>();
  for (const card of cards) {
    const label = reasonLabel(card.reason_code);
    if (label === "暂无阻塞原因") continue;
    counter.set(label, (counter.get(label) ?? 0) + 1);
  }
  return [...counter.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}

function diagnosticRows(card: DashboardDayViewCard): Array<[string, string]> {
  const diagnostics = asRecord(card.diagnostics);
  const readiness = asRecord(diagnostics.data_readiness_summary);
  const missingFields = card.missing_fields ?? [];
  const staleFields = card.stale_fields ?? [];
  const scoreline = scorelineStatusText(card);
  return [
    ["decision", tierLabel(card.decision_tier)],
    ["data", dataStatusLabel(card.data_status)],
    ["reason", reasonLabel(card.reason_code)],
    ["action", actionLabel(card.action)],
    ["next_eval_at", textValue(card.next_eval_at, "-")],
    ["probability_source", probabilitySourceLabel(card)],
    ["model_market_divergence", divergenceLabel(card)],
    ["model_applicability", applicabilityLabel(card)],
    ["scoreline", scoreline.message],
    ["scoreline_readiness", textValue(card.scoreline_readiness?.status, "-")],
    ["card_hash", textValue(card.card_hash, "-").slice(0, 16)],
    ["missing", missingFields.join(", ") || "-"],
    ["stale", staleFields.join(", ") || "-"],
    ["readiness", textValue(readiness.data_status, "-")],
  ];
}

function evidenceStatements(card: DashboardDayViewCard): string[] {
  const gate = asRecord(card.analysis_gate);
  const gateMarket = analysisMarketLabel(textValue(gate.market));
  const gateStatus = analysisGateLabel(textValue(gate.status));
  const fairLine = numericValue(gate.fair_line);
  const marketLine = numericValue(gate.market_line);
  const gateSummary = fairLine != null && marketLine != null
    ? `${gateMarket} ${gateStatus}; 公平盘 ${fairLine.toFixed(2)} / 市场盘 ${marketLine.toFixed(2)}`
    : `${gateMarket} ${gateStatus}`;
  return [
    `盘口源:${marketSourceLabel(card)}`,
    `决策:${tierLabel(card.decision_tier)}; ${l1OneLiner(card)}`,
    `数据:${dataStatusLabel(card.data_status)}; ${trustSignalSummary(card)}`,
    `模型:${applicabilityLabel(card)}; ${divergenceLabel(card)}`,
    `分析资格:${gateSummary}`,
    `可选增强:${optionalEnrichmentStatements(card).join("；")}`,
    `模拟:${scorelineStatusText(card).message}`,
    `下一步:${actionLabel(card.action)}; ${card.next_eval_at ? fmtTime(card.next_eval_at) : "待定"}再看`,
  ];
}

function evidenceOverviewStatements(card: DashboardDayViewCard): string[] {
  const statements = evidenceStatements(card);
  return [statements[0], statements[2], statements[3], statements[4], statements[5], statements[7]].filter(Boolean);
}

function nextVisibleKickoff(cards: DashboardDayViewCard[]): string | null {
  return cards
    .filter((card) => card.kickoff_utc && isPreMatch(card))
    .sort((left, right) => (left.kickoff_utc ?? "").localeCompare(right.kickoff_utc ?? ""))[0]?.kickoff_utc ?? null;
}

export function MatchdayHeader({
  dayView,
}: {
  dayView: DashboardDayView;
  release?: ReleaseSyncState;
}) {
  const upcoming = dayView.cards.filter(isPreMatch).length;
  const truth = cardTruthCounts(dayView.cards);
  return (
    <header className="boss-commandbar">
      <div className="boss-brand">
        <strong>FOOTBALL</strong>
        <span>INTELLIGENCE</span>
      </div>
      <button className="boss-view-select" type="button">Boss View</button>
      <div className="boss-command-meta">
        <span>日期 <strong>{dayView.football_day}</strong></span>
        <span>环境 <strong>{dayView.environment}</strong></span>
        <span>最后刷新 <strong>{dayView.freshness.last_refresh ? fmtTime(dayView.freshness.last_refresh) : "--:--"}</strong></span>
        <span>下次刷新 <strong>{dayView.freshness.next_refresh_tick ? fmtTime(dayView.freshness.next_refresh_tick) : "待定"}</strong></span>
        <span>即将比赛 <strong>{upcoming}</strong></span>
        <span>验证推荐 <strong>{truth.analysisPick}</strong></span>
        <span>正式推荐 <strong>{truth.recommend}</strong></span>
        <span>数据阻塞 <strong>{truth.blocked}</strong></span>
      </div>
    </header>
  );
}

export function DecisionCounts({ dayView, performance }: { dayView: DashboardDayView; performance?: DashboardPerformance }) {
  const lockLabel = dayView.environment === "production" ? "正式可锁" : "可锁审批";
  const validationRecommendations = dayView.cards.filter((card) => card.decision_tier === "ANALYSIS_PICK").length;
  const metrics = [
    [lockLabel, dayView.counts.lock_eligible, "审批候选由 DecisionCard 给出"],
    ["验证推荐", validationRecommendations, "单独追踪，不计入正式战绩"],
    ["正式战绩", performance?.official?.sample_size ?? performance?.sample_size ?? 0, `命中率 ${percent(performance?.official?.hit_rate ?? performance?.hit_rate)}`],
    ["今日待评估", dayView.counts.not_ready + dayView.counts.watch + dayView.counts.skip, "按开球时间继续观察"],
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
    const reasons = nonRecommendationReasons(selectedCard);
    const scoreline = scorelineStatusText(selectedCard);
    const scorelines = scorelineItems(selectedCard).filter((pick) => pick.scoreline).slice(0, 3);
    return (
      <aside className="evidence-panel" aria-label="选中比赛证据预览">
        <span>选中比赛证据</span>
        <h2 title={`${localizedTeamTitle(selectedCard, "home") ?? localizedTeamName(selectedCard, "home")} vs ${localizedTeamTitle(selectedCard, "away") ?? localizedTeamName(selectedCard, "away")}`}>
          {teamLabel(selectedCard)}
        </h2>
        <p>{marketSourceLabel(selectedCard)}</p>
        <div className="trust-grid">
          {evidenceOverviewStatements(selectedCard).map((statement) => (
            <strong key={statement}>{statement}</strong>
          ))}
        </div>
        <div className="evidence-section">
          <strong>
            {selectedCard.decision_tier === "RECOMMEND"
              ? "正式推荐依据"
              : selectedCard.decision_tier === "ANALYSIS_PICK"
                ? "为什么选择这个方向"
                : "为什么当前只观察"}
          </strong>
          <ul>
            {(selectedCard.decision_tier === "ANALYSIS_PICK"
              ? [evidenceStatements(selectedCard)[4]]
              : reasons).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
        <div className="evidence-section">
          <strong>可选增强状态</strong>
          <ul>
            {optionalEnrichmentStatements(selectedCard).map((statement) => (
              <li key={statement}>{statement}</li>
            ))}
          </ul>
        </div>
        <div className="evidence-section">
          <strong>方向比分与模型审计</strong>
          <p>{scoreline.message}</p>
          {scorelines.length ? (
            <div className="boss-scoreline-picks">
              {scorelines.map((pick) => (
                <span key={`${pick.scoreline}-${pick.probability_label ?? ""}`}>{scorelineAuditText(pick)}</span>
              ))}
            </div>
          ) : null}
          {selectedCard.scoreline_reference?.top_scorelines?.length ? (
            <p>全局最高概率比分：{selectedCard.scoreline_reference.top_scorelines.slice(0, 3).map(scorelineAuditText).join(" / ")}</p>
          ) : null}
        </div>
        <div className="tracking-note">
          <span>赛后追踪</span>
          <strong>{selectedCard.outcome_tracked ? "已纳入赛后追踪" : "等待完场后追踪"}</strong>
          <small>验证推荐单独累计，不计入正式推荐战绩；shadow 证据也保持独立。</small>
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
          ? reasons.slice(0, 3).map((reason) => `${reason.label} × ${reason.count}`).join(" · ")
          : "没有阻塞原因时，继续按时间轴观察下一次刷新。"}
      </p>
      <div className="tracking-note">
        <span>赛后验证</span>
        <strong>{settledCount ? `已有 ${settledCount} 条结算样本` : "暂无可展示结算样本"}</strong>
        <small>命中率必须和 ROI、样本量一起看。</small>
      </div>
    </aside>
  );
}

export function DecisionRow({
  card,
  selected,
  now,
  onSelect,
  apiReleaseSha,
}: {
  card: DashboardDayViewCard;
  selected: boolean;
  now: Date;
  onSelect: () => void;
  apiReleaseSha: string;
}) {
  const tierClass = `tier-${card.decision_tier.toLowerCase().replace("_", "-")}`;
  const muted = card.decision_tier === "NOT_READY" || card.decision_tier === "SKIP" || card.data_status === "BLOCKED";
  const scoreline = scorelineStatusText(card);
  const estimateId = card.audit_estimate_id
    ?? card.pick?.estimate_id
    ?? textValue(card.compact_provenance?.estimate_id)
    ?? null;
  const captureHash = card.audit_capture_hash ?? null;
  const auditIdentity = [card.fixture_id, captureHash ?? "NO_CAPTURE", estimateId ?? "NO_ESTIMATE", apiReleaseSha].join(":");
  const auditIdentityRef = useRef(auditIdentity);
  const [audit, setAudit] = useState<FixtureAuditDetails | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<Record<string, unknown> | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState(false);
  useEffect(() => {
    auditIdentityRef.current = auditIdentity;
    setAudit(null);
    setAuditError(null);
    setTimeline(null);
    setTimelineError(false);
  }, [auditIdentity]);
  function loadAudit(): void {
    if (auditLoading || audit) return;
    if (!captureHash) {
      setAuditError("该卡尚无冻结审计快照");
      return;
    }
    const requestedIdentity = auditIdentity;
    setAuditLoading(true);
    setAuditError(null);
    fetchFixtureAuditDetails(card.fixture_id, captureHash, estimateId, apiReleaseSha)
      .then((detail) => {
        if (auditIdentityRef.current === requestedIdentity) setAudit(detail);
      })
      .catch((error: unknown) => {
        if (auditIdentityRef.current !== requestedIdentity) return;
        const status = error instanceof DashboardHttpError ? error.status : 0;
        setAuditError(
          status === 404 ? "该卡尚无冻结审计快照"
            : status === 409 ? "L1/L2 快照身份不一致，请刷新页面"
              : status === 413 ? "审计投影超出安全限制"
                : status === 503 ? "审计源暂不可用"
                  : "L2 技术诊断加载失败",
        );
      })
      .finally(() => {
        if (auditIdentityRef.current === requestedIdentity) setAuditLoading(false);
      });
  }
  function loadTimeline(): void {
    if (timelineLoading || timeline) return;
    const requestedIdentity = auditIdentity;
    setTimelineLoading(true);
    setTimelineError(false);
    fetchFixtureOddsTimeline(card.fixture_id, apiReleaseSha)
      .then((detail) => {
        if (auditIdentityRef.current === requestedIdentity) setTimeline(detail);
      })
      .catch(() => {
        if (auditIdentityRef.current === requestedIdentity) setTimelineError(true);
      })
      .finally(() => {
        if (auditIdentityRef.current === requestedIdentity) setTimelineLoading(false);
      });
  }
  return (
    <article className={`decision-row ${tierClass}${selected ? " is-selected" : ""}${muted ? " is-muted" : ""}`}>
      <button className="decision-row-button" type="button" onClick={onSelect} aria-pressed={selected}>
        <div className="decision-cell decision-time">
          <strong>{fmtTime(card.kickoff_utc)}</strong>
          <span>{kickoffDateLabel(card.kickoff_utc)} · T{minutesUntil(card, now) != null ? `${minutesUntil(card, now)}min` : "--"}</span>
        </div>
        <div className="decision-cell decision-league">
          <span>{competitionLabel(card)}</span>
        </div>
        <div className="decision-cell decision-teams">
          <strong title={`${localizedTeamTitle(card, "home") ?? localizedTeamName(card, "home")} vs ${localizedTeamTitle(card, "away") ?? localizedTeamName(card, "away")}`}>
            {teamLabel(card)}
          </strong>
          {card.decision_tier === "ANALYSIS_PICK" ? null : <span>{l1OneLiner(card)}</span>}
          <small className={scoreline.hasPicks ? "scoreline-mini has-picks" : "scoreline-mini"}>{scoreline.message}</small>
        </div>
        <div className="decision-cell decision-market">
          <span>{rowMarketSummary(card)}</span>
          <small>{marketProbabilitySummary(card) ?? marketSourceLabel(card)}</small>
        </div>
        <div className="decision-cell decision-data">
          <span>{dataStatusLabel(card.data_status)}</span>
          <i aria-hidden="true" />
        </div>
        <div className="decision-cell decision-tier">
          <span className={`tier-badge ${tierClass}`}>{tierLabel(card.decision_tier)}</span>
        </div>
        <div className="decision-cell decision-next">
          <span>{nextEvalLabel(card)}</span>
        </div>
      </button>
      <details className="l2-diagnostics-drawer" onToggle={(event) => {
        if (event.currentTarget.open) loadAudit();
      }}>
        <summary>L2 技术诊断</summary>
        <div className="l2-diagnostics-body">
          {auditLoading ? <p>正在按需加载完整审计信息…</p> : null}
          {auditError ? (
            <div className="l2-load-error">
              <strong>{auditError}</strong>
              <span>L1 决策摘要仍然有效；这不代表没有审计数据。</span>
              <button type="button" onClick={() => {
                setAudit(null);
                loadAudit();
              }}>重试</button>
            </div>
          ) : null}
          {audit ? <RecommendationCard match={audit.match} /> : null}
          {audit ? (
            <details className="l2-raw-audit">
              <summary>完整 provenance / FME / Strict 审计</summary>
              <pre>{JSON.stringify({
                audit: audit.audit,
                integrity: audit.integrity,
                performance: audit.performance,
              }, null, 2)}</pre>
            </details>
          ) : null}
          {audit ? (
            <details className="l2-raw-audit" onToggle={(event) => {
              if (event.currentTarget.open) loadTimeline();
            }}>
              <summary>盘口时间线</summary>
              {timelineLoading ? <p>正在加载盘口时间线…</p> : null}
              {timelineError ? <p>盘口时间线暂不可用；冻结审计不受影响。</p> : null}
              {timeline ? <pre>{JSON.stringify(timeline, null, 2)}</pre> : null}
            </details>
          ) : null}
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

function cardTruthCounts(cards: DashboardDayViewCard[]) {
  return cards.reduce(
    (counts, card) => {
      if (card.decision_tier === "ANALYSIS_PICK") counts.analysisPick += 1;
      if (card.decision_tier === "RECOMMEND") counts.recommend += 1;
      if (card.decision_tier === "WATCH") counts.watch += 1;
      if (card.decision_tier === "NOT_READY") counts.notReady += 1;
      if (card.decision_tier === "SKIP") counts.skip += 1;
      if (card.data_status === "PARTIAL") counts.partial += 1;
      if (card.data_status === "STALE") counts.stale += 1;
      if (card.data_status === "BLOCKED") counts.blocked += 1;
      return counts;
    },
    { analysisPick: 0, recommend: 0, watch: 0, notReady: 0, skip: 0, partial: 0, stale: 0, blocked: 0 },
  );
}

function HealthStrip({ dayView }: { dayView: DashboardDayView }) {
  const truth = cardTruthCounts(dayView.cards);
  const blocked = truth.blocked + truth.stale;
  const headline = blocked
    ? `${blocked} 场数据阻塞`
    : truth.partial
      ? `${truth.partial} 场部分就绪`
      : "比赛数据正常";
  return (
    <section className={`health-strip${blocked ? " has-warning" : ""}`} aria-label="白名单健康状态">
      <strong>{headline}</strong>
      <span>{dayView.active_whitelist_count ?? "--"} 个活跃联赛 · 验证推荐 {truth.analysisPick} · 观察 {truth.watch} · 部分就绪 {truth.partial} · 数据阻塞 {blocked}</span>
      {blocked
        ? <small>仅受阻比赛等待补数；验证推荐和观察比赛继续保留在赛程中。</small>
        : truth.partial
          ? <small>部分就绪不等于阻塞；已满足分析门的比赛仍正常展示。</small>
          : <small>覆盖诊断只在异常时展开。</small>}
    </section>
  );
}

function FilterControls({ filter, onFilterChange }: { filter: ScheduleFilter; onFilterChange: (filter: ScheduleFilter) => void }) {
  const filters: Array<[ScheduleFilter, string]> = [
    ["all", "全部赛程"],
    ["recommended", "只看值得看"],
    ["hide-not-ready", "隐藏未就绪"],
  ];
  return (
    <div className="schedule-controls" aria-label="赛程筛选">
      {filters.map(([id, label]) => (
        <button key={id} type="button" className={filter === id ? "is-active" : ""} onClick={() => onFilterChange(id)} aria-pressed={filter === id}>
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
  now,
  onSelect,
  apiReleaseSha,
  collapsed,
}: {
  title: string;
  hint: string;
  cards: DashboardDayViewCard[];
  empty: string;
  selectedFixtureId?: string | null;
  now: Date;
  onSelect: (fixtureId: string) => void;
  apiReleaseSha: string;
  collapsed?: boolean;
}) {
  return (
    <section className={`schedule-section${collapsed ? " is-collapsed" : ""}${cards.length ? "" : " is-empty"}`} aria-label={title}>
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
              now={now}
              onSelect={() => onSelect(card.fixture_id)}
              apiReleaseSha={apiReleaseSha}
            />
          ))}
        </div>
      ) : (
        <div className="inline-empty">{empty}</div>
      )}
    </section>
  );
}

function TrustStrip({ performance }: { performance?: DashboardPerformance }) {
  const forwardLedger = performance?.forward_ledger;
  const validation = forwardLedger?.outcomes_validation;
  const performanceIntegrity = forwardLedger?.performance_integrity;
  if (performanceIntegrity?.status === "BLOCKED") {
    return (
      <section className="trust-strip" aria-label="赛后信任摘要">
        <strong>近 30 天</strong>
        <span>验证口径校验中，暂不用于决策</span>
      </section>
    );
  }
  const settled = validation?.settled_sample_count ?? 0;
  const validationTotal = forwardLedger?.validation_fixture_count ?? 0;
  const pending = forwardLedger?.validation_pending_fixture_count ?? 0;
  const pendingStatus = forwardLedger?.validation_pending_status;
  const pendingLabel = pendingStatus
    ? [
        `未到结算窗口 ${pendingStatus.pre_settlement_window_fixture_count}`,
        `等官方赛果 ${pendingStatus.awaiting_official_result_fixture_count}`,
        `已有赛果待结算 ${pendingStatus.result_available_unsettled_fixture_count}`,
        pendingStatus.result_source_unavailable_fixture_count
          ? `赛果库不可读 ${pendingStatus.result_source_unavailable_fixture_count}`
          : "",
      ].filter(Boolean).join(" · ")
    : `待分类 ${pending}`;
  return (
    <section className="trust-strip" aria-label="赛后信任摘要">
      <strong>近 30 天</strong>
      <span>验证推荐 {validationTotal} 场</span>
      <span>已结算 {settled} 场</span>
      <span title={pendingLabel}>待结算 {pending} 场（{pendingLabel}）</span>
      <span>
        结算结果 {settled
          ? `${validation?.hit_count ?? 0} 中 · ${validation?.miss_count ?? 0} 未中 · ${validation?.push_count ?? 0} 走水`
          : "积累中"}
      </span>
    </section>
  );
}

function VerificationPreview({ matches, performance }: { matches: DashboardMatchCard[]; performance?: DashboardPerformance }) {
  const forwardLedger = performance?.forward_ledger;
  if (forwardLedger) {
    const validation = forwardLedger.outcomes_validation;
    const performanceIntegrity = forwardLedger.performance_integrity;
    if (performanceIntegrity.status === "BLOCKED") {
      return (
        <section className="verification-preview" aria-label="赛后验证预览">
          <header><span>赛后验证</span><strong>验证口径校验中，暂不用于决策</strong></header>
          <details>
            <summary>L2 完整性阻断</summary>
            <p>冲突 {performanceIntegrity.outcome_conflict_count} · canonical 重复 {performanceIntegrity.canonical_duplicate_count} · candidate 不唯一 {performanceIntegrity.canonical_candidate_nonunique_count} · 身份未匹配 {performanceIntegrity.identity_aware_unmatched_count} · 跨轨 {performanceIntegrity.cross_track_contamination_count}</p>
          </details>
        </section>
      );
    }
    const settled = validation.settled_sample_count;
    return (
      <section className="verification-preview" aria-label="赛后验证预览">
        <header>
          <span>赛后验证</span>
          <strong>
            {settled
              ? `验证结算 ${settled} 条`
              : `已记录 ${forwardLedger.validation_fixture_count} 场验证推荐 · 待结算 ${forwardLedger.validation_pending_fixture_count} 场`}
          </strong>
        </header>
        {settled ? (
          <div className="verification-list">
            <div>
              <span>真实 forward_ledger + outcome</span>
              <strong>
                命中 {validation.hit_count} · 未中 {validation.miss_count} · 走水 {validation.push_count} · 作废 {validation.void_count}
              </strong>
              <small>验证命中率 {percent(validation.hit_rate)} · 不计入正式推荐战绩</small>
            </div>
          </div>
        ) : (
          <p>真实前向比赛已记录，当前验证结算 0 场；暂不显示命中率，不制造战绩。</p>
        )}
        <small>
          L2 审计：前向比赛 {forwardLedger.fixture_count} 场 · 有效双快照 {forwardLedger.double_snapshot_fixture_count} 场
        </small>
        {performanceIntegrity.historical_compatibility_outcome_count > 0 ? (
          <small>历史兼容口径，不属于 corrected evidence</small>
        ) : null}
        <details>
          <summary>L2 outcome 审计</summary>
          <p>原始 outcome 行 {forwardLedger.outcomes_raw_audit.raw_outcome_row_count} · canonical {forwardLedger.outcomes_raw_audit.canonical_outcome_count} · audit-only {forwardLedger.outcomes_raw_audit.audit_only_outcome_count} · 重复审计 {forwardLedger.outcomes_raw_audit.duplicate_audit_row_count} · 身份未匹配 {forwardLedger.outcomes_raw_audit.identity_aware_unmatched_count} · 冲突 {forwardLedger.outcomes_raw_audit.outcome_conflict_count}</p>
          {(forwardLedger.outcomes_by_strategy ?? []).map((row) => (
            <p key={`${row.recommendation_scope}:${row.strategy_version}`}>
              {row.recommendation_scope} · {row.strategy_version} · canonical {row.settled_sample_count}
            </p>
          ))}
        </details>
      </section>
    );
  }
  const settled = settledMatches(matches).slice(0, 5);
  return (
    <section className="verification-preview" aria-label="赛后验证预览">
      <header>
        <span>赛后验证</span>
        <strong>{settled.length ? `最近 ${settled.length} 条` : "暂无结算样本"}</strong>
      </header>
      {settled.length ? (
        <div className="verification-list">
          {settled.map((match) => (
            <div key={match.fixture_id}>
              <span>{fmtTime(match.kickoff_utc)} · {translateCompetition(match.competition_name)}</span>
              <strong>
                <span title={localizedTeamTitle(match, "home")}>{localizedTeamName(match, "home")}</span>
                {" vs "}
                <span title={localizedTeamTitle(match, "away")}>{localizedTeamName(match, "away")}</span>
              </strong>
              <small>{settlementLabel(match.validation?.settlement)} · {match.result?.final_score ?? "比分待同步"} · {match.validation?.closing_line_value ?? "CLV 待接入"}</small>
            </div>
          ))}
        </div>
      ) : (
        <p>完场并结算后，推荐会在这里显示命中、走水、作废和原因码。</p>
      )}
    </section>
  );
}

function LeaguePerformancePreview({ rows, performance }: { rows: LeaguePerformanceRow[]; performance?: DashboardPerformance }) {
  const forwardLedger = performance?.forward_ledger;
  if (forwardLedger) {
    const visibleForwardRows = forwardLedger.by_league
      .filter((row) => row.league !== "world_cup_2026")
      .sort((left, right) => right.fixture_count - left.fixture_count || left.league.localeCompare(right.league))
      .slice(0, 6);
    return (
      <section className="league-performance-preview" aria-label="联赛表现预览">
        <header>
          <span>联赛表现</span>
          <strong>{visibleForwardRows.length ? "真实前向记录" : "样本积累中"}</strong>
        </header>
        {visibleForwardRows.length ? (
          <div className="league-performance-table">
            <div className="league-performance-head">
              <span>联赛</span>
              <span>比赛</span>
              <span>双快照</span>
              <span>影子 CLV</span>
              <span>状态</span>
            </div>
            {visibleForwardRows.map((row) => (
              <div key={row.league}>
                <span>{translateCompetition(row.league)}</span>
                <span>{row.fixture_count}</span>
                <span>{row.double_snapshot_fixture_count || "积累中"}</span>
                <span>{row.clv_shadow_sample_count && row.clv_shadow_median_decimal != null ? `${clvUnits(row.clv_shadow_median_decimal)} · ${row.clv_shadow_sample_count} 样本` : "积累中"}</span>
                <span>{row.settled_sample_count ? `${row.settled_sample_count} 场已结算` : "未结算"}</span>
              </div>
            ))}
          </div>
        ) : (
          <p>真实前向记录还没有足够联赛样本；当前只显示积累状态，不制造胜率。</p>
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
              <span>{percent(row.sampleSize ? row.hitCount / row.sampleSize : null)}</span>
              <span>{units(row.roiUnits)}</span>
              <span>{performanceStatus(row.sampleSize)}</span>
            </div>
          ))}
        </div>
      ) : (
        <p>联赛命中率必须等有足够结算样本后展示；当前只保留占位，不制造胜率。</p>
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
        <span>{nextKickoff ? `下一场 ${fmtTime(nextKickoff)}` : "当前没有下一场"}</span>
      </summary>
      <div className="coverage-foldout-body">
        <p>
          白名单比赛只有进入 DayView/DecisionCard 后才展示；未就绪不会被删掉,会带着原因和下一次评估时间留在赛程里。
        </p>
        <div>
          {reasons.slice(0, 4).map((reason) => (
            <span key={reason.label}>{reason.label} × {reason.count}</span>
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
  onLoadMore,
  loadingMore = false,
  pageNotice,
}: {
  dayView: DashboardDayView;
  legacyMatches: DashboardMatchCard[];
  performance?: DashboardPerformance;
  release?: ReleaseSyncState;
  onLoadMore?: () => void;
  loadingMore?: boolean;
  pageNotice?: string | null;
}) {
  const now = useMemo(() => referenceTime(dayView), [dayView]);
  const [scheduleFilter, setScheduleFilter] = useState<ScheduleFilter>("all");
  const scheduleDay = dayView.selected_football_day || dayView.football_day || dayView.generated_at;
  const activeCards = useMemo(() => orderedByKickoff(dayView.cards.filter(isPreMatch)), [dayView.cards]);
  const worthWatching = useMemo(
    () => orderedForTriage(activeCards.filter((card) => isReadyRecommendation(card) && !isLiveOrRecentlyStarted(card, now))),
    [activeCards, now],
  );
  const worthWatchingIds = useMemo(
    () => new Set(worthWatching.map((card) => card.fixture_id)),
    [worthWatching],
  );
  const liveCards = useMemo(
    () => orderedByKickoff(activeCards.filter((card) => isLiveOrRecentlyStarted(card, now) && !worthWatchingIds.has(card.fixture_id))),
    [activeCards, now, worthWatchingIds],
  );
  const liveIds = useMemo(() => new Set(liveCards.map((card) => card.fixture_id)), [liveCards]);
  const todaySchedule = useMemo(
    () => orderedByKickoff(activeCards.filter((card) => (
      isSameShanghaiDate(card.kickoff_utc, scheduleDay)
      && !worthWatchingIds.has(card.fixture_id)
      && !liveIds.has(card.fixture_id)
    ))),
    [activeCards, liveIds, scheduleDay, worthWatchingIds],
  );
  const futureSchedule = useMemo(
    () => orderedByKickoff(activeCards.filter((card) => (
      !isSameShanghaiDate(card.kickoff_utc, scheduleDay)
      && !worthWatchingIds.has(card.fixture_id)
      && !liveIds.has(card.fixture_id)
    ))),
    [activeCards, liveIds, scheduleDay, worthWatchingIds],
  );
  const filteredTodaySchedule = useMemo(() => filterScheduleCards(todaySchedule, scheduleFilter), [scheduleFilter, todaySchedule]);
  const filteredFutureSchedule = useMemo(() => filterScheduleCards(futureSchedule, scheduleFilter), [futureSchedule, scheduleFilter]);
  const visibleCards = useMemo(
    () => [...worthWatching, ...liveCards, ...filteredTodaySchedule, ...filteredFutureSchedule],
    [filteredFutureSchedule, filteredTodaySchedule, liveCards, worthWatching],
  );
  const firstCard = worthWatching[0] ?? liveCards[0] ?? filteredTodaySchedule[0] ?? filteredFutureSchedule[0];
  const [selectedFixtureId, setSelectedFixtureId] = useState<string | null>(firstCard?.fixture_id ?? null);
  const selectedCard = visibleCards.find((card) => card.fixture_id === selectedFixtureId) ?? firstCard;
  const leagueRows = useMemo(() => buildLeaguePerformanceRows(legacyMatches), [legacyMatches]);
  const settledCount = useMemo(() => settledMatches(legacyMatches).length, [legacyMatches]);

  return (
    <section className="boss-dashboard" aria-label="老板视角决策页">
      <MatchdayHeader dayView={dayView} release={release} />
      <TrustStrip performance={performance} />
      <HealthStrip dayView={dayView} />
      {isWorldCup(dayView) ? (
        <aside className="model-caveat">
          世界杯输出按 staging 保守展示：当前拟合模型在五大俱乐部离线验证，尚未对国际赛完成独立验证。
        </aside>
      ) : null}

      <div className="boss-workspace">
        <section className="schedule-board" aria-label="赛前决策与赛程">
          <FilterControls filter={scheduleFilter} onFilterChange={setScheduleFilter} />
          {visibleCards.length ? (
            <>
              <ScheduleSection
                title="值得看"
                hint="逐场通过分析门才置顶；排序不改变推荐资格"
                cards={worthWatching}
                empty="现在没有值得置顶的比赛 · 不是系统坏了，是分歧门槛未过"
                selectedFixtureId={selectedCard?.fixture_id}
                now={now}
                onSelect={setSelectedFixtureId}
                apiReleaseSha={release?.api_git_sha ?? "UNKNOWN"}
              />
              <ScheduleSection
                title="赛中 / 刚开赛"
                hint="开球后仍保留在台面，避免临场比赛突然消失"
                cards={liveCards}
                empty="当前没有赛中或刚开赛比赛"
                selectedFixtureId={selectedCard?.fixture_id}
                now={now}
                onSelect={setSelectedFixtureId}
                apiReleaseSha={release?.api_git_sha ?? "UNKNOWN"}
              />
              <ScheduleSection
                title="今日赛程"
                hint="严格按开球时间；未就绪比赛留在原时间位置并说明原因"
                cards={filteredTodaySchedule}
                empty="今日没有符合筛选条件的待赛比赛"
                selectedFixtureId={selectedCard?.fixture_id}
                now={now}
                onSelect={setSelectedFixtureId}
                apiReleaseSha={release?.api_git_sha ?? "UNKNOWN"}
              />
              <ScheduleSection
                title="未来赛程"
                hint="明天及以后先折叠看摘要，临近窗口再进入今日赛程"
                cards={filteredFutureSchedule}
                empty="未来窗口暂无待赛比赛"
                selectedFixtureId={selectedCard?.fixture_id}
                now={now}
                onSelect={setSelectedFixtureId}
                apiReleaseSha={release?.api_git_sha ?? "UNKNOWN"}
                collapsed
              />
              <CoverageFoldout dayView={dayView} />
              <div className="dayview-pagination" aria-live="polite">
                <span>已显示 {dayView.cards.length} / {dayView.pagination.total_count} 场</span>
                {dayView.pagination.has_more ? (
                  <button type="button" className="toolbar-button" disabled={loadingMore} onClick={onLoadMore}>
                    {loadingMore ? "加载中…" : "加载更多比赛"}
                  </button>
                ) : null}
                {pageNotice ? <span>{pageNotice}</span> : null}
              </div>
            </>
          ) : (
            <div className="decision-empty">
              <strong>未来 36 小时暂无比赛</strong>
              <span>{nextVisibleKickoff(dayView.cards) ? `下一场 ${fmtTime(nextVisibleKickoff(dayView.cards))} 进入窗口后自动出现。` : "白名单赛程进入 read-model 后会自动显示。"}</span>
            </div>
          )}
        </section>
        <aside className="boss-side-rail" aria-label="证据与信任层">
          <EvidencePanel cards={visibleCards} selectedCard={selectedCard} settledCount={settledCount} />
          <VerificationPreview matches={legacyMatches} performance={performance} />
          <LeaguePerformancePreview rows={leagueRows} performance={performance} />
        </aside>
      </div>

      <details className="boss-system-info">
        <summary>系统信息</summary>
        <span>Web {shortSha(release?.web_git_sha)} · API {shortSha(release?.api_git_sha)}</span>
      </details>
    </section>
  );
}
