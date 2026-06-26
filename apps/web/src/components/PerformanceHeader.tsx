import type { DashboardPerformance } from "../types/dashboard";

function pct(value: number | null | undefined): string {
  return value === undefined || value === null ? "样本不足" : `${Math.round(value * 100)}%`;
}

function confidence(value: number | null | undefined): string {
  return value === undefined || value === null ? "样本不足" : `${Math.round(value * 100)}%`;
}

export function PerformanceHeader({ performance }: { performance: DashboardPerformance }) {
  const officialCount = (performance.formal_count ?? 0) + performance.candidate_count;
  const official = performance.official ?? {
    sample_size: performance.sample_size,
    hit_count: performance.hit_count,
    miss_count: performance.miss_count,
    push_count: performance.push_count,
    void_count: performance.void_count,
    hit_rate: performance.hit_rate,
  };
  const analysisShadow = performance.analysis_shadow ?? {
    sample_size: 0,
    hit_count: 0,
    miss_count: 0,
    push_count: 0,
    void_count: 0,
    hit_rate: null,
  };
  const totals = [
    ["今日比赛", performance.today_count],
    ["正式/候选", officialCount],
    ["分析倾向", performance.analysis_pick_count ?? 0],
    ["分析可行动", performance.analysis_actionable_count ?? 0],
    ["分析阻塞", performance.analysis_blocked_count ?? 0],
    ["未来36h", performance.next36_count],
    ["已完场", performance.finished_count],
  ];
  const validation = [
    ["分析就绪率", pct(performance.analysis_readiness_rate)],
    ["正式命中率", official.sample_size ? pct(official.hit_rate) : `样本 ${official.sample_size}`],
    ["分析影子命中", analysisShadow.sample_size ? pct(analysisShadow.hit_rate) : `样本 ${analysisShadow.sample_size}`],
    ["比分命中", performance.score_exact.sample_size ? pct(performance.score_exact.hit_rate) : "样本不足"],
    ["平均置信度", confidence(performance.average_confidence)],
  ];
  return (
    <section className="performance-header">
      <div className="hero-copy">
        <p>W2 Football Intelligence</p>
        <h1>今日推荐看板</h1>
        <span>分析倾向参考，非投注建议 · as-of 防泄漏 · 不承诺盈利</span>
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
            <small>WATCH/SKIP 不计入</small>
          </div>
        ))}
      </div>
      <p className="health-line">数据健康：{performance.data_health_status}</p>
    </section>
  );
}
