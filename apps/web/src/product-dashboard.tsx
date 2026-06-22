import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  beijingToday,
  emptyResource,
  fixtureListFromMatchday,
  loadJson,
  resourceTone,
} from "./api";
import type {
  DataHealth,
  Fixture,
  FixtureDetail,
  ForwardStatus,
  Integrity,
  MarketRanking,
  Matchday,
  MatchdayCoverage,
  OpsList,
  Probability,
  ProviderStatus,
  Resource,
  ShadowStrategyStatus,
} from "./types";

type WorkspaceTab = "overview" | "markets" | "card" | "integrity" | "shadow" | "comparison";
type MarketFilter = "ALL" | "1X2" | "AH" | "OU" | "BTTS";

const tabs: Array<{ id: WorkspaceTab; label: string }> = [
  { id: "overview", label: "概览" },
  { id: "markets", label: "Market Ranking" },
  { id: "card", label: "Research Card" },
  { id: "integrity", label: "Integrity / Timeline" },
  { id: "shadow", label: "Shadow Strategy" },
  { id: "comparison", label: "Comparison" },
];

function displayTeam(fixture: Pick<Fixture, "home_team_name" | "home_team_id">): string {
  return fixture.home_team_name ?? fixture.home_team_id;
}

function displayAway(fixture: Pick<Fixture, "away_team_name" | "away_team_id">): string {
  return fixture.away_team_name ?? fixture.away_team_id;
}

function valueText(value: unknown, fallback = "暂无"): string {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
}

function marketKind(row: Record<string, unknown>): MarketFilter {
  const raw = String(row.market ?? row.market_type ?? row.primary_market ?? "").toUpperCase();
  if (raw.includes("ASIAN") || raw === "AH") {
    return "AH";
  }
  if (raw.includes("TOTAL") || raw === "OU") {
    return "OU";
  }
  if (raw.includes("BTTS")) {
    return "BTTS";
  }
  if (raw.includes("1X2") || raw.includes("ONE")) {
    return "1X2";
  }
  return "ALL";
}

function StatusBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`status-badge tone-${tone}`}>{children}</span>;
}

function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton-card" aria-label="loading">
      {Array.from({ length: lines }, (_, index) => (
        <span key={index} />
      ))}
    </div>
  );
}

function EmptyStatePanel({ endpoint }: { endpoint: string }) {
  return (
    <div className="state-panel empty-panel">
      <strong>暂无可展示数据</strong>
      <p>接口返回为空：{endpoint}</p>
    </div>
  );
}

function ErrorStatePanel({
  resource,
  onRetry,
}: {
  resource: Resource<unknown>;
  onRetry: () => void;
}) {
  return (
    <div className="state-panel error-panel">
      <strong>读取失败</strong>
      <p>endpoint: {resource.endpoint}</p>
      <p>request_id: {resource.requestId ?? "n/a"}</p>
      <p>error: {resource.errorCode ?? resource.message ?? "UNKNOWN"}</p>
      <button type="button" onClick={onRetry}>
        重试
      </button>
    </div>
  );
}

function ResourceView<T>({
  resource,
  onRetry,
  children,
  skeletonLines = 3,
}: {
  resource: Resource<T>;
  onRetry: () => void;
  children: (data: T) => React.ReactNode;
  skeletonLines?: number;
}) {
  if (resource.status === "LOADING") {
    return <SkeletonCard lines={skeletonLines} />;
  }
  if (resource.status === "EMPTY") {
    return <EmptyStatePanel endpoint={resource.endpoint} />;
  }
  if (resource.status === "ERROR") {
    return <ErrorStatePanel resource={resource as Resource<unknown>} onRetry={onRetry} />;
  }
  return (
    <>
      {resource.status === "STALE" ? (
        <div className="state-panel stale-panel">
          <strong>数据可能过期</strong>
          <p>正在展示最后一份 read model 快照。</p>
        </div>
      ) : null}
      {resource.data ? children(resource.data) : <EmptyStatePanel endpoint={resource.endpoint} />}
    </>
  );
}

function GlobalStatusBar({
  provider,
  health,
}: {
  provider: Resource<ProviderStatus>;
  health: Resource<DataHealth>;
}) {
  const status = health.data?.provider_status ?? provider.data?.status ?? health.status;
  return (
    <header className="global-header">
      <div className="header-copy">
        <p className="eyebrow">W2 Football Intelligence</p>
        <h1>比赛日研究工作台</h1>
        <p>所有时间按北京时间展示，底层数据保持 UTC。当前只读展示，不生成正式推荐。</p>
      </div>
      <div className="global-status">
        <StatusBadge tone={status === "READY" || status === "OK" ? "good" : "watch"}>
          {valueText(status, "UNKNOWN")}
        </StatusBadge>
        <strong>正式推荐未启用 / Shadow & Research Only</strong>
        <span>最新更新时间：{health.data?.generated_at ?? "等待 read model"}</span>
      </div>
    </header>
  );
}

function SummaryKpiRow({
  fixtures,
  provider,
  health,
  forward,
  gate5,
}: {
  fixtures: Fixture[];
  provider: Resource<ProviderStatus>;
  health: Resource<DataHealth>;
  forward: Resource<ForwardStatus>;
  gate5: Resource<OpsList>;
}) {
  const researchable = fixtures.filter((fixture) => fixture.lifecycle_state === "WATCH").length;
  const kpis = [
    {
      label: "今日比赛",
      value: String(fixtures.length),
      hint: "北京时间比赛日",
      tone: "neutral",
    },
    {
      label: "可研究场次",
      value: String(researchable),
      hint: "WATCH，不等于正式推荐",
      tone: researchable > 0 ? "good" : "watch",
    },
    {
      label: "数据健康",
      value: health.data?.provider_status ?? health.status,
      hint: `${health.data?.stale_data_count ?? 0} stale records`,
      tone: health.status === "ERROR" ? "bad" : "neutral",
    },
    {
      label: "Provider / Quota",
      value: provider.data?.remaining_quota?.toLocaleString() ?? provider.status,
      hint: provider.data?.provider ?? "API-Football",
      tone: provider.status === "ERROR" ? "bad" : "neutral",
    },
    {
      label: "Gate 4",
      value: "PENDING",
      hint: "等级展示受限，最高 C",
      tone: "watch",
    },
    {
      label: "Gate 5",
      value: gate5.data?.items?.[0]?.status ?? "PROVISIONAL",
      hint: `${forward.data?.current_settled_n ?? 0}/${forward.data?.target_n ?? 0} forward samples`,
      tone: "watch",
    },
  ];
  return (
    <section className="kpi-row">
      {kpis.map((item) => (
        <article className={`kpi-card tone-${item.tone}`} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          <small>{item.hint}</small>
        </article>
      ))}
    </section>
  );
}

function FixtureListItem({
  fixture,
  active,
  onSelect,
}: {
  fixture: Fixture;
  active: boolean;
  onSelect: () => void;
}) {
  const actionTone = fixture.lifecycle_state === "WATCH" ? "good" : "neutral";
  return (
    <button className={active ? "fixture-item active" : "fixture-item"} onClick={onSelect} type="button">
      <span className="fixture-time">北京时间 {fixture.kickoff_beijing ?? fixture.kickoff_display}</span>
      <strong>
        {displayTeam(fixture)} <span>vs</span> {displayAway(fixture)}
      </strong>
      <span className="fixture-meta">{fixture.competition_name}</span>
      <span className="fixture-badges">
        <StatusBadge tone={actionTone}>{fixture.lifecycle_state}</StatusBadge>
        <StatusBadge tone="watch">Grade {fixture.published_grade ?? "X"}</StatusBadge>
        <StatusBadge tone={fixture.data_state === "READY" ? "good" : "neutral"}>
          {fixture.data_state}
        </StatusBadge>
      </span>
      <small>
        主方向：{fixture.primary_market ?? "暂无"} {fixture.primary_line ?? ""} · 快照{" "}
        {fixture.last_captured ?? "暂无"}
      </small>
    </button>
  );
}

function MatchdayFixtureList({
  fixtures,
  selected,
  selectedDate,
  onSelect,
  onDate,
}: {
  fixtures: Fixture[];
  selected: string | null;
  selectedDate: string;
  onSelect: (fixtureId: string) => void;
  onDate: (date: string) => void;
}) {
  return (
    <section className="matchday-panel">
      <div className="section-title">
        <div>
          <p className="eyebrow">Matchday Center</p>
          <h2>今日比赛</h2>
        </div>
        <label className="date-control">
          <span>北京时间日期</span>
          <input type="date" value={selectedDate} onChange={(event) => onDate(event.target.value)} />
        </label>
      </div>
      <p className="helper-text">北京时间 00:00:00 至次日 00:00:00，左闭右开。</p>
      <div className="fixture-list">
        {fixtures.map((fixture) => (
          <FixtureListItem
            active={fixture.fixture_id === selected}
            fixture={fixture}
            key={fixture.fixture_id}
            onSelect={() => onSelect(fixture.fixture_id)}
          />
        ))}
      </div>
    </section>
  );
}

function FactGrid({ items }: { items: Array<[string, React.ReactNode]> }) {
  return (
    <dl className="fact-grid">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function FixtureOverviewPanel({
  detail,
  market,
  model,
}: {
  detail: FixtureDetail;
  market: Resource<Probability>;
  model: Resource<Probability>;
}) {
  return (
    <div className="workspace-grid">
      <article className="hero-card">
        <span>{detail.competition_name}</span>
        <h2>
          {displayTeam(detail)} <em>vs</em> {displayAway(detail)}
        </h2>
        <p>北京时间 {detail.kickoff_beijing ?? detail.kickoff_display}</p>
        <div className="hero-badges">
          <StatusBadge tone={detail.forward_decision === "WATCH" ? "good" : "neutral"}>
            {detail.forward_decision}
          </StatusBadge>
          <StatusBadge tone="watch">正式推荐未启用</StatusBadge>
          <StatusBadge tone="watch">Gate 4 未通过，等级展示受限</StatusBadge>
        </div>
      </article>
      <FactGrid
        items={[
          ["最新快照时间", detail.source_captured_at ?? "暂无"],
          ["数据状态", detail.data_state],
          ["市场状态", detail.integrity_status ?? "UNKNOWN"],
          ["Bookmaker 数", detail.bookmaker_count],
          ["主方向", `${detail.primary_market ?? "暂无"} ${detail.primary_selection ?? ""}`],
          ["风险调整 EV", detail.primary_risk_adjusted_ev ?? "暂无"],
          ["Model fair odds", detail.primary_model_fair_odds ?? "暂无"],
          ["失效条件", detail.risk_notes.length ? detail.risk_notes.join(" / ") : "暂无"],
        ]}
      />
      <ProbabilityBars title="市场公平概率" resource={market} />
      <ProbabilityBars title="独立模型概率" resource={model} />
    </div>
  );
}

function ProbabilityBars({ title, resource }: { title: string; resource: Resource<Probability> }) {
  const rows = Object.entries(resource.data?.probabilities ?? {});
  return (
    <article className="probability-card">
      <div className="section-title compact-title">
        <h3>{title}</h3>
        <StatusBadge tone={resource.status === "SUCCESS" ? "good" : "neutral"}>
          {resource.status}
        </StatusBadge>
      </div>
      {rows.length ? (
        rows.map(([label, value]) => (
          <div className="probability-row" key={label}>
            <span>{label}</span>
            <div>
              <i style={{ width: `${Math.max(4, value * 100)}%` }} />
            </div>
            <strong>{(value * 100).toFixed(1)}%</strong>
          </div>
        ))
      ) : (
        <p className="helper-text">暂无概率 read model。</p>
      )}
      <small>{resource.data?.source ?? "source pending"}</small>
    </article>
  );
}

function PrimaryResearchCard({ detail }: { detail: FixtureDetail }) {
  return (
    <article className="research-card">
      <div className="section-title">
        <div>
          <p className="eyebrow">Research Card</p>
          <h2>{detail.forward_decision === "WATCH" ? "研究观察" : "暂不进入观察"}</h2>
        </div>
        <StatusBadge tone="watch">研究级输出</StatusBadge>
      </div>
      <div className="research-primary">
        <span>Primary direction</span>
        <strong>
          {detail.primary_market ?? "NO_MARKET"} {detail.primary_selection ?? ""}{" "}
          {detail.primary_line ?? ""}
        </strong>
        <p>
          executable {detail.primary_executable_odds ?? "n/a"} · HK{" "}
          {detail.primary_hong_kong_odds ?? "n/a"} · grade {detail.research_grade ?? "D"}
        </p>
      </div>
      <FactGrid
        items={[
          ["Model fair odds", detail.primary_model_fair_odds ?? "暂无"],
          ["Risk-adjusted EV", detail.primary_risk_adjusted_ev ?? "暂无"],
          ["Secondary", detail.secondary_market_direction ? "存在次方向" : "无或已 suppressed"],
          ["Published grade", `${detail.published_grade ?? detail.research_grade ?? "X"}（受 Gate 限制）`],
          ["正式推荐", "false"],
          ["Candidate", "false"],
        ]}
      />
      <p className="notice">正式推荐尚未启用。当前 grade 不能解释为正式推荐强度。</p>
    </article>
  );
}

function MarketRankingPanel({ detail, ranking }: { detail: FixtureDetail; ranking: Resource<MarketRanking> }) {
  const [filter, setFilter] = useState<MarketFilter>("ALL");
  const [expanded, setExpanded] = useState(false);
  const rows = ranking.data?.items?.length
    ? ranking.data.items
    : [
        ...(detail.all_market_ranking ?? []),
        ...(detail.ah_ladder ?? []),
        ...(detail.ou_ladder ?? []),
        ...(detail.one_x_two_ranking ?? []),
        ...(detail.btts_ranking ?? []),
      ];
  const visibleRows = rows.filter((row) => filter === "ALL" || marketKind(row) === filter);
  const limit = expanded ? visibleRows.length : 6;
  return (
    <article className="table-card">
      <div className="section-title">
        <div>
          <p className="eyebrow">Market Ranking</p>
          <h2>全市场排序</h2>
        </div>
        <div className="segmented-control">
          {(["ALL", "1X2", "AH", "OU", "BTTS"] as MarketFilter[]).map((item) => (
            <button
              className={filter === item ? "selected" : ""}
              key={item}
              onClick={() => setFilter(item)}
              type="button"
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      {visibleRows.length ? (
        <>
          <table className="ranking-table">
            <thead>
              <tr>
                <th>市场</th>
                <th>方向</th>
                <th>盘口</th>
                <th>可执行赔率</th>
                <th>模型公平赔率</th>
                <th>Risk EV</th>
                <th>质量</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.slice(0, limit).map((row, index) => (
                <tr key={`${String(row.market ?? row.market_type)}-${index}`}>
                  <td>{valueText(row.market ?? row.market_type)}</td>
                  <td>{valueText(row.selection ?? row.direction ?? row.canonical_selection)}</td>
                  <td>{valueText(row.line ?? row.normalized_line, "-")}</td>
                  <td>{valueText(row.executable_odds ?? row.decimal_odds)}</td>
                  <td>{valueText(row.model_fair_odds)}</td>
                  <td>{valueText(row.risk_adjusted_ev ?? row.net_edge_after_uncertainty)}</td>
                  <td>{valueText(row.market_quality ?? row.data_quality ?? row.outlier_status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {visibleRows.length > 6 ? (
            <button className="text-button" onClick={() => setExpanded((value) => !value)} type="button">
              {expanded ? "收起市场" : `展开更多市场（${visibleRows.length - 6}）`}
            </button>
          ) : null}
        </>
      ) : (
        <EmptyStatePanel endpoint={ranking.endpoint} />
      )}
    </article>
  );
}

function IntegrityPanel({ detail, integrity }: { detail: FixtureDetail; integrity: Resource<Integrity> }) {
  return (
    <article className="detail-card">
      <div className="section-title">
        <h2>数据完整性与时间线</h2>
        <StatusBadge tone={detail.integrity_status === "PASS" ? "good" : "watch"}>
          {detail.integrity_status ?? integrity.status}
        </StatusBadge>
      </div>
      <FactGrid
        items={[
          ["Snapshot", detail.source_snapshot_id ?? "暂无"],
          ["Phase", detail.source_phase ?? "暂无"],
          ["Captured", detail.source_captured_at ?? "暂无"],
          ["Valuation generated", detail.valuation_generated_at ?? "暂无"],
          ["Projector generated", detail.projector_generated_at ?? "暂无"],
          ["Temporal status", detail.temporal_status ?? "UNKNOWN"],
        ]}
      />
      <pre>{JSON.stringify(integrity.data?.integrity ?? detail.provenance ?? {}, null, 2)}</pre>
    </article>
  );
}

function ShadowStrategyPanel({ shadow }: { shadow: Resource<ShadowStrategyStatus> }) {
  if (!shadow.data) {
    return <EmptyStatePanel endpoint={shadow.endpoint} />;
  }
  return (
    <article className="detail-card">
      <div className="section-title">
        <h2>Shadow Strategy</h2>
        <StatusBadge tone="watch">{shadow.data.gate5_status}</StatusBadge>
      </div>
      <FactGrid
        items={[
          ["Status", shadow.data.status],
          ["Version", shadow.data.strategy_version],
          ["Locks", shadow.data.locks],
          ["Decisions", shadow.data.decisions],
          ["Gate 4", shadow.data.gate4_status],
          ["Latest run", shadow.data.latest_run_id ?? "暂无"],
        ]}
      />
      <p className="notice">Shadow 仅允许 WATCH / SKIP；正式推荐未启用。</p>
    </article>
  );
}

function ComparisonPanel({ comparison }: { comparison: Resource<OpsList> }) {
  if (!comparison.data?.items.length) {
    return <EmptyStatePanel endpoint={comparison.endpoint} />;
  }
  return (
    <article className="detail-card">
      <div className="section-title">
        <h2>W1/W2 Comparison</h2>
        <StatusBadge tone="neutral">只读</StatusBadge>
      </div>
      <div className="ops-list">
        {comparison.data.items.map((item) => (
          <div key={item.key}>
            <strong>{item.key}</strong>
            <span>{item.status}</span>
          </div>
        ))}
      </div>
    </article>
  );
}

function FixtureWorkspace({
  detail,
  market,
  model,
  ranking,
  integrity,
  shadow,
  comparison,
  onRetryDetail,
}: {
  detail: Resource<FixtureDetail>;
  market: Resource<Probability>;
  model: Resource<Probability>;
  ranking: Resource<MarketRanking>;
  integrity: Resource<Integrity>;
  shadow: Resource<ShadowStrategyStatus>;
  comparison: Resource<OpsList>;
  onRetryDetail: () => void;
}) {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("overview");
  return (
    <section className="workspace-panel">
      <div className="workspace-tabs" role="tablist" aria-label="Fixture detail tabs">
        {tabs.map((tab) => (
          <button
            className={activeTab === tab.id ? "selected" : ""}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <ResourceView resource={detail} onRetry={onRetryDetail} skeletonLines={8}>
        {(data) => (
          <>
            {activeTab === "overview" ? (
              <FixtureOverviewPanel detail={data} market={market} model={model} />
            ) : null}
            {activeTab === "markets" ? <MarketRankingPanel detail={data} ranking={ranking} /> : null}
            {activeTab === "card" ? <PrimaryResearchCard detail={data} /> : null}
            {activeTab === "integrity" ? <IntegrityPanel detail={data} integrity={integrity} /> : null}
            {activeTab === "shadow" ? <ShadowStrategyPanel shadow={shadow} /> : null}
            {activeTab === "comparison" ? <ComparisonPanel comparison={comparison} /> : null}
          </>
        )}
      </ResourceView>
    </section>
  );
}

function ProviderQuotaCard({ provider }: { provider: Resource<ProviderStatus> }) {
  return (
    <aside className="rail-card">
      <div className="section-title compact-title">
        <h3>Provider / Quota</h3>
        <StatusBadge tone={provider.status === "SUCCESS" ? "good" : "neutral"}>
          {provider.status}
        </StatusBadge>
      </div>
      <strong>{provider.data?.remaining_quota ?? "unknown"}</strong>
      <p>{provider.data?.provider ?? "API-Football"} · last {provider.data?.last_request_status ?? "n/a"}</p>
    </aside>
  );
}

function GateStatusCard({ forward, gate5 }: { forward: Resource<ForwardStatus>; gate5: Resource<OpsList> }) {
  return (
    <aside className="rail-card">
      <div className="section-title compact-title">
        <h3>Gate 状态</h3>
        <StatusBadge tone="watch">PENDING</StatusBadge>
      </div>
      <p>Gate 4 未通过，等级展示受限。</p>
      <p>Gate 5：{gate5.data?.items?.[0]?.status ?? "PROVISIONAL_BLOCKED_GATE4"}</p>
      <small>
        Forward settled {forward.data?.current_settled_n ?? 0}/{forward.data?.target_n ?? 0}
      </small>
    </aside>
  );
}

function SystemHealthCard({ health, coverage }: { health: Resource<DataHealth>; coverage: Resource<MatchdayCoverage> }) {
  return (
    <aside className="rail-card">
      <div className="section-title compact-title">
        <h3>数据健康</h3>
        <StatusBadge tone={health.status === "ERROR" ? "bad" : "neutral"}>
          {health.data?.provider_status ?? health.status}
        </StatusBadge>
      </div>
      <p>stale: {health.data?.stale_data_count ?? 0}</p>
      <p>coverage: {coverage.data?.coverage_status ?? coverage.status}</p>
      <small>Provider/read model/displayed: {coverage.data ? `${coverage.data.authoritative_count}/${coverage.data.read_model_count}/${coverage.data.displayed_count}` : "pending"}</small>
    </aside>
  );
}

function RightRail({
  provider,
  health,
  coverage,
  forward,
  gate5,
  alerts,
}: {
  provider: Resource<ProviderStatus>;
  health: Resource<DataHealth>;
  coverage: Resource<MatchdayCoverage>;
  forward: Resource<ForwardStatus>;
  gate5: Resource<OpsList>;
  alerts: Resource<OpsList>;
}) {
  return (
    <aside className="right-rail">
      <ProviderQuotaCard provider={provider} />
      <GateStatusCard forward={forward} gate5={gate5} />
      <SystemHealthCard coverage={coverage} health={health} />
      <aside className="rail-card">
        <div className="section-title compact-title">
          <h3>运行告警</h3>
          <StatusBadge tone={alerts.status === "ERROR" ? "bad" : "neutral"}>
            {alerts.status}
          </StatusBadge>
        </div>
        {alerts.data?.items.length ? (
          <div className="ops-list">
            {alerts.data.items.slice(0, 4).map((item) => (
              <div key={item.key}>
                <strong>{item.key}</strong>
                <span>{item.status}</span>
              </div>
            ))}
          </div>
        ) : (
          <p>暂无未解决告警。</p>
        )}
      </aside>
    </aside>
  );
}

export function DashboardShell() {
  const initialDate = beijingToday();
  const [selectedDate, setSelectedDate] = useState<string>(initialDate);
  const [fixtures, setFixtures] = useState<Resource<{ items: Fixture[] }>>(
    emptyResource(`/api/v1/matchday/${initialDate}`),
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Resource<FixtureDetail>>(emptyResource("/api/v1/fixtures/none"));
  const [forward, setForward] = useState<Resource<ForwardStatus>>(
    emptyResource("/api/v1/forward-holdout/status"),
  );
  const [provider, setProvider] = useState<Resource<ProviderStatus>>(
    emptyResource("/api/v1/providers/status"),
  );
  const [health, setHealth] = useState<Resource<DataHealth>>(emptyResource("/api/v1/data-health"));
  const [market, setMarket] = useState<Resource<Probability>>(
    emptyResource("/api/v1/fixtures/none/market-probabilities"),
  );
  const [model, setModel] = useState<Resource<Probability>>(
    emptyResource("/api/v1/fixtures/none/model-probabilities"),
  );
  const [coverage, setCoverage] = useState<Resource<MatchdayCoverage>>(
    emptyResource("/api/ops/matchday-coverage"),
  );
  const [ranking, setRanking] = useState<Resource<MarketRanking>>(
    emptyResource("/api/v1/fixtures/none/market-ranking"),
  );
  const [integrity, setIntegrity] = useState<Resource<Integrity>>(
    emptyResource("/api/v1/fixtures/none/integrity"),
  );
  const [alerts, setAlerts] = useState<Resource<OpsList>>(emptyResource("/api/ops/alerts"));
  const [shadowStrategy, setShadowStrategy] = useState<Resource<ShadowStrategyStatus>>(
    emptyResource("/api/ops/shadow-strategy/status"),
  );
  const [gate5, setGate5] = useState<Resource<OpsList>>(
    emptyResource("/api/ops/gates/5-preflight"),
  );
  const [w1w2, setW1w2] = useState<Resource<OpsList>>(
    emptyResource("/api/ops/w1-w2-shadow-comparison"),
  );

  const fixtureItems = fixtures.data?.items ?? [];
  const selectedFixture = useMemo(
    () => fixtureItems.find((fixture) => fixture.fixture_id === selected) ?? null,
    [fixtureItems, selected],
  );

  const loadFixtures = useCallback(() => {
    const endpoint = `/api/v1/matchday/${selectedDate}`;
    setFixtures(emptyResource(endpoint));
    loadJson<Matchday>(endpoint).then((payload) => {
      const fixturePayload = fixtureListFromMatchday(payload);
      setFixtures(fixturePayload);
      setSelected((current) => {
        if (current && fixturePayload.data?.items.some((fixture) => fixture.fixture_id === current)) {
          return current;
        }
        return fixturePayload.data?.items?.[0]?.fixture_id ?? null;
      });
    });
  }, [selectedDate]);

  const loadCommon = useCallback(() => {
    loadJson<ForwardStatus>("/api/v1/forward-holdout/status").then(setForward);
    loadJson<ProviderStatus>("/api/v1/providers/status").then(setProvider);
    loadJson<DataHealth>("/api/v1/data-health").then(setHealth);
    loadJson<MatchdayCoverage>("/api/ops/matchday-coverage").then(setCoverage);
    loadJson<OpsList>("/api/ops/alerts").then(setAlerts);
    loadJson<ShadowStrategyStatus>("/api/ops/shadow-strategy/status").then(setShadowStrategy);
    loadJson<OpsList>("/api/ops/gates/5-preflight").then(setGate5);
    loadJson<OpsList>("/api/ops/w1-w2-shadow-comparison").then(setW1w2);
  }, []);

  const loadSelected = useCallback(() => {
    if (!selected) {
      return;
    }
    const detailEndpoint = `/api/v1/fixtures/${selected}`;
    const marketEndpoint = `/api/v1/fixtures/${selected}/market-probabilities`;
    const modelEndpoint = `/api/v1/fixtures/${selected}/model-probabilities`;
    const rankingEndpoint = `/api/v1/fixtures/${selected}/market-ranking`;
    const integrityEndpoint = `/api/v1/fixtures/${selected}/integrity`;
    setDetail(emptyResource(detailEndpoint));
    setMarket(emptyResource(marketEndpoint));
    setModel(emptyResource(modelEndpoint));
    setRanking(emptyResource(rankingEndpoint));
    setIntegrity(emptyResource(integrityEndpoint));
    loadJson<FixtureDetail>(detailEndpoint).then(setDetail);
    loadJson<Probability>(marketEndpoint).then(setMarket);
    loadJson<Probability>(modelEndpoint).then(setModel);
    loadJson<MarketRanking>(rankingEndpoint).then(setRanking);
    loadJson<Integrity>(integrityEndpoint).then(setIntegrity);
  }, [selected]);

  useEffect(() => {
    loadFixtures();
    loadCommon();
  }, [loadCommon, loadFixtures]);

  useEffect(() => {
    loadSelected();
  }, [loadSelected]);

  return (
    <main className="dashboard-shell">
      <GlobalStatusBar health={health} provider={provider} />
      <SummaryKpiRow
        fixtures={fixtureItems}
        forward={forward}
        gate5={gate5}
        health={health}
        provider={provider}
      />
      <section className="dashboard-grid">
        <ResourceView resource={fixtures} onRetry={loadFixtures} skeletonLines={6}>
          {(data) => (
            <MatchdayFixtureList
              fixtures={data.items}
              onDate={setSelectedDate}
              onSelect={setSelected}
              selected={selected}
              selectedDate={selectedDate}
            />
          )}
        </ResourceView>
        <FixtureWorkspace
          comparison={w1w2}
          detail={detail}
          integrity={integrity}
          market={market}
          model={model}
          onRetryDetail={loadSelected}
          ranking={ranking}
          shadow={shadowStrategy}
        />
        <RightRail
          alerts={alerts}
          coverage={coverage}
          forward={forward}
          gate5={gate5}
          health={health}
          provider={provider}
        />
      </section>
      <section className="footer-status">
        <strong>研究级输出，正式推荐尚未启用。</strong>
        <span>
          当前选中：{selectedFixture ? `${displayTeam(selectedFixture)} vs ${displayAway(selectedFixture)}` : "暂无"}
        </span>
        <span>Dashboard states: loading / empty / error / stale / success</span>
      </section>
    </main>
  );
}
