from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from w2.competitions.registry import CoverageProfile
from w2.features.asof import latest_as_of
from w2.features.framework import (
    FeatureContext,
    FeatureContribution,
    FeatureStatus,
    TeamSide,
    coverage_or_unavailable,
)


@dataclass(frozen=True, kw_only=True)
class TeamXgSnapshot:
    team_id: str
    observed_at: datetime
    xg_for: float
    xg_against: float
    goals_for: int
    goals_against: int


def parse_api_football_xg(
    *,
    payload: dict[str, Any],
    captured_at: datetime,
) -> list[TeamXgSnapshot]:
    rows: list[TeamXgSnapshot] = []
    response = payload.get("response")
    if not isinstance(response, list):
        return rows
    for item in response:
        if not isinstance(item, dict):
            continue
        team_id = str((item.get("team") or {}).get("id") or "")
        if not team_id:
            continue
        xg_value = _stat_value(item.get("statistics"), "expected_goals")
        if xg_value is None:
            xg_value = _stat_value(item.get("statistics"), "Expected Goals")
        if xg_value is None:
            continue
        rows.append(
            TeamXgSnapshot(
                team_id=team_id,
                observed_at=captured_at,
                xg_for=xg_value,
                xg_against=0.0,
                goals_for=0,
                goals_against=0,
            )
        )
    if len(rows) == 2:
        first, second = rows
        rows = [
            TeamXgSnapshot(
                team_id=first.team_id,
                observed_at=first.observed_at,
                xg_for=first.xg_for,
                xg_against=second.xg_for,
                goals_for=0,
                goals_against=0,
            ),
            TeamXgSnapshot(
                team_id=second.team_id,
                observed_at=second.observed_at,
                xg_for=second.xg_for,
                xg_against=first.xg_for,
                goals_for=0,
                goals_against=0,
            ),
        ]
    return rows


def true_xg_factor(
    *,
    context: FeatureContext,
    profile: CoverageProfile,
    home_xg: list[TeamXgSnapshot],
    away_xg: list[TeamXgSnapshot],
    weight: float = 0.10,
) -> FeatureContribution:
    blocked = coverage_or_unavailable(
        profile=profile,
        key="xg",
        feature_id="F9_TRUE_XG",
        label="真实 xG",
        weight=weight,
    )
    if blocked is not None:
        return blocked
    home = latest_as_of(home_xg, context.as_of)
    away = latest_as_of(away_xg, context.as_of)
    if home is None or away is None:
        return FeatureContribution(
            feature_id="F9_TRUE_XG",
            label="真实 xG",
            status=FeatureStatus.UNAVAILABLE,
            score=None,
            weight=weight,
            reason="XG_DATA_UNAVAILABLE",
            coverage_key="xg",
        )
    home_net = home.xg_for - home.xg_against
    away_net = away.xg_for - away.xg_against
    score = max(min((home_net - away_net) / 2.0, 1.0), -1.0)
    return FeatureContribution(
        feature_id="F9_TRUE_XG",
        label="真实 xG",
        status=FeatureStatus.READY,
        score=score,
        weight=weight,
        side=TeamSide.HOME if score > 0 else TeamSide.AWAY if score < 0 else TeamSide.NEUTRAL,
        reason="AS_OF_ROLLING_XG_DIFF",
        coverage_key="xg",
        observed_at=max(home.observed_at, away.observed_at),
        inputs={"home_xg_net": home_net, "away_xg_net": away_net},
        source="api_football_statistics",
        source_group="xg",
        is_independent_signal=True,
        collection_status="READY",
    )


def _stat_value(statistics: Any, stat_type: str) -> float | None:
    if not isinstance(statistics, list):
        return None
    for item in statistics:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").lower() != stat_type.lower():
            continue
        value = item.get("value")
        try:
            return float(str(value).replace("%", ""))
        except (TypeError, ValueError):
            return None
    return None
