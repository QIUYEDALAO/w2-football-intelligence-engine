import { fmtTime, teamCode } from "../lib/formatters";
import type { DashboardMatchCard, PricingShadow } from "../types/dashboard";
import { DataReadinessRow } from "./DataReadinessRow";

const BLOCKER_LABELS: Record<string, string> = {
  MISSING_ANALYSIS_CARD: "缺分析卡",
  ALL_MARKETS_SKIP: "全市场 SKIP",
  MISSING_MARKET_OBSERVATIONS: "缺盘口观测",
  MISSING_BOOKMAKER_QUOTES: "缺庄家报价",
  MISSING_ODDS_TIMELINE: "缺盘口时间线",
  MISSING_XG: "缺 xG",
  MISSING_SCORE_MATRIX: "缺比分矩阵",
  MISSING_MODEL_PROBABILITIES: "缺模型概率",
  MISSING_MARKET_PROBABILITIES: "缺市场概率",
  AS_OF_BLOCKED: "赛前时间点拦截",
  SCORE_MARKET_UNAVAILABLE: "比分市场不可用",
  ODDS_UNAVAILABLE: "缺当前赔率",
  AH_MAINLINE_AMBIGUOUS: "全场让球主盘口不明确",
  AH_PRIMARY_MAINLINE_MISSING: "缺少可确认的全场让球主盘口",
  AH_MAINLINE_JUMP_REQUIRES_PRIMARY_CONFIRMATION: "全场让球主盘口跳线缺少确认",
  FIXTURE_NOT_UPCOMING: "非赛前",
  UNSUPPORTED_MARKET: "市场不支持",
  UNKNOWN_BLOCKER: "未知阻塞",
};

const ACTION_LABELS: Record<string, string> = {
  READY_FOR_ANALYSIS: "可分析",
  WAIT_MARKET_OBSERVATIONS: "等待盘口观测",
  WAIT_BOOKMAKER_QUOTES: "等待庄家报价",
  WAIT_ODDS_TIMELINE: "等待盘口时间线",
  WAIT_XG: "等待 xG",
  WAIT_SCORE_MODEL: "等待比分模型",
  WAIT_MODEL_PROBABILITIES: "等待模型概率",
  WAIT_MARKET_PROBABILITIES: "等待市场概率",
  WAIT_FIXTURE_STATUS: "等待赛前状态",
  INVESTIGATE_DATA_PIPELINE: "检查数据链路",
};

function pricingShadowLine(shadow?: PricingShadow | null): string | null {
  if (!shadow) return null;
  if (shadow.status === "INSUFFICIENT_INDEPENDENT_FACTORS") return "独立评分覆盖不足 · 当前观察，不强推";
  const coverage = typeof shadow.coverage === "number" ? ` · 覆盖率 ${Math.round(Math.max(0, Math.min(1, shadow.coverage)) * 100)}%` : "";
  if (shadow.status === "WATCH") return `无明显独立优势 · 观察${coverage}`;
  return `独立评分参考 · 待校准${coverage}`;
}

function blockerLabel(blocker: string): string {
  const known = BLOCKER_LABELS[blocker];
  if (known) return known;
  return /^[A-Z0-9_:.-]+$/.test(blocker) ? "数据状态待确认" : blocker;
}

export function UpcomingFixtureCard({ match }: { match: DashboardMatchCard }) {
  const judgement = match.recommendation ? `${match.recommendation.market_label_cn} · ${match.recommendation.selection_label_cn ?? match.recommendation.selection}` : "观察";
  const readiness = match.analysis_readiness;
  const blockers = readiness?.blockers ?? [];
  const inputs = readiness?.available_inputs;
  return (
    <article className={`upcoming-card readiness-${readiness?.status.toLowerCase() ?? "unknown"}`}>
      <span className="match-meta">
        {fmtTime(match.kickoff_utc)} · {match.competition_name}
      </span>
      <div className="compact-teams">
        <span>{teamCode(match.home_team_name)}</span>
        <strong>{match.home_team_name}</strong>
        <em>vs</em>
        <strong>{match.away_team_name}</strong>
        <span>{teamCode(match.away_team_name)}</span>
      </div>
      <DataReadinessRow match={match} />
      {readiness ? (
        <div className="analysis-readiness-line">
          <strong>{readiness.status}</strong>
          <span>{ACTION_LABELS[readiness.next_action] ?? readiness.next_action}</span>
          <small>
            盘口 {inputs?.market_observations ?? 0} · 庄家 {inputs?.bookmakers ?? 0} · 快照 {inputs?.odds_snapshots ?? 0}
          </small>
        </div>
      ) : null}
      {blockers.length ? (
        <div className="blocker-chips" aria-label="分析阻塞原因">
          {blockers.slice(0, 5).map((blocker) => (
            <span key={blocker}>{blockerLabel(blocker)}</span>
          ))}
        </div>
      ) : null}
      {pricingShadowLine(match.pricing_shadow) ? <p className="pricing-shadow-compact">{pricingShadowLine(match.pricing_shadow)}</p> : null}
      <p>当前判断：{judgement}</p>
      <small>{match.missing_inputs.length ? `等待：${match.missing_inputs.join("、")}` : "可分析 · 下一次刷新按赛前梯度执行"}</small>
    </article>
  );
}
