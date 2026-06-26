import { readinessItems } from "../lib/normalize";
import type { DashboardCard } from "../types/dashboard";

export function ReadinessChips({ card }: { card: DashboardCard }) {
  return (
    <div className="readiness-chips">
      {readinessItems(card).map((item) => (
        <span className={item.ready ? "readiness-chip is-ready" : "readiness-chip"} key={item.key}>
          {item.short}
        </span>
      ))}
    </div>
  );
}
