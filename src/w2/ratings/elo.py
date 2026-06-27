from __future__ import annotations

from datetime import datetime

from w2.features.team_factors import TeamMatchHistory, TeamRatingSnapshot


def rating_from_history(
    *,
    team_id: str,
    history: list[TeamMatchHistory],
    as_of: datetime,
    min_matches: int = 2,
) -> TeamRatingSnapshot | None:
    rows = [row for row in history if row.team_id == team_id and row.kickoff_at <= as_of]
    if len(rows) < min_matches:
        return None
    points = 0
    goal_diff = 0
    goals_for = 0
    goals_against = 0
    for row in rows:
        diff = row.goals_for - row.goals_against
        goal_diff += diff
        goals_for += row.goals_for
        goals_against += row.goals_against
        points += 3 if diff > 0 else 1 if diff == 0 else 0
    matches = len(rows)
    ppg = points / matches
    avg_goal_diff = goal_diff / matches
    attack_strength = goals_for / matches
    defence_strength = goals_against / matches
    form_index = max(min((ppg - 1.0) / 2.0 + avg_goal_diff / 6.0, 1.0), -1.0)
    elo = 1500.0 + avg_goal_diff * 70.0 + (ppg - 1.0) * 55.0
    return TeamRatingSnapshot(
        team_id=team_id,
        observed_at=max(row.kickoff_at for row in rows),
        elo=elo,
        attack_strength=attack_strength,
        defence_strength=defence_strength,
        form_index=form_index,
        source="internal_elo_v1",
        source_group="ratings",
        is_independent_signal=True,
        collection_status="READY",
    )
