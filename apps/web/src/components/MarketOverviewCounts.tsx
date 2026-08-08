import type { DashboardDayView } from "../types/dashboard";

export function MarketOverviewCounts({ dayView }: { dayView: DashboardDayView }) {
  const states = dayView.counts.by_intelligence_state || {};
  const metrics = [
    ["监测比赛", dayView.counts.monitored_fixtures, "monitored fixtures"],
    ["市场变化", dayView.counts.market_movement_fixtures, "market-movement fixtures"],
    ["模型市场分歧", states.MODEL_MARKET_DISAGREEMENT || 0, "diagnostic disagreement"],
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
