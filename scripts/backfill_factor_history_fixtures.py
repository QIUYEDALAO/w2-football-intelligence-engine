#!/usr/bin/env python3
"""Bounded API-Football fixture-manifest backfill for Factor Model V2 Gate 1."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

import w2.providers.api_football as api_football_module
from w2.competitions.registry import CompetitionRegistry
from w2.domain.canonical_serialization import HashDomain
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
)
from w2.ingestion.future_refresh import iso, sha256_payload, write_json_atomic
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.matchday.intake_v2 import REQUIRED_MATCHDAY_COMPETITIONS
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse
from w2.providers.quota import parse_api_football_quota, provider_daily_hard_cap_decision

BACKFILL_SEASONS = ("2022", "2023")
BACKFILL_LOGICAL_REQUEST_CAP = len(REQUIRED_MATCHDAY_COMPETITIONS) * len(BACKFILL_SEASONS)
BLOCKED_UTC_DATES = frozenset({date(2026, 8, 22), date(2026, 8, 23)})
QUIET_LOOKBACK = timedelta(minutes=15)
QUIET_HORIZON = timedelta(minutes=60)
ACTIVE_PLAN_STATUSES = ("PLANNED", "DUE")


class HistoricalFixtureBackfillError(RuntimeError):
    pass


class BackfillRepository(Protocol):
    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        pass

    def raw_payload_exists(self, *, sha256: str, endpoint: str) -> bool:
        pass

    def save_raw_payload(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: dict[str, Any],
    ) -> str:
        pass

    def request_count_since(self, since: datetime) -> int:
        pass


class FixtureClient(Protocol):
    def request_live(
        self, endpoint: str, params: dict[str, str]
    ) -> LiveApiFootballResponse:
        pass


@dataclass(frozen=True, kw_only=True)
class BackfillScope:
    competition_id: str
    provider_league_id: str
    season: str


@dataclass(frozen=True, kw_only=True)
class BackfillConfig:
    request_timeout_seconds: int = 45
    max_attempts: int = 2
    retry_backoff_seconds: int = 2
    quota_reserve: int = 1500
    daily_hard_cap: int = 7500
    daily_reserve: int = 1500
    requests_per_minute: int = 60

    @property
    def worst_case_logical_request_seconds(self) -> int:
        return (
            self.request_timeout_seconds * self.max_attempts
            + self.retry_backoff_seconds * (self.max_attempts - 1)
        )

    @classmethod
    def from_env(cls) -> BackfillConfig:
        return cls(
            request_timeout_seconds=_env_int(
                "W2_PROVIDER_REQUEST_TIMEOUT_SECONDS", default=45
            ),
            max_attempts=_env_int("W2_PROVIDER_TIMEOUT_MAX_ATTEMPTS", default=2),
            retry_backoff_seconds=_env_int(
                "W2_PROVIDER_TIMEOUT_RETRY_BACKOFF_SECONDS", default=2
            ),
            quota_reserve=_env_int("W2_API_MINIMUM_RESERVE", default=1500),
            daily_hard_cap=_env_int("W2_PROVIDER_DAILY_HARD_CAP", default=7500),
            daily_reserve=_env_int("W2_PROVIDER_DAILY_RESERVE", default=1500),
            requests_per_minute=_env_int(
                "W2_FACTOR_HISTORY_BACKFILL_REQUESTS_PER_MINUTE", default=60
            ),
        )


def _env_int(name: str, *, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise HistoricalFixtureBackfillError(f"INVALID_INTEGER_ENV:{name}") from exc


def _validate_config(config: BackfillConfig) -> None:
    if not 45 <= config.request_timeout_seconds <= 60:
        raise HistoricalFixtureBackfillError("BACKFILL_TIMEOUT_MUST_BE_45_TO_60_SECONDS")
    if config.max_attempts != 2:
        raise HistoricalFixtureBackfillError("BACKFILL_MAX_ATTEMPTS_MUST_EQUAL_2")
    if not 0 <= config.retry_backoff_seconds <= 5:
        raise HistoricalFixtureBackfillError("BACKFILL_RETRY_BACKOFF_OUT_OF_RANGE")
    if config.quota_reserve < 1500 or config.daily_reserve < 1500:
        raise HistoricalFixtureBackfillError("BACKFILL_QUOTA_RESERVE_BELOW_1500")
    if config.daily_hard_cap <= config.daily_reserve:
        raise HistoricalFixtureBackfillError("BACKFILL_DAILY_CAP_INVALID")
    if not 1 <= config.requests_per_minute <= 60:
        raise HistoricalFixtureBackfillError("BACKFILL_RATE_LIMIT_INVALID")
    if config.worst_case_logical_request_seconds > 125:
        raise HistoricalFixtureBackfillError("BACKFILL_RETRY_WALL_TIME_EXCESSIVE")


def exact_backfill_scopes(registry: CompetitionRegistry) -> tuple[BackfillScope, ...]:
    entries = registry.entries()
    if set(REQUIRED_MATCHDAY_COMPETITIONS) - set(entries):
        raise HistoricalFixtureBackfillError("BACKFILL_EXACT13_REGISTRY_INCOMPLETE")
    scopes: list[BackfillScope] = []
    provider_ids: set[str] = set()
    for competition_id in sorted(REQUIRED_MATCHDAY_COMPETITIONS):
        entry = entries[competition_id]
        if not entry.enabled:
            raise HistoricalFixtureBackfillError(
                f"BACKFILL_COMPETITION_DISABLED:{competition_id}"
            )
        league_id = str(entry.provider_mapping.get("api_football_league_id") or "")
        if not league_id or league_id in provider_ids:
            raise HistoricalFixtureBackfillError(
                f"BACKFILL_PROVIDER_LEAGUE_ID_INVALID:{competition_id}"
            )
        provider_ids.add(league_id)
        scopes.extend(
            BackfillScope(
                competition_id=competition_id,
                provider_league_id=league_id,
                season=season,
            )
            for season in BACKFILL_SEASONS
        )
    if len(scopes) != BACKFILL_LOGICAL_REQUEST_CAP:
        raise HistoricalFixtureBackfillError("BACKFILL_SCOPE_NOT_EXACT_13_BY_2")
    return tuple(scopes)


def blocking_checkpoint_plans(
    engine: Engine,
    *,
    as_of: datetime,
    horizon: timedelta = QUIET_HORIZON,
) -> list[dict[str, Any]]:
    start = as_of.astimezone(UTC) - QUIET_LOOKBACK
    end = as_of.astimezone(UTC) + horizon
    plans = MatchdayCheckpointPlanModel
    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(plans)
                .where(
                    plans.test_only.is_(False),
                    plans.window_end >= start,
                    plans.window_start <= end,
                    or_(
                        plans.status.in_(ACTIVE_PLAN_STATUSES),
                        plans.claimed_at.is_not(None),
                    ),
                )
                .order_by(plans.window_start, plans.plan_id)
            )
        )
    return [
        {
            "plan_id": row.plan_id,
            "fixture_id": row.fixture_id,
            "competition_id": row.competition_id,
            "checkpoint": row.checkpoint,
            "status": row.status,
            "window_start": iso(row.window_start),
            "window_end": iso(row.window_end),
        }
        for row in rows
    ]


def _payload_scope(payload: Mapping[str, Any]) -> tuple[str, str]:
    parameters = payload.get("parameters")
    if not isinstance(parameters, Mapping):
        return "", ""
    return str(parameters.get("league") or ""), str(parameters.get("season") or "")


def _validate_payload(scope: BackfillScope, payload: Mapping[str, Any]) -> int:
    if _payload_scope(payload) != (scope.provider_league_id, scope.season):
        raise HistoricalFixtureBackfillError(
            f"BACKFILL_RESPONSE_SCOPE_MISMATCH:{scope.competition_id}:{scope.season}"
        )
    if payload.get("errors") not in (None, {}, [], ""):
        raise HistoricalFixtureBackfillError(
            f"BACKFILL_PROVIDER_ERROR:{scope.competition_id}:{scope.season}"
        )
    response = payload.get("response")
    if not isinstance(response, list) or not response:
        raise HistoricalFixtureBackfillError(
            f"BACKFILL_FIXTURES_EMPTY:{scope.competition_id}:{scope.season}"
        )
    for item in response:
        league = item.get("league") if isinstance(item, Mapping) else None
        fixture = item.get("fixture") if isinstance(item, Mapping) else None
        teams = item.get("teams") if isinstance(item, Mapping) else None
        if (
            not isinstance(league, Mapping)
            or str(league.get("id") or "") != scope.provider_league_id
            or str(league.get("season") or "") != scope.season
            or not isinstance(fixture, Mapping)
            or not fixture.get("id")
            or not fixture.get("date")
            or not isinstance(teams, Mapping)
        ):
            raise HistoricalFixtureBackfillError(
                f"BACKFILL_FIXTURE_IDENTITY_INVALID:{scope.competition_id}:{scope.season}"
            )
    declared = payload.get("results")
    if declared is not None and int(declared) != len(response):
        raise HistoricalFixtureBackfillError(
            f"BACKFILL_RESULTS_COUNT_MISMATCH:{scope.competition_id}:{scope.season}"
        )
    return len(response)


def _cached_scopes(
    rows: list[dict[str, Any]], scopes: tuple[BackfillScope, ...]
) -> dict[tuple[str, str], dict[str, Any]]:
    expected = {(scope.provider_league_id, scope.season): scope for scope in scopes}
    cached: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, Mapping):
            continue
        key = _payload_scope(payload)
        scope = expected.get(key)
        if scope is None:
            continue
        try:
            fixture_count = _validate_payload(scope, payload)
        except (HistoricalFixtureBackfillError, TypeError, ValueError):
            continue
        cached[key] = {
            "raw_payload_sha256": str(row.get("sha256") or ""),
            "raw_captured_at": str(row.get("captured_at") or ""),
            "fixture_count": fixture_count,
        }
    return cached


class HistoricalFixtureBackfillService:
    def __init__(
        self,
        *,
        scopes: tuple[BackfillScope, ...],
        repository: BackfillRepository,
        client: FixtureClient,
        config: BackfillConfig,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
        quiet_guard: Callable[[datetime], list[dict[str, Any]]],
        runtime_hardening_guard: Callable[[], None],
    ) -> None:
        _validate_config(config)
        if len(scopes) != BACKFILL_LOGICAL_REQUEST_CAP:
            raise HistoricalFixtureBackfillError("BACKFILL_SCOPE_NOT_EXACT_13_BY_2")
        if {scope.season for scope in scopes} != set(BACKFILL_SEASONS):
            raise HistoricalFixtureBackfillError("BACKFILL_SEASON_SCOPE_INVALID")
        self.scopes = scopes
        self.repository = repository
        self.client = client
        self.config = config
        self.now = now
        self.sleep = sleep
        self.quiet_guard = quiet_guard
        self.runtime_hardening_guard = runtime_hardening_guard

    def run(self, *, live: bool) -> dict[str, Any]:
        started_at = self.now().astimezone(UTC)
        raw_rows = self.repository.raw_payloads("fixtures")
        cached = _cached_scopes(raw_rows, self.scopes)
        pending = [
            scope
            for scope in self.scopes
            if (scope.provider_league_id, scope.season) not in cached
        ]
        scope_results = [
            {
                **scope.__dict__,
                "status": "CACHED"
                if (scope.provider_league_id, scope.season) in cached
                else "PENDING",
                **cached.get((scope.provider_league_id, scope.season), {}),
                "physical_attempt_count": 0,
            }
            for scope in self.scopes
        ]
        worst_case_pending_seconds = (
            len(pending) * self.config.worst_case_logical_request_seconds
            + max(len(pending) - 1, 0) * (60 / self.config.requests_per_minute)
        )
        report: dict[str, Any] = {
            "schema_version": "w2.factor_model.gate1_fixture_backfill.v1",
            "started_at_utc": iso(started_at),
            "endpoint_allowlist": ["fixtures"],
            "seasons": list(BACKFILL_SEASONS),
            "competition_count": len({scope.competition_id for scope in self.scopes}),
            "scope_count": len(self.scopes),
            "cached_scope_count": len(cached),
            "pending_scope_count": len(pending),
            "logical_request_cap": BACKFILL_LOGICAL_REQUEST_CAP,
            "physical_attempt_cap": len(pending) * self.config.max_attempts,
            "request_timeout_seconds": self.config.request_timeout_seconds,
            "max_attempts_per_scope": self.config.max_attempts,
            "retry_backoff_seconds": self.config.retry_backoff_seconds,
            "worst_case_logical_request_seconds": (
                self.config.worst_case_logical_request_seconds
            ),
            "worst_case_pending_seconds": worst_case_pending_seconds,
            "quiet_window_reserve_seconds": (
                QUIET_HORIZON.total_seconds() - worst_case_pending_seconds
            ),
            "quiet_window_lookback_minutes": int(QUIET_LOOKBACK.total_seconds() / 60),
            "quiet_window_horizon_minutes": int(QUIET_HORIZON.total_seconds() / 60),
            "scheduler_used": False,
            "provider_calls": 0,
            "logical_request_count": 0,
            "physical_attempt_count": 0,
            "raw_payloads_added": 0,
            "fixture_count_added": 0,
            "remaining_quota": None,
            "blockers": [],
            "scope_results": scope_results,
            "live": live,
        }
        if not live or not pending:
            return report
        if started_at.date() in BLOCKED_UTC_DATES:
            report["blockers"] = ["WEEKEND_BACKFILL_FORBIDDEN"]
            return report
        self.runtime_hardening_guard()
        active = self.quiet_guard(started_at)
        if active:
            report["blockers"] = ["MATCHDAY_CHECKPOINT_WINDOW_OVERLAP"]
            report["blocking_checkpoint_plans"] = active
            return report
        day_start = started_at.replace(hour=0, minute=0, second=0, microsecond=0)
        actual_calls_today = self.repository.request_count_since(day_start)
        quota_preflight = provider_daily_hard_cap_decision(
            actual_calls_today=actual_calls_today,
            planned_calls=len(pending) * self.config.max_attempts,
            daily_cap=self.config.daily_hard_cap,
            reserve_bucket=self.config.daily_reserve,
        )
        report["quota_preflight"] = quota_preflight
        if not quota_preflight["allowed"]:
            report["blockers"] = [str(quota_preflight["blocker"])]
            return report

        result_by_scope = {
            (row["provider_league_id"], row["season"]): row
            for row in scope_results
        }
        for ordinal, scope in enumerate(pending):
            active = self.quiet_guard(self.now().astimezone(UTC))
            if active:
                report["blockers"] = ["MATCHDAY_CHECKPOINT_WINDOW_OVERLAP"]
                report["blocking_checkpoint_plans"] = active
                break
            row = result_by_scope[(scope.provider_league_id, scope.season)]
            response, attempts, transport_error = self._request(scope)
            report["physical_attempt_count"] = int(
                report["physical_attempt_count"]
            ) + attempts
            row["physical_attempt_count"] = attempts
            if response is None:
                row["status"] = "FAILED"
                row["error_type"] = transport_error
                report["blockers"] = [
                    f"BACKFILL_TRANSPORT_FAILED:{scope.competition_id}:{scope.season}:"
                    f"{transport_error}"
                ]
                break
            report["logical_request_count"] = int(report["logical_request_count"]) + 1
            report["provider_calls"] = report["physical_attempt_count"]
            if response.endpoint != "fixtures":
                raise HistoricalFixtureBackfillError("BACKFILL_NON_FIXTURES_ENDPOINT")
            row["elapsed_ms"] = response.elapsed_ms
            row["status_code"] = response.status_code
            if response.status_code >= 400:
                row["status"] = "FAILED"
                report["blockers"] = [
                    f"BACKFILL_HTTP_{response.status_code}:"
                    f"{scope.competition_id}:{scope.season}"
                ]
                break
            try:
                fixture_count = _validate_payload(scope, response.payload)
            except HistoricalFixtureBackfillError as exc:
                row["status"] = "FAILED"
                report["blockers"] = [str(exc)]
                break
            digest = sha256_payload(
                response.payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD
            )
            existed = self.repository.raw_payload_exists(
                sha256=digest, endpoint="fixtures"
            )
            self.repository.save_raw_payload(
                sha256=digest,
                endpoint="fixtures",
                captured_at=response.captured_at,
                payload=response.payload,
            )
            if not self.repository.raw_payload_exists(
                sha256=digest, endpoint="fixtures"
            ):
                raise HistoricalFixtureBackfillError("BACKFILL_RAW_WRITE_GUARD_FAILED")
            quota = parse_api_football_quota(
                headers=response.headers,
                payload=response.payload,
                observed_at=response.captured_at,
            )
            report["remaining_quota"] = quota.daily_remaining
            row.update(
                {
                    "status": "CAPTURED",
                    "fixture_count": fixture_count,
                    "raw_payload_sha256": digest,
                    "raw_captured_at": iso(response.captured_at),
                    "remaining_quota": quota.daily_remaining,
                }
            )
            report["raw_payloads_added"] = int(report["raw_payloads_added"]) + int(
                not existed
            )
            report["fixture_count_added"] = int(
                report["fixture_count_added"]
            ) + fixture_count
            if (
                quota.daily_remaining is not None
                and quota.daily_remaining <= self.config.quota_reserve
            ):
                report["blockers"] = ["BACKFILL_QUOTA_GUARD"]
                break
            if ordinal + 1 < len(pending):
                self.sleep(60 / self.config.requests_per_minute)
        report["completed_at_utc"] = iso(self.now().astimezone(UTC))
        report["provider_calls"] = report["physical_attempt_count"]
        return report

    def _request(
        self, scope: BackfillScope
    ) -> tuple[LiveApiFootballResponse | None, int, str | None]:
        params = {"league": scope.provider_league_id, "season": scope.season}
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return self.client.request_live("fixtures", params), attempt, None
            except OSError as exc:
                if attempt == self.config.max_attempts:
                    return None, attempt, type(exc).__name__
                self.sleep(self.config.retry_backoff_seconds * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")


def _runtime_hardening_guard() -> None:
    if not hasattr(api_football_module, "provider_request_timeout_seconds"):
        raise HistoricalFixtureBackfillError("PROVIDER_TIMEOUT_HARDENING_NOT_PRESENT")


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return iso(value)
    raise TypeError(f"UNSUPPORTED_JSON_TYPE:{type(value).__name__}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exact-13 x 2022/2023 fixtures-only Gate 1 history backfill."
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    engine = create_engine()
    scopes = exact_backfill_scopes(CompetitionRegistry(engine))
    service = HistoricalFixtureBackfillService(
        scopes=scopes,
        repository=FutureRefreshDbRepository(engine=engine),
        client=ApiFootballClient(
            allow_live=True,
            allowed_live_endpoints=frozenset({"fixtures"}),
        ),
        config=BackfillConfig.from_env(),
        quiet_guard=lambda as_of: blocking_checkpoint_plans(engine, as_of=as_of),
        runtime_hardening_guard=_runtime_hardening_guard,
    )
    report = service.run(live=args.live)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json_atomic(args.output_dir / "fixture_backfill_report.json", report)
    print(json.dumps(report, sort_keys=True, default=_json_default))
    return 0 if not report["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
