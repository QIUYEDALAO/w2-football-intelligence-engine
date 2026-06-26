import { fmtTime, teamCode } from "../lib/formatters";
import { currentOdds, watchLevel } from "../lib/normalize";
import type { DashboardMatchCard } from "../types/dashboard";
import { DataReadinessRow } from "./DataReadinessRow";
import { MarketPickSummary } from "./MarketPickSummary";
import { OddsMovementMini } from "./OddsMovementMini";
import { ScorelinePicks } from "./ScorelinePicks";
import { SettlementBadge } from "./SettlementBadge";

function tierLabel(match: DashboardMatchCard): string {
  const settlement = match.validation?.settlement;
  if (settlement && settlement !== "PENDING") return "";
  if (match.recommendation?.tier === "FORMAL") return "正式推荐";
  if (match.recommendation?.tier === "CANDIDATE") return "候选推荐";
  if (match.recommendation?.tier === "ANALYSIS_PICK") return "分析参考";
  if (match.recommendation?.tier === "WATCH") return "观察";
  return "暂无推荐";
}

export function RecommendationCard({ match }: { match: DashboardMatchCard }) {
  const pick = match.recommendation;
  const odds = currentOdds({ current_odds: match.current_odds });
  const risks = pick?.risks.length ? pick.risks : ["天气、红牌、阵容临场变化可能改变判断"];
  return (
    <article className={`recommendation-card tier-${pick?.tier.toLowerCase() ?? "none"}`}>
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
        {match.validation ? <SettlementBadge status={match.validation.settlement} /> : <span className="status-pill is-pick">{tierLabel(match)}</span>}
      </header>
      {pick ? <MarketPickSummary pick={pick} /> : <p className="no-pick-copy">当前仅观察，不展示候选推荐。</p>}
      <ScorelinePicks picks={match.scoreline_picks} />
      <DataReadinessRow match={match} />
      <OddsMovementMini match={match} />
      <div className="recommendation-footer">
        <div>
          <p className="reason-line">理由：{pick?.reasons.slice(0, 2).join("；") ?? "等待盘口、xG、阵容和 as-of 条件满足。"}</p>
          <p className="risk-line">风险：{risks.slice(0, 2).join("、")}</p>
          <p className="odds-line">{odds.length ? odds.join(" · ") : "当前盘口等待采集"}</p>
        </div>
        <span className="watch-stars">关注度 {"★".repeat(watchLevel({ watch_level: match.watch_level }))}{"☆".repeat(5 - watchLevel({ watch_level: match.watch_level }))}</span>
      </div>
    </article>
  );
}
