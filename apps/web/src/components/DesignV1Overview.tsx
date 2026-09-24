import type { IntelligenceWorkspaceList, PerformanceSummary, TodayRecommendation } from "../types/intelligenceWorkspace";

type Props = {
  workspace: IntelligenceWorkspaceList;
  activeTab: "matches" | "validation" | "validation-calibrated" | "replay";
  onTabChange: (tab: "matches" | "validation" | "validation-calibrated" | "replay") => void;
};

function signed(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(2)}`;
}

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
}

function tierFor(ev: number | null | undefined): string {
  if (ev === null || ev === undefined) return "待融合";
  if (ev >= 0.05) return "重点";
  if (ev >= 0.02) return "一般";
  if (ev >= 0) return "观察";
  return "不推";
}

function statusLabel(value: string): string {
  return { settled: "已结算", confirmed: "已确认", candidate: "候选", withdrawn: "已撤回" }[value] || value;
}

function summary(workspace: IntelligenceWorkspaceList): PerformanceSummary {
  return workspace.performance_summary || {
    calibration_identity: null,
    status: "UNAVAILABLE",
    last_7_days: { match_count: 0, hit_rate: null, profit_units: 0 },
    last_30_days: { match_count: 0, hit_rate: null, profit_units: 0 },
    daily_series: [],
  };
}

function recommendations(workspace: IntelligenceWorkspaceList): TodayRecommendation[] {
  return workspace.today_recommendations || [];
}

function PnlChart({ points }: { points: PerformanceSummary["daily_series"] }) {
  if (!points.length) return <div className="design-v1-chart-empty">暂无近 30 天累计盈亏数据</div>;
  const width = 720;
  const height = 180;
  const values = points.map((point) => point.cumulative_profit_units);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const span = max - min || 1;
  const x = (index: number) => (index / Math.max(1, points.length - 1)) * width;
  const y = (value: number) => height - ((value - min) / span) * height;
  const path = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.cumulative_profit_units).toFixed(1)}`).join(" ");
  const zero = y(0);
  return <svg className="design-v1-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="近 30 天累计盈亏折线图">
    <line className="design-v1-chart-zero" x1="0" x2={width} y1={zero} y2={zero} />
    <path className="design-v1-chart-line" d={path} />
    <circle className="design-v1-chart-dot" cx={x(points.length - 1)} cy={y(values[values.length - 1] || 0)} r="4" />
  </svg>;
}

export function DesignV1Overview({ workspace, activeTab, onTabChange }: Props) {
  const performance = summary(workspace);
  const picks = recommendations(workspace);
  const status = workspace.system_status || {};
  return <section className="design-v1-shell" aria-label="设计稿 v1 情报台">
    <header className="design-v1-header">
      <div><span className="design-v1-eyebrow">W2 / INTELLIGENCE DESK</span><h1>情报工作台</h1><p>{workspace.date} · 当前模型版本 {performance.calibration_identity || "未绑定"}</p></div>
      <div className="design-v1-status" aria-label="系统状态"><span className="design-v1-badge is-live">{status.data || "数据未就绪"}</span><span className="design-v1-badge is-open">{status.recommendations || "推荐未开启"}</span></div>
    </header>
    <div className="design-v1-kpis" aria-label="战绩汇总">
      <article><span>今日推荐</span><strong>{picks.length}<small>条</small></strong><em>已结算 {picks.filter((p) => p.status === "settled").length} · 待开赛 {picks.filter((p) => p.status === "confirmed" || p.status === "candidate").length} · 撤回 {picks.filter((p) => p.status === "withdrawn").length}</em></article>
      <article><span>今日结算</span><strong>{performance.status === "AVAILABLE" ? signed(performance.daily_series[performance.daily_series.length - 1]?.daily_profit_units) : "—"}<small>单位</small></strong><em>按当前模型版本</em></article>
      <article><span>下一场推荐</span><strong>{picks.find((p) => p.status === "confirmed" || p.status === "candidate") ? new Date(picks.find((p) => p.status === "confirmed" || p.status === "candidate")!.kickoff_utc || "").toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }) : "—"}<small>开球</small></strong><em>{picks.find((p) => p.status === "confirmed" || p.status === "candidate")?.home || "暂无待开赛推荐"}</em></article>
      <article><span>近 7 天</span><strong>{performance.status === "AVAILABLE" ? signed(performance.last_7_days.profit_units) : "—"}<small>单位</small></strong><em>{performance.status === "AVAILABLE" ? performance.last_7_days.match_count : "—"} 场 · 命中 {percent(performance.last_7_days.hit_rate)}</em></article>
      <article><span>近 30 天</span><strong>{performance.status === "AVAILABLE" ? signed(performance.last_30_days.profit_units) : "—"}<small>单位</small></strong><em>{performance.status === "AVAILABLE" ? performance.last_30_days.match_count : "—"} 场 · 命中 {percent(performance.last_30_days.hit_rate)}</em></article>
    </div>
    <p className="design-v1-note">战绩统计口径：当前模型版本（calibration_identity）</p>
    <div className="design-v1-grid">
      <section className="design-v1-panel" aria-labelledby="design-v1-picks-title"><header><div><span className="design-v1-eyebrow">TODAY PICKS</span><h2 id="design-v1-picks-title">今日推荐</h2></div><span className="design-v1-muted">三档展示冻结：重点 / 一般 / 观察 / 不推</span></header>
        {picks.length ? <div className="design-v1-table-wrap"><table className="design-v1-table"><thead><tr><th>开球</th><th>联赛</th><th>对阵</th><th>推荐</th><th>赔率</th><th>EV</th><th>档位</th><th>状态</th><th>公平线 / 价差</th></tr></thead><tbody>{picks.map((pick) => { const displayEv = pick.fusion_ev ?? pick.ev; const tier = pick.tier || tierFor(displayEv); return <tr key={`${pick.fixture_id}-${pick.market}`}><td>{pick.kickoff_utc ? new Date(pick.kickoff_utc).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }) : "—"}</td><td>{pick.competition_name_zh || "赛事待确认"}</td><td>{pick.home || "主队待确认"} vs {pick.away || "客队待确认"}</td><td>{pick.market || "—"} {pick.line ?? ""} · {pick.selection || "—"}</td><td>{pick.odds ?? "—"}</td><td className={Number(displayEv) >= 0 ? "is-positive" : "is-negative"}>{displayEv === null || displayEv === undefined ? "—" : `${(displayEv * 100).toFixed(1)}%`}</td><td><span className={`design-v1-tier tier-${tier}`}>{tier}</span></td><td><span className={`design-v1-pick-status status-${pick.status}`}>{statusLabel(pick.status)}</span>{pick.withdraw_reason ? <small className="design-v1-withdraw">{pick.withdraw_reason}</small> : null}</td><td>{pick.pinnacle_fair_line ?? "—"} / {pick.channel_price_gap === null || pick.channel_price_gap === undefined ? "—" : `${(pick.channel_price_gap * 100).toFixed(1)}%`}</td></tr>; })}</tbody></table></div> : <p className="design-v1-empty">今日没有当前模型版本推荐。</p>}
      </section>
      <aside className="design-v1-panel design-v1-chart-panel" aria-labelledby="design-v1-pnl-title"><header><div><span className="design-v1-eyebrow">PERFORMANCE</span><h2 id="design-v1-pnl-title">近 30 天累计盈亏</h2></div><strong>{performance.status === "AVAILABLE" ? signed(performance.last_30_days.profit_units) : "—"} <small>单位</small></strong></header><PnlChart points={performance.daily_series} /></aside>
    </div>
    <nav className="design-v1-tabs" aria-label="设计稿视图"><button aria-current={activeTab === "matches" ? "page" : undefined} onClick={() => onTabChange("matches")} type="button">比赛</button><button aria-current={activeTab === "validation" || activeTab === "validation-calibrated" ? "page" : undefined} onClick={() => onTabChange("validation")} type="button">战绩复盘</button><button aria-current={activeTab === "replay" ? "page" : undefined} onClick={() => onTabChange("replay")} type="button">回放记录</button></nav>
  </section>;
}

export default DesignV1Overview;
