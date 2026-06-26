import type { DashboardPerformance } from "../types/dashboard";

export function PerformanceHeader({ performance, updatedAt }: { performance: DashboardPerformance; updatedAt: string }) {
  const officialCount = (performance.formal_count ?? 0) + performance.candidate_count;
  const metrics = [
    ["今日", performance.today_count],
    ["分析参考", performance.analysis_pick_count ?? 0],
    ["未来36h", performance.next36_count],
    ["已完场", performance.finished_count],
    ["正式/候选", officialCount],
    ["观察", performance.watch_count ?? 0],
  ];
  return (
    <section className="performance-header compact-summary">
      <div className="compact-title-row">
        <div>
          <p>W2 今日推荐看板</p>
          <h1>紧凑型足球情报 Dashboard</h1>
        </div>
        <span>Updated {updatedAt}</span>
      </div>
      <div className="compact-metrics" aria-label="Dashboard summary">
        {metrics.map(([label, value]) => (
          <span key={label}>
            {label} <strong>{value}</strong>
          </span>
        ))}
      </div>
    </section>
  );
}
