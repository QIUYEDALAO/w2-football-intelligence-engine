import type { DashboardMatchCard } from "../types/dashboard";
import { EmptySection } from "./EmptySection";
import { UpcomingFixtureCard } from "./UpcomingFixtureCard";

export function UpcomingFixturesPanel({ matches }: { matches: DashboardMatchCard[] }) {
  return (
    <section className="dashboard-section">
      <div className="section-heading">
        <h2>Upcoming Fixtures</h2>
        <p>未来比赛不强推；数据不足时明确展示还缺什么。</p>
      </div>
      {matches.length ? (
        <div className="upcoming-grid">
          {matches.map((match) => (
            <UpcomingFixtureCard key={match.fixture_id} match={match} />
          ))}
        </div>
      ) : (
        <EmptySection title="未来 36 小时暂无已收录比赛" detail="白名单赛程进入 read-model 后会自动显示。" />
      )}
    </section>
  );
}
