import { isMarketPick, leanLabel, marketClass, marketList, marketShort, preferredMarket, scoreRows } from "../lib/normalize";
import type { DashboardCard } from "../types/dashboard";

export function MarketStrip({ card }: { card: DashboardCard }) {
  const primary = preferredMarket(card);
  const rows = marketList(card).filter((market) => market.market !== primary.market);
  return (
    <div className="market-strip" aria-label="其他市场">
      {rows.map((market) => {
        const scores = scoreRows(market);
        const label = scores.length ? scores.map((score) => `${score.scoreline}${score.probability ? ` ${score.probability}` : ""}`).join(" / ") : leanLabel(market);
        return (
          <span className={isMarketPick(market) ? `market-chip ${marketClass(market)} is-pick` : "market-chip"} key={String(market.market)}>
            {marketShort(market)}：{isMarketPick(market) ? label : "数据不足"}
          </span>
        );
      })}
    </div>
  );
}
