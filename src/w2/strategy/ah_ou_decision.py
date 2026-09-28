"""AH/OU F9+F6 softmax decision orchestration.

Reads the *correct* production data sources (rolling xG snapshots + canonical
match history with ``team_side``), builds the 14/22-dim features, and runs the
frozen softmax selection. This is the replacement for the old weighted
``factor_score`` AH direction and the ``bookmaker_intent`` OU view.

Pure orchestration: it takes a repository (duck-typed) and explicit quote
inputs, so it can be exercised offline against a fixture set without touching
the production analysis pipeline.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from w2.strategy.ah_ou_features import build_features
from w2.strategy.ah_ou_softmax import ah_select, ou_select


class AhOuRepository(Protocol):
    def team_xg_rolling_snapshots_for_w2_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        competition_id: str,
        season: str,
    ) -> list[dict[str, Any]]: ...

    def canonical_match_history_for_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        limit_per_team: int = 20,
    ) -> list[dict[str, Any]]: ...


def build_ah_ou_selections(
    repository: AhOuRepository,
    *,
    home_team_id: str,
    away_team_id: str,
    kickoff: datetime,
    competition_id: str,
    season: str,
    ah_line: float,
    ah_home_odds: float,
    ah_away_odds: float,
    ou_line: float,
    ou_over_odds: float,
    ou_under_odds: float,
) -> dict[str, Any]:
    """Return ``{"status", "ah", "ou", "features"}``.

    Fail-closed: any missing F9 snapshot or F6 meeting yields ``status`` other
    than ``READY`` and ``ah/ou = None``, so a caller must never emit a direction
    on partial evidence.
    """
    snapshots = repository.team_xg_rolling_snapshots_for_w2_teams(
        [home_team_id, away_team_id],
        before=kickoff,
        competition_id=competition_id,
        season=season,
    )
    home_snapshot = next((s for s in snapshots if s.get("team_id") == home_team_id), None)
    away_snapshot = next((s for s in snapshots if s.get("team_id") == away_team_id), None)
    if home_snapshot is None or away_snapshot is None:
        return {"status": "F9_ROLLING_SNAPSHOT_MISSING", "ah": None, "ou": None}

    history = repository.canonical_match_history_for_teams(
        [home_team_id], before=kickoff, limit_per_team=20
    )
    meetings = [
        {
            "goals_for": int(row["goals_for"]),
            "goals_against": int(row["goals_against"]),
            "kickoff_at": row["kickoff_utc"],
            "team_side": row["team_side"],
        }
        for row in history
        if row.get("opponent_w2_id") == away_team_id
    ]
    meetings.sort(key=lambda row: row["kickoff_at"])
    if not meetings:
        return {"status": "F6_H2H_MISSING", "ah": None, "ou": None}

    features = build_features(
        home_snapshot=home_snapshot,
        away_snapshot=away_snapshot,
        meetings=meetings,
        kickoff=kickoff,
    )
    return {
        "status": "READY",
        "ah": ah_select(
            features, home_line=ah_line, home_odds=ah_home_odds, away_odds=ah_away_odds
        ),
        "ou": ou_select(
            features, line=ou_line, over_odds=ou_over_odds, under_odds=ou_under_odds
        ),
        "features": features,
    }
