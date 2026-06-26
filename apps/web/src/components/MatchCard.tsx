import { cardStatus } from "../lib/normalize";
import type { DashboardCard } from "../types/dashboard";
import { BookmakerIntentLine } from "./BookmakerIntentLine";
import { MainPickPanel } from "./MainPickPanel";
import { MarketStrip } from "./MarketStrip";
import { MatchHeader } from "./MatchHeader";
import { ReadinessChips } from "./ReadinessChips";
import { RiskFooter } from "./RiskFooter";

export function MatchCard({ card, compact = true }: { card: DashboardCard; compact?: boolean }) {
  const status = cardStatus(card);
  return (
    <article className={`match-card is-${status}${compact ? " is-compact" : ""}`}>
      <MatchHeader card={card} />
      <ReadinessChips card={card} />
      <MainPickPanel card={card} />
      <BookmakerIntentLine card={card} />
      <MarketStrip card={card} />
      <RiskFooter card={card} />
    </article>
  );
}
