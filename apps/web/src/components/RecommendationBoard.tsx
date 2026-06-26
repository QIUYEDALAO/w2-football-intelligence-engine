import type { DashboardMatchCard } from "../types/dashboard";
import { EmptySection } from "./EmptySection";
import { RecommendationCard } from "./RecommendationCard";

export function RecommendationBoard({ matches }: { matches: DashboardMatchCard[] }) {
  return (
    <section className="dashboard-section">
      <div className="section-heading">
        <h2>Recommendation Board</h2>
        <p>只展示正式、候选或有 PICK 市场的比赛；非 formal 一律标为候选/观察。</p>
      </div>
      {matches.length ? (
        <div className="recommendation-grid">
          {matches.map((match) => (
            <RecommendationCard key={match.fixture_id} match={match} />
          ))}
        </div>
      ) : (
        <EmptySection title="暂无候选推荐" detail="系统会在盘口、xG、阵容和 as-of 条件满足后生成候选；当前比赛仍显示在未来赛程。" />
      )}
    </section>
  );
}
