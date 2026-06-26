import type { ScorelinePick } from "../types/dashboard";

function scoreClass(pick: ScorelinePick): string {
  if (pick.hit) return "score-pick is-hit";
  if (pick.direction_hit) return "score-pick is-direction";
  return "score-pick";
}

export function ScorelinePicks({ picks }: { picks: ScorelinePick[] }) {
  if (!picks.length) {
    return <p className="scoreline-empty">推荐比分：比分模型未就绪</p>;
  }
  return (
    <div className="scoreline-picks" aria-label="推荐比分">
      <span>推荐比分</span>
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
