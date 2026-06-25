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


@dataclass(frozen=True, kw_only=True)
class AvailabilitySnapshot:
    team_id: str
    observed_at: datetime
    goalkeeper_absent: bool = False
    core_absences: int = 0
    suspended_players: int = 0
    rotation_risk: float = 0.0


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


def parse_api_football_availability(
    *,
    lineups_payload: dict[str, Any],
    injuries_payload: dict[str, Any],
    captured_at: datetime,
) -> list[AvailabilitySnapshot]:
    risk_by_team: dict[str, dict[str, float | int | bool]] = {}
    for item in _response_items(injuries_payload):
        team_id = str((item.get("team") or {}).get("id") or "")
        if not team_id:
            continue
        player = item.get("player") or {}
        reason = str(item.get("reason") or item.get("type") or "").lower()
        role = str(player.get("type") or player.get("position") or "").lower()
        current = risk_by_team.setdefault(
            team_id,
            {
                "goalkeeper_absent": False,
                "core_absences": 0,
                "suspended_players": 0,
                "rotation_risk": 0.0,
            },
        )
        current["core_absences"] = int(current["core_absences"]) + 1
        if "goalkeeper" in role or role == "g":
            current["goalkeeper_absent"] = True
        if "suspend" in reason:
            current["suspended_players"] = int(current["suspended_players"]) + 1
    for item in _response_items(lineups_payload):
        team_id = str((item.get("team") or {}).get("id") or "")
        if not team_id:
            continue
        substitutes = item.get("substitutes")
        start_xi = item.get("startXI") or item.get("start_xi")
        current = risk_by_team.setdefault(
            team_id,
            {
                "goalkeeper_absent": False,
                "core_absences": 0,
                "suspended_players": 0,
                "rotation_risk": 0.0,
            },
        )
        if isinstance(substitutes, list) and isinstance(start_xi, list):
            current["rotation_risk"] = min(len(substitutes) / max(len(start_xi), 1), 1.0)
    return [
        AvailabilitySnapshot(
            team_id=team_id,
            observed_at=captured_at,
            goalkeeper_absent=bool(values["goalkeeper_absent"]),
            core_absences=int(values["core_absences"]),
            suspended_players=int(values["suspended_players"]),
            rotation_risk=float(values["rotation_risk"]),
        )
        for team_id, values in sorted(risk_by_team.items())
    ]


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
    )


def lineup_injury_factor(
    *,
    context: FeatureContext,
    profile: CoverageProfile,
    home_availability: list[AvailabilitySnapshot],
    away_availability: list[AvailabilitySnapshot],
    weight: float = 0.10,
) -> FeatureContribution:
    blocked = coverage_or_unavailable(
        profile=profile,
        key="lineups_injuries",
        feature_id="F10_LINEUPS_INJURIES",
        label="首发/伤停",
        weight=weight,
    )
    if blocked is not None:
        return blocked
    home = latest_as_of(home_availability, context.as_of)
    away = latest_as_of(away_availability, context.as_of)
    if home is None or away is None:
        return FeatureContribution(
            feature_id="F10_LINEUPS_INJURIES",
            label="首发/伤停",
            status=FeatureStatus.UNAVAILABLE,
            score=None,
            weight=weight,
            reason="LINEUPS_INJURIES_UNAVAILABLE",
            coverage_key="lineups_injuries",
        )
    home_risk = _availability_risk(home)
    away_risk = _availability_risk(away)
    score = max(min(away_risk - home_risk, 1.0), -1.0)
    return FeatureContribution(
        feature_id="F10_LINEUPS_INJURIES",
        label="首发/伤停",
        status=FeatureStatus.READY,
        score=score,
        weight=weight,
        side=TeamSide.HOME if score > 0 else TeamSide.AWAY if score < 0 else TeamSide.NEUTRAL,
        reason="AS_OF_AVAILABILITY_RISK_DIFF",
        coverage_key="lineups_injuries",
        observed_at=max(home.observed_at, away.observed_at),
        inputs={"home_availability_risk": home_risk, "away_availability_risk": away_risk},
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


def _response_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response")
    if not isinstance(response, list):
        return []
    return [item for item in response if isinstance(item, dict)]


def _availability_risk(row: AvailabilitySnapshot) -> float:
    return min(
        (0.35 if row.goalkeeper_absent else 0.0)
        + 0.08 * row.core_absences
        + 0.07 * row.suspended_players
        + 0.25 * row.rotation_risk,
        1.0,
    )
