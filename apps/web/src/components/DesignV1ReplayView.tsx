import type { IntelligenceReplayResponse } from "../types/intelligenceWorkspace";

export default function DesignV1ReplayView({ response }: { response: IntelligenceReplayResponse }) {
  return <ul className="w2-replay" data-design-v1-replay>{response.matches.length ? response.matches.map((match) => <li key={match.fixture_id}><span className="num">{match.date || match.kickoff_utc?.slice(5, 10) || "—"}</span><div className="w2-match"><strong>{match.match || `${match.home_team_name || "主队待确认"} vs ${match.away_team_name || "客队待确认"}`}</strong><span>{match.league || match.competition_name || "赛事待确认"} · {match.evaluation_count ?? 0} 个评估时点 · 最终推荐 {match.final_recommendation || "—"}</span></div><span className="w2-link">回放记录</span></li>) : <li>当前足球日没有回放记录。</li>}</ul>;
}
