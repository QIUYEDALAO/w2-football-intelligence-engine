import { asRecord, textValue } from "../lib/normalize";
import type { DashboardMatchCard } from "../types/dashboard";

export function OddsMovementMini({ match }: { match: DashboardMatchCard }) {
  const intent = asRecord(match.bookmaker_intent);
  const open = textValue(intent.opening_line);
  const current = textValue(intent.current_line);
  return (
    <p className="odds-movement">
      <span aria-hidden="true">↗</span>
      庄家意图：{textValue(intent.label_cn ?? intent.intent, "数据不足")}
      {" · "}
      {open && current ? `盘口 ${open} → ${current}` : "等待初盘与当前盘"}
    </p>
  );
}
