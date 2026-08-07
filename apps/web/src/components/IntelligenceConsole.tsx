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

function facts(value: unknown, prefix = "", depth = 0): string[] {
  if (depth > 2) return [];
  return Object.entries(record(value)).flatMap(([key, item]) => {
    const label = prefix ? `${prefix}.${key}` : key;
    if (item == null || item === "") return [];
    if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") {
      return [`${label}: ${String(item)}`];
    }
    return facts(item, label, depth + 1);
  });
}

function MarketFacts({ card }: { card: DashboardDayViewCard }) {
  const current = facts(card.current_odds).slice(0, 6);
  const reference = current.length ? [] : facts(card.last_known_odds).slice(0, 6);
  const rows = current.length ? current : reference;
  return (
    <div className="intel-facts" data-ui="market-facts">
      <strong>{current.length ? "当前市场事实" : reference.length ? "最后已知市场事实 · 参考/不可执行" : "市场事实待补"}</strong>
      {rows.length ? rows.map((row) => <code key={row}>{row}</code>) : <span>尚无可验证的 AH/OU 盘口事实。</span>}
    </div>
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
  const modelFacts = facts(card.market_probabilities).slice(0, 3);
  return (
    <article className="intel-card" data-intelligence-state={card.intelligence_state} data-ui="match-intelligence-card">
      <header><div><span>{card.competition_name || card.competition_id || "比赛"}</span><h3>{card.home_team_name || "主队"} <b>vs</b> {card.away_team_name || "客队"}</h3></div><time>{card.kickoff_beijing || card.kickoff_utc || "时间待确认"}</time></header>
      <div className={`intel-state intel-state--${card.intelligence_state.toLowerCase()}`}><strong>{STATE_LABELS[card.intelligence_state]}</strong><code>{card.intelligence_state}</code></div>
      <MarketFacts card={card} />
      <div className="intel-diagnostic"><strong>模型诊断</strong>{modelFacts.length ? modelFacts.map((row) => <code key={row}>{row}</code>) : <span>当前没有可展示的模型概率。</span>}{card.intelligence_state === "MODEL_MARKET_DISAGREEMENT" ? <p>差异仅用于模型校准与特征复核。</p> : null}</div>
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
      <section aria-labelledby="match-intelligence-heading"><div className="intelligence-section-heading"><span>Match Intelligence</span><h2 id="match-intelligence-heading">比赛情报</h2><p>市场事实、数据质量与模型诊断相互独立。</p></div>{dayView.cards.length ? <div className="intelligence-grid">{dayView.cards.map((card) => <IntelligenceCard card={card} key={card.fixture_id} />)}</div> : <div className="intelligence-empty"><strong>当前足球日没有比赛</strong><p>{emptyDetail || "这是明确的空日状态；不会虚构稳定比赛。"}</p></div>}</section>
      <section aria-labelledby="operations-heading"><div className="intelligence-section-heading"><span>Data &amp; Operations Summary</span><h2 id="operations-heading">数据与运行摘要</h2></div><div className="intelligence-ops"><div><span>页面更新时间</span><strong>{dayView.freshness.page_updated_at || "待确认"}</strong></div><div><span>最近确认赔率</span><strong>{dayView.freshness.odds_last_confirmed_at || "待确认"}</strong></div><div><span>下次检查点</span><strong>{dayView.freshness.next_refresh_tick || "待确认"}</strong></div><div><span>Provider</span><strong>{dayView.freshness.provider_budget_status || "UNKNOWN"}</strong></div><div><span>Scheduler</span><strong>ON · CONTROLLED</strong></div><div><span>API / Web SHA</span><strong className={release.mismatch ? "is-incident" : "is-ok"}>{release.api_git_sha.slice(0, 7)} / {release.web_git_sha.slice(0, 7)} · {release.mismatch ? "MISMATCH" : "SYNC"}</strong></div><div><span>Safety switches</span><strong>Candidate OFF · Formal OFF · Lock OFF · Production OFF</strong></div></div></section>
    </div>
  );
}
