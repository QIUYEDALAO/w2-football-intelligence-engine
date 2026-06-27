import type { ScorelinePick } from "../types/dashboard";

function scoreClass(pick: ScorelinePick): string {
  if (pick.hit) return "score-pick is-hit";
  if (pick.direction_hit) return "score-pick is-direction";
  return "score-pick";
}

export function ScorelinePicks({ picks }: { picks: ScorelinePick[] }) {
  if (!picks.length) {
    return null;
  }
  return (
    <div className="scoreline-picks" aria-label="最可能比分">
      <span>最可能比分（基于我们的 xG）</span>
      {picks.slice(0, 3).map((pick) => (
        <strong className={scoreClass(pick)} key={`${pick.scoreline}-${pick.probability_label ?? ""}`}>
          {pick.scoreline}
          {pick.probability_label ? <small>{pick.probability_label}</small> : null}
          {pick.hit ? <em>命中</em> : pick.direction_hit ? <em>方向中</em> : null}
        </strong>
      ))}
    </div>
  );
}
