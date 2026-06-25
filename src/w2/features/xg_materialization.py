from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from w2.features.live_factors import TeamXgSnapshot

FINISHED_STATUS = {"FT", "AET", "PEN"}


@dataclass(frozen=True, kw_only=True)
class TeamXgMatch:
    fixture_id: str
    team_id: str
    opponent_team_id: str
    kickoff_at: datetime
    captured_at: datetime
    xg_for: float
    xg_against: float
    goals_for: int
    goals_against: int
    raw_payload_sha256: str
    source_system: str = "api_football_statistics"
    candidate: bool = False
    formal_recommendation: bool = False

    @property
    def id(self) -> str:
        return f"{self.fixture_id}:{self.team_id}"


@dataclass(frozen=True, kw_only=True)
class TeamXgRollingSnapshot:
    snapshot_id: str
    team_id: str
    as_of_fixture_id: str
    as_of_time: datetime
    match_count: int
    rolling_xg_for: float
    rolling_xg_against: float
    rolling_goals_for: float
    rolling_goals_against: float
    regression_index: float
    source_system: str = "team_xg_match"
    candidate: bool = False
    formal_recommendation: bool = False

    def as_feature_snapshot(self) -> TeamXgSnapshot:
        return TeamXgSnapshot(
            team_id=self.team_id,
            observed_at=self.as_of_time,
            xg_for=self.rolling_xg_for,
            xg_against=self.rolling_xg_against,
            goals_for=round(self.rolling_goals_for),
            goals_against=round(self.rolling_goals_against),
        )


def parse_team_xg_matches(
    *,
    fixture_payload: dict[str, Any],
    statistics_payload: dict[str, Any],
    captured_at: datetime,
    raw_payload_sha256: str,
) -> list[TeamXgMatch]:
    fixture = fixture_payload.get("fixture", {}) if isinstance(fixture_payload, dict) else {}
    status = fixture.get("status", {}) if isinstance(fixture, dict) else {}
    if not isinstance(status, dict) or str(status.get("short")) not in FINISHED_STATUS:
        return []
    fixture_id = str(fixture.get("id") or "")
    kickoff = _parse_utc(fixture.get("date"))
    teams = fixture_payload.get("teams", {}) if isinstance(fixture_payload, dict) else {}
    goals = fixture_payload.get("goals", {}) if isinstance(fixture_payload, dict) else {}
    home = (
        teams.get("home", {})
        if isinstance(teams, dict) and isinstance(teams.get("home"), dict)
        else {}
    )
    away = (
        teams.get("away", {})
        if isinstance(teams, dict) and isinstance(teams.get("away"), dict)
        else {}
    )
    home_id = str(home.get("id") or "")
    away_id = str(away.get("id") or "")
    home_goals = _int_or_zero(goals.get("home") if isinstance(goals, dict) else None)
    away_goals = _int_or_zero(goals.get("away") if isinstance(goals, dict) else None)
    if not fixture_id or kickoff is None or not home_id or not away_id:
        return []
    xg_by_team = _xg_by_team(statistics_payload)
    if home_id not in xg_by_team or away_id not in xg_by_team:
        return []
    return [
        TeamXgMatch(
            fixture_id=fixture_id,
            team_id=home_id,
            opponent_team_id=away_id,
            kickoff_at=kickoff,
            captured_at=captured_at.astimezone(UTC),
            xg_for=xg_by_team[home_id],
            xg_against=xg_by_team[away_id],
            goals_for=home_goals,
            goals_against=away_goals,
            raw_payload_sha256=raw_payload_sha256,
        ),
        TeamXgMatch(
            fixture_id=fixture_id,
            team_id=away_id,
            opponent_team_id=home_id,
            kickoff_at=kickoff,
            captured_at=captured_at.astimezone(UTC),
            xg_for=xg_by_team[away_id],
            xg_against=xg_by_team[home_id],
            goals_for=away_goals,
            goals_against=home_goals,
            raw_payload_sha256=raw_payload_sha256,
        ),
    ]


def materialize_rolling_xg(
    *,
    team_id: str,
    as_of_fixture_id: str,
    as_of_time: datetime,
    matches: list[TeamXgMatch],
    window: int = 5,
    min_matches: int = 3,
) -> TeamXgRollingSnapshot | None:
    cutoff = as_of_time.astimezone(UTC)
    eligible = [
        row
        for row in matches
        if row.team_id == team_id and row.kickoff_at.astimezone(UTC) < cutoff
    ]
    eligible.sort(key=lambda row: row.kickoff_at)
    selected = eligible[-window:]
    if len(selected) < min_matches:
        return None
    count = len(selected)
    xg_for = sum(row.xg_for for row in selected) / count
    xg_against = sum(row.xg_against for row in selected) / count
    goals_for = sum(row.goals_for for row in selected) / count
    goals_against = sum(row.goals_against for row in selected) / count
    regression_index = (goals_for - xg_for) - (goals_against - xg_against)
    return TeamXgRollingSnapshot(
        snapshot_id=f"{team_id}:{as_of_fixture_id}",
        team_id=team_id,
        as_of_fixture_id=as_of_fixture_id,
        as_of_time=cutoff,
        match_count=count,
        rolling_xg_for=round(xg_for, 4),
        rolling_xg_against=round(xg_against, 4),
        rolling_goals_for=round(goals_for, 4),
        rolling_goals_against=round(goals_against, 4),
        regression_index=round(regression_index, 4),
    )


def _xg_by_team(payload: dict[str, Any]) -> dict[str, float]:
    response = payload.get("response")
    if not isinstance(response, list):
        return {}
    values: dict[str, float] = {}
    for item in response:
        if not isinstance(item, dict):
            continue
        team = item.get("team")
        team_id = str(team.get("id") if isinstance(team, dict) else "")
        if not team_id:
            continue
        value = _stat_value(item.get("statistics"), "expected_goals")
        if value is None:
            value = _stat_value(item.get("statistics"), "Expected Goals")
        if value is not None:
            values[team_id] = value
    return values


def _stat_value(statistics: Any, stat_type: str) -> float | None:
    if not isinstance(statistics, list):
        return None
    for item in statistics:
        if not isinstance(item, dict) or item.get("type") != stat_type:
            continue
        value = item.get("value")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
