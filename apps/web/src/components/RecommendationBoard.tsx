import type { DashboardMatchCard } from "../types/dashboard";
import { EmptySection } from "./EmptySection";
import { RecommendationCard } from "./RecommendationCard";

export function RecommendationBoard({ matches }: { matches: DashboardMatchCard[] }) {
  return (
    <section className="dashboard-section">
      <div className="section-heading">
        <h2>推荐看板</h2>
        <p>正式/候选只来自显式标记；未校准 analysis 字段只作背景，不输出方向。</p>
      </div>
      {matches.length ? (
        <div className="recommendation-grid">
          {matches.map((match) => (
            <RecommendationCard key={match.fixture_id} match={match} />
          ))}
        </div>
      ) : (
        <EmptySection title="暂无正式/候选或分析倾向" detail="未来赛程仍保留展示；观察或跳过的比赛不进入赛后统计。" />
      )}
    </section>
  );
}
