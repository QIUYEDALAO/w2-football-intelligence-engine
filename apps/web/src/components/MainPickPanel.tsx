import { SignalStrengthDots } from "./ConfidenceDots";
import {
  isMarketPick,
  leanLabel,
  marketClass,
  marketLabel,
  preferredMarket,
  readableReasons,
  scoreRows,
} from "../lib/normalize";
import type { DashboardCard } from "../types/dashboard";

export function MainPickPanel({ card }: { card: DashboardCard }) {
  const market = preferredMarket(card);
  const isPick = isMarketPick(market);
  const reasons = readableReasons(market.reasons, market.reason ?? market.reason_cn);
  const scores = scoreRows(market);
  return (
    <section className={isPick ? "main-pick-panel is-pick" : "main-pick-panel is-skip"}>
      <div className="main-pick-copy">
        <strong>
          {marketLabel(market)}
          {isPick ? " · 倾向 " : " · "}
          <span>{isPick ? leanLabel(market) : "暂不推荐"}</span>
        </strong>
        <p>{reasons.length ? reasons.join(" · ") : "数据不足，暂不输出该市场倾向。"}</p>
        {scores.length ? (
          <div className="score-chips">
            {scores.map((score) => (
              <span className={`score-chip ${marketClass(market)}`} key={`${score.scoreline}-${score.probability}`}>
                {score.scoreline}
                {score.probability ? <small>{score.probability}</small> : null}
              </span>
            ))}
          </div>
        ) : null}
        {card.ai_summary ? <p className="ai-summary">{card.ai_summary}</p> : null}
      </div>
      <SignalStrengthDots value={isPick ? market.signal_strength ?? market.confidence : 0} />
    </section>
  );
}
