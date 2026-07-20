from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from w2.matchday.intake_v2 import POLICY_VERSION as MATCHDAY_INTAKE_POLICY_VERSION

AUTHORIZED_MATCHDAY_ENDPOINTS = frozenset({"status", "fixtures", "odds", "lineups"})
MATCHDAY_SCHEDULE_AUTHORITY = MATCHDAY_INTAKE_POLICY_VERSION
DEFAULT_TICK_OFFSETS: tuple[tuple[str, int], ...] = (
    ("T_24H", 24 * 60 * 60),
    ("T_3H", 3 * 60 * 60),
    ("T_90M", 90 * 60),
    ("T_30M", 30 * 60),
    ("T_15M", 15 * 60),
)
PROVIDER_REFRESH_BUDGET_TOO_HIGH = "PROVIDER_REFRESH_BUDGET_TOO_HIGH"


@dataclass(frozen=True)
class MatchdayRefreshPolicy:
    tick_offsets: tuple[tuple[str, int], ...] = DEFAULT_TICK_OFFSETS
    allowed_endpoints: tuple[str, ...] = ("status", "fixtures", "odds", "lineups")
    tick_hard_cap: int = 30
    min_interval_seconds: int = 900
    dedupe_ttl_seconds: int = 1800

    @property
    def effective_min_interval_seconds(self) -> int:
        return max(int(self.min_interval_seconds), 900)


@dataclass(frozen=True)
class MatchdayRefreshTick:
    label: str
    offset_seconds_before_kickoff: int
    scheduled_at: datetime
    fixture_ids: tuple[str, ...]
    allowed_endpoints: tuple[str, ...]
    skipped_endpoints: tuple[str, ...]
    projected_calls: int
    projected_calls_by_endpoint: dict[str, int]
    hard_cap: int
    task_key: str
    status: str
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "offset_seconds_before_kickoff": self.offset_seconds_before_kickoff,
            "scheduled_at": _iso(self.scheduled_at),
            "fixture_ids": list(self.fixture_ids),
            "allowed_endpoints": list(self.allowed_endpoints),
            "skipped_endpoints": list(self.skipped_endpoints),
            "projected_calls": self.projected_calls,
            "projected_calls_by_endpoint": dict(self.projected_calls_by_endpoint),
            "hard_cap": self.hard_cap,
            "task_key": self.task_key,
            "status": self.status,
            "blockers": list(self.blockers),
            "provider_calls": 0 if self.status == "BLOCKED" else None,
        }


def build_matchday_refresh_plan(
    fixtures: Iterable[Mapping[str, Any]],
    *,
    as_of: datetime,
    policy: MatchdayRefreshPolicy,
) -> list[MatchdayRefreshTick]:
    normalized = _normal_fixture_rows(fixtures)
    current = _normalize_utc(as_of)
    endpoint_set, skipped = _authorized_endpoint_lists(policy.allowed_endpoints)
    ticks: list[MatchdayRefreshTick] = []
    for label, offset in policy.tick_offsets:
        due_groups: dict[datetime, list[str]] = {}
        for fixture_id, kickoff in normalized:
            scheduled_at = kickoff - timedelta(seconds=offset)
            if scheduled_at < current:
                continue
            due_groups.setdefault(scheduled_at, []).append(fixture_id)
        for scheduled_at, fixture_ids in sorted(due_groups.items()):
            ordered_fixture_ids = tuple(sorted(fixture_ids))
            projected_by_endpoint = estimate_refresh_tick_calls(
                ordered_fixture_ids,
                endpoint_set,
            )
            projected_calls = sum(projected_by_endpoint.values())
            blockers = tuple(f"ENDPOINT_NOT_AUTHORIZED:{endpoint}" for endpoint in skipped)
            status = "PLANNED"
            if not endpoint_set:
                status = "BLOCKED"
                blockers = (*blockers, "NO_AUTHORIZED_ENDPOINTS")
            elif projected_calls > policy.tick_hard_cap:
                status = "BLOCKED"
                blockers = (*blockers, PROVIDER_REFRESH_BUDGET_TOO_HIGH)
            ticks.append(
                MatchdayRefreshTick(
                    label=label,
                    offset_seconds_before_kickoff=offset,
                    scheduled_at=scheduled_at,
                    fixture_ids=ordered_fixture_ids,
                    allowed_endpoints=endpoint_set,
                    skipped_endpoints=skipped,
                    projected_calls=projected_calls,
                    projected_calls_by_endpoint=projected_by_endpoint,
                    hard_cap=policy.tick_hard_cap,
                    task_key=matchday_refresh_task_key(
                        football_day=_football_day(scheduled_at),
                        label=label,
                        fixture_ids=ordered_fixture_ids,
                        endpoints=endpoint_set,
                    ),
                    status=status,
                    blockers=blockers,
                )
            )
    return ticks


def estimate_refresh_tick_calls(
    fixtures: Iterable[str] | Iterable[Mapping[str, Any]],
    endpoints: Iterable[str],
) -> dict[str, int]:
    fixture_ids = tuple(_fixture_id(item) for item in fixtures)
    fixture_count = len(tuple(item for item in fixture_ids if item))
    authorized, _skipped = _authorized_endpoint_lists(endpoints)
    calls = {
        "status": 1 if "status" in authorized and fixture_count > 0 else 0,
        "fixtures": 1 if "fixtures" in authorized and fixture_count > 0 else 0,
        "odds": fixture_count if "odds" in authorized else 0,
        "lineups": fixture_count if "lineups" in authorized else 0,
    }
    return {endpoint: count for endpoint, count in calls.items() if count}


def matchday_refresh_task_key(
    *,
    football_day: date,
    label: str,
    fixture_ids: Iterable[str],
    endpoints: Iterable[str],
) -> str:
    identity = "|".join(
        [
            football_day.isoformat(),
            label,
            ",".join(sorted(str(item) for item in fixture_ids)),
            ",".join(sorted(str(item) for item in endpoints)),
        ]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"matchday-refresh:{football_day.isoformat()}:{label}:{digest}"


def _normal_fixture_rows(fixtures: Iterable[Mapping[str, Any]]) -> list[tuple[str, datetime]]:
    rows: list[tuple[str, datetime]] = []
    for item in fixtures:
        fixture_id = _fixture_id(item)
        kickoff = _kickoff_utc(item)
        if fixture_id and kickoff is not None:
            rows.append((fixture_id, kickoff))
    return rows


def _authorized_endpoint_lists(endpoints: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    seen: list[str] = []
    skipped: list[str] = []
    for endpoint in endpoints:
        normalized = str(endpoint).strip().lower()
        if not normalized:
            continue
        if normalized in AUTHORIZED_MATCHDAY_ENDPOINTS:
            if normalized not in seen:
                seen.append(normalized)
        elif normalized not in skipped:
            skipped.append(normalized)
    return tuple(seen), tuple(skipped)


def _fixture_id(item: str | Mapping[str, Any]) -> str:
    if isinstance(item, str):
        return item
    fixture = item.get("fixture")
    if isinstance(fixture, Mapping):
        return str(fixture.get("id") or fixture.get("fixture_id") or item.get("fixture_id") or "")
    return str(item.get("fixture_id") or item.get("id") or "")


def _kickoff_utc(item: Mapping[str, Any]) -> datetime | None:
    fixture = item.get("fixture")
    if isinstance(fixture, Mapping):
        value = fixture.get("date") or fixture.get("kickoff_utc")
    else:
        value = item.get("kickoff_utc") or item.get("date")
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _normalize_utc(parsed)


def _normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _football_day(value: datetime) -> date:
    return _normalize_utc(value).date()


def _iso(value: datetime) -> str:
    return _normalize_utc(value).isoformat().replace("+00:00", "Z")
