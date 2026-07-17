import { fmtTime } from "../lib/formatters";
import type { DashboardMatchCard } from "../types/dashboard";
import { ScorelinePicks } from "./ScorelinePicks";
import { SettlementBadge } from "./SettlementBadge";

export function ResultValidationCard({ match }: { match: DashboardMatchCard }) {
  const validation = match.validation ?? { settlement: "UNKNOWN" as const };
  return (
    <article className="result-card">
      <header>
        <div>
          <span className="match-meta">
            已完场 · {fmtTime(match.kickoff_utc)} · {match.competition_name}
          </span>
          <strong>
            {match.home_team_name} {match.result?.final_score ?? "-"} {match.away_team_name}
          </strong>
        </div>
        <SettlementBadge status={validation.settlement} />
      </header>
      <p>推荐：{match.recommendation ? `${match.recommendation.market_label_cn} ${match.recommendation.selection_label_cn ?? match.recommendation.selection} ${match.recommendation.line ?? ""} ${match.recommendation.odds ? `@${match.recommendation.odds}` : ""}` : "无推荐 · 不进入赛后统计"}</p>
      <ScorelinePicks picks={match.scoreline_picks} />
      <p className="odds-line">
        收益：{validation.profit_units === undefined ? "--" : `${validation.profit_units > 0 ? "+" : ""}${validation.profit_units.toFixed(2)}u`}
        {validation.closing_line_value ? ` · 收盘线差 ${validation.closing_line_value}` : ""}
      </p>
      <p className="risk-line">验证：{validation.validation_notes?.join("；") ?? "等待结果同步"}</p>
    </article>
  );
}
