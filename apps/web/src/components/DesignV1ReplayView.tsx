import type { IntelligenceReplayResponse } from "../types/intelligenceWorkspace";

export default function DesignV1ReplayView({ response }: { response: IntelligenceReplayResponse }) {
  return <section className="design-v1-review" aria-label="回放记录" data-design-v1-replay>
    <header><div><span className="design-v1-eyebrow">REPLAY</span><h2>回放记录</h2></div><span>{response.date} · {response.matches.length} 场</span></header>
    {response.matches.length ? <ol className="design-v1-replay-list">{response.matches.map((match) => <li key={match.fixture_id}><time>{match.date || match.kickoff_utc || "—"}</time><div><strong>{match.league || match.competition_name || "赛事待确认"}</strong><span>{match.match || `${match.home_team_name || "主队"} vs ${match.away_team_name || "客队"}`}</span></div><em>{match.evaluation_count ?? 0} 个评估时点 · 最终推荐 {match.final_recommendation || "—"}</em></li>)}</ol> : <p className="design-v1-empty">当前比赛日没有回放记录。</p>}
  </section>;
}
