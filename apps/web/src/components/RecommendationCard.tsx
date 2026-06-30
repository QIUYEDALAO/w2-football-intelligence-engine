import { fmtTime, formatLine, formatOdds, teamCode, translateCompetition, translateTeam } from "../lib/formatters";
import { matchPhase, minutesToKickoff, phaseLabel, requiresPrematchReview } from "../lib/matchPhase";
import { asRecord, currentOdds, readinessItems, textValue, watchLevel } from "../lib/normalize";
import {
  formatAhDelta,
  formatAhMainLine,
  hasFactorLeanConflict,
  hasValidatedAhCalibration,
  teamScoreLeader,
  unvalidatedAhLean,
} from "../lib/pricingDisplay";
import type { DashboardMatchCard, PricingShadow, PricingShadowFactor, RecommendationPick, RecommendationTier } from "../types/dashboard";
import { OddsMovementMini } from "./OddsMovementMini";
import { SettlementBadge } from "./SettlementBadge";

type VerdictState = "REFERENCE" | "WATCH" | "INSUFFICIENT" | "LOCKED";

const TIER_LABELS: Record<RecommendationTier, string> = {
  FORMAL: "正式推荐",
  CANDIDATE: "候选观察",
  ANALYSIS_PICK: "分析参考",
  WATCH: "观察",
  NO_RECOMMENDATION: "暂无推荐",
};

const BLOCKER_LABELS: Record<string, string> = {
  MISSING_ANALYSIS_CARD: "分析卡缺失",
  ALL_MARKETS_SKIP: "市场暂跳过",
  MISSING_MARKET_OBSERVATIONS: "缺盘口",
  MISSING_BOOKMAKER_QUOTES: "缺报价",
  MISSING_ODDS_TIMELINE: "缺快照",
  MISSING_XG: "xG 富集中",
  MISSING_SCORE_MATRIX: "缺比分矩阵",
  MISSING_MODEL_PROBABILITIES: "缺模型概率",
  MISSING_MARKET_PROBABILITIES: "缺市场概率",
  AS_OF_BLOCKED: "赛前时间点拦截",
  SCORE_MARKET_UNAVAILABLE: "比分未就绪",
  ODDS_UNAVAILABLE: "赔率缺失",
  FIXTURE_NOT_UPCOMING: "非赛前",
  UNSUPPORTED_MARKET: "市场未支持",
  UNKNOWN_BLOCKER: "数据不足",
};

const ACTION_LABELS: Record<string, string> = {
  READY_FOR_ANALYSIS: "可分析",
  WAIT_MARKET_OBSERVATIONS: "等盘口",
  WAIT_BOOKMAKER_QUOTES: "等报价",
  WAIT_ODDS_TIMELINE: "等快照",
  WAIT_XG: "等 xG",
  WAIT_SCORE_MODEL: "等比分模型",
  WAIT_MODEL_PROBABILITIES: "等模型概率",
  WAIT_MARKET_PROBABILITIES: "等市场概率",
  WAIT_FIXTURE_STATUS: "等赛程状态",
  INVESTIGATE_DATA_PIPELINE: "排查数据链路",
};

const MARKET_LABELS: Record<string, string> = {
  ASIAN_HANDICAP: "让球",
  TOTALS: "大小球",
  FIRST_HALF_GOALS: "半场",
  SCORE: "比分",
};

const VERDICT_LABELS: Record<VerdictState, string> = {
  REFERENCE: "分析参考",
  WATCH: "观察",
  INSUFFICIENT: "数据不足",
  LOCKED: "已锁定",
};

const FACTOR_LABELS: Record<string, string> = {
  F3_REST_FITNESS: "体能/休息",
  F4_MATCH_IMPORTANCE: "赛事重要性",
  F5_RECENT_AH_COVER: "近期赢盘",
  F6_H2H: "历史交锋",
  F7_STRENGTH_FORM: "强度/状态",
  F8_SQUAD_VALUE: "球队身价",
  F9_TRUE_XG: "真实 xG",
};

const SIGNAL_GROUP_LABELS: Record<string, string> = {
  team_fixture_history: "赛程历史",
  ratings: "评分",
  xg: "xG",
  h2h: "交锋",
  squad_value: "身价",
};

const FORMAL_BLOCKER_LABELS: Record<string, string> = {
  EDGE_BELOW_FORMAL_THRESHOLD: "盘口价值差未达正式推荐阈值",
  SIMULATION_NOT_READY: "模拟引擎未就绪",
  MISSING_AH_MARKET: "缺少可锁定的全场让球市场盘",
  MISSING_MARKET_AH: "缺少赛前锁定的市场让球盘",
  MISSING_FAIR_AH: "缺少模拟公平让球盘",
  MISSING_DEVIG_BASELINE: "缺少去水后市场基准",
  MISSING_ODDS: "缺少可展示赔率",
  LOW_COVERAGE: "独立信号覆盖不足",
  FACTOR_CONFLICT: "因子方向与盘口价值仍需复核",
  FORMAL_DISABLED: "正式推荐开关未开启",
  NOT_PREMATCH: "非赛前状态",
  FIXTURE_NOT_PREMATCH: "比赛已开赛或已完场",
  FIXTURE_NOT_UPCOMING: "比赛已开赛或已完场",
  AH_EV_BELOW_FORMAL_THRESHOLD: "让球结算期望未达正式推荐阈值",
  MISSING_AH_SETTLEMENT_DISTRIBUTION: "缺少让球结算分布",
  INVALID_AH_EV_INPUTS: "让球期望输入不完整",
  INVALID_AH_SETTLEMENT_DISTRIBUTION: "让球结算分布不可用",
  AH_MARKET_LINE_SIDE_MISMATCH: "全场让球双边盘口方向不一致",
  AH_MARKET_LINE_NOT_CANONICAL: "全场让球盘口未匹配主线",
  AH_MARKET_LINE_NOT_QUARTER: "全场让球盘口格式异常",
  AH_MARKET_PRICE_OUT_OF_RANGE: "全场让球赔率超出可信范围",
  AH_MARKET_PRICE_GAP_TOO_WIDE: "全场让球双边赔率差过大",
  AH_MARKET_UNDERROUND_OR_OVERROUND: "全场让球市场水位异常",
  INSUFFICIENT_INDEPENDENT_SIGNALS: "独立信号不足",
  AS_OF_BLOCKED: "赛前时间点校验未通过",
  LEAKAGE_BLOCKED: "赛前数据防泄漏校验未通过",
  SIMULATION_DIRECTION_CONTRADICTION: "模拟方向与推荐方向不一致",
  REVERSE_FACTOR_VALUE_NOT_STRONG_ENOUGH: "逆因子盘口价值不足",
  SCORELINE_DIRECTION_CONTRADICTION: "模拟比分方向与推荐方向不一致",
  INVALID_AH_MARKET: "全场让球市场不可用",
};

const REQUIRED_SIGNAL_GROUPS = ["xg", "team_fixture_history", "h2h", "squad_value", "ratings"];

function verdictState(match: DashboardMatchCard): VerdictState {
  const phase = matchPhase(match.kickoff_utc, match.status);
  const settlement = match.validation?.settlement;
  if ((settlement && settlement !== "PENDING") || phase === "LIVE" || phase === "FINISHED") {
    return "LOCKED";
  }
  if (match.recommendation?.tier === "FORMAL" && match.formal_recommendation === true) {
    return "REFERENCE";
  }
  const shadow = match.pricing_shadow;
  if (!shadow || shadow.status === "INSUFFICIENT_INDEPENDENT_FACTORS") {
    return "INSUFFICIENT";
  }
  if (!hasValidatedAhCalibration(shadow)) {
    return "WATCH";
  }
  const coverage = typeof shadow.coverage === "number" && Number.isFinite(shadow.coverage)
    ? shadow.coverage
    : 0;
  const hasAh = shadow.fair_ah != null && shadow.market_ah != null;
  if (!hasAh || coverage < 0.5) {
    return "WATCH";
  }
  if (shadow.edge_ah == null || Math.abs(shadow.edge_ah) < 0.25 || shadow.status === "WATCH") {
    return "WATCH";
  }
  return "REFERENCE";
}

function cardTone(state: VerdictState): string {
  return `verdict-${state.toLowerCase()}`;
}

function blockerLabels(match: DashboardMatchCard): string[] {
  const blockers = match.analysis_readiness?.blockers ?? match.missing_inputs;
  return blockers.map((blocker) => BLOCKER_LABELS[blocker] ?? "数据不足").filter(Boolean).slice(0, 4);
}

function nextActionLabel(match: DashboardMatchCard): string {
  const action = match.analysis_readiness?.next_action;
  return action ? ACTION_LABELS[action] ?? "继续观察" : "继续观察";
}

function marketStrip(match: DashboardMatchCard): string {
  const rows = (match.market_strip ?? [])
    .map((item) => {
      const row = asRecord(item);
      const market = textValue(row.market);
      const label = textValue(row.market_label_cn ?? row.label_cn, MARKET_LABELS[market] ?? "市场");
      const lean = textValue(row.selection_label_cn ?? row.lean_cn ?? row.selection ?? row.decision);
      const decision = textValue(row.decision);
      if (decision === "SKIP") return `${label}不看`;
      if (decision === "WATCH") return `${label}观察`;
      return lean ? `${label}${lean === "大球" ? "大" : lean === "小球" ? "小" : lean}` : `${label}待看`;
    })
    .filter(Boolean)
    .slice(0, 4);
  return rows.length ? rows.join(" · ") : "数据不足，暂不推荐";
}

function oddsRecord(match: DashboardMatchCard, market: string): Record<string, unknown> {
  const odds = asRecord(match.current_odds);
  if (market === "TOTALS") return asRecord(odds.ou);
  if (market === "ASIAN_HANDICAP") return asRecord(odds.ah);
  return {};
}

function displayPick(match: DashboardMatchCard): RecommendationPick | null {
  const pick = match.recommendation;
  if (!pick) return null;
  const marketOdds = oddsRecord(match, pick.market);
  const line = pick.line ?? (textValue(marketOdds.line) || undefined);
  const odds = pick.odds ?? (textValue(marketOdds.price) || undefined);
  return { ...pick, line, odds };
}

function recommendationReference(pick: RecommendationPick | null): string {
  if (!pick) return "参考结论：暂无推荐";
  const tier = TIER_LABELS[pick.tier] ?? pick.tier;
  const market = pick.market_label_cn || MARKET_LABELS[pick.market] || pick.market;
  const selection = pick.selection_label_cn ?? pick.selection;
  const line = pick.line ? ` ${formatLine(pick.line)}` : "";
  const odds = pick.odds ? ` @${formatOdds(pick.odds)}` : "";
  return `参考结论：${tier} · ${market} ${selection}${line}${odds}`;
}

function pickMarketLabel(pick: RecommendationPick | null): string {
  if (!pick) return "暂无";
  if (pick.market === "ASIAN_HANDICAP") return "全场让球";
  if (pick.market === "TOTALS") return "全场大小球";
  if (pick.market === "SCORE") return "比分";
  if (pick.market === "FIRST_HALF_GOALS") return "半场进球";
  return pick.market_label_cn || MARKET_LABELS[pick.market] || pick.market;
}

function pickDirectionLabel(pick: RecommendationPick | null): string {
  if (!pick) return "暂无";
  return pick.selection_label_cn ?? pick.selection ?? "方向待定";
}

function pickLineLabel(pick: RecommendationPick | null): string {
  if (!pick?.line) return "无盘口";
  const line = formatLine(pick.line);
  const numeric = Number(line);
  if (
    pick.market === "ASIAN_HANDICAP"
    && Number.isFinite(numeric)
    && numeric > 0
    && (pick.selection === "AWAY_AH" || pick.selection_label_cn?.includes("受让"))
  ) {
    return `+${line}`;
  }
  return line;
}

function pickOddsLabel(pick: RecommendationPick | null): string {
  return pick?.odds ? `@${formatOdds(pick.odds)}` : "赔率等待";
}

function formalHeroSummary(pick: RecommendationPick | null): string {
  if (!pick) return "方向待定";
  return [
    pickDirectionLabel(pick),
    pick.line ? pickLineLabel(pick) : null,
    pick.odds ? `@${formatOdds(pick.odds)}` : null,
  ].filter(Boolean).join(" · ");
}

function displayReason(reason: string): string {
  return reason
    .replace(/as-of/gi, "赛前时间点")
    .replace(/devig\s*基准/gi, "市场基准")
    .replace(/\bdevig\b/gi, "去水")
    .replace(/value\s*gap/gi, "盘口差")
    .replace(/\bvalue\b/gi, "盘口价值")
    .replace(/\bedge\b/gi, "盘口差")
    .replace(/\bmarket\b/gi, "市场")
    .replace(/\b(?:hit|win)\s+rate\b/gi, "样本统计暂不展示")
    .replace(/\bR\s*O\s*I\b/g, "样本统计暂不展示")
    .replace(/\bopening\b/gi, "初盘")
    .replace(/\bopen\b/gi, "初盘")
    .replace(/\block\b/gi, "锁盘")
    .replace(/(\d+(?:\.\d+)?)\s*pct\b/gi, "$1个百分点")
    .replace(/\bFORMAL\b/g, "正式推荐")
    .replace(/\bWATCH\b/g, "观察")
    .replace(/AH/g, "让球")
    .replace(/OU/g, "大小球")
    .replace(/高于\s+市场基准/g, "高于市场基准")
    .replace(/按价格\/盘口价值\s*输出/g, "按盘口价值输出");
}

function formalReason(match: DashboardMatchCard): string {
  if (match.formal_suppressed_reason) return `正式推荐被抑制：${match.formal_suppressed_reason}`;
  const blockers = match.pricing_shadow?.formal_blockers ?? [];
  if (blockers.length) {
    return blockers
      .map((blocker) => FORMAL_BLOCKER_LABELS[blocker] ?? blocker)
      .slice(0, 3)
      .join(" · ");
  }
  const readinessBlockers = blockerLabels(match);
  if (readinessBlockers.length) return readinessBlockers.join(" · ");
  if (match.pricing_shadow?.simulation_status !== "READY") return "模拟引擎未就绪";
  if (match.pricing_shadow?.formal_eligible === false) return "未达到正式推荐门槛";
  return "当前只保留为观察/分析参考，不伪装成正式推荐。";
}

function lockedSettlementText(match: DashboardMatchCard): string {
  const settlement = match.locked_pre_match_recommendation?.settlement;
  if (!settlement?.status) return "待赛果确认";
  if (settlement.status === "SETTLED") {
    const outcome = settlement.settlement_outcome ? ` · ${settlement.settlement_outcome}` : "";
    return `已结算${outcome}`;
  }
  if (settlement.status === "PENDING") return "待结算";
  if (settlement.status === "WAITING_RESULT") return "待赛果确认";
  if (settlement.status === "NO_BET") return "无需结算";
  return "待赛果确认";
}

function lockedPrematchReason(match: DashboardMatchCard): string {
  const locked = match.locked_pre_match_recommendation;
  if (locked?.status === "LOCKED") {
    return `赛前推荐已锁定，不随开赛后盘口或赛果重算；${lockedSettlementText(match)}。`;
  }
  if (locked?.status === "NO_PREMATCH_FORMAL") {
    return "没有赛前正式推荐快照，不能在开赛后补造推荐。";
  }
  return formalReason(match);
}

function dataLine(match: DashboardMatchCard): string {
  const items = readinessItems({ data_readiness: match.data_readiness });
  const odds = items.find((item) => item.key === "odds");
  const xg = items.find((item) => item.key === "xg");
  const lineups = items.find((item) => item.key === "lineups");
  const blockers = blockerLabels(match);
  const status = [
    odds ? odds.short.replace("盘口等待", "盘口等待") : "盘口等待",
    xg ? xg.short : "xG 等待",
    lineups?.ready ? "首发已出" : "首发未出",
  ];
  if (blockers.includes("赛前时间点拦截")) status.push("赛前时间点拦截");
  return status.join(" · ");
}

function actionabilityLine(match: DashboardMatchCard): string {
  if (match.recommendation?.tier === "FORMAL") return "正式推荐：赛前真实数据与模拟策略自洽";
  const items = readinessItems({ data_readiness: match.data_readiness });
  const oddsReady = Boolean(items.find((item) => item.key === "odds")?.ready);
  const lineupsReady = Boolean(items.find((item) => item.key === "lineups")?.ready);
  const phase = matchPhase(match.kickoff_utc, match.status);
  if (phase === "LIVE") return "已开赛：赛前判断停止更新";
  if (phase === "FINISHED") return "已完场：查看复盘验证";
  if (requiresPrematchReview(phase)) {
    if (!lineupsReady) return "临场待确认：首发未出，开赛前需复核";
    if (!oddsReady) return "临场待确认：盘口快照不足，需复核";
    return "临场可参考：仍需赛前复核阵容与盘口跳线";
  }
  if (!oddsReady) return "等待盘口快照后再看";
  return "赛前分析参考，等待正式条件";
}

function canShowScoreline(match: DashboardMatchCard): boolean {
  const source = match.scoreline_readiness?.source;
  return (
    match.scoreline_readiness?.status === "READY"
    && (source === "independent_xg_poisson" || source === "formal_simulation")
    && match.scoreline_picks.length > 0
  );
}

function scoreText(match: DashboardMatchCard): string | null {
  if (!canShowScoreline(match)) return null;
  const prefix = match.scoreline_readiness?.source === "formal_simulation" ? "模拟比分参考：" : "最可能比分（基于我们的 xG）：";
  return `${prefix}${match.scoreline_picks
    .slice(0, 3)
    .map((pick) => `${pick.scoreline}${pick.probability_label ? ` ${pick.probability_label}` : ""}`)
    .join(" · ")}`;
}

function scorelineHeroText(match: DashboardMatchCard): string {
  const scoreSummary = scoreText(match);
  if (scoreSummary) return scoreSummary.replace("最可能比分（基于我们的 xG）：", "").replace("模拟比分参考：", "");
  const reason = match.scoreline_readiness?.reason;
  return reason ? `未就绪：${reason}` : "未就绪";
}

function scorelineItemText(pick: { scoreline?: string; probability_label?: string | null } | null | undefined): string | null {
  if (!pick?.scoreline) return null;
  return `${pick.scoreline}${pick.probability_label ? ` ${pick.probability_label}` : ""}`;
}

function highTotalText(match: DashboardMatchCard): string | null {
  const highTotal = match.scoreline_reference?.high_total;
  if (!highTotal?.probability_label) return null;
  const representative = scorelineItemText(highTotal.representative_scoreline);
  const prefix = `总进球≥${highTotal.threshold ?? 4}：${highTotal.probability_label}`;
  return representative ? `${prefix}，代表 ${representative}` : prefix;
}

function veryHighTotalText(match: DashboardMatchCard): string | null {
  const veryHigh = match.scoreline_reference?.very_high_total;
  if (!veryHigh?.probability_label) return null;
  return `总进球≥${veryHigh.threshold ?? 5}：${veryHigh.probability_label}`;
}

function ahKeyScorelineText(match: DashboardMatchCard): string | null {
  const rows = match.scoreline_reference?.ah_key_scorelines ?? [];
  const text = rows
    .filter((row) => row.label && row.scoreline)
    .map((row) => {
      const settlement = row.settlement_probability_label ? ` ${row.settlement_probability_label}` : "";
      return `${row.label}：${row.scoreline}${settlement}`;
    })
    .join(" / ");
  return text || null;
}

function ScorelineReferenceBlock({ match, isFormal }: { match: DashboardMatchCard; isFormal: boolean }) {
  if (!isFormal) {
    return (
      <p className="scoreline-hero-copy">
        <strong>比分模拟参考：</strong>
        {scorelineHeroText(match)}
      </p>
    );
  }
  const reference = match.scoreline_reference;
  const topScorelines = (reference?.top_scorelines?.length ? reference.top_scorelines : match.scoreline_picks)
    .slice(0, 3)
    .map((pick) => scorelineItemText(pick))
    .filter(Boolean)
    .join(" · ");
  const highTotal = highTotalText(match);
  const veryHighTotal = veryHighTotalText(match);
  const ahKeys = ahKeyScorelineText(match);
  if (!topScorelines && !highTotal && !ahKeys) {
    return (
      <p className="scoreline-hero-copy">
        <strong>模拟比分参考：</strong>
        {scorelineHeroText(match)}
      </p>
    );
  }
  return (
    <div className="scoreline-reference-block" aria-label="分层模拟比分参考">
      <strong>模拟比分参考，不是推荐比分</strong>
      {topScorelines ? <p>最可能：{topScorelines}</p> : null}
      {highTotal ? <p>{highTotal}{veryHighTotal ? ` · ${veryHighTotal}` : ""}</p> : null}
      {ahKeys ? <p>让球结算关键比分：{ahKeys}</p> : null}
    </div>
  );
}

function resultLine(match: DashboardMatchCard): string | null {
  if (!match.result?.final_score && !match.validation) return null;
  const finalScore = match.result?.final_score ? `完场 ${match.result.final_score}` : "完场待同步";
  const settlementLabel: Record<string, string> = {
    PENDING: "待验证",
    HIT: "命中",
    MISS: "未中",
    PUSH: "走水",
    VOID: "无效",
    NO_BET: "无推荐",
    UNKNOWN: "待确认",
  };
  const settlement = match.validation?.settlement ? ` · ${settlementLabel[match.validation.settlement] ?? "待确认"}` : "";
  return `${finalScore}${settlement}`;
}

function percentValue(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

function lineValue(value: number | null | undefined, market: "ah" | "ou"): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  if (market === "ou") return formatLine(Math.abs(value));
  return formatAhMainLine(value);
}

function edgeDisplayText(edge: number | null | undefined, calibrated: boolean): string {
  const delta = formatAhDelta(edge);
  if (!delta) return calibrated ? "未形成差距" : "未形成可展示差距";
  return calibrated ? delta : `${delta}（未校准，不作为方向判断）`;
}

function pricingShadowDetail(shadow: PricingShadow | null | undefined, state: VerdictState): string {
  if (!shadow) return "未形成独立定价结果，保持观察。";
  if (state === "LOCKED") return "赛前分析已锁定，仅供复盘验证。";
  if (shadow.status === "INSUFFICIENT_INDEPENDENT_FACTORS") return "独立因子不足，不能形成主市场判断。";
  if (shadow.simulation_status === "READY") return "模拟引擎已就绪，让球、大小球、比分同源生成。";
  if (!hasValidatedAhCalibration(shadow)) return "模拟输入不足，暂不输出正式让球推荐。";
  return "模拟公平盘已形成。";
}

function sideName(side: "HOME" | "AWAY" | "NEUTRAL" | "UNKNOWN", homeName: string, awayName: string): string {
  if (side === "HOME") return homeName;
  if (side === "AWAY") return awayName;
  if (side === "NEUTRAL") return "两队接近";
  return "方向未知";
}

function uncalibratedAhExplanation(shadow: PricingShadow | null | undefined, homeName: string, awayName: string): string {
  if (!shadow) return "缺少独立定价结果，暂不输出让球倾向。";
  if (shadow.status === "INSUFFICIENT_INDEPENDENT_FACTORS") return "独立信号不足，暂不输出让球倾向。";
  const leader = teamScoreLeader(shadow);
  const lean = unvalidatedAhLean(shadow);
  if (hasFactorLeanConflict(shadow)) {
    return `因子更支持${sideName(leader, homeName, awayName)}；规则盘差距指向${sideName(lean, homeName, awayName)}，但 B4 未校准，本场无可靠让球倾向。`;
  }
  if (leader === "NEUTRAL") return "两队独立评分接近；规则盘未校准，本场无可靠让球倾向。";
  return `因子更支持${sideName(leader, homeName, awayName)}；规则盘未通过 B4 校准，暂不判断市场让球是否可参考。`;
}

function factorCount(shadow: PricingShadow | null | undefined): number {
  const summary = shadow?.factor_source_summary ?? {};
  const summaryReady = Object.values(summary).filter((item) => item.collection_status === "READY").length;
  return Math.max(summaryReady, shadow?.factors.length ?? 0);
}

function missingSignalLabels(shadow: PricingShadow | null | undefined, match: DashboardMatchCard): string[] {
  const missing = new Set<string>();
  const xgStatus = statusText(match.data_refresh?.xg_status ?? asRecord(match.data_readiness).xg_status);
  if (xgStatus === "PARTIAL_HISTORY") missing.add("xG样本不足");
  if (xgStatus === "INSUFFICIENT_HISTORY") missing.add("xG历史不足");
  for (const group of shadow?.missing_independent_sources ?? []) {
    if (group === "h2h") missing.add("无交锋历史");
    else if (group === "squad_value") missing.add("身价未映射");
    else if (group === "xg" && !["PARTIAL_HISTORY", "INSUFFICIENT_HISTORY"].includes(xgStatus)) missing.add("xG样本");
    else if (SIGNAL_GROUP_LABELS[group]) missing.add(SIGNAL_GROUP_LABELS[group]);
  }
  const summary = shadow?.factor_source_summary ?? {};
  for (const [id, item] of Object.entries(summary)) {
    if (id === "F5_RECENT_AH_COVER" && item.collection_status === "MISSING_AH_EVIDENCE") missing.add("亚盘历史");
    if (id === "F6_H2H" && item.collection_status === "NO_H2H_HISTORY") missing.add("无交锋历史");
    if (id === "F8_SQUAD_VALUE" && item.collection_status === "MAPPING_MISSING") missing.add("身价未映射");
  }
  return Array.from(missing).slice(0, 5);
}

function independentSignalLine(shadow: PricingShadow | null | undefined, match: DashboardMatchCard): string {
  if (!shadow) return "独立信号：0/5 · 因子就绪：0/7 · 缺：独立评分输入";
  const groups = shadow.independent_signal_groups ?? [];
  const used = groups.map((group) => SIGNAL_GROUP_LABELS[group] ?? group).filter(Boolean);
  const missing = missingSignalLabels(shadow, match);
  const signalCount = typeof shadow.independent_signal_count === "number" ? shadow.independent_signal_count : groups.length;
  return [
    `独立信号：${signalCount}/${REQUIRED_SIGNAL_GROUPS.length}`,
    `因子就绪：${factorCount(shadow)}/7`,
    used.length ? `已用：${used.join("、")}` : "已用：无",
    missing.length ? `缺：${missing.join("、")}` : "缺：无",
  ].join(" · ");
}

function lowInformationState(state: VerdictState): boolean {
  return state === "INSUFFICIENT" || state === "WATCH";
}

function hasReliableAhLean(shadow: PricingShadow | null | undefined): boolean {
  if (!hasValidatedAhCalibration(shadow)) return false;
  if (shadow?.fair_ah == null || shadow.market_ah == null || shadow.edge_ah == null) return false;
  const leader = teamScoreLeader(shadow);
  if (leader === "NEUTRAL" || leader === "UNKNOWN") return false;
  return !hasFactorLeanConflict(shadow);
}

function shouldHideDirectionalCopy(match: DashboardMatchCard, state: VerdictState): boolean {
  if (match.recommendation?.tier === "FORMAL") return false;
  return lowInformationState(state) || !hasReliableAhLean(match.pricing_shadow);
}

function scoreIndexValue(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  const normalized = Math.abs(value) <= 1 ? value * 100 : value;
  return Math.round(Math.max(0, Math.min(100, normalized))).toString();
}

function scoreGapLabel(shadow: PricingShadow | null | undefined): string {
  const home = shadow?.team_score?.home;
  const away = shadow?.team_score?.away;
  if (typeof home !== "number" || typeof away !== "number") return "指数待补";
  const homeIndex = Number(scoreIndexValue(home));
  const awayIndex = Number(scoreIndexValue(away));
  if (!Number.isFinite(homeIndex) || !Number.isFinite(awayIndex)) return "指数待补";
  return Math.abs(homeIndex - awayIndex) < 5 ? "接近持平" : "相对差距";
}

function factorDetailText(factor: PricingShadowFactor, homeName: string, awayName: string): string {
  const value = factor.score;
  if (typeof value !== "number" || !Number.isFinite(value)) return "证据不足";
  const strength = Math.abs(value);
  if (strength < 0.05) return "接近持平";
  if (factor.side !== "HOME" && factor.side !== "AWAY") return `中性 · ${strength.toFixed(2)}`;
  const sideLabel = factor.side === "HOME" ? homeName : awayName;
  const advantage = strength < 0.15 ? "略占优" : "占优";
  return `${sideLabel}${advantage} · ${strength.toFixed(2)}`;
}

function statusText(value: unknown): string {
  return textValue(value).toUpperCase();
}

function oddsPillLabel(match: DashboardMatchCard): string {
  const status = statusText(match.data_refresh?.odds_status);
  if (status === "READY") return "已更新";
  if (status === "STALE") return "可能过期";
  const items = readinessItems({ data_readiness: match.data_readiness });
  return items.find((item) => item.key === "odds")?.ready ? "已更新" : "等待";
}

function lineupsPillLabel(match: DashboardMatchCard): string {
  const status = statusText(match.data_refresh?.lineups_status ?? asRecord(match.data_readiness).lineups_status);
  if (status === "READY") return "已出";
  if (status === "PROVIDER_EMPTY") return "未返回";
  if (status === "NOT_REQUESTED") return "未到时点";
  if (status === "STALE") return "可能过期";
  return "状态待确认";
}

function xgPillLabel(match: DashboardMatchCard): string {
  const status = statusText(match.data_refresh?.xg_status ?? asRecord(match.data_readiness).xg_status);
  const items = readinessItems({ data_readiness: match.data_readiness });
  if (status === "READY" || items.find((item) => item.key === "xg")?.ready) return "已就绪";
  if (status === "INSUFFICIENT_HISTORY" || status === "PARTIAL_HISTORY") return "样本不足";
  if (status === "PROVIDER_EMPTY" || status === "PROVIDER_EMPTY_OR_UNAVAILABLE") return "未返回";
  if (status === "MAPPING_MISSING") return "映射缺失";
  return "状态待确认";
}

function DataReadinessPills({ match }: { match: DashboardMatchCard }) {
  return (
    <div className="readiness-pill-row" aria-label="数据状态">
      <span>盘口：{oddsPillLabel(match)}</span>
      <span>首发：{lineupsPillLabel(match)}</span>
      <span>xG：{xgPillLabel(match)}</span>
    </div>
  );
}

function FormalDecisionHero({
  match,
  pick,
  isFormal,
  verdict,
}: {
  match: DashboardMatchCard;
  pick: RecommendationPick | null;
  isFormal: boolean;
  verdict: VerdictState;
}) {
  const locked = match.locked_pre_match_recommendation;
  const lockedPick = locked?.status === "LOCKED" ? locked.recommendation ?? null : null;
  const noPrematchFormal = locked?.status === "NO_PREMATCH_FORMAL";
  const visiblePick = lockedPick ?? pick;
  const showPickGrid = isFormal || Boolean(lockedPick);
  const title = isFormal ? "正式推荐" : lockedPick ? "赛前锁定推荐" : noPrematchFormal ? "赛前无正式推荐" : "当前暂无正式推荐";
  const headline = isFormal || lockedPick ? `推荐：${formalHeroSummary(visiblePick)}` : VERDICT_LABELS[verdict];
  const reason = isFormal
    ? displayReason(pick?.reasons?.[0] ?? "模拟公平盘与市场盘形成策略自洽。")
    : lockedPrematchReason(match);
  return (
    <section className={isFormal || lockedPick ? "formal-decision-hero is-formal" : "formal-decision-hero is-empty"} aria-label="正式推荐状态">
      <div className="formal-decision-topline">
        <span>{title}</span>
        <strong>{headline}</strong>
      </div>
      {showPickGrid ? (
        <div className="formal-pick-grid" aria-label="正式推荐详情">
          <span>市场</span>
          <strong>{pickMarketLabel(visiblePick)}</strong>
          <span>方向</span>
          <strong>{pickDirectionLabel(visiblePick)}</strong>
          <span>盘口</span>
          <strong>{pickLineLabel(visiblePick)}</strong>
          <span>赔率</span>
          <strong>{pickOddsLabel(visiblePick)}</strong>
        </div>
      ) : null}
      <p>{isFormal ? `理由：${reason}` : `${lockedPick ? "锁定说明" : "未出正式推荐原因"}：${displayReason(reason)}`}</p>
      <ScorelineReferenceBlock match={match} isFormal={isFormal} />
    </section>
  );
}

function MainMarketBox({
  shadow,
  state,
  homeName,
  awayName,
}: {
  shadow?: PricingShadow | null;
  state: VerdictState;
  homeName: string;
  awayName: string;
}) {
  const coverage = percentValue(shadow?.coverage ?? null);
  const calibrated = hasValidatedAhCalibration(shadow);
  const fairAh = lineValue(shadow?.fair_ah ?? null, "ah");
  const marketAh = lineValue(shadow?.market_ah ?? null, "ah");
  const edgeAh = edgeDisplayText(shadow?.edge_ah ?? null, calibrated);
  const factors = (shadow?.factors ?? [])
    .filter((factor) => factor.status === "READY")
    .sort((a, b) => Number(b.is_independent_signal === true) - Number(a.is_independent_signal === true));
  return (
    <section className="main-market-box" aria-label="正式推荐依据详情">
      <div className="main-market-heading">
        <span>依据/详情</span>
        <strong>独立评分 · 全场让球</strong>
        <em>{coverage ? `覆盖 ${coverage}` : "覆盖不足"}</em>
      </div>
      <div className="team-score-row" aria-label="两队独立评分">
        <strong>{homeName} 指数 {scoreIndexValue(shadow?.team_score?.home)}</strong>
        <span>—</span>
        <strong>{awayName} 指数 {scoreIndexValue(shadow?.team_score?.away)}</strong>
      </div>
      <p className="score-scale-note">独立评分指数，仅用于两队相对比较；{scoreGapLabel(shadow)}。中性因子不偏向任何一方。</p>
      <div className="factor-detail-list" aria-label="独立因子明细">
        {factors.length ? factors.slice(0, 5).map((factor) => (
          <span key={factor.id}>
            {FACTOR_LABELS[factor.id] ?? factor.id} · {factorDetailText(factor, homeName, awayName)}
          </span>
        )) : <span>独立因子未就绪</span>}
      </div>
      <div className="main-market-grid">
        <span>{shadow?.simulation_status === "READY" ? "模拟公平盘" : calibrated ? "独立公平盘" : "规则公平盘"}</span>
        <strong>{fairAh ? `让球 ${fairAh}${shadow?.simulation_status === "READY" || calibrated ? "" : "（未校准）"}` : "未形成"}</strong>
        <span>{calibrated ? "市场主线" : "市场主线（背景）"}</span>
        <strong>{marketAh ? `让球 ${marketAh}` : "盘口等待"}</strong>
        <span>{calibrated ? "盘口差距" : "差距展示"}</span>
        <strong>{edgeAh}</strong>
      </div>
      <p>
        {calibrated ? pricingShadowDetail(shadow, state) : uncalibratedAhExplanation(shadow, homeName, awayName)}
      </p>
    </section>
  );
}

export function RecommendationCard({ match }: { match: DashboardMatchCard }) {
  const pick = displayPick(match);
  const risks = pick?.risks.length ? pick.risks : ["天气、红牌、阵容临场变化可能改变判断"];
  const stars = watchLevel({ watch_level: match.watch_level });
  const homeName = translateTeam(match.home_team_name);
  const awayName = translateTeam(match.away_team_name);
  const minutes = minutesToKickoff(match.kickoff_utc);
  const phase = matchPhase(match.kickoff_utc, match.status);
  const prematchReview = requiresPrematchReview(phase);
  const verdict = verdictState(match);
  const lowInfo = shouldHideDirectionalCopy(match, verdict);
  const odds = currentOdds(
    { current_odds: match.current_odds },
    {
      directionalTotals: !lowInfo,
      canonicalAhLine: match.pricing_shadow?.market_ah,
    },
  );
  const signalLine = independentSignalLine(match.pricing_shadow, match);
  const scoreSummary = scoreText(match);
  const isFormal = pick?.tier === "FORMAL" && match.formal_recommendation === true;
  return (
    <article className={`recommendation-card ${cardTone(verdict)} ${prematchReview ? "is-prematch" : ""}`}>
      <header className="recommendation-card-header">
        <div>
          <span className="match-meta">
            {fmtTime(match.kickoff_utc)} · {translateCompetition(match.competition_name)}
          </span>
          <div className="fixture-title">
            <strong>{homeName}</strong>
            <span>{match.result?.final_score ?? "vs"}</span>
            <strong>{awayName}</strong>
          </div>
          <div className="team-code-row" aria-hidden="true">
            <span>{teamCode(match.home_team_name)}</span>
            <span>{teamCode(match.away_team_name)}</span>
          </div>
        </div>
        <div className="card-status-stack">
          <span className={prematchReview ? "phase-pill is-urgent" : "phase-pill"}>{phaseLabel(phase, minutes)}</span>
          {match.validation ? <SettlementBadge status={match.validation.settlement} /> : null}
        </div>
      </header>

      <FormalDecisionHero match={match} pick={pick} isFormal={isFormal} verdict={verdict} />

      <details className="analysis-details">
        <summary>查看分析依据</summary>
        <div className="analysis-details-body">
          <MainMarketBox
            shadow={match.pricing_shadow}
            state={verdict}
            homeName={homeName}
            awayName={awayName}
          />

          <DataReadinessPills match={match} />
          <p className="market-strip-line">{signalLine}</p>

          {lowInfo ? null : (
            <div className="card-info-lines">
              <p className={prematchReview ? "prematch-action-line" : ""}>
                <strong>临场：</strong>
                {actionabilityLine(match)}
              </p>
              <p>
                <strong>数据：</strong>
                {dataLine(match)}
              </p>
              {scoreSummary && !isFormal ? <p><strong>{scoreSummary}</strong></p> : null}
            </div>
          )}
          <OddsMovementMini match={match} />
          {lowInfo ? null : <p className="market-strip-line">{recommendationReference(pick)}</p>}
          {lowInfo ? null : <p className="market-strip-line">其他参考：{marketStrip(match)}</p>}
          <div className="recommendation-footer">
            <div>
              <p className="odds-line">{lowInfo ? "市场盘（仅背景）：" : "盘口参考（含备选线）："}{odds.length ? odds.join(" · ") : "等待采集"}</p>
              {resultLine(match) ? <p className="result-line">{resultLine(match)}</p> : null}
              {lowInfo ? null : <p className="risk-line">风险：{risks.slice(0, 2).join("、")}</p>}
            </div>
            {lowInfo ? null : <span className="watch-stars" aria-label={`关注度 ${stars}/5`}>
              关注度 {"★".repeat(stars)}
              {"☆".repeat(5 - stars)}
            </span>}
          </div>
        </div>
      </details>
    </article>
  );
}
