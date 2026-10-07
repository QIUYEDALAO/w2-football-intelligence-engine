from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from w2.domain.canonical_serialization import HashDomain, SerializerVersion
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
    # PIT provenance (AH/OU v3 S1): the latest statistics capture this snapshot
    # depends on. Distinct from ``as_of_time`` (the match-time the rolling window
    # is "as of"); None for BACKTEST_LOOKBACK rows that have no real first capture.
    first_captured_at: datetime | None = None
    # 双层 PIT（V7 包2/B）: the moment this target snapshot row was first
    # committed/readable, locked by the DB write clock (set by the writer, never
    # backfilled from component capture times). None = BACKTEST_LOOKBACK.
    first_committed_at: datetime | None = None
    pit_proven: bool = False
    decision_at: datetime | None = None
    source_matches: tuple[dict[str, Any], ...] = ()

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
    xg_by_team = statistics_xg_by_team(statistics_payload)
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
    captured_before_cutoff: bool = True,
    now: datetime | None = None,
) -> TeamXgRollingSnapshot | None:
    """Build a target-fixture snapshot without making it visible before its inputs.

    ``as_of_time`` is the target cutoff used only to select strictly earlier
    components.  The persisted snapshot timestamp is the latest time at which
    every selected component was knowable.

    ``captured_before_cutoff=False`` is the 回测口径: historical backfill rows carry a
    ``captured_at`` of the (late) backfill run rather than the match time, so eligibility
    is gated only by ``kickoff_at < cutoff`` and ``available_at`` uses kickoff only.  The
    default keeps the online PIT semantics unchanged.
    """
    if window < 1 or min_matches < 1:
        raise ValueError("window and min_matches must be positive")
    cutoff = as_of_time.astimezone(UTC)
    eligible = [
        row
        for row in matches
        if row.team_id == team_id
        and row.kickoff_at.astimezone(UTC) < cutoff
        and (captured_before_cutoff is False or row.captured_at.astimezone(UTC) < cutoff)
    ]
    eligible.sort(key=lambda row: row.kickoff_at)
    selected = eligible[-window:]
    if len(selected) < min_matches:
        return None
    if captured_before_cutoff:
        available_at = max(
            max(row.kickoff_at.astimezone(UTC), row.captured_at.astimezone(UTC))
            for row in selected
        )
    else:
        available_at = max(row.kickoff_at.astimezone(UTC) for row in selected)
    count = len(selected)
    xg_for = sum(row.xg_for for row in selected) / count
    xg_against = sum(row.xg_against for row in selected) / count
    goals_for = sum(row.goals_for for row in selected) / count
    goals_against = sum(row.goals_against for row in selected) / count
    regression_index = (goals_for - xg_for) - (goals_against - xg_against)
    first_captured_at = (
        max(row.captured_at.astimezone(UTC) for row in selected)
        if captured_before_cutoff
        else None
    )
    # 双层 PIT（V7 包2/B）: the target snapshot's own first-commit instant is the
    # DB write clock now, never backfilled from the component capture times. A
    # BACKTEST_LOOKBACK materialisation has no PIT commit time and is not proven.
    first_committed_at = (now or datetime.now(UTC)) if captured_before_cutoff else None
    # pit_proven 语义（V7 B 字面）: 快照在决策点前已物化可读（first_committed_at
    # <= cutoff）且组件在 cutoff 前捕获。晚物化（now > as_of_time）→ false，与
    # first_committed_at=None 一致。
    pit_proven = (
        captured_before_cutoff
        and first_committed_at is not None
        and first_committed_at <= cutoff
    )
    return TeamXgRollingSnapshot(
        snapshot_id=f"{team_id}:{as_of_fixture_id}",
        team_id=team_id,
        as_of_fixture_id=as_of_fixture_id,
        as_of_time=available_at,
        match_count=count,
        rolling_xg_for=round(xg_for, 4),
        rolling_xg_against=round(xg_against, 4),
        rolling_goals_for=round(goals_for, 4),
        rolling_goals_against=round(goals_against, 4),
        regression_index=round(regression_index, 4),
        first_captured_at=first_captured_at,
        first_committed_at=first_committed_at,
        pit_proven=pit_proven,
        decision_at=cutoff if captured_before_cutoff else None,
        source_matches=tuple({
            "id": row.id, "fixture_id": row.fixture_id, "team_id": row.team_id,
            "opponent_team_id": row.opponent_team_id,
            "kickoff_at": row.kickoff_at.isoformat(), "captured_at": row.captured_at.isoformat(),
            "raw_payload_sha256": row.raw_payload_sha256,
            "raw_hash_domain": HashDomain.FUTURE_REFRESH_RAW_PAYLOAD.value,
            "raw_serializer_version": SerializerVersion.LEGACY_V1.value,
            "xg_for": row.xg_for, "xg_against": row.xg_against,
            "goals_for": row.goals_for, "goals_against": row.goals_against,
        } for row in selected),
    )


def source_matches_signature(matches: Any) -> frozenset[str]:
    """Canonical id-set of a snapshot's source_matches.

    用于幂等比较与「source_matches 覆盖边界是否推进」判定：只比较每场比赛的
    唯一 id（``fixture_id:team_id``）。新增/移除比赛即视为覆盖边界变化；
    xg 数值漂移（append-only 不可变事实）不在本签名内。
    """
    if not matches:
        return frozenset()
    return frozenset(
        str(item.get("id") or item.get("fixture_id") or "")
        for item in matches
        if isinstance(item, dict)
    )


def statistics_xg_by_team(payload: dict[str, Any]) -> dict[str, float]:
    """Return only Provider teams whose expected_goals value is numeric."""
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
