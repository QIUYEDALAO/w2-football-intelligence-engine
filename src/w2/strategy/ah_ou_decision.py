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

import math
from datetime import datetime, timedelta
from decimal import Decimal
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
        opponent_w2_id: str | None = None,
        fixture_status: str = "FT",
    ) -> list[dict[str, Any]]: ...

    # Optional AS-OF role scoping (task 整改 item 4): when present, the reads
    # are performed under ``quant_asof_reader_role`` so the softmax path cannot
    # see result/settlement tables. Implementations may no-op if unsupported.
    def set_asof_role(self, role: str | None) -> None: ...


def _skip(status: str) -> dict[str, Any]:
    return {"status": status, "ah": None, "ou": None, "features": None}


def _is_hemisphere_line(line: float) -> bool:
    """True only for a half line (decimal part exactly .5), never integer/quarter."""
    doubled = line * 2
    return abs(doubled - round(doubled)) < 1e-9 and round(doubled) % 2 == 1


def _parse_asof(value: Any) -> datetime | None:
    """Parse an AS-OF timestamp strictly: naive (timezone-less) values are refused.

    The AS-OF contract (S1) requires every decision input to be an unambiguous
    instant; a naive datetime is not an instant, so it is not silently coerced.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None
    return None


def _is_finite_number(value: Any) -> bool:
    """True only for a real (non-NaN, non-infinity) numeric value."""
    if isinstance(value, bool) or value is None:
        return False
    if not isinstance(value, (int, float, Decimal)):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def build_ah_ou_selections(
    repository: AhOuRepository,
    *,
    fixture_id: str,
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

    # --- 盘口准入：双侧价 + AH 半球线（仅 .5）---------------------------
    if ah_home_odds <= 1.0 or ah_away_odds <= 1.0:
        return _skip("AH_ODDS_INCOMPLETE")
    if ou_over_odds <= 1.0 or ou_under_odds <= 1.0:
        return _skip("OU_ODDS_INCOMPLETE")
    if not _is_hemisphere_line(ah_line):
        return _skip("AH_LINE_NOT_HEMISPHERE")

    set_role = getattr(repository, "set_asof_role", None)
    if asof_role and callable(set_role):
        set_role(asof_role)
    try:
        # --- F9 准入：滚动快照绑定唯一 + 目标 fixture 绑定 + 首捕获 ≤ decision_at
        snapshots = repository.team_xg_rolling_snapshots_for_w2_teams(
            [home_team_id, away_team_id],
            before=decision_at,
            competition_id=competition_id,
            season=season,
        )
        home_rows = [s for s in snapshots if s.get("team_id") == home_team_id]
        away_rows = [s for s in snapshots if s.get("team_id") == away_team_id]
        # Unique target binding: each team must resolve to exactly one snapshot.
        if len(home_rows) != 1 or len(away_rows) != 1:
            return _skip("F9_ROLLING_SNAPSHOT_NOT_UNIQUE")
        home_snapshot = home_rows[0]
        away_snapshot = away_rows[0]
        for snapshot in (home_snapshot, away_snapshot):
            if str(snapshot.get("as_of_fixture_id") or "") != fixture_id:
                return _skip("F9_SNAPSHOT_FIXTURE_MISBOUND")
            asof = _parse_asof(snapshot.get("as_of_time"))
            if asof is None:
                return _skip("F9_SNAPSHOT_AS_OF_NAIVE")
            if asof > decision_at:
                return _skip("F9_SNAPSHOT_AS_OF_AFTER_DECISION")
            if not snapshot.get("pit_proven"):
                return _skip("F9_SNAPSHOT_NOT_PIT_PROVEN")
            first_captured = _parse_asof(snapshot.get("first_captured_at"))
            if first_captured is None:
                return _skip("F9_SNAPSHOT_FIRST_CAPTURE_MISSING")
            if first_captured > decision_at:
                return _skip("F9_SNAPSHOT_FIRST_CAPTURE_AFTER_DECISION")
            for field in (
                "rolling_xg_for",
                "rolling_xg_against",
                "rolling_goals_for",
                "rolling_goals_against",
            ):
                if not _is_finite_number(snapshot.get(field)):
                    return _skip("F9_SNAPSHOT_NON_FINITE")

        # --- F6 准入：FT + 同对手（先筛再取 ≤10 场）--------------------
        history = repository.canonical_match_history_for_teams(
            [home_team_id],
            before=decision_at,
            limit_per_team=MAX_SAME_OPPONENT_MEETINGS,
            opponent_w2_id=away_team_id,
            fixture_status="FT",
        )
    finally:
        if asof_role and callable(set_role):
            set_role(None)

    meetings: list[dict[str, Any]] = []
    seen_fixtures: set[str] = set()
    for row in history:
        captured = _parse_asof(row.get("captured_at"))
        if captured is None or captured > decision_at:
            return _skip("F6_H2H_CAPTURED_AFTER_DECISION")
        status_first_visible = _parse_asof(row.get("status_first_visible_at"))
        if status_first_visible is None or status_first_visible > decision_at:
            return _skip("F6_H2H_STATUS_NOT_VISIBLE")
        if not row.get("pit_proven"):
            return _skip("F6_H2H_NOT_PIT_PROVEN")
        if _parse_asof(row.get("kickoff_utc")) is None:
            return _skip("F6_H2H_KICKOFF_NAIVE")
        if not _is_finite_number(row.get("goals_for")) or not _is_finite_number(
            row.get("goals_against")
        ):
            return _skip("F6_H2H_NON_FINITE")
        fixture_key = str(row.get("fixture_id") or "")
        if not fixture_key or fixture_key in seen_fixtures:
            return _skip("F6_H2H_DUPLICATE_MEETING")
        seen_fixtures.add(fixture_key)
        meetings.append(
            {
                "goals_for": int(row["goals_for"]),
                "goals_against": int(row["goals_against"]),
                "kickoff_at": row["kickoff_utc"],
                "team_side": row["team_side"],
            }
        )
    meetings.sort(key=lambda row: row["kickoff_at"])
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
        # Frozen input provenance for the decision ledger (S3): the exact F9
        # snapshot pair and F6 meeting rows the softmax consumed.
        "home_snapshot": home_snapshot,
        "away_snapshot": away_snapshot,
        "meetings": meetings,
    }
