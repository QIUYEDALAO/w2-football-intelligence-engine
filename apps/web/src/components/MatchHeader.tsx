import { fmtTime } from "../lib/formatters";
import { awayName, cardStatus, competitionName, homeName, readinessLabel } from "../lib/normalize";
import type { DashboardCard } from "../types/dashboard";
import { TeamBadge } from "./TeamBadge";

export function MatchHeader({ card }: { card: DashboardCard }) {
  const home = homeName(card);
  const away = awayName(card);
  const status = cardStatus(card);
  return (
    <header className="match-header">
      <div>
        <span className="match-meta">
          {fmtTime(card.kickoff_utc)} · {competitionName(card)}
        </span>
        <div className="teams-row">
          <TeamBadge name={home} />
          <strong>{home}</strong>
          <span>vs</span>
          <strong>{away}</strong>
          <TeamBadge name={away} />
        </div>
      </div>
      <span className={`status-pill is-${status}`}>{readinessLabel(card)}</span>
    </header>
  );
}
