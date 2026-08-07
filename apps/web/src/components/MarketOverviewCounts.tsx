import type { DashboardDayView } from "../types/dashboard";

export function MarketOverviewCounts({ dayView }: { dayView: DashboardDayView }) {
  const metrics = [
    ["监测比赛", dayView.counts.monitored_fixtures, "monitored fixtures"],
    ["市场完整", dayView.counts.market_complete_fixtures, "market-complete fixtures"],
    ["新鲜报价", dayView.counts.fresh_quotes, "fresh quotes"],
    ["市场稳定", dayView.counts.market_stable_fixtures, "market-stable fixtures"],
    ["市场变化", dayView.counts.market_movement_fixtures, "market-movement fixtures"],
    ["模型诊断警告", dayView.counts.model_diagnostic_warnings, "model diagnostic warnings"],
    ["数据事件", dayView.counts.data_incidents, "data incidents"],
    ["采集事件", dayView.counts.collection_incidents, "collection incidents"],
  ] as const;
  return (
    <section className="decision-counts" aria-label="Market Overview">
      {metrics.map(([label, value, hint]) => (
        <div className="decision-count" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{hint}</small>
        </div>
      ))}
    </section>
  );
}
