from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.features.offline_materialization import verify_materialization_payload
from w2.infrastructure.persistence.future_refresh_models import (
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)


class MaterializationInjectionError(ValueError):
    pass


@dataclass(frozen=True, kw_only=True)
class MaterializationInjectionReport:
    mode: str
    materialization_id: str
    ready_fixture_ids: tuple[str, ...]
    match_rows_before: int
    snapshot_rows_before: int
    match_rows_inserted: int
    snapshot_rows_inserted: int
    match_rows_unchanged: int
    snapshot_rows_unchanged: int

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "ready_fixture_ids": list(self.ready_fixture_ids),
            "provider_calls": 0,
        }


def inject_staging_materialization(
    *,
    engine: Engine,
    payload: dict[str, Any],
    environment: str,
    apply: bool = False,
) -> MaterializationInjectionReport:
    if environment.casefold() != "staging":
        raise MaterializationInjectionError("STAGING_ENVIRONMENT_REQUIRED")
    if not verify_materialization_payload(payload):
        raise MaterializationInjectionError("MATERIALIZATION_INTEGRITY_INVALID")
    summary = _mapping(payload.get("summary"))
    if summary.get("provider_calls") != 0:
        raise MaterializationInjectionError("PROVIDER_MATERIALIZATION_FORBIDDEN")

    snapshots = [dict(row) for row in _rows(payload.get("team_xg_rolling_snapshots"))]
    fixture_teams: dict[str, set[str]] = {}
    for row in snapshots:
        fixture_teams.setdefault(str(row.get("as_of_fixture_id") or ""), set()).add(
            str(row.get("team_id") or "")
        )
    ready_fixture_ids = tuple(
        sorted(fixture_id for fixture_id, teams in fixture_teams.items() if len(teams) == 2)
    )
    ready_team_ids = {
        team_id for fixture_id in ready_fixture_ids for team_id in fixture_teams[fixture_id]
    }
    snapshots = [
        row for row in snapshots if str(row.get("as_of_fixture_id") or "") in ready_fixture_ids
    ]
    matches = [
        dict(row)
        for row in _rows(payload.get("team_xg_matches"))
        if str(row.get("team_id") or "") in ready_team_ids
    ]
    _validate_strict_as_of(matches=matches, snapshots=snapshots)

    with Session(engine) as session:
        match_rows_before = session.query(TeamXgMatchModel).count()
        snapshot_rows_before = session.query(TeamXgRollingSnapshotModel).count()
        match_inserted, match_unchanged = _stage_matches(session, matches)
        snapshot_inserted, snapshot_unchanged = _stage_snapshots(session, snapshots)
        if apply:
            session.commit()
        else:
            session.rollback()

    integrity = _mapping(payload.get("integrity"))
    return MaterializationInjectionReport(
        mode="APPLY" if apply else "DRY_RUN",
        materialization_id=str(integrity.get("materialization_id") or ""),
        ready_fixture_ids=ready_fixture_ids,
        match_rows_before=match_rows_before,
        snapshot_rows_before=snapshot_rows_before,
        match_rows_inserted=match_inserted,
        snapshot_rows_inserted=snapshot_inserted,
        match_rows_unchanged=match_unchanged,
        snapshot_rows_unchanged=snapshot_unchanged,
    )


def _stage_matches(session: Session, rows: list[dict[str, Any]]) -> tuple[int, int]:
    inserted = unchanged = 0
    for row in rows:
        existing = session.scalar(
            select(TeamXgMatchModel).where(
                TeamXgMatchModel.fixture_id == str(row["fixture_id"]),
                TeamXgMatchModel.team_id == str(row["team_id"]),
            )
        )
        expected = _match_values(row)
        if existing is not None:
            if _match_model_values(existing) != expected:
                raise MaterializationInjectionError(
                    f"TEAM_XG_MATCH_CONFLICT:{row['fixture_id']}:{row['team_id']}"
                )
            unchanged += 1
            continue
        session.add(TeamXgMatchModel(**expected))
        inserted += 1
    return inserted, unchanged


def _stage_snapshots(session: Session, rows: list[dict[str, Any]]) -> tuple[int, int]:
    inserted = unchanged = 0
    for row in rows:
        existing = session.scalar(
            select(TeamXgRollingSnapshotModel).where(
                TeamXgRollingSnapshotModel.team_id == str(row["team_id"]),
                TeamXgRollingSnapshotModel.as_of_fixture_id
                == str(row["as_of_fixture_id"]),
            )
        )
        expected = _snapshot_values(row)
        if existing is not None:
            if _snapshot_model_values(existing) != expected:
                raise MaterializationInjectionError(
                    f"TEAM_XG_SNAPSHOT_CONFLICT:{row['as_of_fixture_id']}:{row['team_id']}"
                )
            unchanged += 1
            continue
        session.add(TeamXgRollingSnapshotModel(**expected))
        inserted += 1
    return inserted, unchanged


def _validate_strict_as_of(
    *, matches: list[dict[str, Any]], snapshots: list[dict[str, Any]]
) -> None:
    by_team: dict[str, list[tuple[datetime, datetime]]] = {}
    for row in matches:
        by_team.setdefault(str(row.get("team_id") or ""), []).append(
            (_datetime(row.get("kickoff_at")), _datetime(row.get("captured_at")))
        )
    for snapshot in snapshots:
        as_of = _datetime(snapshot.get("as_of_time"))
        team_id = str(snapshot.get("team_id") or "")
        if any(
            kickoff >= as_of or captured >= as_of
            for kickoff, captured in by_team.get(team_id, [])
        ):
            raise MaterializationInjectionError(
                f"POST_KICKOFF_HISTORY_FORBIDDEN:{snapshot.get('as_of_fixture_id')}:{team_id}"
            )


def _match_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "fixture_id": str(row["fixture_id"]),
        "team_id": str(row["team_id"]),
        "opponent_team_id": str(row["opponent_team_id"]),
        "kickoff_at": _datetime(row["kickoff_at"]),
        "captured_at": _datetime(row["captured_at"]),
        "xg_for": float(row["xg_for"]),
        "xg_against": float(row["xg_against"]),
        "goals_for": int(row["goals_for"]),
        "goals_against": int(row["goals_against"]),
        "raw_payload_sha256": str(row["raw_payload_sha256"]),
        "source_system": str(row["source_system"]),
        "candidate": False,
        "formal_recommendation": False,
    }


def _snapshot_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_id": str(row["snapshot_id"]),
        "team_id": str(row["team_id"]),
        "as_of_fixture_id": str(row["as_of_fixture_id"]),
        "as_of_time": _datetime(row["as_of_time"]),
        "match_count": int(row["match_count"]),
        "rolling_xg_for": float(row["rolling_xg_for"]),
        "rolling_xg_against": float(row["rolling_xg_against"]),
        "rolling_goals_for": float(row["rolling_goals_for"]),
        "rolling_goals_against": float(row["rolling_goals_against"]),
        "regression_index": float(row["regression_index"]),
        "source_system": str(row["source_system"]),
        "candidate": False,
        "formal_recommendation": False,
    }


def _match_model_values(row: TeamXgMatchModel) -> dict[str, Any]:
    values = {key: getattr(row, key) for key in _match_values_from_model_keys()}
    values["kickoff_at"] = _datetime(values["kickoff_at"])
    values["captured_at"] = _datetime(values["captured_at"])
    return values


def _snapshot_model_values(row: TeamXgRollingSnapshotModel) -> dict[str, Any]:
    values = {key: getattr(row, key) for key in _snapshot_values_from_model_keys()}
    values["as_of_time"] = _datetime(values["as_of_time"])
    return values


def _match_values_from_model_keys() -> tuple[str, ...]:
    return (
        "id", "fixture_id", "team_id", "opponent_team_id", "kickoff_at", "captured_at",
        "xg_for", "xg_against", "goals_for", "goals_against", "raw_payload_sha256",
        "source_system", "candidate", "formal_recommendation",
    )


def _snapshot_values_from_model_keys() -> tuple[str, ...]:
    return (
        "snapshot_id", "team_id", "as_of_fixture_id", "as_of_time", "match_count",
        "rolling_xg_for", "rolling_xg_against", "rolling_goals_for",
        "rolling_goals_against", "regression_index", "source_system", "candidate",
        "formal_recommendation",
    )


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
