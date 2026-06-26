import { readinessItems } from "../lib/normalize";
import type { DashboardMatchCard } from "../types/dashboard";

export function DataReadinessRow({ match }: { match: DashboardMatchCard }) {
  return (
    <div className="readiness-chips">
      {readinessItems({ data_readiness: match.data_readiness }).map((item) => (
        <span className={item.ready ? "readiness-chip is-ready" : "readiness-chip"} key={item.key} title={item.value}>
          {item.short}
        </span>
      ))}
    </div>
  );
}
