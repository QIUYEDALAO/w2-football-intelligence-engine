import { fmtTime, teamCode, translateCompetition, translateTeam } from "../lib/formatters";
import { matchPhase, minutesToKickoff, phaseLabel, requiresPrematchReview } from "../lib/matchPhase";
import { asRecord, currentOdds, readinessItems, textValue, watchLevel } from "../lib/normalize";
import type { DashboardMatchCard, PricingShadow, RecommendationPick, RecommendationTier } from "../types/dashboard";
import { MarketPickSummary } from "./MarketPickSummary";
import { OddsMovementMini } from "./OddsMovementMini";
import { SettlementBadge } from "./SettlementBadge";

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

function tierLabel(match: DashboardMatchCard): string {
  const settlement = match.validation?.settlement;
  if (settlement && settlement !== "PENDING") return "";
  return match.recommendation ? TIER_LABELS[match.recommendation.tier] : "暂无推荐";
}

function cardTone(match: DashboardMatchCard): string {
  const tier = match.recommendation?.tier;
  if (tier === "FORMAL" || tier === "CANDIDATE" || tier === "ANALYSIS_PICK") return "is-pick";
  if (tier === "WATCH") return "is-watch";
  return "is-skip";
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

function edgeText(edge: number | null | undefined): string | null {
  if (typeof edge !== "number" || !Number.isFinite(edge)) return null;
  const abs = Math.abs(edge).toFixed(2).replace(/\.00$/, "").replace(/0$/, "");
  if (Math.abs(edge) < 0.05) return "接近市场，无明显优势";
  return edge > 0 ? `+${abs} · 我们比市场更看主队` : `-${abs} · 市场让得更深 / 更看客队`;
}

function pricingShadowTitle(shadow: PricingShadow): string {
  if (shadow.status === "INSUFFICIENT_INDEPENDENT_FACTORS") return "独立评分覆盖不足";
  if (shadow.status === "WATCH") return "无明显独立优势 · 观察";
  return "独立评分参考 · 待校准";
}

function pricingShadowDetail(shadow: PricingShadow): string {
  if (shadow.status === "INSUFFICIENT_INDEPENDENT_FACTORS") return "当前观察，不强推";
  if (shadow.fair_ah == null && shadow.fair_ou == null && shadow.edge_ah == null && shadow.edge_ou == null) return "独立评分未形成公平盘";
  return "规则映射 · 待校准 · 非正式推荐";
}

function PricingShadowPanel({ shadow }: { shadow?: PricingShadow | null }) {
  if (!shadow) return null;
  const coverage = percentValue(shadow.coverage);
  const fairAh = lineValue(shadow.fair_ah, "ah");
  const fairOu = lineValue(shadow.fair_ou, "ou");
  const marketAh = lineValue(shadow.market_ah, "ah");
  const marketOu = lineValue(shadow.market_ou, "ou");
  const edgeAh = edgeText(shadow.edge_ah);
  const edgeOu = edgeText(shadow.edge_ou);
  const hasFairLine = Boolean(fairAh || fairOu || edgeAh || edgeOu);
  return (
    <section className="pricing-shadow-panel" aria-label="独立盘分析">
      <div className="pricing-shadow-heading">
        <strong>{pricingShadowTitle(shadow)}</strong>
        {coverage ? <span>覆盖率 {coverage}</span> : null}
      </div>
      {hasFairLine ? (
        <div className="pricing-shadow-grid">
          <span>我们盘</span>
          <strong>{[fairAh ? `让球 ${fairAh}` : "", fairOu ? `大小 ${fairOu}` : ""].filter(Boolean).join(" · ") || "未形成公平盘"}</strong>
          <span>市场盘</span>
          <strong>{[marketAh ? `让球 ${marketAh}` : "", marketOu ? `大小 ${marketOu}` : ""].filter(Boolean).join(" · ") || "盘口等待"}</strong>
          <span>Edge</span>
          <strong>{[edgeAh, edgeOu].filter(Boolean).join(" · ") || "接近市场，无明显优势"}</strong>
        </div>
      ) : null}
      <p>{pricingShadowDetail(shadow)}</p>
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
  return (
    <article className={`recommendation-card ${cardTone(match)} ${prematchReview ? "is-prematch" : ""} tier-${pick?.tier.toLowerCase() ?? "none"}`}>
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
          {match.validation ? <SettlementBadge status={match.validation.settlement} /> : <span className={`status-pill ${cardTone(match)}`}>{tierLabel(match)}</span>}
        </div>
      </header>

      {pick ? (
        <MarketPickSummary pick={pick} />
      ) : (
        <div className="market-pick-summary is-empty">
          <div>
            <span>主看</span>
            <strong>暂不推荐</strong>
            <p>{nextActionLabel(match)}；盘口和模型条件不足时不强出方向。</p>
          </div>
        </div>
      )}

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
      <OddsMovementMini match={match} />
      <PricingShadowPanel shadow={match.pricing_shadow} />
      <p className="market-strip-line">其他：{marketStrip(match)}</p>
      <div className="recommendation-footer">
        <div>
          <p className="odds-line">当前：{odds.length ? odds.join(" · ") : "盘口等待采集"}</p>
          {resultLine(match) ? <p className="result-line">{resultLine(match)}</p> : null}
          <p className="risk-line">风险：{risks.slice(0, 2).join("、")}</p>
        </div>
        <span className="watch-stars" aria-label={`关注度 ${stars}/5`}>
          关注度 {"★".repeat(stars)}
          {"☆".repeat(5 - stars)}
        </span>
      </div>
    </article>
  );
}
