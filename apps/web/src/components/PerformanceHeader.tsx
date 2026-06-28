import type { DashboardPerformance } from "../types/dashboard";

export function PerformanceHeader({ performance, updatedAt }: { performance: DashboardPerformance; updatedAt: string }) {
  const officialCount = (performance.formal_count ?? 0) + performance.candidate_count;
  const headline = officialCount > 0
    ? "正式推荐 · 策略自洽 · 真实赛前数据"
    : "赛前分析 · 等待正式条件 · 真实数据";
  const metrics = [
    ["今日", performance.today_count],
    ["分析参考", performance.analysis_pick_count ?? 0],
    ["未来36h", performance.next36_count],
    ["已完场", performance.finished_count],
    ["门控通过", officialCount],
    ["观察", performance.watch_count ?? 0],
  ];
  return (
    <section className="performance-header compact-summary">
      <div className="compact-title-row">
        <div>
          <p>{headline}</p>
          <h1>世界杯 · 今日赛前分析</h1>
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
