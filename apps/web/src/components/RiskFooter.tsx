import { currentOdds, risks } from "../lib/normalize";
import type { DashboardCard } from "../types/dashboard";
import { WatchStars } from "./WatchStars";

export function RiskFooter({ card }: { card: DashboardCard }) {
  const odds = currentOdds(card);
  const riskRows = risks(card);
  return (
    <footer className="risk-footer">
      <div>
        <p className="odds-line">{odds.length ? odds.join(" · ") : "当前盘口等待采集"}</p>
        <p className="risk-line">
          <span aria-hidden="true">⚠</span>
          风险：{(riskRows.length ? riskRows : ["天气、红牌、阵容临场变化可能改变判断"]).join("、")}
        </p>
      </div>
      <WatchStars card={card} />
    </footer>
  );
}
