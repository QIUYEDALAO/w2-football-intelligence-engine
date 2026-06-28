import { lineMovement } from "../lib/normalize";
import type { DashboardCard } from "../types/dashboard";

export function BookmakerIntentLine({ card }: { card: DashboardCard }) {
  return (
    <p className="intent-line">
      <span aria-hidden="true">↗</span>
      盘口假设 · 未验证：{lineMovement(card)} · 可能来自伤停、公众热度或盘口保护；等待完整盘口轨迹。
    </p>
  );
}
