from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from w2.competitions.registry import CompetitionRegistry
from w2.features.xg_materialization import (
    FINISHED_STATUS,
    TeamXgMatch,
    materialize_rolling_xg,
    parse_team_xg_matches,
)
from w2.ingestion.future_refresh import (
    LiveApiFootballPort,
    canonical_json,
    fixture_id_from_payload,
    iso,
    parse_utc,
    sanitize_params,
    sha256_payload,
)
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
    FutureRefreshPersistenceError,
)
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse
from w2.providers.control import env_int
from w2.providers.quota import (
    parse_api_football_quota,
    provider_daily_hard_cap_decision,
    quota_guard_decision,
)


class XgBackfillError(RuntimeError):
    pass


class XgBackfillRepository(Protocol):
    def fixture_payloads(self) -> list[dict[str, Any]]:
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

    def upsert_team_xg_matches(self, matches: list[dict[str, Any]]) -> int:
        pass

    def team_xg_matches(self) -> list[dict[str, Any]]:
        pass

    def upsert_team_xg_rolling_snapshots(self, snapshots: list[dict[str, Any]]) -> int:
        pass

    def request_count_since(self, since: datetime) -> int:
        pass


@dataclass(frozen=True, kw_only=True)
class XgBackfillConfig:
    competition_id: str = "world_cup_2026"
    recent_match_count: int = 5
    request_budget: int = 120
    quota_reserve: int = 1500
    min_rolling_matches: int = 3
    max_rolling_matches: int = 5
    source_revision: str = "LOCAL_UNDEPLOYED"
    daily_hard_cap: int = 7500
    daily_reserve: int = 1500
    actual_provider_calls_today: int | None = None


@dataclass(frozen=True, kw_only=True)
class XgBackfillResult:
    generated_at_utc: datetime
    team_count: int
    historical_fixture_count: int
    statistics_request_count: int
    team_xg_match_rows: int
    rolling_snapshot_rows: int
    remaining_quota: int | None
    blockers: list[str] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)
    candidate: bool = False
    formal_recommendation: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at_utc": iso(self.generated_at_utc),
            "team_count": self.team_count,
            "historical_fixture_count": self.historical_fixture_count,
            "statistics_request_count": self.statistics_request_count,
            "team_xg_match_rows": self.team_xg_match_rows,
            "rolling_snapshot_rows": self.rolling_snapshot_rows,
            "remaining_quota": self.remaining_quota,
            "provider_calls": sum(
                1
                for request in self.requests
                if request.get("endpoint") != "provider_daily_hard_cap_preflight"
            ),
            "blockers": self.blockers,
            "requests": self.requests,
            "candidate": False,
            "formal_recommendation": False,
        }


class XgHistoryBackfillService:
    def __init__(
        self,
        *,
        client: LiveApiFootballPort | None = None,
        repository: XgBackfillRepository | None = None,
        config: XgBackfillConfig | None = None,
        now: datetime | None = None,
    ) -> None:
        self.client = client or ApiFootballClient(
            allow_live=True,
            allowed_live_endpoints=frozenset({"fixtures", "statistics", "status"}),
        )
        self.repository = repository or FutureRefreshDbRepository()
        self.config = config or XgBackfillConfig()
        self.now = now or datetime.now(UTC)
        self._audit: list[dict[str, Any]] = []
        self._remaining_quota: int | None = None
        entry = CompetitionRegistry().require_enabled(self.config.competition_id)
        self._api_football_league_id = entry.provider_mapping.get("api_football_league_id")
        self._api_football_season = entry.provider_mapping.get("api_football_season")

    def run(self) -> XgBackfillResult:
        future_fixtures = [
            item
            for item in self.repository.fixture_payloads()
            if self._is_target_future_fixture(item)
        ]
        team_ids = sorted(self._world_cup_team_ids(future_fixtures))
        try:
            preflight = self._provider_hard_cap_preflight()
        except XgBackfillError as exc:
            preflight = {
                "allowed": False,
                "blocker": str(exc),
                "mode": "HARD_CAP_AUDIT_UNAVAILABLE",
                "actual_calls_today": None,
                "planned_calls": max(self.config.request_budget, 0),
                "daily_cap": self.config.daily_hard_cap,
                "reserve_bucket": self.config.daily_reserve,
            }
        if not preflight["allowed"]:
            blocker = str(preflight["blocker"])
            return XgBackfillResult(
                generated_at_utc=self.now,
                team_count=len(team_ids),
                historical_fixture_count=0,
                statistics_request_count=0,
                team_xg_match_rows=0,
                rolling_snapshot_rows=0,
                remaining_quota=self._remaining_quota,
                blockers=[blocker],
                requests=[
                    {
                        "endpoint": "provider_daily_hard_cap_preflight",
                        "params": {},
                        "status_code": None,
                        "elapsed_ms": 0,
                        "captured_at_utc": iso(self.now),
                        "payload_sha256": None,
                        "remaining_quota": None,
                        "error_code": blocker,
                        "quota_guard_mode": preflight["mode"],
                        "actual_calls_today": preflight["actual_calls_today"],
                        "planned_calls": preflight["planned_calls"],
                        "daily_cap": preflight["daily_cap"],
                        "reserve_bucket": preflight["reserve_bucket"],
                        "candidate": False,
                        "formal_recommendation": False,
                    }
                ],
            )
        historical_fixtures: dict[str, dict[str, Any]] = {}
        blockers: list[str] = []
        try:
            for team_id in team_ids:
                if self._attempt_count() >= self.config.request_budget:
                    blockers.append("XG_BACKFILL_BUDGET_EXHAUSTED")
                    break
                response = self._request(
                    "fixtures",
                    {"team": team_id, "last": str(self.config.recent_match_count)},
                )
                if response.status_code >= 400:
                    blockers.append(f"HISTORICAL_FIXTURES_HTTP_{response.status_code}:{team_id}")
                    continue
                self._save_raw(response)
                for item in self._finished_fixture_items(response.payload):
                    historical_fixtures[fixture_id_from_payload(item)] = item
            xg_rows: list[TeamXgMatch] = []
            for fixture_id, fixture in sorted(historical_fixtures.items()):
                if self._attempt_count() >= self.config.request_budget:
                    blockers.append("XG_BACKFILL_BUDGET_EXHAUSTED")
                    break
                response = self._request("statistics", {"fixture": fixture_id})
                if response.status_code >= 400:
                    blockers.append(f"STATISTICS_HTTP_{response.status_code}:{fixture_id}")
                    continue
                payload_hash = sha256_payload(response.payload)
                self._save_raw(response)
                xg_rows.extend(
                    parse_team_xg_matches(
                        fixture_payload=fixture,
                        statistics_payload=response.payload,
                        captured_at=response.captured_at,
                        raw_payload_sha256=payload_hash,
                    )
                )
        except XgBackfillError as exc:
            blockers.append(str(exc))
            xg_rows = []
        match_rows = [self._xg_match_dict(row) for row in xg_rows]
        persisted_xg_rows = self._persisted_xg_matches()
        rolling_inputs = {
            row.id: row for row in [*persisted_xg_rows, *xg_rows]
        }
        snapshot_rows = self._rolling_snapshot_rows(
            future_fixtures=future_fixtures,
            materialized_matches=list(rolling_inputs.values()),
        )
        try:
            upserted_matches = self.repository.upsert_team_xg_matches(match_rows)
            upserted_snapshots = self.repository.upsert_team_xg_rolling_snapshots(snapshot_rows)
        except FutureRefreshPersistenceError as exc:
            raise XgBackfillError(f"PERSISTENCE_WRITE_FAILED:{exc}") from exc
        return XgBackfillResult(
            generated_at_utc=self.now,
            team_count=len(team_ids),
            historical_fixture_count=len(historical_fixtures),
            statistics_request_count=sum(
                1 for item in self._audit if item["endpoint"] == "statistics"
            ),
            team_xg_match_rows=upserted_matches,
            rolling_snapshot_rows=upserted_snapshots,
            remaining_quota=self._remaining_quota,
            blockers=blockers,
            requests=self._audit,
        )

    def _request(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        preflight = quota_guard_decision(
            remaining_quota=self._remaining_quota,
            reserve_bucket=self.config.quota_reserve,
            task_type="xg_backfill",
        )
        if self._remaining_quota is not None and not preflight["allowed"]:
            raise XgBackfillError(str(preflight["blocker"]))
        response = self.client.request_live(endpoint, params)
        quota = parse_api_football_quota(
            headers=response.headers,
            payload=response.payload,
            observed_at=response.captured_at,
        )
        self._remaining_quota = quota.daily_remaining
        payload_hash = sha256_payload(response.payload)
        self._audit.append(
            {
                "endpoint": endpoint,
                "params": sanitize_params(params),
                "status_code": response.status_code,
                "elapsed_ms": response.elapsed_ms,
                "captured_at_utc": iso(response.captured_at),
                "payload_sha256": payload_hash,
                "remaining_quota": quota.daily_remaining,
                "candidate": False,
                "formal_recommendation": False,
            }
        )
        guard = quota_guard_decision(
            remaining_quota=quota.daily_remaining,
            reserve_bucket=self.config.quota_reserve,
            task_type="xg_backfill",
        )
        if not guard["allowed"]:
            raise XgBackfillError(str(guard["blocker"]))
        if response.status_code in {401, 403}:
            return response
        return response

    def _provider_hard_cap_preflight(self) -> dict[str, Any]:
        daily_cap = env_int("W2_PROVIDER_DAILY_HARD_CAP", default=self.config.daily_hard_cap)
        reserve = env_int("W2_PROVIDER_DAILY_RESERVE", default=self.config.daily_reserve)
        actual_calls_today = self._actual_provider_calls_today()
        return provider_daily_hard_cap_decision(
            actual_calls_today=actual_calls_today,
            planned_calls=max(self.config.request_budget, 0),
            daily_cap=daily_cap,
            reserve_bucket=reserve,
        )

    def _actual_provider_calls_today(self) -> int:
        if self.config.actual_provider_calls_today is not None:
            return max(self.config.actual_provider_calls_today, 0)
        day_start = self.now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            return self.repository.request_count_since(day_start)
        except Exception as exc:
            raise XgBackfillError("PROVIDER_USAGE_AUDIT_UNAVAILABLE") from exc

    def _save_raw(self, response: LiveApiFootballResponse) -> None:
        self.repository.save_raw_payload(
            sha256=sha256_payload(response.payload),
            endpoint=response.endpoint,
            captured_at=response.captured_at,
            payload=response.payload,
        )

    def _attempt_count(self) -> int:
        return len(self._audit)

    def _world_cup_team_ids(self, fixtures: list[dict[str, Any]]) -> set[str]:
        ids: set[str] = set()
        for item in fixtures:
            teams = item.get("teams", {}) if isinstance(item, dict) else {}
            for side in ("home", "away"):
                team = teams.get(side) if isinstance(teams, dict) else None
                if isinstance(team, dict) and team.get("id") is not None:
                    ids.add(str(team["id"]))
        return ids

    def _is_target_future_fixture(self, item: dict[str, Any]) -> bool:
        fixture = item.get("fixture", {}) if isinstance(item, dict) else {}
        league = item.get("league", {}) if isinstance(item, dict) else {}
        if not isinstance(fixture, dict) or not isinstance(league, dict):
            return False
        if self._api_football_league_id is not None:
            league_id = str(league.get("id") or "")
            if league_id != self._api_football_league_id:
                return False
        if self._api_football_season is not None and league.get("season") is not None:
            season = str(league.get("season") or "")
            if season != self._api_football_season:
                return False
        status = fixture.get("status", {}) if isinstance(fixture.get("status"), dict) else {}
        if status.get("short") in FINISHED_STATUS:
            return False
        kickoff = parse_utc(fixture.get("date"))
        return kickoff is not None and kickoff > self.now

    def _finished_fixture_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        response = payload.get("response")
        if not isinstance(response, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in response:
            if not isinstance(item, dict):
                continue
            fixture = item.get("fixture", {}) if isinstance(item.get("fixture"), dict) else {}
            status = fixture.get("status", {}) if isinstance(fixture.get("status"), dict) else {}
            kickoff = parse_utc(fixture.get("date"))
            is_finished = status.get("short") in FINISHED_STATUS
            if is_finished and kickoff is not None and kickoff < self.now:
                rows.append(item)
        return rows

    def _rolling_snapshot_rows(
        self,
        *,
        future_fixtures: list[dict[str, Any]],
        materialized_matches: list[TeamXgMatch],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in future_fixtures:
            fixture = item.get("fixture", {}) if isinstance(item.get("fixture"), dict) else {}
            fixture_id = str(fixture.get("id") or "")
            kickoff = parse_utc(fixture.get("date"))
            teams = item.get("teams", {}) if isinstance(item.get("teams"), dict) else {}
            if not fixture_id or kickoff is None:
                continue
            for side in ("home", "away"):
                team_raw = teams.get(side) if isinstance(teams, dict) else None
                team = team_raw if isinstance(team_raw, dict) else {}
                team_id = str(team.get("id") or "")
                if not team_id:
                    continue
                snapshot = materialize_rolling_xg(
                    team_id=team_id,
                    as_of_fixture_id=fixture_id,
                    as_of_time=kickoff,
                    matches=materialized_matches,
                    window=self.config.max_rolling_matches,
                    min_matches=self.config.min_rolling_matches,
                )
                if snapshot is not None:
                    rows.append(
                        {
                            "snapshot_id": snapshot.snapshot_id,
                            "team_id": snapshot.team_id,
                            "as_of_fixture_id": snapshot.as_of_fixture_id,
                            "as_of_time": iso(snapshot.as_of_time),
                            "match_count": snapshot.match_count,
                            "rolling_xg_for": snapshot.rolling_xg_for,
                            "rolling_xg_against": snapshot.rolling_xg_against,
                            "rolling_goals_for": snapshot.rolling_goals_for,
                            "rolling_goals_against": snapshot.rolling_goals_against,
                            "regression_index": snapshot.regression_index,
                            "source_system": snapshot.source_system,
                            "candidate": False,
                            "formal_recommendation": False,
                        }
                    )
        return rows

    def _persisted_xg_matches(self) -> list[TeamXgMatch]:
        rows: list[TeamXgMatch] = []
        for item in self.repository.team_xg_matches():
            try:
                kickoff = parse_utc(item.get("kickoff_at"))
                captured = parse_utc(item.get("captured_at"))
                if kickoff is None or captured is None:
                    continue
                rows.append(
                    TeamXgMatch(
                        fixture_id=str(item["fixture_id"]),
                        team_id=str(item["team_id"]),
                        opponent_team_id=str(item["opponent_team_id"]),
                        kickoff_at=kickoff,
                        captured_at=captured,
                        xg_for=float(item["xg_for"]),
                        xg_against=float(item["xg_against"]),
                        goals_for=int(item["goals_for"]),
                        goals_against=int(item["goals_against"]),
                        raw_payload_sha256=str(item["raw_payload_sha256"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return rows

    def _xg_match_dict(self, row: TeamXgMatch) -> dict[str, Any]:
        return {
            "id": row.id,
            "fixture_id": row.fixture_id,
            "team_id": row.team_id,
            "opponent_team_id": row.opponent_team_id,
            "kickoff_at": iso(row.kickoff_at),
            "captured_at": iso(row.captured_at),
            "xg_for": row.xg_for,
            "xg_against": row.xg_against,
            "goals_for": row.goals_for,
            "goals_against": row.goals_against,
            "raw_payload_sha256": row.raw_payload_sha256,
            "source_system": row.source_system,
            "candidate": False,
            "formal_recommendation": False,
        }


def run_xg_history_backfill(
    *,
    client: LiveApiFootballPort | None = None,
    repository: XgBackfillRepository | None = None,
    now: datetime | None = None,
) -> XgBackfillResult:
    return XgHistoryBackfillService(
        client=client,
        repository=repository,
        now=now,
        config=XgBackfillConfig(
            competition_id=os.environ.get(
                "W2_XG_BACKFILL_COMPETITION_ID",
                "world_cup_2026",
            ),
            recent_match_count=int(os.environ.get("W2_XG_BACKFILL_RECENT_MATCHES", "5")),
            request_budget=int(os.environ.get("W2_XG_BACKFILL_REQUEST_BUDGET", "120")),
            quota_reserve=int(os.environ.get("W2_API_MINIMUM_RESERVE", "1500")),
            daily_hard_cap=env_int("W2_PROVIDER_DAILY_HARD_CAP", default=7500),
            daily_reserve=env_int("W2_PROVIDER_DAILY_RESERVE", default=1500),
            source_revision=os.environ.get("W2_SERVICE_VERSION", "LOCAL_UNDEPLOYED"),
        ),
    ).run()


def write_backfill_report(path: Path, result: XgBackfillResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(result.as_dict()) + "\n", encoding="utf-8")
