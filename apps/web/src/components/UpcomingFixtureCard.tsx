import { fmtTime, teamCode } from "../lib/formatters";
import type { DashboardMatchCard } from "../types/dashboard";
import { DataReadinessRow } from "./DataReadinessRow";

export function UpcomingFixtureCard({ match }: { match: DashboardMatchCard }) {
  const judgement = match.recommendation ? `${match.recommendation.market_label_cn} · ${match.recommendation.selection_label_cn ?? match.recommendation.selection}` : "观察";
  return (
    <article className="upcoming-card">
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
      <p>当前判断：{judgement}</p>
      <small>{match.missing_inputs.length ? `等待：${match.missing_inputs.join("、")}` : "可分析 · 下一次刷新按赛前梯度执行"}</small>
    </article>
  );
}
