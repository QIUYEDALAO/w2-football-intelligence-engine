import { intentLabel, lineMovement } from "../lib/normalize";
import type { DashboardCard } from "../types/dashboard";

export function BookmakerIntentLine({ card }: { card: DashboardCard }) {
  return (
    <p className="intent-line">
      <span aria-hidden="true">↗</span>
      庄家意图：{intentLabel(card)} · {lineMovement(card)}
    </p>
  );
}
