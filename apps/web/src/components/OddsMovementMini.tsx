import { asRecord, textValue } from "../lib/normalize";
import type { DashboardMatchCard } from "../types/dashboard";

export function OddsMovementMini({ match }: { match: DashboardMatchCard }) {
  const intent = asRecord(match.bookmaker_intent);
  const open = textValue(intent.opening_line);
  const current = textValue(intent.current_line);
  const odds = asRecord(match.current_odds);
  const hasOdds = Boolean(Object.keys(asRecord(odds.ah)).length || Object.keys(asRecord(odds.ou)).length);
  return (
    <p className="odds-movement">
      <span aria-hidden="true">↗</span>
      庄家意图：{textValue(intent.label_cn ?? intent.intent, "数据不足")}
      {" · "}
      {open && current ? `盘口 ${open} → ${current}` : hasOdds ? "盘口已更新，等待完整轨迹" : "等待盘口"}
    </p>
  );
}
