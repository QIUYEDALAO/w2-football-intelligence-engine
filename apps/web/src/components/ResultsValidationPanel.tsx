import type { DashboardMatchCard } from "../types/dashboard";
import { EmptySection } from "./EmptySection";
import { ResultValidationCard } from "./ResultValidationCard";

export function ResultsValidationPanel({ matches }: { matches: DashboardMatchCard[] }) {
  return (
    <section className="dashboard-section">
      <div className="section-heading">
        <h2>完场复盘</h2>
        <p>official 与 analysis_shadow 分层统计；样本不足时不计算命中率。</p>
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
