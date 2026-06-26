import { translateReason } from "../lib/formatters";
import { confidenceDots } from "../lib/normalize";
import type { RecommendationPick } from "../types/dashboard";

export function MarketPickSummary({ pick }: { pick: RecommendationPick }) {
  const dots = confidenceDots(pick.confidence);
  const odds = pick.odds ? ` @${pick.odds}` : "";
  const line = pick.line ? ` ${pick.line}` : "";
  const probability = Number.isFinite(pick.model_probability) ? `模型概率 ${Math.round((pick.model_probability ?? 0) * 100)}%` : "模型概率待确认";
  const reason = pick.reasons.length ? pick.reasons.slice(0, 2).map(translateReason).join(" · ") : probability;
  return (
    <div className="market-pick-summary">
      <div>
        <span>主推</span>
        <strong>
          {pick.market_label_cn} {pick.selection_label_cn ?? pick.selection}
          {line}
          {odds}
        </strong>
        <p>
          {reason}
          {pick.fair_odds ? ` · 公允赔率 ${pick.fair_odds}` : ""}
          {pick.risk_adjusted_ev ? ` · EV ${pick.risk_adjusted_ev}` : ""}
        </p>
      </div>
      <span className="confidence-dots" aria-label={`信心 ${dots}/5`}>
        {[0, 1, 2, 3, 4].map((index) => (
          <span className={index < dots ? "dot is-filled" : "dot"} key={index} />
        ))}
      </span>
    </div>
  );
}
