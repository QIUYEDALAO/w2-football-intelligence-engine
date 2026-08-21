from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from w2.domain.canonical_serialization import HashDomain, canonical_sha256

PIT_HISTORY_MANIFEST_SCHEMA_VERSION = "w2.factor_model.pit_history_manifest.v1"
FINISHED_FIXTURE_STATUSES = frozenset({"FT", "AET", "PEN"})


class HistoricalFixtureRepository(Protocol):
    def fixture_payloads(
        self, *, provider_league_id: str | None = None
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class HistoricalFixtureBatch:
    fixture_payloads: tuple[dict[str, Any], ...]
    provider_calls: int = 0
    source_scope: str = "KICKOFF_BEFORE_AS_OF"


def _fixture_kickoff(item: dict[str, Any]) -> datetime | None:
    fixture = item.get("fixture")
    value = fixture.get("date") if isinstance(fixture, dict) else None
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def materialize_factor_history_from_persisted_raw(
    repository: HistoricalFixtureRepository,
    *,
    kickoff_from: datetime,
    kickoff_to: datetime,
    as_of: datetime,
    provider_league_id: str | None = None,
) -> HistoricalFixtureBatch:
    """Return the DB-only input batch; this contract has no Provider capability."""
    lower = kickoff_from.astimezone(UTC)
    upper = min(kickoff_to.astimezone(UTC), as_of.astimezone(UTC))
    rows = [
        item
        for item in repository.fixture_payloads(provider_league_id=provider_league_id)
        if (kickoff := _fixture_kickoff(item)) is not None and lower <= kickoff < upper
    ]
    return HistoricalFixtureBatch(fixture_payloads=tuple(rows))


def build_pit_history_manifest(
    rows: list[Mapping[str, Any]],
    *,
    target_fixture_id: str,
    target_kickoff: datetime,
    feature_as_of: datetime,
) -> dict[str, Any]:
    """Select fixture-level history known strictly before a target feature time."""
    target_time = _aware_utc(target_kickoff, "target_kickoff")
    as_of = _aware_utc(feature_as_of, "feature_as_of")
    if as_of > target_time:
        raise ValueError("PIT_HISTORY_FEATURE_ASOF_AFTER_TARGET_KICKOFF")

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    malformed_count = 0
    for row in rows:
        fixture_id = str(row.get("fixture_id") or "")
        if not fixture_id:
            malformed_count += 1
            continue
        grouped.setdefault(fixture_id, []).append(row)

    included: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    if malformed_count:
        excluded["MALFORMED_FIXTURE_IDENTITY"] = malformed_count

    for fixture_rows in grouped.values():
        reason, fixture = _pit_fixture(
            fixture_rows,
            target_fixture_id=str(target_fixture_id),
            target_kickoff=target_time,
            feature_as_of=as_of,
        )
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
        elif fixture is not None:
            included.append(fixture)

    included.sort(key=lambda item: (item["kickoff_utc"], item["fixture_id"]))
    body = {
        "schema_version": PIT_HISTORY_MANIFEST_SCHEMA_VERSION,
        "target_fixture_id": str(target_fixture_id),
        "target_kickoff": target_time,
        "feature_as_of": as_of,
        "source_fixture_count": len(included),
        "source_history_row_count": len(included) * 2,
        "source_fixtures": included,
        "excluded_fixture_counts": dict(sorted(excluded.items())),
    }
    return {
        **body,
        "manifest_sha256": canonical_sha256(
            {"identity_type": "FACTOR_MODEL_PIT_HISTORY_MANIFEST", **body},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
    }


def _pit_fixture(
    rows: list[Mapping[str, Any]],
    *,
    target_fixture_id: str,
    target_kickoff: datetime,
    feature_as_of: datetime,
) -> tuple[str | None, dict[str, Any] | None]:
    if str(rows[0].get("fixture_id")) == target_fixture_id:
        return "TARGET_FIXTURE", None
    if any(
        str(row.get("fixture_status") or "").upper() not in FINISHED_FIXTURE_STATUSES
        for row in rows
    ):
        return "UNFINISHED_FIXTURE", None

    try:
        kickoffs = {_aware_utc(row.get("kickoff_utc"), "kickoff_utc") for row in rows}
        captures = [_aware_utc(row.get("captured_at"), "captured_at") for row in rows]
    except (TypeError, ValueError):
        return "MALFORMED_FIXTURE_IDENTITY", None
    if len(kickoffs) != 1:
        return "IDENTITY_CONFLICT", None
    kickoff = next(iter(kickoffs))
    if kickoff >= target_kickoff:
        return "NOT_BEFORE_TARGET_KICKOFF", None
    if any(captured_at >= feature_as_of for captured_at in captures):
        return "RESULT_NOT_KNOWN_AT_ASOF", None

    by_side: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        side = str(row.get("team_side") or "").upper()
        if side not in {"HOME", "AWAY"}:
            return "MALFORMED_FIXTURE_IDENTITY", None
        previous = by_side.get(side)
        if previous is not None and _history_identity(previous) != _history_identity(row):
            return "IDENTITY_CONFLICT", None
        by_side[side] = row
    if set(by_side) != {"HOME", "AWAY"}:
        return "INCOMPLETE_FIXTURE_IDENTITY", None

    home = by_side["HOME"]
    away = by_side["AWAY"]
    if not _coherent_pair(home, away):
        return "IDENTITY_CONFLICT", None

    return None, {
        "fixture_id": str(home["fixture_id"]),
        "provider": str(home["provider"]),
        "provider_fixture_id": str(home["provider_fixture_id"]),
        "competition_id": str(home["competition_id"]),
        "season": str(home["season"]),
        "kickoff_utc": kickoff,
        "fixture_status": str(home["fixture_status"]).upper(),
        "home_w2_team_id": str(home["team_w2_id"]),
        "away_w2_team_id": str(away["team_w2_id"]),
        "home_goals": int(home["goals_for"]),
        "away_goals": int(away["goals_for"]),
        "result_identity_hash": str(home["result_identity_hash"]),
        "captured_at": max(captures),
        "source_history_hashes": sorted(
            {str(row["history_hash"]) for row in by_side.values()}
        ),
        "source_raw_hashes": sorted(
            {str(row["source_raw_hash"]) for row in by_side.values()}
        ),
    }


def _history_identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        row.get(field)
        for field in (
            "fixture_id",
            "provider",
            "provider_fixture_id",
            "competition_id",
            "season",
            "kickoff_utc",
            "fixture_status",
            "team_side",
            "team_w2_id",
            "opponent_w2_id",
            "goals_for",
            "goals_against",
            "result_identity_hash",
            "source_raw_hash",
            "captured_at",
            "history_hash",
        )
    )


def _coherent_pair(home: Mapping[str, Any], away: Mapping[str, Any]) -> bool:
    same_fields = (
        "fixture_id",
        "provider",
        "provider_fixture_id",
        "competition_id",
        "season",
        "kickoff_utc",
        "fixture_status",
        "result_identity_hash",
    )
    return (
        all(home.get(field) == away.get(field) for field in same_fields)
        and home.get("team_w2_id") == away.get("opponent_w2_id")
        and away.get("team_w2_id") == home.get("opponent_w2_id")
        and home.get("goals_for") == away.get("goals_against")
        and away.get("goals_for") == home.get("goals_against")
    )


def _aware_utc(value: Any, field: str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"PIT_HISTORY_{field.upper()}_NAIVE_OR_INVALID")
    return value.astimezone(UTC)
