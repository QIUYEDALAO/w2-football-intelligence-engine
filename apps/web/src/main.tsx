import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Fixture = {
  fixture_id: string;
  competition_name: string;
  kickoff_display: string;
  status: string;
  lifecycle_state: string;
  data_state: string;
};

type FixtureList = {
  items: Fixture[];
};

type ForwardStatus = {
  status: string;
  locks: number;
  market_comparable: number;
  current_settled_n: number;
  target_n: number;
};

type ProviderStatus = {
  provider: string;
  status: string;
  remaining_quota: number | null;
  credential_status: string;
};

type DataHealth = {
  stale_data_count: number;
  provider_status: string;
  forward_cycle_age_seconds: number | null;
};

type Probability = {
  probability_type: string;
  probabilities: Record<string, number>;
  source: string;
  quality: string;
};

type OpsList = {
  items: Array<{ key: string; status: string; payload: Record<string, unknown> }>;
};

type WorldCupReadiness = {
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
  items: LeagueSummary[];
};

const emptyProbability: Probability = {
  probability_type: "not_available",
  probabilities: {},
  source: "not_available",
  quality: "SKIP",
};

async function getJson<T>(path: string): Promise<T | null> {
  const response = await fetch(path);
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as T;
}

function ProbabilityTable({ title, data }: { title: string; data: Probability }) {
  const rows = Object.entries(data.probabilities);
  return (
    <section className="panel">
      <div className="panel-title">
        <h2>{title}</h2>
        <span>{data.quality}</span>
      </div>
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
        <p className="muted">No probability snapshot available.</p>
      )}
      <p className="source">{data.source}</p>
    </section>
  );
}

function App() {
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [forward, setForward] = useState<ForwardStatus | null>(null);
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [health, setHealth] = useState<DataHealth | null>(null);
  const [market, setMarket] = useState<Probability>(emptyProbability);
  const [model, setModel] = useState<Probability>(emptyProbability);
  const [tasks, setTasks] = useState<OpsList | null>(null);
  const [alerts, setAlerts] = useState<OpsList | null>(null);
  const [worldCup, setWorldCup] = useState<WorldCupReadiness | null>(null);
  const [leagues, setLeagues] = useState<LeagueSummary[]>([]);

  useEffect(() => {
    getJson<FixtureList>("/v1/fixtures?page_size=12&timezone=UTC").then((payload) => {
      const items = payload?.items ?? [];
      setFixtures(items);
      setSelected(items[0]?.fixture_id ?? null);
    });
    getJson<ForwardStatus>("/v1/forward-holdout/status").then(setForward);
    getJson<ProviderStatus>("/v1/providers/status").then(setProvider);
    getJson<DataHealth>("/v1/data-health").then(setHealth);
    getJson<OpsList>("/ops/tasks").then(setTasks);
    getJson<OpsList>("/ops/alerts").then(setAlerts);
    getJson<WorldCupReadiness>("/ops/world-cup-readiness").then(setWorldCup);
    getJson<LeagueList>("/v1/leagues").then((payload) => setLeagues(payload?.items ?? []));
  }, []);

  useEffect(() => {
    if (!selected) {
      return;
    }
    getJson<Probability>(`/v1/fixtures/${selected}/market-probabilities`).then(
      (payload) => setMarket(payload ?? emptyProbability),
    );
    getJson<Probability>(`/v1/fixtures/${selected}/model-probabilities`).then(
      (payload) => setModel(payload ?? emptyProbability),
    );
  }, [selected]);

  const selectedFixture = useMemo(
    () => fixtures.find((fixture) => fixture.fixture_id === selected),
    [fixtures, selected],
  );

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="kicker">W2 Operations Console</p>
          <h1>Read-only football intelligence monitor</h1>
        </div>
        <strong className="banner">正式推荐尚未启用，当前仅为研究与前瞻验证。</strong>
      </header>

      <section className="grid three">
        <div className="panel metric">
          <span>Forward Holdout</span>
          <strong>{forward?.status ?? "SKIP"}</strong>
          <p>{forward ? `${forward.current_settled_n}/${forward.target_n} settled` : "loading"}</p>
        </div>
        <div className="panel metric">
          <span>Provider</span>
          <strong>{provider?.status ?? "UNKNOWN"}</strong>
          <p>{provider?.remaining_quota ?? "quota unknown"}</p>
        </div>
        <div className="panel metric">
          <span>Data Health</span>
          <strong>{health?.provider_status ?? "UNKNOWN"}</strong>
          <p>{health?.stale_data_count ?? 0} stale records</p>
        </div>
      </section>

      <section className="grid main-grid">
        <section className="panel">
          <div className="panel-title">
            <h2>Today Fixtures</h2>
            <span>Decision / lifecycle / data</span>
          </div>
          <div className="fixture-list">
            {fixtures.map((fixture) => (
              <button
                className={fixture.fixture_id === selected ? "fixture active" : "fixture"}
                key={fixture.fixture_id}
                onClick={() => setSelected(fixture.fixture_id)}
                type="button"
              >
                <span>{fixture.competition_name}</span>
                <strong>{fixture.kickoff_display}</strong>
                <small>
                  {fixture.status} · {fixture.lifecycle_state} · {fixture.data_state}
                </small>
              </button>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-title">
            <h2>Fixture Detail</h2>
            <span>{selectedFixture?.fixture_id ?? "none"}</span>
          </div>
          {selectedFixture ? (
            <dl className="facts">
              <div>
                <dt>Competition</dt>
                <dd>{selectedFixture.competition_name}</dd>
              </div>
              <div>
                <dt>Kickoff</dt>
                <dd>{selectedFixture.kickoff_display}</dd>
              </div>
              <div>
                <dt>Forward status</dt>
                <dd>{selectedFixture.lifecycle_state}</dd>
              </div>
              <div>
                <dt>Coverage</dt>
                <dd>1X2 captured; AH/OU shown only when present</dd>
              </div>
            </dl>
          ) : (
            <p className="muted">No fixture selected.</p>
          )}
        </section>
      </section>

      <section className="grid two">
        <ProbabilityTable data={market} title="Market fair probabilities" />
        <ProbabilityTable data={model} title="Independent model probabilities" />
      </section>

      <section className="panel readiness">
        <div className="panel-title">
          <h2>World Cup Readiness</h2>
          <span>{worldCup?.strategy_version ?? "NOT_AVAILABLE_GATE4"}</span>
        </div>
        <div className="readiness-grid">
          <div>
            <span>Profile</span>
            <strong>{worldCup?.profile_version ?? "loading"}</strong>
          </div>
          <div>
            <span>Fixture coverage</span>
            <strong>{worldCup?.fixture_coverage_count ?? 0}</strong>
          </div>
          <div>
            <span>Phase plan</span>
            <strong>{worldCup?.phase_count_per_fixture ?? 0} phases</strong>
          </div>
          <div>
            <span>Gate</span>
            <strong>{worldCup?.gate_status ?? "pending"}</strong>
          </div>
        </div>
        <dl className="facts compact">
          <div>
            <dt>Data coverage</dt>
            <dd>{JSON.stringify(worldCup?.data_coverage ?? {})}</dd>
          </div>
          <div>
            <dt>Shadow runtime</dt>
            <dd>{worldCup?.shadow_runtime ?? "DISABLED_PENDING_GATE4"}</dd>
          </div>
          <div>
            <dt>Blockers</dt>
            <dd>{worldCup?.blockers.length ? worldCup.blockers.join(", ") : "None"}</dd>
          </div>
        </dl>
        <p className="warning">正式推荐尚未启用。</p>
      </section>

      <section className="panel readiness">
        <div className="panel-title">
          <h2>League Readiness</h2>
          <span>top five onboarding</span>
        </div>
        <div className="league-grid">
          {leagues.map((league) => (
            <article className="league-card" key={league.competition_id}>
              <div>
                <h3>{league.name}</h3>
                <span>{league.country}</span>
              </div>
              <dl className="facts compact">
                <div>
                  <dt>Season</dt>
                  <dd>{league.latest_season ?? "review"}</dd>
                </div>
                <div>
                  <dt>Results</dt>
                  <dd>{league.results_status}</dd>
                </div>
                <div>
                  <dt>Markets</dt>
                  <dd>{JSON.stringify(league.market_status)}</dd>
                </div>
                <div>
                  <dt>Blocker</dt>
                  <dd>{league.blocker ?? "None"}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
        <p className="warning">正式推荐尚未启用。</p>
      </section>

      <section className="grid two">
        <section className="panel">
          <div className="panel-title">
            <h2>Tasks & Alerts</h2>
            <span>read-only</span>
          </div>
          <pre>{JSON.stringify({ tasks: tasks?.items, alerts: alerts?.items }, null, 2)}</pre>
        </section>
        <section className="panel">
          <div className="panel-title">
            <h2>Backtest & Gate</h2>
            <span>provisional</span>
          </div>
          <p className="muted">
            Gate 4 remains pending. WATCH/SKIP are lifecycle states, not recommendations.
          </p>
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
