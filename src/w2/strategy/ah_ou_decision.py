"""AH/OU F9+F6 softmax decision orchestration.

Reads the *correct* production data sources (rolling xG snapshots + canonical
match history with ``team_side``), enforces the per-fixture admission gates,
builds the 14/22-dim features and runs the frozen softmax selection. This is
the replacement for the old weighted ``factor_score`` AH direction and the
``bookmaker_intent`` OU view.

Admission gates (task "原子切换前整改" item 3):
* F9/F6 evidence must be observable at ``decision_at = kickoff - 2h`` (not the
  kickoff), so both reads use ``before=decision_at``.
* F6 meetings are FT only and limited to the last 10 against the same opponent.
* F9 snapshot must bind to the target team uniquely.
* Both AH sides and both OU sides must carry real prices (> 1); a missing or
  non-positive price is a structured SKIP, not a direction.
* A hemisphere AH line is required (no quarter lines).

Every refusal returns ``status != READY`` with ``ah/ou = None`` (direction 0):
the caller must never emit a pick on partial or conflicted evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Protocol

from w2.strategy.ah_ou_features import build_features
from w2.strategy.ah_ou_softmax import ah_select, ou_select

DECISION_LEAD_TIME = timedelta(hours=2)
MAX_SAME_OPPONENT_MEETINGS = 10


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

    # Optional AS-OF role scoping (task 整改 item 4): when present, the reads
    # are performed under ``quant_asof_reader_role`` so the softmax path cannot
    # see result/settlement tables. Implementations may no-op if unsupported.
    def set_asof_role(self, role: str | None) -> None: ...


def _skip(status: str) -> dict[str, Any]:
    return {"status": status, "ah": None, "ou": None, "features": None}


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
    asof_role: str | None = "quant_asof_reader_role",
) -> dict[str, Any]:
    """Return ``{"status", "ah", "ou", "features"}``.

    ``status == "READY"`` only when every admission gate passes; otherwise it is
    a machine-readable refusal code and both ``ah``/``ou`` are ``None``.

    The F9/F6 reads are scoped to ``asof_role`` (default the AS-OF reader role)
    so the softmax path can never observe a result or settlement row.
    """
    decision_at = kickoff - DECISION_LEAD_TIME

    # --- 盘口准入：双侧价 + AH 半球线 -----------------------------------
    if ah_home_odds <= 1.0 or ah_away_odds <= 1.0:
        return _skip("AH_ODDS_INCOMPLETE")
    if ou_over_odds <= 1.0 or ou_under_odds <= 1.0:
        return _skip("OU_ODDS_INCOMPLETE")
    if (ah_line * 2) % 1 != 0:
        return _skip("AH_LINE_NOT_HEMISPHERE")

    set_role = getattr(repository, "set_asof_role", None)
    if asof_role and callable(set_role):
        set_role(asof_role)
    try:
        # --- F9 准入：滚动快照绑定唯一 -----------------------------------
        snapshots = repository.team_xg_rolling_snapshots_for_w2_teams(
            [home_team_id, away_team_id],
            before=decision_at,
            competition_id=competition_id,
            season=season,
        )
        home_rows = [s for s in snapshots if s.get("team_id") == home_team_id]
        away_rows = [s for s in snapshots if s.get("team_id") == away_team_id]
        # Unique target binding: each team must resolve to exactly one snapshot.
        # Zero or multiple bindings are a structured SKIP, never an arbitrary pick.
        if len(home_rows) != 1 or len(away_rows) != 1:
            return _skip("F9_ROLLING_SNAPSHOT_NOT_UNIQUE")
        home_snapshot = home_rows[0]
        away_snapshot = away_rows[0]

        # --- F6 准入：FT + 同对手 ≤10 场 ----------------------------------
        history = repository.canonical_match_history_for_teams(
            [home_team_id], before=decision_at, limit_per_team=20
        )
    finally:
        if asof_role and callable(set_role):
            set_role(None)

    meetings = [
        {
            "goals_for": int(row["goals_for"]),
            "goals_against": int(row["goals_against"]),
            "kickoff_at": row["kickoff_utc"],
            "team_side": row["team_side"],
        }
        for row in history
        if row.get("opponent_w2_id") == away_team_id
        and str(row.get("fixture_status") or "").upper() == "FT"
    ]
    meetings.sort(key=lambda row: row["kickoff_at"])
    meetings = meetings[-MAX_SAME_OPPONENT_MEETINGS:]
    if not meetings:
        return _skip("F6_H2H_MISSING")

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
