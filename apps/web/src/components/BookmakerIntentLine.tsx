import { bookmakerIntent, lineMovement, signalStrengthLabel } from "../lib/normalize";
import type { DashboardCard } from "../types/dashboard";

export function BookmakerIntentLine({ card }: { card: DashboardCard }) {
  const intent = bookmakerIntent(card);
  const strength = intent.signal_strength ?? intent.confidence;
  return (
    <p className="intent-line">
      <span aria-hidden="true">↗</span>
      盘口假设 · 未验证：{lineMovement(card)} · 信号强度：{signalStrengthLabel(strength)}；规则评分，不是概率或命中率。可能来自伤停、公众热度或盘口保护；等待完整盘口轨迹。
    </p>
  );
}
