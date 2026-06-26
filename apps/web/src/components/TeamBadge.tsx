import { teamBadgeLabel } from "../lib/normalize";

export function TeamBadge({ name }: { name: string }) {
  return <span className="team-badge">{teamBadgeLabel(name)}</span>;
}
