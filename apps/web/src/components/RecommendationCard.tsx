import { fmtTime, formatLine, formatOdds, teamCode, translateCompetition, translateTeam } from "../lib/formatters";
import { matchPhase, minutesToKickoff, phaseLabel, requiresPrematchReview } from "../lib/matchPhase";
import { asRecord, currentOdds, readinessItems, textValue, watchLevel } from "../lib/normalize";
import type { DashboardMatchCard, PricingShadow, RecommendationPick, RecommendationTier } from "../types/dashboard";
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
  AS_OF_BLOCKED: "as-of 拦截",
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

function verdictState(match: DashboardMatchCard): VerdictState {
  const phase = matchPhase(match.kickoff_utc, match.status);
  const settlement = match.validation?.settlement;
  if ((settlement && settlement !== "PENDING") || phase === "LIVE" || phase === "FINISHED") {
    return "LOCKED";
  }
  const shadow = match.pricing_shadow;
  if (!shadow || shadow.status === "INSUFFICIENT_INDEPENDENT_FACTORS") {
    return "INSUFFICIENT";
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
  if (!pick) return "参考结论：暂无 recommendation";
  const tier = TIER_LABELS[pick.tier] ?? pick.tier;
  const market = pick.market_label_cn || MARKET_LABELS[pick.market] || pick.market;
  const selection = pick.selection_label_cn ?? pick.selection;
  const line = pick.line ? ` ${formatLine(pick.line)}` : "";
  const odds = pick.odds ? ` @${formatOdds(pick.odds)}` : "";
  return `参考结论：${tier} · ${market} ${selection}${line}${odds}`;
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
  if (blockers.includes("as-of 拦截")) status.push("as-of拦截");
  return status.join(" · ");
}

function refreshLine(match: DashboardMatchCard): string | null {
  const refresh = match.data_refresh;
  if (!refresh?.status) return null;
  const parts = [
    refresh.status_label || (refresh.status === "PROVIDER_EMPTY" ? "provider 未返回" : refresh.status),
    refresh.odds_status ? `盘口 ${refresh.odds_status}` : "",
    refresh.lineups_status_label || (refresh.lineups_status ? `阵容 ${refresh.lineups_status}` : ""),
    refresh.xg_status_label || (refresh.xg_status ? `xG ${refresh.xg_status}` : ""),
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

function actionabilityLine(match: DashboardMatchCard): string {
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
  return "赛前分析参考，非正式推荐";
}

function scoreText(match: DashboardMatchCard): string {
  if (!match.scoreline_picks.length) {
    const phase = matchPhase(match.kickoff_utc, match.status);
    if (phase === "LIVE" || phase === "FINISHED") return "比分：赛前未就绪 · 已锁定";
    return "比分：等待 xG 数据";
  }
  return `比分：${match.scoreline_picks
    .slice(0, 3)
    .map((pick) => `${pick.scoreline}${pick.probability_label ? ` ${pick.probability_label}` : ""}`)
    .join(" · ")}`;
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
  const abs = Math.abs(value).toFixed(2).replace(/\.00$/, "").replace(/0$/, "");
  if (market === "ou") return abs;
  if (Math.abs(value) < 0.001) return "平手";
  return value < 0 ? `主 -${abs}` : `客 -${abs}`;
}

function edgeText(edge: number | null | undefined): string {
  if (typeof edge !== "number" || !Number.isFinite(edge)) return "未形成 edge";
  const abs = Math.abs(edge).toFixed(2).replace(/\.00$/, "").replace(/0$/, "");
  if (Math.abs(edge) < 0.05) return "接近市场，无明显优势";
  return edge > 0 ? `+${abs} · 我们比市场更看主队` : `-${abs} · 市场让得更深 / 更看客队`;
}

function ahSideLabel(edge: number | null | undefined): string {
  if (typeof edge !== "number" || !Number.isFinite(edge) || Math.abs(edge) < 0.05) {
    return "让球主市场：接近市场";
  }
  return edge > 0 ? "让球主市场：偏主队" : "让球主市场：偏客队/市场更深";
}

function pricingShadowDetail(shadow: PricingShadow | null | undefined, state: VerdictState): string {
  if (!shadow) return "未形成 S1 shadow，保持观察。";
  if (state === "LOCKED") return "赛前分析已锁定，仅供复盘验证。";
  if (shadow.status === "INSUFFICIENT_INDEPENDENT_FACTORS") return "独立因子不足，不能形成主市场判断。";
  return "S1-Shadow · 规则映射 · 未校准 · 非正式推荐。";
}

function lowInformationState(state: VerdictState): boolean {
  return state === "INSUFFICIENT" || state === "WATCH";
}

function scoreValue(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return (value * 100).toFixed(1).replace(/\.0$/, "");
}

function factorSideLabel(side: string, homeName: string, awayName: string): string {
  if (side === "HOME") return `${homeName}占优`;
  if (side === "AWAY") return `${awayName}占优`;
  if (side === "NEUTRAL") return "中性";
  return "未知";
}

function factorScore(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}分`;
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
  const lowInfo = lowInformationState(state);
  const fairAh = lineValue(shadow?.fair_ah ?? null, "ah");
  const marketAh = lineValue(shadow?.market_ah ?? null, "ah");
  const edgeAh = edgeText(shadow?.edge_ah ?? null);
  const factors = (shadow?.factors ?? []).filter((factor) => factor.status === "READY");
  return (
    <section className="main-market-box" aria-label="全场让球主市场">
      <div className="main-market-heading">
        <span>独立评分</span>
        <strong>主市场 · 全场让球</strong>
        <em>{coverage ? `覆盖 ${coverage}` : "覆盖不足"}</em>
      </div>
      <div className="team-score-row" aria-label="两队独立评分">
        <strong>{homeName} {scoreValue(shadow?.team_score?.home)}</strong>
        <span>—</span>
        <strong>{awayName} {scoreValue(shadow?.team_score?.away)}</strong>
      </div>
      <div className="factor-detail-list" aria-label="独立因子明细">
        {factors.length ? factors.slice(0, 5).map((factor) => (
          <span key={factor.id}>
            {FACTOR_LABELS[factor.id] ?? factor.id} · {factorSideLabel(factor.side, homeName, awayName)} · {factorScore(factor.score)}
          </span>
        )) : <span>独立因子未就绪</span>}
      </div>
      <div className="main-market-grid">
        {lowInfo ? null : (
          <>
            <span>独立公平盘</span>
            <strong>{fairAh ? `让球 ${fairAh}` : "未形成"}</strong>
          </>
        )}
        <span>{lowInfo ? "市场主线（背景）" : "市场主线"}</span>
        <strong>{marketAh ? `让球 ${marketAh}` : "盘口等待"}</strong>
        {lowInfo ? null : (
          <>
            <span>差距判断</span>
            <strong>{edgeAh}</strong>
          </>
        )}
      </div>
      {lowInfo ? null : (
        <p>
          {ahSideLabel(shadow?.edge_ah ?? null)} · {pricingShadowDetail(shadow, state)}
        </p>
      )}
    </section>
  );
}

export function RecommendationCard({ match }: { match: DashboardMatchCard }) {
  const pick = displayPick(match);
  const odds = currentOdds({ current_odds: match.current_odds });
  const risks = pick?.risks.length ? pick.risks : ["天气、红牌、阵容临场变化可能改变判断"];
  const stars = watchLevel({ watch_level: match.watch_level });
  const homeName = translateTeam(match.home_team_name);
  const awayName = translateTeam(match.away_team_name);
  const minutes = minutesToKickoff(match.kickoff_utc);
  const phase = matchPhase(match.kickoff_utc, match.status);
  const prematchReview = requiresPrematchReview(phase);
  const verdict = verdictState(match);
  const blockers = blockerLabels(match);
  const lowInfo = lowInformationState(verdict);
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

      <div className="verdict-hero">
        <span>{VERDICT_LABELS[verdict]}</span>
        <strong>{verdict === "REFERENCE" ? "可作赛前分析参考" : verdict === "WATCH" ? "观察，不升级" : verdict === "LOCKED" ? "赛前判断已锁定" : "样本/因子不足"}</strong>
        <p>{blockers.length ? blockers.join(" · ") : "beats_market=false · FORMAL/CANDIDATE 未开启"}</p>
      </div>

      <MainMarketBox
        shadow={match.pricing_shadow}
        state={verdict}
        homeName={homeName}
        awayName={awayName}
      />

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
          {refreshLine(match) ? (
            <p>
              <strong>刷新：</strong>
              {refreshLine(match)}
            </p>
          ) : null}
          <p>
            <strong>{scoreText(match)}</strong>
          </p>
        </div>
      )}
      {lowInfo ? null : <OddsMovementMini match={match} />}
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
    </article>
  );
}
