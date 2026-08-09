import { useMemo, useState } from "react";
import type {
  IntelligenceState,
  IntelligenceWorkspace,
  RiskAxisName,
  WorkspaceAttentionItem,
  WorkspaceMarket,
  WorkspaceMatch,
} from "../types/intelligenceWorkspace";

const STATE_LABELS: Record<IntelligenceState, string> = {
  COLLECTION_INCIDENT: "Collection incident",
  DATA_INCOMPLETE: "Data incomplete",
  MODEL_DIAGNOSTIC_WARNING: "Model diagnostic warning",
  MARKET_ANOMALY: "Market anomaly",
  MODEL_MARKET_DISAGREEMENT: "Model–market disagreement",
  MARKET_MOVEMENT: "Market movement",
  MARKET_STABLE: "Market stable",
};

const RISK_LABELS: Record<RiskAxisName, string> = {
  EVENT_RISK: "Event",
  DATA_RISK: "Data",
  MODEL_RISK: "Model",
  COLLECTION_RISK: "Collection",
};

const NAVIGATION = [
  ["attention", "Attention"],
  ["matches", "Match Board"],
  ["market-radar", "Market Radar"],
  ["model-lab", "Model Lab"],
  ["validation", "Validation"],
  ["history", "Forward / Replay"],
  ["external", "External"],
  ["operations", "Data & Ops"],
] as const;

function text(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function percent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function decimal(value: number | null): string {
  return value === null ? "—" : value.toFixed(4);
}

function localTime(value: string | null): string {
  if (!value) return "TIME_NOT_AVAILABLE";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function marketFactLabel(match: WorkspaceMatch): string {
  const market = Object.values(match.market_radar.markets).find((item) => item.main_line === match.market_fact.main_line);
  if (!market || !match.market_fact.main_line) return "MARKET NOT AVAILABLE";
  return `${market.market === "ASIAN_HANDICAP" ? "AH" : "OU"} ${match.market_fact.main_line}`;
}

function StateBadge({ state }: { state: IntelligenceState }) {
  return <span className={`workspace-state workspace-state--${state.toLowerCase()}`}>{state}</span>;
}

function SectionHeading({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) {
  return <header className="workspace-section-heading"><div><span>{eyebrow}</span><h2>{title}</h2></div><p>{detail}</p></header>;
}

function KeyValue({ label, value, mono = false }: { label: string; value: unknown; mono?: boolean }) {
  return <div className="workspace-key-value"><span>{label}</span><strong className={mono ? "is-mono" : undefined}>{text(value)}</strong></div>;
}

function RiskGrid({ match }: { match: WorkspaceMatch }) {
  return (
    <div className="workspace-risk-grid" aria-label="Exact four-axis risk contract">
      {(Object.keys(RISK_LABELS) as RiskAxisName[]).map((axis) => {
        const risk = match.risks[axis];
        return <div className={`workspace-risk workspace-risk--${risk.status.toLowerCase()}`} data-risk-axis={axis} key={axis}><span>{RISK_LABELS[axis]} risk</span><strong>{risk.status}</strong><small>{risk.explanation}</small></div>;
      })}
    </div>
  );
}

function Attention({ items, matches, onSelect }: { items: WorkspaceAttentionItem[]; matches: WorkspaceMatch[]; onSelect: (id: string) => void }) {
  const nameById = new Map(matches.map((match) => [match.fixture_id, `${match.home_team_name || "Home"} vs ${match.away_team_name || "Away"}`]));
  return (
    <section className="workspace-panel workspace-panel--attention" id="attention" data-ui="attention">
      <SectionHeading eyebrow="Priority feed" title="Attention" detail="Seven-state factual triage. Attention is not a recommendation." />
      <div data-ui="attention-feed">{items.length ? <div className="attention-table" role="list">{items.map((item) => (
        <button className="attention-row" data-intelligence-state={item.intelligence_state} key={item.fixture_id} onClick={() => onSelect(item.fixture_id)} role="listitem" type="button">
          <div><StateBadge state={item.intelligence_state} /><strong>{nameById.get(item.fixture_id) || item.fixture_id}</strong><time>{localTime(item.kickoff_utc)}</time></div>
          <p>{item.factual_summary}</p>
          <div className="attention-context"><span>Domains: {item.affected_domains.join(" · ")}</span><span>Readiness: {item.readiness_status} / {item.readiness_context.reason_code || "NO_REASON_CODE"}</span><span>Next eval: {localTime(item.next_eval_at)}</span></div>
          <div className="attention-reasons">{item.reason_codes.map((reason) => <code key={reason}>{reason}</code>)}</div>
        </button>
      ))}</div> : <div className="workspace-empty"><strong>No attention items</strong><span>The read model returned an explicit empty day.</span></div>}</div>
    </section>
  );
}

function MatchBoard({ matches, selectedId, onSelect }: { matches: WorkspaceMatch[]; selectedId: string | null; onSelect: (id: string) => void }) {
  return (
    <section className="workspace-panel" id="matches" data-ui="match-board">
      <SectionHeading eyebrow="13-league watchlist" title="Match Board" detail="Market facts and readiness only; no picks or opportunity labels." />
      {matches.length ? <div className="match-board-table"><div className="match-board-head"><span>Time</span><span>League / match</span><span>W2 state</span><span>Main line fact</span><span>Readiness</span><span>Next eval</span></div>{matches.map((match) => (
        <button aria-pressed={match.fixture_id === selectedId} className={match.fixture_id === selectedId ? "match-board-row is-selected" : "match-board-row"} data-fixture-id={match.fixture_id} key={match.fixture_id} onClick={() => onSelect(match.fixture_id)} type="button">
          <time>{localTime(match.kickoff_utc)}</time>
          <span><small>{match.competition_name || match.competition_id || "League unavailable"}</small><strong>{match.home_team_name || "Home"} <b>vs</b> {match.away_team_name || "Away"}</strong></span>
          <StateBadge state={match.intelligence_state} />
          <span className="is-mono match-board-market">{marketFactLabel(match)}</span>
          <span><strong>{match.readiness.status}</strong><small>{match.readiness.reason_code || "NO_REASON_CODE"}</small></span>
          <time>{localTime(match.readiness.next_eval_at)}</time>
        </button>
      ))}</div> : <div className="workspace-empty"><strong>Empty football day</strong><span>No match rows were projected; nothing synthetic was substituted.</span></div>}
    </section>
  );
}

function Inspector({ match }: { match: WorkspaceMatch | null }) {
  if (!match) return <section className="workspace-panel workspace-empty" data-ui="match-inspector"><strong>No selected fixture</strong><span>The selected inspector remains empty until a real match exists.</span></section>;
  return (
    <section className="workspace-panel workspace-inspector" data-ui="match-inspector">
      <SectionHeading eyebrow={`Fixture ${match.fixture_id}`} title={`${match.home_team_name || "Home"} vs ${match.away_team_name || "Away"}`} detail={`${match.competition_name || "League unavailable"} · ${localTime(match.kickoff_utc)}`} />
      <div className="inspector-state"><StateBadge state={match.intelligence_state} /><span>{STATE_LABELS[match.intelligence_state]}</span></div>
      <div className="inspector-grid">
        <div className="inspector-layer"><span>W2 analysis</span><strong>{match.w2_analysis.status}</strong><code>{match.w2_analysis.proof_status}</code><small>{match.w2_analysis.decision_tier} · {match.w2_analysis.analysis_state}</small></div>
        <div className="inspector-layer"><span>Model view</span><strong>{match.w2_analysis.model_view.status}</strong><small>{match.w2_analysis.model_view.model_version || "MODEL_VERSION_NOT_AVAILABLE"} · calibration {match.w2_analysis.model_view.calibration_status || "NOT_AVAILABLE"}</small></div>
        <div className="inspector-layer"><span>Market view</span><strong>{match.market_fact.status}</strong><small>Main line {match.market_fact.main_line || "NOT_AVAILABLE"} · {match.market_fact.price_reference}</small></div>
        <div className="inspector-layer"><span>Formal</span><strong className="is-off">{match.formal_recommendation.status}</strong><code>{match.formal_recommendation.reason}</code><small>Candidate / Lock / Production also remain OFF.</small></div>
      </div>
      <div className="relation-grid">{Object.values(match.w2_analysis.model_market_relation).map((relation) => <div key={relation.market}><span>{relation.market}</span><strong>{relation.status}</strong><small>Line {relation.canonical_line || "NOT_AVAILABLE"} · {relation.bookmaker_count} bookmakers · freshness {relation.freshness_status || "NOT_AVAILABLE"}</small>{relation.blockers.map((blocker) => <code key={blocker}>{blocker}</code>)}</div>)}</div>
      <RiskGrid match={match} />
      <div className="readiness-strip"><KeyValue label="Readiness" value={match.readiness.status} /><KeyValue label="Reason" value={match.readiness.reason_code || "NO_REASON_CODE"} mono /><KeyValue label="Lineup" value={`${match.readiness.lineup_expectation || "NOT_AVAILABLE"} / ${match.readiness.lineup_status || "NOT_AVAILABLE"}`} /><KeyValue label="Next evaluation" value={localTime(match.readiness.next_eval_at)} /></div>
      <div className="reason-code-list">{match.intelligence_reason_codes.map((reason) => <code key={reason}>{reason}</code>)}</div>
    </section>
  );
}

function MarketTimeline({ market }: { market: WorkspaceMarket }) {
  return (
    <div className="discrete-timeline" data-real-point-count={market.timeline_points.length} data-snapshot-state={market.snapshot_state}>
      <div><code>{market.snapshot_state}</code><span>{market.snapshot_count} snapshots · {market.observation_count} observations</span></div>
      {market.timeline_points.length < 2 ? <p>{market.timeline_points.length === 0 ? "No timeline evidence. Movement is not inferred." : "One observation is not a trend."}</p> : <ol>{market.timeline_points.map((point, index) => <li key={point.capture_id || `${point.captured_at}-${index}`}><time>{localTime(point.captured_at)}</time><strong>{point.canonical_line || "NO_LINE"}</strong><span>{point.bookmaker_count} books</span></li>)}</ol>}
    </div>
  );
}

function MarketPrices({ market }: { market: WorkspaceMarket }) {
  if (!Object.keys(market.prices).length) return <div className="market-prices" data-ui="market-prices"><p>PRICE_EVIDENCE_NOT_AVAILABLE</p></div>;
  const sides = market.market === "ASIAN_HANDICAP" ? ["HOME", "AWAY"] : ["OVER", "UNDER"];
  return <div className="market-prices" data-ui="market-prices">{sides.map((side) => {
    const available = Object.prototype.hasOwnProperty.call(market.prices, side);
    return <span data-price-side={side} key={side}><small>{side}</small><strong>{available ? text(market.prices[side]) : "NOT_AVAILABLE"}</strong></span>;
  })}</div>;
}

function MarketRadar({ match }: { match: WorkspaceMatch | null }) {
  return (
    <section className="workspace-panel" id="market-radar" data-ui="market-radar">
      <SectionHeading eyebrow="Persisted evidence" title="Market Radar" detail="0 / 1 / 2+ snapshots stay discrete; no interpolation or synthetic path." />
      {match ? <div className="market-grid">{Object.values(match.market_radar.markets).map((market) => <article className="market-card" data-market={market.market} key={market.market}><header><div><span>{market.market}</span><strong>{market.status}</strong></div><b>{market.main_line || "NO_MAIN_LINE"}</b></header><div className="market-metrics"><KeyValue label="Bookmakers" value={market.bookmaker_count} /><KeyValue label="Freshness" value={market.freshness.status || "NOT_AVAILABLE"} /><KeyValue label="Movement" value={market.movement.status || "INSUFFICIENT"} /></div><MarketPrices market={market} /><MarketTimeline market={market} /></article>)}</div> : <div className="workspace-empty"><span>No selected market evidence.</span></div>}
    </section>
  );
}

function ModelLab({ match }: { match: WorkspaceMatch | null }) {
  const history = match?.model_lab.historical_validation || {};
  return (
    <section className="workspace-panel" id="model-lab" data-ui="model-lab">
      <SectionHeading eyebrow="Diagnostic comparison" title="Model Lab" detail="W2, market, and external benchmark roles remain separate." />
      {match ? <><div className="model-lab-grid"><div><span>W2 model</span><strong>{match.model_lab.w2_model.status}</strong><small>{match.model_lab.w2_model.model_version || "VERSION_NOT_AVAILABLE"} · {match.model_lab.w2_model.calibration_status || "CALIBRATION_NOT_AVAILABLE"}</small></div><div><span>Market</span><strong>{Object.values(match.model_lab.market).map((market) => market.status).join(" · ")}</strong><small>Observed prematch market facts</small></div><div><span>API-Football Prediction</span><strong>{match.model_lab.api_football_prediction.status}</strong><small>{match.model_lab.api_football_prediction.role} · {match.model_lab.api_football_prediction.reason_code}</small></div></div><div className="model-relations">{Object.values(match.model_lab.relation).map((relation) => <article key={relation.market}><header><span>{relation.market}</span><strong>{relation.status}</strong></header>{relation.diagnostics.length ? relation.diagnostics.map((row, index) => <code key={`${relation.market}-${index}`}>{JSON.stringify(row)}</code>) : <small>No projected diagnostic rows.</small>}<p>模型与市场差异仅用于诊断；优先检查模型校准、特征时效、盘口身份和数据质量。Difference is not opportunity or a market pick.</p></article>)}</div><div className="phase-context" data-ui="phase-0-5-context"><span>Frozen Phase 0.5</span><strong>{text(history.final_verdict, "NO_EDGE")} · V gate {text(history.v_continuation_gate, "FAIL")} · HISTORICAL_INCREMENTAL_EDGE={text(history.historical_incremental_edge, "NOT_PROVEN")} · H {text(history.h_result_access, "PERMANENTLY_CLOSED")}</strong><small>Historical result reused; Phase 0.5 was not re-run.</small></div></> : <div className="workspace-empty"><span>No selected model evidence.</span></div>}
    </section>
  );
}

function Scoreline({ match }: { match: WorkspaceMatch | null }) {
  const scoreline = match?.scoreline_reference;
  const ready = scoreline?.status === "READY" && scoreline.simulations_completed === 10_000;
  return (
    <section className="workspace-panel scoreline-panel" data-ui="scoreline-top3">
      <SectionHeading eyebrow="Model score reference" title="Scoreline Top 3" detail="Unconditional outcomes from the existing 10,000-simulation artifact; never simulated on API read." />
      <div className="scoreline-context" data-ui="scoreline-context"><KeyValue label="Model status" value={match?.w2_analysis.model_view.status || "NOT_AVAILABLE"} /><KeyValue label="Readiness" value={match?.readiness.status || "NOT_AVAILABLE"} /><KeyValue label="Readiness reason" value={match?.readiness.reason_code || "NO_REASON_CODE"} mono /></div>
      {ready && scoreline ? <div className="scoreline-grid">{scoreline.top3.map((row, index) => <article key={`${row.scoreline}-${index}`}><span>#{index + 1}</span><strong>{row.scoreline}</strong><b>{percent(row.unconditional_probability)}</b><small>unconditional_probability</small><code>sample_count={row.sample_count}</code></article>)}</div> : <div className="workspace-empty"><strong>{scoreline?.status || "UNAVAILABLE"}</strong><span>{scoreline?.status === "READY" ? "Fail-closed: READY requires exactly 10,000 simulations." : "No scoreline reference is projected."}</span></div>}
      <footer><code>simulations_completed={scoreline?.simulations_completed ?? "NOT_AVAILABLE"}</code><span>{scoreline?.proof_status || "NOT_PROVEN"}</span></footer>
    </section>
  );
}

function ReliabilityBins({ title, bins }: { title: string; bins: Record<string, unknown>[] }) {
  return <div className="reliability-bins"><span>{title}</span>{bins.length ? <ol>{bins.map((bin, index) => <li key={`${title}-${index}`}><code>{Object.entries(bin).map(([key, value]) => `${key}=${text(value)}`).join(" · ")}</code></li>)}</ol> : <small>No reliability bins in checkpoint.</small>}</div>;
}

function Validation({ workspace }: { workspace: IntelligenceWorkspace }) {
  const { probability, directional, league_performance: leagues } = workspace.validation;
  return (
    <section className="workspace-panel" id="validation" data-ui="validation">
      <SectionHeading eyebrow="Evidence checkpoints" title="Validation & League Performance" detail="Probability quality is primary; directional outcome is secondary and explicitly bounded." />
      <div className="validation-status"><StateLabel label="Probability" status={probability.status} /><StateLabel label="Directional" status={directional.status} /><KeyValue label="Sample / effective N" value={`${probability.sample_count} / ${directional.effective_n}`} /></div>
      <div className="validation-grid"><article><h3>Probability Validation</h3><div className="metric-grid"><KeyValue label="W2 Brier" value={decimal(probability.model_brier)} /><KeyValue label="Market Brier" value={decimal(probability.market_brier)} /><KeyValue label="W2 LogLoss" value={decimal(probability.model_log_loss)} /><KeyValue label="Market LogLoss" value={decimal(probability.market_log_loss)} /><KeyValue label="W2 ECE" value={decimal(probability.model_calibration_error)} /><KeyValue label="Market ECE" value={decimal(probability.market_calibration_error)} /></div><div className="validation-checkpoint" data-ui="validation-checkpoint"><span>Checkpoint / cohort identity</span>{Object.entries(probability.checkpoint_metadata).length ? Object.entries(probability.checkpoint_metadata).map(([key, value]) => <code key={key}>{key}={text(value)}</code>) : <code>CHECKPOINT_METADATA_NOT_AVAILABLE</code>}</div><ReliabilityBins bins={probability.model_reliability_bins} title="W2 reliability bins" /><ReliabilityBins bins={probability.market_reliability_bins} title="Market reliability bins" /></article><article><h3>Directional Outcome</h3><div className="metric-grid"><KeyValue label="Correct" value={directional.correct} /><KeyValue label="Wrong" value={directional.wrong} /><KeyValue label="PUSH" value={directional.push} /><KeyValue label="VOID" value={directional.void} /><KeyValue label="Accuracy" value={percent(directional.direction_accuracy)} /><KeyValue label="Effective N" value={directional.effective_n} /></div><div className="contract-note"><span>Market direction benchmark</span><strong>{directional.market_direction_benchmark}</strong></div></article></div>
      <div className="league-table" data-ui="league-performance"><div className="league-table-head"><span>League</span><span>Validation N</span><span>Decisive N</span><span>Correct</span><span>Wrong</span><span>PUSH</span><span>VOID</span><span>Accuracy</span><span>Brier</span><span>Calibration</span><span>Status</span></div>{leagues.length ? leagues.map((league) => <div className="league-table-row" key={league.league}><strong>{league.league}</strong><span>{league.validation_n}</span><span>{league.decisive_n}</span><span>{league.correct}</span><span>{league.wrong}</span><span>{league.push}</span><span>{league.void}</span><span>{percent(league.direction_accuracy)}</span><span>{decimal(league.brier)}</span><span>{decimal(league.calibration)}</span><code>{league.statistical_status}</code></div>) : <div className="workspace-empty"><span>League samples are still building.</span></div>}</div>
    </section>
  );
}

function StateLabel({ label, status }: { label: string; status: string }) {
  return <div className="state-label"><span>{label}</span><strong>{status}</strong></div>;
}

function History({ workspace }: { workspace: IntelligenceWorkspace }) {
  const forward = workspace.validation.forward_validation_records;
  const replay = workspace.validation.history_replay;
  return (
    <section className="workspace-panel" id="history" data-ui="history-replay">
      <SectionHeading eyebrow="Known-at evidence" title="Forward Records & Replay" detail="Decisions, reasons, outcomes, hashes, and gaps are displayed from existing checkpoints." />
      <div className="forward-grid"><StateLabel label="Forward records" status={forward.status} /><KeyValue label="Validation / eligible" value={`${forward.validation_count} / ${forward.eligible_count}`} /><KeyValue label="Excluded / pending" value={`${forward.excluded_count} / ${forward.pending_count}`} /><StateLabel label="Replay" status={replay.status} /></div>
      <div className="history-grid"><article><h3>Known at</h3>{Object.entries(replay.known_at).map(([key, value]) => <KeyValue key={key} label={key} value={value} mono />)}</article><article><h3>Decision summary</h3><KeyValue label="Total cards" value={replay.decision_summary.total_cards} /><KeyValue label="Lock-eligible evidence count" value={replay.decision_summary.lock_eligible_count} /><KeyValue label="By tier" value={replay.decision_summary.by_decision_tier} /><KeyValue label="By readiness" value={replay.decision_summary.by_data_status} /></article><article><h3>Outcome / settlement tracking</h3>{Object.entries(replay.outcome_tracking_summary).map(([key, value]) => <KeyValue key={key} label={key} value={value} />)}<KeyValue label="Canonical outcomes" value={forward.outcomes} /></article><article><h3>Hashes & gaps</h3><KeyValue label="Hash checks" value={replay.card_hash_checks.length} /><div className="reason-code-list">{replay.replay_gaps.length ? replay.replay_gaps.map((gap) => <code key={gap}>{gap}</code>) : <code>NO_REPLAY_GAPS</code>}</div></article></div>
      <div className="reason-code-list">{replay.reason_summary.map((reason, index) => <code key={index}>{JSON.stringify(reason)}</code>)}</div>
    </section>
  );
}

function External({ workspace }: { workspace: IntelligenceWorkspace }) {
  return (
    <section className="workspace-panel" id="external" data-ui="external-intelligence">
      <SectionHeading eyebrow="Non-blocking sources" title="External Intelligence" detail="Not connected is an explicit integration state and does not make current match readiness incomplete." />
      <div className="external-grid">{Object.entries(workspace.external_intelligence).map(([name, source]) => <article key={name}><span>{name.replaceAll("_", " ")}</span><strong>{source.status}</strong><small>affects_match_readiness={String(source.affects_match_readiness)}</small></article>)}</div>
    </section>
  );
}

function Operations({ workspace }: { workspace: IntelligenceWorkspace }) {
  return (
    <section className="workspace-panel" id="operations" data-ui="data-operations">
      <SectionHeading eyebrow="Read-only truth" title="Data & Operations" detail="Source, freshness, degradation, counts, budget, and read contract." />
      <div className="operations-grid"><KeyValue label="Read model source" value={workspace.data_operations.read_model_source} mono /><KeyValue label="Checkpoint" value={workspace.data_operations.checkpoint_key} mono /><KeyValue label="System health" value={workspace.data_operations.system_health} /><KeyValue label="Provider budget" value={workspace.data_operations.provider_budget_status} /><KeyValue label="Generated at" value={workspace.generated_at} /><KeyValue label="Degradation" value={workspace.data_operations.degradation} /></div>
      <div className="read-contract"><strong>NO CALL / NO WRITE</strong><code>provider_calls={workspace.read_contract.provider_calls}</code><code>db_writes={workspace.read_contract.db_writes}</code><code>would_write_checkpoint={String(workspace.read_contract.would_write_checkpoint)}</code><code>no_call_on_read={String(workspace.read_contract.no_call_on_read)}</code></div>
      <details className="freshness-contract"><summary>Freshness domains</summary><div>{Object.values(workspace.freshness.domains).map((domain) => <article key={domain.domain}><header><strong>{domain.domain}</strong><code>{domain.status}</code></header><span>{domain.source} · as of {domain.source_as_of || "NOT_PROJECTED"}</span><small>{domain.availability} · {domain.readiness_semantics} · authority {domain.provider_refresh_authority} · no_call_on_read={String(domain.no_call_on_read)}</small></article>)}</div></details>
    </section>
  );
}

export function IntelligenceConsole({ date, loading, onDateChange, onRefresh, workspace }: { date: string; loading: boolean; onDateChange: (date: string) => void; onRefresh: () => void; workspace: IntelligenceWorkspace }) {
  const initialId = workspace.selected_fixture_id || workspace.matches[0]?.fixture_id || null;
  const [selectedId, setSelectedId] = useState<string | null>(initialId);
  const selected = useMemo(() => workspace.matches.find((match) => match.fixture_id === selectedId) || workspace.matches[0] || null, [selectedId, workspace.matches]);
  const select = (id: string) => {
    setSelectedId(id);
    document.querySelector("[data-ui='match-inspector']")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  return (
    <div className="unified-workspace" data-public-authority={workspace.runtime.public_dashboard_authority} data-schema-version={workspace.schema_version}>
      <aside className="workspace-sidebar"><a className="workspace-brand" href="#top"><span>W2</span><strong>INTELLIGENCE</strong><small>Unified workspace</small></a><nav aria-label="Workspace sections">{NAVIGATION.map(([target, label]) => <a href={`#${target}`} key={target}><span aria-hidden="true" />{label}</a>)}</nav><div className="sidebar-contract"><strong>READ ONLY</strong><span>{workspace.runtime.free_bridge_mode}</span><span>{workspace.runtime.active_whitelist_count} leagues</span></div></aside>
      <main className="workspace-main" id="top">
        <header className="workspace-topbar"><div><span>W2 INTELLIGENCE</span><strong>{workspace.date}</strong><small data-ui="header-context">{workspace.timezone} · {workspace.window.toUpperCase()} · Updated {localTime(workspace.generated_at)} · Health {workspace.data_operations.system_health}</small></div><div className="topbar-status"><span>13 LEAGUES</span><span>SHADOW_ONLY</span><span>CANDIDATE OFF</span><span>FORMAL OFF</span><span>LOCK OFF</span><span>PRODUCTION OFF</span></div><div className="topbar-actions"><label><span>Date</span><input aria-label="Workspace date" onChange={(event) => onDateChange(event.target.value)} type="date" value={date} /></label><button disabled={loading} onClick={onRefresh} type="button">{loading ? "Reading…" : "Refresh"}</button></div></header>
        <div className="workspace-authority"><span>ONE FINAL UNIFIED DASHBOARD</span><code>{workspace.schema_version}</code><strong>{workspace.runtime.public_dashboard_authority}</strong></div>
        <Attention items={workspace.attention} matches={workspace.matches} onSelect={select} />
        <MatchBoard matches={workspace.matches} onSelect={select} selectedId={selected?.fixture_id || null} />
        <Inspector match={selected} />
        <div className="workspace-two-column"><MarketRadar match={selected} /><div><ModelLab match={selected} /><Scoreline match={selected} /></div></div>
        <Validation workspace={workspace} />
        <History workspace={workspace} />
        <External workspace={workspace} />
        <Operations workspace={workspace} />
        <footer className="workspace-footer"><span>ANALYSIS_REFERENCE · NOT_PROVEN</span><span>Formal recommendation is OFF. Public output is limited to factual intelligence and model diagnostics.</span></footer>
      </main>
    </div>
  );
}
