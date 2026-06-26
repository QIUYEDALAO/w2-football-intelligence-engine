import { fmtTime, teamCode } from "../lib/formatters";
import { asRecord, currentOdds, textValue, watchLevel } from "../lib/normalize";
import type { DashboardMatchCard, RecommendationTier } from "../types/dashboard";
import { DataReadinessRow } from "./DataReadinessRow";
import { MarketPickSummary } from "./MarketPickSummary";
import { OddsMovementMini } from "./OddsMovementMini";
import { ScorelinePicks } from "./ScorelinePicks";
import { SettlementBadge } from "./SettlementBadge";

const TIER_LABELS: Record<RecommendationTier, string> = {
  FORMAL: "正式推荐",
  CANDIDATE: "候选观察",
  ANALYSIS_PICK: "有分析",
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

function readinessStatus(match: DashboardMatchCard): string {
  const readiness = match.analysis_readiness;
  if (!readiness) return "数据加载中";
  if (readiness.status === "READY") return "数据就绪";
  if (readiness.status === "PARTIAL") return "部分就绪";
  if (readiness.status === "BLOCKED") return "数据不足";
  return "生成中";
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
      return lean ? `${label} ${lean}` : `${label} 数据不足`;
    })
    .filter(Boolean)
    .slice(0, 3);
  return rows.length ? rows.join(" · ") : "数据不足，暂不推荐";
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

export function RecommendationCard({ match }: { match: DashboardMatchCard }) {
  const pick = match.recommendation;
  const odds = currentOdds({ current_odds: match.current_odds });
  const risks = pick?.risks.length ? pick.risks : ["天气、红牌、阵容临场变化可能改变判断"];
  const stars = watchLevel({ watch_level: match.watch_level });
  return (
    <article className={`recommendation-card ${cardTone(match)} tier-${pick?.tier.toLowerCase() ?? "none"}`}>
      <header className="recommendation-card-header">
        <div>
          <span className="match-meta">
            {fmtTime(match.kickoff_utc)} · {match.competition_name}
          </span>
          <div className="fixture-title">
            <span className="team-badge">{teamCode(match.home_team_name)}</span>
            <strong>{match.home_team_name}</strong>
            <span>{match.result?.final_score ?? "vs"}</span>
            <strong>{match.away_team_name}</strong>
            <span className="team-badge">{teamCode(match.away_team_name)}</span>
          </div>
        </div>
        {match.validation ? <SettlementBadge status={match.validation.settlement} /> : <span className={`status-pill ${cardTone(match)}`}>{tierLabel(match)}</span>}
      </header>
      <DataReadinessRow match={match} />

      {pick ? (
        <MarketPickSummary pick={pick} />
      ) : (
        <div className="market-pick-summary is-empty">
          <div>
            <span>主推</span>
            <strong>暂不推荐</strong>
            <p>{nextActionLabel(match)}；满足盘口、模型与 as-of 条件后自动更新。</p>
          </div>
        </div>
      )}

      <ScorelinePicks picks={match.scoreline_picks} />
      <div className="analysis-readiness-line">
        <strong>{readinessStatus(match)}</strong>
        <span>{nextActionLabel(match)}</span>
        {blockerLabels(match).map((label) => (
          <small key={label}>{label}</small>
        ))}
      </div>
      <OddsMovementMini match={match} />
      <p className="market-strip-line">其他市场：{marketStrip(match)}</p>
      <div className="recommendation-footer">
        <div>
          <p className="odds-line">{odds.length ? odds.join(" · ") : "当前盘口等待采集"}</p>
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
