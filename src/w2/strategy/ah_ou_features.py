"""Feature construction for the AH/OU F9+F6 softmax models.

Pure functions: given an F9 snapshot pair and the F6 meeting history, build the
14/22-dim feature dict consumed by ``ah_ou_softmax``. This mirrors the frozen
backtest feature construction (``build_enriched_f9_f6_matrix.py`` /
``build_ou_research_matrix.py``); do not change the arithmetic without a new
model version and an unseen forward window.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any


def clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _aware(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _days_between(kickoff: datetime, meeting_kickoff: Any) -> float:
    return (_aware(kickoff) - _aware(meeting_kickoff)).total_seconds() / 86400


def build_features(
    *,
    home_snapshot: Mapping[str, Any],
    away_snapshot: Mapping[str, Any],
    meetings: Sequence[Mapping[str, Any]],
    kickoff: datetime,
) -> dict[str, Any]:
    """Build the full AH+OU feature dict.

    ``meetings`` are the canonical-home-vs-canonical-away FT meetings before
    ``kickoff``, ascending by kickoff time, each carrying ``goals_for`` /
    ``goals_against`` / ``kickoff_at`` / ``team_side``. Raises on empty history:
    both models require at least one pre-kickoff meeting.
    """
    if not meetings:
        raise ValueError("AH_OU_FEATURES_EMPTY_H2H")

    h_xgf = float(home_snapshot["rolling_xg_for"])
    h_xga = float(home_snapshot["rolling_xg_against"])
    a_xgf = float(away_snapshot["rolling_xg_for"])
    a_xga = float(away_snapshot["rolling_xg_against"])

    diffs = [int(m["goals_for"]) - int(m["goals_against"]) for m in meetings]
    totals = [int(m["goals_for"]) + int(m["goals_against"]) for m in meetings]
    n = len(meetings)
    recent = meetings[-3:]
    venue = [m for m in meetings if m.get("team_side") == "HOME"]
    last = meetings[-1]

    def decay(values: Sequence[int], half_life_days: int) -> float:
        weights = [
            2 ** (-_days_between(kickoff, m["kickoff_at"]) / half_life_days) for m in meetings
        ]
        return sum(value * weight for value, weight in zip(values, weights, strict=False)) / sum(
            weights
        )

    f6_raw = clip(sum(diffs) / n / 2)
    last_age = _days_between(kickoff, last["kickoff_at"])

    return {
        # F9 (xg family)
        "f9_score": clip(((h_xgf - h_xga) - (a_xgf - a_xga)) / 2),
        "f9_home_xgf": h_xgf,
        "f9_home_xga": h_xga,
        "f9_away_xgf": a_xgf,
        "f9_away_xga": a_xga,
        # F6 goal-difference (h2h family)
        "f6_n": n,
        "f6_score": f6_raw,
        "f6_shrunk": f6_raw * n / (n + 5),
        "f6_recent3": clip(
            sum(int(m["goals_for"]) - int(m["goals_against"]) for m in recent) / min(3, n) / 2
        ),
        "f6_decay365": clip(decay(diffs, 365) / 2),
        "f6_decay730": clip(decay(diffs, 730) / 2),
        "f6_same_venue": (
            clip(sum(int(m["goals_for"]) - int(m["goals_against"]) for m in venue) / len(venue) / 2)
            if venue
            else ""
        ),
        "f6_same_venue_n": len(venue),
        "f6_last_diff": clip((int(last["goals_for"]) - int(last["goals_against"])) / 2),
        "f6_last_age_days": last_age,
        # F6 total-goals (OU only)
        "f6_total_mean": sum(totals) / n,
        "f6_total_recent3": sum(int(m["goals_for"]) + int(m["goals_against"]) for m in recent)
        / min(3, n),
        "f6_total_decay365": decay(totals, 365),
        "f6_total_decay730": decay(totals, 730),
        "f6_total_same_venue": (
            sum(int(m["goals_for"]) + int(m["goals_against"]) for m in venue) / len(venue)
            if venue
            else ""
        ),
        "f6_total_same_venue_n": len(venue),
        "f6_total_last": totals[-1],
        "f6_total_last_age_days": last_age,
    }
