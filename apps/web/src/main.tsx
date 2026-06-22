import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type LoadStatus = "LOADING" | "SUCCESS" | "EMPTY" | "ERROR" | "STALE";

type Resource<T> = {
  status: LoadStatus;
  endpoint: string;
  data: T | null;
  requestId: string | null;
  errorCode: string | null;
  message: string | null;
};

type Fixture = {
  fixture_id: string;
  competition_id: string;
  competition_name: string;
  kickoff_utc: string;
  kickoff_display: string;
  status: string;
  home_team_id: string;
  away_team_id: string;
  lifecycle_state: string;
  data_state: string;
};

type FixtureDetail = Fixture & {
  venue: string | null;
  bookmaker_count: number;
  market_coverage: Record<string, boolean>;
  forward_decision: string;
  provenance: Record<string, string>;
  risk_notes: string[];
};

type FixtureList = {
  request_id: string;
  items: Fixture[];
};

type ForwardStatus = {
  request_id: string;
  status: string;
  locks: number;
  market_comparable: number;
  current_settled_n: number;
  target_n: number;
};

type ProviderStatus = {
  request_id: string;
  provider: string;
  status: string;
  remaining_quota: number | null;
  credential_status: string;
  last_request_status: number | null;
};

type DataHealth = {
  request_id: string;
  stale_data_count: number;
  provider_status: string;
  forward_cycle_age_seconds: number | null;
  generated_at: string;
  gate4_progress: Record<string, unknown>;
};

type Probability = {
  request_id: string;
  probability_type: string;
  probabilities: Record<string, number>;
  source: string;
  quality: string;
  as_of_time: string | null;
};

type OpsList = {
  request_id: string;
  items: Array<{ key: string; status: string; payload: Record<string, unknown> }>;
};

type WorldCupReadiness = {
  request_id: string;
  competition_id: string;
  profile_version: string;
  fixture_coverage_count: number;
  data_coverage: Record<string, string>;
  phase_count_per_fixture: number;
  gate_status: string;
  strategy_version: string;
  production_deployment: string;
  shadow_runtime: string;
  blockers: string[];
};

type LeagueSummary = {
  competition_id: string;
  name: string;
  country: string;
  results_status: string;
  market_status: Record<string, string>;
  latest_season: string | null;
  blocker: string | null;
};

type LeagueList = {
  request_id: string;
  items: LeagueSummary[];
};

type OperationsLatest = {
  request_id: string;
  latest: {
    kind?: string;
    status?: string;
    checkpoint?: string;
    BLOCKER?: string[];
    WARN_ONLY?: string[];
  };
};

type ReleaseReadiness = {
  request_id: string;
  approval_status: string;
  production_release: string;
  dependency_blocker: string | null;
};

type RetentionStatus = {
  request_id: string;
  status: string;
  policy: Record<string, unknown>;
};

const staleMs = 15 * 60 * 1000;

function emptyResource<T>(endpoint: string): Resource<T> {
  return {
    status: "LOADING",
    endpoint,
    data: null,
    requestId: null,
    errorCode: null,
    message: null,
  };
}

function isEmptyPayload(payload: unknown): boolean {
  if (payload === null || payload === undefined) {
    return true;
  }
  if (Array.isArray(payload)) {
    return payload.length === 0;
  }
  if (typeof payload === "object") {
    const maybeItems = (payload as { items?: unknown }).items;
    return Array.isArray(maybeItems) && maybeItems.length === 0;
  }
  return false;
}

function isStale(payload: unknown): boolean {
  const maybeTime =
    (payload as { generated_at?: string; as_of_time?: string; updated_at?: string })?.generated_at ??
    (payload as { generated_at?: string; as_of_time?: string; updated_at?: string })?.as_of_time ??
    (payload as { generated_at?: string; as_of_time?: string; updated_at?: string })?.updated_at;
  if (!maybeTime) {
    return false;
  }
  const timestamp = Date.parse(maybeTime);
  return Number.isFinite(timestamp) && Date.now() - timestamp > staleMs;
}

async function loadJson<T>(endpoint: string): Promise<Resource<T>> {
  const requestId = crypto.randomUUID();
  try {
    const response = await fetch(endpoint, {
      headers: { Accept: "application/json", "X-Request-ID": requestId },
    });
    const text = await response.text();
    const payload = text ? (JSON.parse(text) as T & { request_id?: string; code?: string; message?: string }) : null;
    if (!response.ok) {
      return {
        status: "ERROR",
        endpoint,
        data: null,
        requestId: payload?.request_id ?? requestId,
        errorCode: payload?.code ?? String(response.status),
        message: payload?.message ?? response.statusText,
      };
    }
    return {
      status: isEmptyPayload(payload) ? "EMPTY" : isStale(payload) ? "STALE" : "SUCCESS",
      endpoint,
      data: payload as T,
      requestId: payload?.request_id ?? requestId,
      errorCode: null,
      message: null,
    };
  } catch (error) {
    return {
      status: "ERROR",
      endpoint,
      data: null,
      requestId,
      errorCode: error instanceof SyntaxError ? "JSON_PARSE_ERROR" : "FETCH_FAILED",
      message: error instanceof Error ? error.message : "Request failed",
    };
  }
}

function StatePanel<T>({
  title,
  resource,
  onRetry,
  children,
}: {
  title: string;
  resource: Resource<T>;
  onRetry: () => void;
  children: (data: T) => React.ReactNode;
}) {
  return (
    <section className={`panel state-${resource.status.toLowerCase()}`}>
      <div className="panel-title">
        <h2>{title}</h2>
        <span>{resource.status}</span>
      </div>
      {resource.status === "LOADING" ? <p className="muted">Loading {resource.endpoint}</p> : null}
      {resource.status === "EMPTY" ? <p className="muted">No read-model records available for {resource.endpoint}.</p> : null}
      {resource.status === "ERROR" ? (
        <div className="error-box">
          <p>Endpoint: {resource.endpoint}</p>
          <p>request_id: {resource.requestId}</p>
          <p>error: {resource.errorCode}</p>
          <button type="button" onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : null}
      {resource.status === "STALE" ? <p className="warning">Data is stale; showing last read-model snapshot.</p> : null}
      {(resource.status === "SUCCESS" || resource.status === "STALE") && resource.data ? children(resource.data) : null}
    </section>
  );
}

function ProbabilityTable({ title, resource, onRetry }: { title: string; resource: Resource<Probability>; onRetry: () => void }) {
  return (
    <StatePanel title={title} resource={resource} onRetry={onRetry}>
      {(data) => {
        const rows = Object.entries(data.probabilities);
        return (
          <>
            {rows.length ? (
              <table>
                <tbody>
                  {rows.map(([label, value]) => (
                    <tr key={label}>
                      <th>{label}</th>
                      <td>{(value * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">Probability read model is empty.</p>
            )}
            <p className="source">{data.probability_type} · {data.source}</p>
          </>
        );
      }}
    </StatePanel>
  );
}

function App() {
  const [fixtures, setFixtures] = useState<Resource<FixtureList>>(emptyResource("/api/v1/fixtures?page_size=12&timezone=UTC"));
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Resource<FixtureDetail>>(emptyResource("/api/v1/fixtures/none"));
  const [forward, setForward] = useState<Resource<ForwardStatus>>(emptyResource("/api/v1/forward-holdout/status"));
  const [provider, setProvider] = useState<Resource<ProviderStatus>>(emptyResource("/api/v1/providers/status"));
  const [health, setHealth] = useState<Resource<DataHealth>>(emptyResource("/api/v1/data-health"));
  const [market, setMarket] = useState<Resource<Probability>>(emptyResource("/api/v1/fixtures/none/market-probabilities"));
  const [model, setModel] = useState<Resource<Probability>>(emptyResource("/api/v1/fixtures/none/model-probabilities"));
  const [tasks, setTasks] = useState<Resource<OpsList>>(emptyResource("/api/ops/tasks"));
  const [alerts, setAlerts] = useState<Resource<OpsList>>(emptyResource("/api/ops/alerts"));
  const [worldCup, setWorldCup] = useState<Resource<WorldCupReadiness>>(emptyResource("/api/ops/world-cup-readiness"));
  const [leagues, setLeagues] = useState<Resource<LeagueList>>(emptyResource("/api/v1/leagues"));
  const [operations, setOperations] = useState<Resource<OperationsLatest>>(emptyResource("/api/ops/operations/latest"));
  const [release, setRelease] = useState<Resource<ReleaseReadiness>>(emptyResource("/api/ops/releases/readiness"));
  const [retention, setRetention] = useState<Resource<RetentionStatus>>(emptyResource("/api/ops/retention/status"));

  const loadFixtures = useCallback(() => {
    const endpoint = "/api/v1/fixtures?page_size=12&timezone=UTC";
    setFixtures(emptyResource(endpoint));
    loadJson<FixtureList>(endpoint).then((payload) => {
      setFixtures(payload);
      const first = payload.data?.items?.[0]?.fixture_id ?? null;
      setSelected((current) => current ?? first);
    });
  }, []);

  const loadCommon = useCallback(() => {
    loadJson<ForwardStatus>("/api/v1/forward-holdout/status").then(setForward);
    loadJson<ProviderStatus>("/api/v1/providers/status").then(setProvider);
    loadJson<DataHealth>("/api/v1/data-health").then(setHealth);
    loadJson<OpsList>("/api/ops/tasks").then(setTasks);
    loadJson<OpsList>("/api/ops/alerts").then(setAlerts);
    loadJson<WorldCupReadiness>("/api/ops/world-cup-readiness").then(setWorldCup);
    loadJson<LeagueList>("/api/v1/leagues").then(setLeagues);
    loadJson<OperationsLatest>("/api/ops/operations/latest").then(setOperations);
    loadJson<ReleaseReadiness>("/api/ops/releases/readiness").then(setRelease);
    loadJson<RetentionStatus>("/api/ops/retention/status").then(setRetention);
  }, []);

  useEffect(() => {
    loadFixtures();
    loadCommon();
  }, [loadCommon, loadFixtures]);

  useEffect(() => {
    if (!selected) {
      return;
    }
    const detailEndpoint = `/api/v1/fixtures/${selected}`;
    const marketEndpoint = `/api/v1/fixtures/${selected}/market-probabilities`;
    const modelEndpoint = `/api/v1/fixtures/${selected}/model-probabilities`;
    setDetail(emptyResource(detailEndpoint));
    setMarket(emptyResource(marketEndpoint));
    setModel(emptyResource(modelEndpoint));
    loadJson<FixtureDetail>(detailEndpoint).then(setDetail);
    loadJson<Probability>(marketEndpoint).then(setMarket);
    loadJson<Probability>(modelEndpoint).then(setModel);
  }, [selected]);

  const fixtureItems = fixtures.data?.items ?? [];
  const selectedFixture = useMemo(
    () => fixtureItems.find((fixture) => fixture.fixture_id === selected),
    [fixtureItems, selected],
  );

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="kicker">W2 Operations Console</p>
          <h1>Live read-model dashboard</h1>
        </div>
        <strong className="banner">正式推荐尚未启用，当前仅为研究与前瞻验证。</strong>
      </header>

      <section className="grid three">
        <StatePanel title="Forward Holdout" resource={forward} onRetry={loadCommon}>
          {(data) => (
            <div className="metric">
              <strong>{data.status}</strong>
              <p>{data.current_settled_n}/{data.target_n} settled · market comparable {data.market_comparable}</p>
            </div>
          )}
        </StatePanel>
        <StatePanel title="Provider" resource={provider} onRetry={loadCommon}>
          {(data) => (
            <div className="metric">
              <strong>{data.status}</strong>
              <p>{data.provider} · quota {data.remaining_quota ?? "unknown"} · last {data.last_request_status ?? "n/a"}</p>
            </div>
          )}
        </StatePanel>
        <StatePanel title="Data Health" resource={health} onRetry={loadCommon}>
          {(data) => (
            <div className="metric">
              <strong>{data.provider_status}</strong>
              <p>{data.stale_data_count} stale · generated {data.generated_at}</p>
            </div>
          )}
        </StatePanel>
      </section>

      <section className="grid main-grid">
        <StatePanel title="Today Fixtures" resource={fixtures} onRetry={loadFixtures}>
          {(data) => (
            <div className="fixture-list">
              {data.items.map((fixture) => (
                <button
                  className={fixture.fixture_id === selected ? "fixture active" : "fixture"}
                  key={fixture.fixture_id}
                  onClick={() => setSelected(fixture.fixture_id)}
                  type="button"
                >
                  <span>{fixture.competition_name}</span>
                  <strong>{fixture.kickoff_display}</strong>
                  <small>{fixture.status} · {fixture.lifecycle_state} · {fixture.data_state}</small>
                </button>
              ))}
            </div>
          )}
        </StatePanel>

        <StatePanel title="Fixture Detail" resource={detail} onRetry={() => selected && loadJson<FixtureDetail>(`/api/v1/fixtures/${selected}`).then(setDetail)}>
          {(data) => (
            <dl className="facts">
              <div><dt>Fixture</dt><dd>{selectedFixture?.fixture_id ?? data.fixture_id}</dd></div>
              <div><dt>Competition</dt><dd>{data.competition_name}</dd></div>
              <div><dt>Kickoff</dt><dd>{data.kickoff_display}</dd></div>
              <div><dt>Bookmakers</dt><dd>{data.bookmaker_count}</dd></div>
              <div><dt>Coverage</dt><dd>{JSON.stringify(data.market_coverage)}</dd></div>
              <div><dt>Research status</dt><dd>{data.forward_decision}</dd></div>
              <div><dt>Risk notes</dt><dd>{data.risk_notes.length ? data.risk_notes.join(", ") : "None"}</dd></div>
            </dl>
          )}
        </StatePanel>
      </section>

      <section className="grid two">
        <ProbabilityTable title="Market fair probabilities" resource={market} onRetry={() => selected && loadJson<Probability>(`/api/v1/fixtures/${selected}/market-probabilities`).then(setMarket)} />
        <ProbabilityTable title="Independent model probabilities" resource={model} onRetry={() => selected && loadJson<Probability>(`/api/v1/fixtures/${selected}/model-probabilities`).then(setModel)} />
      </section>

      <section className="grid two">
        <StatePanel title="World Cup Readiness" resource={worldCup} onRetry={loadCommon}>
          {(data) => (
            <dl className="facts">
              <div><dt>Profile</dt><dd>{data.profile_version}</dd></div>
              <div><dt>Fixture coverage</dt><dd>{data.fixture_coverage_count}</dd></div>
              <div><dt>Gate</dt><dd>{data.gate_status}</dd></div>
              <div><dt>Strategy</dt><dd>{data.strategy_version}</dd></div>
              <div><dt>Blockers</dt><dd>{data.blockers.length ? data.blockers.join(", ") : "None"}</dd></div>
            </dl>
          )}
        </StatePanel>
        <StatePanel title="League Readiness" resource={leagues} onRetry={loadCommon}>
          {(data) => (
            <div className="league-grid">
              {data.items.map((league) => (
                <article className="league-card" key={league.competition_id}>
                  <h3>{league.name}</h3>
                  <span>{league.country}</span>
                  <p>{league.results_status} · {league.latest_season ?? "review"}</p>
                  <small>{JSON.stringify(league.market_status)}</small>
                </article>
              ))}
            </div>
          )}
        </StatePanel>
      </section>

      <section className="grid two">
        <StatePanel title="Tasks" resource={tasks} onRetry={loadCommon}>
          {(data) => <pre>{JSON.stringify(data.items, null, 2)}</pre>}
        </StatePanel>
        <StatePanel title="Alerts" resource={alerts} onRetry={loadCommon}>
          {(data) => <pre>{JSON.stringify(data.items, null, 2)}</pre>}
        </StatePanel>
      </section>

      <section className="panel readiness">
        <div className="panel-title">
          <h2>Operations Governance</h2>
          <span>{operations.data?.latest.status ?? operations.status}</span>
        </div>
        <div className="readiness-grid">
          <div><span>Forward progress</span><strong>{forward.data ? `${forward.data.current_settled_n}/${forward.data.target_n}` : forward.status}</strong></div>
          <div><span>Dependency risk</span><strong>{release.data?.dependency_blocker ?? release.status}</strong></div>
          <div><span>Backups / retention</span><strong>{retention.data?.status ?? retention.status}</strong></div>
          <div><span>Gate</span><strong>GATE_4_PENDING</strong></div>
        </div>
        <p className="warning">正式推荐与生产发布尚未启用。</p>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
