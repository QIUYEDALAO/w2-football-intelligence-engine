import type { DashboardPerformance } from "../types/dashboard";

function pct(value: number | null | undefined): string {
  return value === undefined || value === null ? "样本不足" : `${Math.round(value * 100)}%`;
}

function confidence(value: number | null | undefined): string {
  return value === undefined || value === null ? "样本不足" : `${Math.round(value * 100)}%`;
}

export function PerformanceHeader({ performance }: { performance: DashboardPerformance }) {
  const totals = [
    ["今日比赛", performance.today_count],
    ["候选推荐", performance.candidate_count],
    ["未来36h", performance.next36_count],
    ["已完场", performance.finished_count],
  ];
  const validation = [
    ["近样本命中率", performance.sample_size ? pct(performance.hit_rate) : `样本 ${performance.sample_size}`],
    ["市场命中率", performance.by_market[0] ? pct(performance.by_market[0].hit_rate) : "样本不足"],
    ["比分命中", performance.score_exact.sample_size ? pct(performance.score_exact.hit_rate) : "样本不足"],
    ["平均置信度", confidence(performance.average_confidence)],
  ];
  return (
    <section className="performance-header">
      <div className="hero-copy">
        <p>W2 Football Intelligence</p>
        <h1>今日推荐看板</h1>
        <span>AI 候选参考，非投注建议 · as-of 防泄漏 · 不承诺盈利</span>
      </div>
      <div className="performance-grid" aria-label="Dashboard performance">
        {totals.map(([label, value]) => (
          <div className="summary-metric" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>世界杯白名单</small>
          </div>
        ))}
        {validation.map(([label, value]) => (
          <div className="summary-metric is-validation" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{performance.sample_size ? `样本 ${performance.sample_size}` : "等待赛后验证"}</small>
          </div>
        ))}
      </div>
      <p className="health-line">数据健康：{performance.data_health_status}</p>
    </section>
  );
}
