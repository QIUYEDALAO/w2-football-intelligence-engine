import { asRecord, textValue } from "../lib/normalize";
import type { DashboardMatchCard } from "../types/dashboard";

export function OddsMovementMini({ match }: { match: DashboardMatchCard }) {
  const intent = asRecord(match.bookmaker_intent);
  const open = textValue(intent.opening_line);
  const current = textValue(intent.current_line);
  const odds = asRecord(match.current_odds);
  const hasOdds = Boolean(Object.keys(asRecord(odds.ah)).length || Object.keys(asRecord(odds.ou)).length);
  const movement = open && current ? `盘口 ${open} → ${current}` : hasOdds ? "盘口已更新" : "等待盘口";
  return (
    <p className="odds-movement">
      <span aria-hidden="true">↗</span>
      盘口假设 · 未验证：
      {" · "}
      {movement}
      {" · "}
      可能来自伤停、公众热度或盘口保护；等待完整盘口轨迹。
    </p>
  );
}
