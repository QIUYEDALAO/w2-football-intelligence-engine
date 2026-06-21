import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Health = {
  service: string;
  version: string;
  environment: string;
  database: string;
  redis: string;
};

function App() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetch("/health")
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: Health | null) => setHealth(payload))
      .catch(() => setHealth(null));
  }, []);

  return (
    <main className="shell">
      <section className="status-panel">
        <p className="kicker">W2 Stage 2</p>
        <h1>Engineering Foundation</h1>
        <p className="notice">真实推荐尚未启用</p>
        <dl className="health-grid">
          <div>
            <dt>API health</dt>
            <dd>{health ? "reachable" : "not connected"}</dd>
          </div>
          <div>
            <dt>Database</dt>
            <dd>{health?.database ?? "unknown"}</dd>
          </div>
          <div>
            <dt>Redis</dt>
            <dd>{health?.redis ?? "unknown"}</dd>
          </div>
          <div>
            <dt>Environment</dt>
            <dd>{health?.environment ?? "local"}</dd>
          </div>
        </dl>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);

