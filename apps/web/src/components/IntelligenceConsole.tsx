import type {
  DashboardDayView,
  DashboardDayViewCard,
  IntelligenceState,
  ReleaseSyncState,
} from "../types/dashboard";
import { MarketOverviewCounts } from "./MarketOverviewCounts";

const STATE_LABELS: Record<IntelligenceState, string> = {
  MARKET_STABLE: "市场稳定 / 未检测到显著异常",
  MARKET_MOVEMENT: "市场发生变化",
  MARKET_ANOMALY: "市场异常",
  MODEL_MARKET_DISAGREEMENT: "模型与市场存在分歧",
  DATA_INCOMPLETE: "数据不完整",
  MODEL_DIAGNOSTIC_WARNING: "模型诊断警告",
  COLLECTION_INCIDENT: "采集事件",
};

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

const MARKET_LABELS = {
  ASIAN_HANDICAP: "亚洲让球",
  TOTALS: "全场大小球",
} as const;

function metric(value: unknown): string {
  return typeof value === "number" || (typeof value === "string" && value)
    ? String(value)
    : "—";
}

function MarketTimeline({ radar }: { radar: Record<string, unknown> }) {
  const timeline = record(radar.timeline);
  const state = metric(timeline.status || "INSUFFICIENT_NO_TIMELINE_EVIDENCE");
  const points = Array.isArray(timeline.points) ? timeline.points.map(record) : [];
  if (points.length === 0) {
    return <div className="intel-timeline intel-timeline--sparse" data-ui="market-timeline" data-timeline-state={state} data-real-point-count="0"><code>{state}</code><span>暂无真实时间线证据，不能推断 movement。</span></div>;
  }
  if (points.length === 1) {
    return <div className="intel-timeline intel-timeline--sparse" data-ui="market-timeline" data-timeline-state={state} data-real-point-count="1"><code>{state}</code><span className="intel-timeline-dot" aria-hidden="true" /><span>仅一个已验证快照，不能绘制 movement 路径。</span></div>;
  }
  const lines = points.map((point) => Number(point.canonical_line)).filter(Number.isFinite);
  const low = Math.min(...lines);
  const high = Math.max(...lines);
  const coordinates = points.map((point, index) => {
    const x = 8 + (index * 204) / Math.max(points.length - 1, 1);
    const line = Number(point.canonical_line);
    const y = high === low ? 24 : 42 - ((line - low) / (high - low)) * 34;
    return { x, y };
  });
  return (
    <div className="intel-timeline" data-ui="market-timeline" data-timeline-state={state} data-real-point-count={points.length}>
      <code>{state}</code>
      <svg aria-label={`${points.length} 个真实盘口时间点`} role="img" viewBox="0 0 220 50">
        <polyline fill="none" points={coordinates.map(({ x, y }) => `${x},${y}`).join(" ")} />
        {coordinates.map(({ x, y }, index) => <circle cx={x} cy={y} key={`${x}-${index}`} r="3" />)}
      </svg>
      <span>{points.length} 个真实快照 · 同线最多 {metric(timeline.same_line_comparable_snapshot_count)}</span>
    </div>
  );
}

function MarketRadar({ card }: { card: DashboardDayViewCard }) {
  const markets = record(card.market_radar?.markets);
  return (
    <div className="intel-facts intel-radar" data-ui="market-radar">
      <strong>Market Radar · 市场雷达</strong>
      {Object.entries(MARKET_LABELS).map(([market, label]) => {
        const radar = record(markets[market]);
        const current = record(radar.current);
        const freshness = record(current.freshness);
        const movement = record(radar.movement);
        const prices = record(current.prices);
        const sides = market === "ASIAN_HANDICAP" ? ["HOME", "AWAY"] : ["OVER", "UNDER"];
        if (radar.status !== "READY") {
          return <div className="intel-panel" key={market}><b>{label}</b><code>INSUFFICIENT</code><span>真实同线双边市场证据不足。</span><MarketTimeline radar={radar} /></div>;
        }
        return (
          <div className="intel-panel" key={market}>
            <b>{label}</b>
            <span>主盘口 {metric(current.canonical_line)} · Bookmakers {metric(current.bookmaker_count)}</span>
            <span>{sides.map((side) => `${side} ${metric(record(prices[side]).median)}`).join(" · ")}</span>
            <span>快照 {metric(radar.snapshot_count)} · 观测 {metric(radar.observation_count)} · Freshness {metric(freshness.status)}</span>
            <code>{metric(movement.status)}</code>
            <MarketTimeline radar={radar} />
          </div>
        );
      })}
      <small>统计异常校准：{card.market_radar?.statistical_anomaly.calibration_status || "NOT_CALIBRATED"}</small>
    </div>
  );
}

function ModelLab({ card }: { card: DashboardDayViewCard }) {
  const markets = record(card.model_lab?.markets);
  const history = record(card.model_lab?.historical_validation);
  return (
    <div className="intel-diagnostic intel-model-lab" data-ui="model-lab">
      <strong>Model Lab · 模型实验室</strong>
      {Object.entries(MARKET_LABELS).map(([market, label]) => {
        const diagnostic = record(markets[market]);
        const rows = Array.isArray(diagnostic.diagnostics) ? diagnostic.diagnostics : [];
        return (
          <div className={`intel-panel ${diagnostic.status === "MODEL_OUTSIDE_MARKET_RANGE" ? "intel-panel--warning" : ""}`} key={market}>
            <b>{label}</b><code>{metric(diagnostic.status || "MODEL_NOT_READY")}</code>
            <span>Bookmakers {Number(diagnostic.bookmaker_count) > 0 ? metric(diagnostic.bookmaker_count) : "—"} · Model {metric(diagnostic.model_version)} · Calibration {metric(diagnostic.calibration_status)}</span>
            {rows.map((value, index) => {
              const row = record(value);
              return <span key={`${market}-${index}`}>{metric(row.selection)} · model {metric(row.model_effective_settlement_probability)} · market median {metric(row.market_probability_median)} · range {metric(row.market_probability_min)}–{metric(row.market_probability_max)} · outside {metric(row.distance_outside_market_range)}</span>;
            })}
          </div>
        );
      })}
      <p className="intel-model-warning">差异仅用于模型校准与特征复核。模型超出市场区间表示需要优先检查模型校准、特征时效、盘口身份和数据质量；不代表市场机会。</p>
      <div className="intel-history-context" data-ui="phase-0-5-context"><strong>冻结历史验证</strong><span>{metric(history.final_verdict || "NO_EDGE")} · V_CONTINUATION_GATE={metric(history.v_continuation_gate || "FAIL")} · {metric(history.ou_pre_best_frozen_selections || 7566)} selections · ROI {metric(history.ou_pre_best_frozen_strategy_roi || "-5.32%")} · HISTORICAL_INCREMENTAL_EDGE={metric(history.historical_incremental_edge || "NOT_PROVEN")}</span></div>
    </div>
  );
}

function AttentionFeed({ cards }: { cards: DashboardDayViewCard[] }) {
  return (
    <section aria-labelledby="attention-feed-heading" data-ui="attention-feed">
      <div className="intelligence-section-heading"><span>Attention Feed</span><h2 id="attention-feed-heading">优先调查</h2><p>仅按七态 precedence、开赛时间和 fixture ID 排序；Attention 不是推荐。</p></div>
      <ol className="attention-feed">{cards.map((card) => <li key={card.fixture_id}><code>{card.intelligence_state}</code><strong>{card.home_team_name || "主队"} vs {card.away_team_name || "客队"}</strong><time>{card.kickoff_beijing || card.kickoff_utc || "时间待确认"}</time></li>)}</ol>
    </section>
  );
}

function RiskGrid({ card }: { card: DashboardDayViewCard }) {
  const labels = {
    EVENT_RISK: "赛事风险",
    DATA_RISK: "数据风险",
    MODEL_RISK: "模型风险",
    COLLECTION_RISK: "采集风险",
  } as const;
  return (
    <div className="intel-risk-grid" aria-label="四个独立风险维度">
      {Object.entries(labels).map(([key, label]) => {
        const dimension = record(card.risk_dimensions[key]);
        const status = String(dimension.status || "OK");
        return <div className={`intel-risk intel-risk--${status.toLowerCase()}`} key={key}><span>{label}</span><strong>{status}</strong><small>{String(dimension.explanation || "未见异常")}</small></div>;
      })}
    </div>
  );
}

function IntelligenceCard({ card }: { card: DashboardDayViewCard }) {
  return (
    <article className="intel-card" data-intelligence-state={card.intelligence_state} data-ui="match-intelligence-card">
      <header><div><span>{card.competition_name || card.competition_id || "比赛"}</span><h3>{card.home_team_name || "主队"} <b>vs</b> {card.away_team_name || "客队"}</h3></div><time>{card.kickoff_beijing || card.kickoff_utc || "时间待确认"}</time></header>
      <div className={`intel-state intel-state--${card.intelligence_state.toLowerCase()}`}><strong>{STATE_LABELS[card.intelligence_state]}</strong><code>{card.intelligence_state}</code></div>
      <MarketRadar card={card} />
      <ModelLab card={card} />
      <RiskGrid card={card} />
      <details><summary>证据与原因代码</summary><div className="intel-reasons">{card.intelligence_reason_codes.map((code) => <code key={code}>{code}</code>)}</div></details>
    </article>
  );
}

export function IntelligenceConsole({ dayView, release, emptyDetail }: { dayView: DashboardDayView; release: ReleaseSyncState; emptyDetail?: string }) {
  return (
    <div className="intelligence-shell" data-ui="football-intelligence">
      <header className="intelligence-hero"><div><span className="intelligence-kicker">W2</span><h1>W2 Football Intelligence</h1><p>W2 Football Market Intelligence &amp; Model Diagnostics</p></div><div className="intelligence-mode">{dayView.environment.toUpperCase()} · READ ONLY</div></header>
      <section aria-labelledby="market-overview-heading"><div className="intelligence-section-heading"><span>Market Overview</span><h2 id="market-overview-heading">市场总览</h2><p>零项显著警报是有效结果，不会通过降低阈值制造内容。</p></div><MarketOverviewCounts dayView={dayView} /></section>
      {dayView.cards.length ? <AttentionFeed cards={dayView.cards} /> : null}
      <section aria-labelledby="match-intelligence-heading"><div className="intelligence-section-heading"><span>Match Intelligence</span><h2 id="match-intelligence-heading">比赛情报</h2><p>市场事实、数据质量与模型诊断相互独立。</p></div>{dayView.cards.length ? <div className="intelligence-grid">{dayView.cards.map((card) => <IntelligenceCard card={card} key={card.fixture_id} />)}</div> : <div className="intelligence-empty"><strong>当前足球日没有比赛</strong><p>{emptyDetail || "这是明确的空日状态；不会虚构稳定比赛。"}</p></div>}</section>
      <section aria-labelledby="operations-heading"><div className="intelligence-section-heading"><span>Data &amp; Operations Summary</span><h2 id="operations-heading">数据与运行摘要</h2></div><div className="intelligence-ops"><div><span>页面更新时间</span><strong>{dayView.freshness.page_updated_at || "待确认"}</strong></div><div><span>最近确认赔率</span><strong>{dayView.freshness.odds_last_confirmed_at || "待确认"}</strong></div><div><span>Provider</span><strong>{dayView.freshness.provider_budget_status || "UNKNOWN"}</strong></div><div><span>API / Web SHA</span><strong className={release.mismatch ? "is-incident" : "is-ok"}>{release.api_git_sha.slice(0, 7)} / {release.web_git_sha.slice(0, 7)} · {release.mismatch ? "MISMATCH" : "SYNC"}</strong></div></div><details className="intelligence-ops-details"><summary>运行细节</summary><div className="intelligence-ops"><div><span>下次检查点</span><strong>{dayView.freshness.next_refresh_tick || "待确认"}</strong></div><div><span>Scheduler</span><strong>ON · CONTROLLED</strong></div><div><span>Safety switches</span><strong>Candidate OFF · Formal OFF · Lock OFF · Production OFF</strong></div></div></details></section>
    </div>
  );
}
