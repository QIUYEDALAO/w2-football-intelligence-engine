import { watchLevel } from "../lib/normalize";
import type { DashboardCard } from "../types/dashboard";

export function WatchStars({ card }: { card: DashboardCard }) {
  const level = watchLevel(card);
  return (
    <span className="watch-stars" aria-label={`关注度 ${level}/5`}>
      关注度 {"★".repeat(level)}
      {"☆".repeat(5 - level)}
    </span>
  );
}
