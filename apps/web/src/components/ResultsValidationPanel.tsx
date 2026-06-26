import type { DashboardMatchCard } from "../types/dashboard";
import { EmptySection } from "./EmptySection";
import { ResultValidationCard } from "./ResultValidationCard";

export function ResultsValidationPanel({ matches }: { matches: DashboardMatchCard[] }) {
  return (
    <section className="dashboard-section">
      <div className="section-heading">
        <h2>Results & Validation</h2>
        <p>只把正式或候选推荐计入命中率；WATCH/SKIP 不计入。</p>
      </div>
      {matches.length ? (
        <div className="results-grid">
          {matches.map((match) => (
            <ResultValidationCard key={match.fixture_id} match={match} />
          ))}
        </div>
      ) : (
        <EmptySection title="暂无已完场验证样本" detail="比赛完场并同步结果后会显示命中/未中；无推荐比赛不计入命中率。" />
      )}
    </section>
  );
}
