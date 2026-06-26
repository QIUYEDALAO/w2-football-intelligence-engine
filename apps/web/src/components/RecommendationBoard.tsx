import type { DashboardMatchCard } from "../types/dashboard";
import { EmptySection } from "./EmptySection";
import { RecommendationCard } from "./RecommendationCard";

export function RecommendationBoard({ matches }: { matches: DashboardMatchCard[] }) {
  return (
    <section className="dashboard-section">
      <div className="section-heading">
        <h2>Recommendation Board</h2>
        <p>正式/候选只来自显式标记；analysis pick 单独作为分析倾向展示，不伪装成正式推荐。</p>
      </div>
      {matches.length ? (
        <div className="recommendation-grid">
          {matches.map((match) => (
            <RecommendationCard key={match.fixture_id} match={match} />
          ))}
        </div>
      ) : (
        <EmptySection title="暂无正式/候选或分析倾向" detail="未来赛程仍保留展示；WATCH/SKIP 不计入命中率。" />
      )}
    </section>
  );
}
