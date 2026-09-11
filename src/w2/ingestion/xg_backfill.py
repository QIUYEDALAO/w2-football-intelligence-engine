from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from w2.competitions.registry import CompetitionRegistry
from w2.domain.canonical_serialization import HashDomain
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
from w2.matchday.intake_v2 import REQUIRED_MATCHDAY_COMPETITIONS
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse
from w2.providers.control import env_int
from w2.providers.quota import (
    ProviderQuota,
    parse_api_football_quota,
    provider_daily_hard_cap_decision,
    quota_guard_decision,
)


class XgBackfillError(RuntimeError):
    pass


class XgBackfillRepository(Protocol):
    def fixture_payloads(self) -> list[dict[str, Any]]:
        pass

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        pass

    def raw_payload_count(self, endpoint: str) -> int:
        pass

    def raw_payload_exists(self, *, sha256: str, endpoint: str) -> bool:
        pass

    def raw_statistics_fixture_ids(self) -> set[str]:
        pass

    def provider_live_request_count_since(self, *, endpoint: str, since: datetime) -> int:
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

    def provider_team_mapping(
        self,
        *,
        provider: str,
        competition_id: str,
        season: str,
        as_of: datetime,
    ) -> dict[str, str]:
        pass


@dataclass(frozen=True, kw_only=True)
class XgBackfillConfig:
    competition_ids: tuple[str, ...] = tuple(sorted(REQUIRED_MATCHDAY_COMPETITIONS))
    recent_match_count: int = 5
    request_budget: int = 120
    quota_reserve: int = 1500
    min_rolling_matches: int = 3
    max_rolling_matches: int = 5
    source_revision: str = "LOCAL_UNDEPLOYED"
    daily_hard_cap: int = 7500
    daily_reserve: int = 1500
    statistics_daily_hard_cap: int = 5500
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
    dry_run: bool = False

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
            "dry_run": self.dry_run,
        }


@dataclass(frozen=True, kw_only=True)
class SavedRawXgPlan:
    team_xg_matches: tuple[dict[str, Any], ...]
    rolling_snapshots: tuple[dict[str, Any], ...]
    raw_statistics_sha256: tuple[str, ...]
    future_fixture_count: int
    blockers: tuple[str, ...]


PRO_BACKFILL_BATCHES: dict[int, tuple[str, ...]] = {
    1: (
        "argentina_primera",
        "brasileirao_serie_a",
        "chinese_super_league",
        "eliteserien",
        "allsvenskan",
        "mls",
    ),
    2: ("bundesliga", "la_liga", "ligue_1", "premier_league", "serie_a"),
    3: ("eredivisie", "primeira_liga"),
}
PRO_BACKFILL_SEASONS = frozenset({"2024", "2025", "2026"})


@dataclass(frozen=True, kw_only=True)
class ProStatisticsBackfillConfig:
    batch: int
    request_budget: int = 5500
    daily_request_limit: int = 5500
    requests_per_minute: int = 60
    quota_reserve: int = 1500
    pilot_per_competition: int = 3
    ensure_fixture_manifests: bool = True


@dataclass(frozen=True, kw_only=True)
class ProStatisticsBackfillResult:
    generated_at_utc: datetime
    batch: int
    fixture_manifest_request_count: int
    raw_fixtures_added: int
    manifest_fixture_count: int
    cached_fixture_count: int
    requested_fixture_count: int
    raw_statistics_before: int
    raw_statistics_after: int
    raw_statistics_added: int
    raw_payload_sha256: tuple[str, ...]
    pilot_xg_verified_competitions: tuple[str, ...]
    skipped_competitions: tuple[str, ...]
    remaining_fixture_count: int
    remaining_quota: int | None
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "generated_at_utc": iso(self.generated_at_utc),
            "raw_payload_sha256": list(self.raw_payload_sha256),
            "pilot_xg_verified_competitions": list(self.pilot_xg_verified_competitions),
            "skipped_competitions": list(self.skipped_competitions),
            "blockers": list(self.blockers),
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
        requested = set(self.config.competition_ids)
        if not requested or not requested <= REQUIRED_MATCHDAY_COMPETITIONS:
            raise XgBackfillError("XG_COMPETITION_SCOPE_NOT_EXACT13")
        entries = CompetitionRegistry().entries()
        missing = requested - set(entries)
        if missing:
            raise XgBackfillError(f"XG_COMPETITION_NOT_REGISTERED:{','.join(sorted(missing))}")
        self._competition_by_provider_scope: dict[tuple[str, str], str] = {}
        for competition_id in sorted(requested):
            entry = entries[competition_id]
            provider_league = str(entry.provider_mapping.get("api_football_league_id") or "")
            provider_season = str(entry.provider_mapping.get("api_football_season") or entry.season)
            if not provider_league or not provider_season:
                raise XgBackfillError(f"XG_PROVIDER_SCOPE_MISSING:{competition_id}")
            scope = (provider_league, provider_season)
            if scope in self._competition_by_provider_scope:
                raise XgBackfillError(
                    f"XG_PROVIDER_SCOPE_CONFLICT:{provider_league}:{provider_season}"
                )
            self._competition_by_provider_scope[scope] = competition_id

    def run(self) -> XgBackfillResult:
        future_fixtures = [
            item
            for item in self.repository.fixture_payloads()
            if self._is_target_future_fixture(item)
        ]
        team_ids = sorted(self._target_team_ids(future_fixtures))
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
        day_start = self.now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            statistics_requests_today = self.repository.provider_live_request_count_since(
                endpoint="statistics",
                since=day_start,
            )
        except Exception as exc:
            raise XgBackfillError("STATISTICS_USAGE_AUDIT_UNAVAILABLE") from exc
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
            cached_statistics = self.repository.raw_statistics_fixture_ids()
            for fixture_id, fixture in sorted(historical_fixtures.items()):
                if fixture_id in cached_statistics:
                    continue
                if statistics_requests_today >= self.config.statistics_daily_hard_cap:
                    blockers.append("STATISTICS_DAILY_HARD_CAP_REACHED")
                    break
                if self._attempt_count() >= self.config.request_budget:
                    blockers.append("XG_BACKFILL_BUDGET_EXHAUSTED")
                    break
                response = self._request("statistics", {"fixture": fixture_id})
                statistics_requests_today += 1
                if response.status_code >= 400:
                    blockers.append(f"STATISTICS_HTTP_{response.status_code}:{fixture_id}")
                    continue
                payload_hash = sha256_payload(
                    response.payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD
                )
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
        rolling_inputs = {row.id: row for row in [*persisted_xg_rows, *xg_rows]}
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

    def run_saved_raw(self, *, persist: bool = True) -> XgBackfillResult:
        """Materialize xG from persisted fixture/statistics evidence only."""
        plan = self.build_saved_raw_plan()
        parsed = {
            str(row["id"]): self._team_xg_match_from_dict(row) for row in plan.team_xg_matches
        }
        persisted = {row.id: row for row in self._persisted_xg_matches()}
        for row_id, row in parsed.items():
            previous = persisted.get(row_id)
            if previous is not None and self._xg_values(previous) != self._xg_values(row):
                raise XgBackfillError(f"SAVED_XG_CONFLICT:{row_id}")
        new_rows = [row for row_id, row in parsed.items() if row_id not in persisted]
        if persist:
            try:
                upserted_matches = self.repository.upsert_team_xg_matches(
                    [self._xg_match_dict(row) for row in new_rows]
                )
                upserted_snapshots = self.repository.upsert_team_xg_rolling_snapshots(
                    list(plan.rolling_snapshots)
                )
            except FutureRefreshPersistenceError as exc:
                raise XgBackfillError(f"PERSISTENCE_WRITE_FAILED:{exc}") from exc
        else:
            upserted_matches = len(new_rows)
            upserted_snapshots = len(plan.rolling_snapshots)
        return XgBackfillResult(
            generated_at_utc=self.now,
            team_count=len(
                {str(row["team_id"]) for row in plan.rolling_snapshots if row.get("team_id")}
            ),
            historical_fixture_count=len({row.fixture_id for row in parsed.values()}),
            statistics_request_count=0,
            team_xg_match_rows=upserted_matches,
            rolling_snapshot_rows=upserted_snapshots,
            remaining_quota=None,
            blockers=list(plan.blockers),
            requests=[],
            dry_run=not persist,
        )

    def build_saved_raw_plan(
        self,
        *,
        snapshot_identities: list[dict[str, Any]] | None = None,
    ) -> SavedRawXgPlan:
        """Derive the complete xG materialization from raw evidence only."""
        fixtures = self.repository.fixture_payloads()
        future_fixtures = [item for item in fixtures if self._is_target_future_fixture(item)]
        fixture_by_id: dict[str, dict[str, Any]] = {}
        for item in fixtures:
            fixture_id = fixture_id_from_payload(item)
            if not fixture_id or not self._is_target_competition_fixture(item):
                continue
            fixture_by_id[fixture_id] = item
        parsed: dict[str, TeamXgMatch] = {}
        raw_statistics_sha256: list[str] = []
        for raw in self.repository.raw_payloads("statistics"):
            payload = raw.get("payload")
            captured_at = parse_utc(raw.get("captured_at"))
            raw_sha256 = str(raw.get("sha256") or "")
            if raw_sha256:
                raw_statistics_sha256.append(raw_sha256)
            fixture_id = self._statistics_fixture_id(payload)
            fixture = fixture_by_id.get(fixture_id)
            if not isinstance(payload, dict) or captured_at is None or fixture is None:
                continue
            for row in parse_team_xg_matches(
                fixture_payload=fixture,
                statistics_payload=payload,
                captured_at=captured_at,
                raw_payload_sha256=raw_sha256,
            ):
                previous = parsed.get(row.id)
                if previous is not None and self._xg_values(previous) != self._xg_values(row):
                    raise XgBackfillError(f"SAVED_XG_CONFLICT:{row.id}")
                parsed.setdefault(row.id, row)

        snapshot_fixtures = future_fixtures
        expected_snapshot_ids: set[str] | None = None
        snapshot_blockers: list[str] = []
        if snapshot_identities is not None:
            expected_snapshot_ids = {
                str(item.get("snapshot_id") or "") for item in snapshot_identities
            }
            snapshot_fixture_ids = {
                str(item.get("as_of_fixture_id") or "") for item in snapshot_identities
            }
            missing_fixture_ids = sorted(snapshot_fixture_ids - set(fixture_by_id))
            snapshot_blockers.extend(
                f"XG_SNAPSHOT_FIXTURE_RAW_MISSING:{fixture_id}"
                for fixture_id in missing_fixture_ids
            )
            snapshot_fixtures = [
                fixture_by_id[fixture_id]
                for fixture_id in sorted(snapshot_fixture_ids & set(fixture_by_id))
            ]
        snapshots = self._rolling_snapshot_rows(
            future_fixtures=snapshot_fixtures,
            materialized_matches=list(parsed.values()),
        )
        if expected_snapshot_ids is not None:
            snapshots = [
                row for row in snapshots if str(row["snapshot_id"]) in expected_snapshot_ids
            ]
            rebuilt_ids = {str(row["snapshot_id"]) for row in snapshots}
            snapshot_blockers.extend(
                f"XG_SNAPSHOT_RAW_REBUILD_MISSING:{snapshot_id}"
                for snapshot_id in sorted(expected_snapshot_ids - rebuilt_ids)
            )
        return SavedRawXgPlan(
            team_xg_matches=tuple(
                self._xg_match_dict(row)
                for row in sorted(parsed.values(), key=lambda item: item.id)
            ),
            rolling_snapshots=tuple(sorted(snapshots, key=lambda item: str(item["snapshot_id"]))),
            raw_statistics_sha256=tuple(sorted(set(raw_statistics_sha256))),
            future_fixture_count=len(future_fixtures),
            blockers=tuple(sorted(snapshot_blockers)),
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
        payload_hash = sha256_payload(
            response.payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD
        )
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
            sha256=sha256_payload(response.payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD),
            endpoint=response.endpoint,
            captured_at=response.captured_at,
            payload=response.payload,
        )

    def _attempt_count(self) -> int:
        return len(self._audit)

    @staticmethod
    def _statistics_fixture_id(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        parameters = payload.get("parameters")
        if not isinstance(parameters, dict):
            return ""
        return str(parameters.get("fixture") or "")

    @staticmethod
    def _xg_values(row: TeamXgMatch) -> tuple[Any, ...]:
        return (
            row.fixture_id,
            row.team_id,
            row.opponent_team_id,
            row.kickoff_at,
            row.xg_for,
            row.xg_against,
            row.goals_for,
            row.goals_against,
        )

    def _target_team_ids(self, fixtures: list[dict[str, Any]]) -> set[str]:
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
        if not isinstance(fixture, dict) or not self._is_target_competition_fixture(item):
            return False
        status = fixture.get("status", {}) if isinstance(fixture.get("status"), dict) else {}
        if status.get("short") in FINISHED_STATUS:
            return False
        kickoff = parse_utc(fixture.get("date"))
        return kickoff is not None and kickoff > self.now and self._canonical_identity_ready(item)

    def _is_target_competition_fixture(self, item: dict[str, Any]) -> bool:
        league = item.get("league", {}) if isinstance(item, dict) else {}
        if not isinstance(league, dict):
            return False
        scope = (str(league.get("id") or ""), str(league.get("season") or ""))
        return scope in self._competition_by_provider_scope or (
            scope[1] in PRO_BACKFILL_SEASONS
            and any(
                league_id == scope[0] for league_id, _season in self._competition_by_provider_scope
            )
        )

    def _canonical_identity_ready(self, item: dict[str, Any]) -> bool:
        fixture = item.get("fixture", {}) if isinstance(item, dict) else {}
        league = item.get("league", {}) if isinstance(item, dict) else {}
        teams = item.get("teams", {}) if isinstance(item, dict) else {}
        kickoff = parse_utc(fixture.get("date") if isinstance(fixture, dict) else None)
        if kickoff is None or not isinstance(league, dict) or not isinstance(teams, dict):
            return False
        scope = (str(league.get("id") or ""), str(league.get("season") or ""))
        competition_id = self._competition_by_provider_scope.get(scope)
        if not competition_id:
            return False
        mapping = self.repository.provider_team_mapping(
            provider="api_football",
            competition_id=competition_id,
            season=scope[1],
            as_of=kickoff,
        )
        provider_ids = {
            str(team.get("id") or "")
            for side in ("home", "away")
            if isinstance((team := teams.get(side)), dict)
        }
        return len(provider_ids) == 2 and provider_ids <= set(mapping)

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
            if (
                is_finished
                and kickoff is not None
                and kickoff < self.now
                and self._is_target_competition_fixture(item)
            ):
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

    @staticmethod
    def _team_xg_match_from_dict(item: dict[str, Any]) -> TeamXgMatch:
        kickoff = parse_utc(item.get("kickoff_at"))
        captured = parse_utc(item.get("captured_at"))
        if kickoff is None or captured is None:
            raise XgBackfillError("SAVED_XG_TIME_INVALID")
        return TeamXgMatch(
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
            source_system=str(item.get("source_system") or "api_football_statistics"),
        )


class ProStatisticsBackfillService:
    """Bounded Pro backfill that persists every response before materialization."""

    def __init__(
        self,
        *,
        config: ProStatisticsBackfillConfig,
        client: LiveApiFootballPort | None = None,
        repository: XgBackfillRepository | None = None,
        now: datetime | None = None,
    ) -> None:
        if config.batch not in PRO_BACKFILL_BATCHES:
            raise XgBackfillError(f"PRO_BACKFILL_BATCH_INVALID:{config.batch}")
        if config.request_budget <= 0 or config.requests_per_minute <= 0:
            raise XgBackfillError("PRO_BACKFILL_BUDGET_INVALID")
        self.config = config
        self.client = client or ApiFootballClient(
            allow_live=True,
            allowed_live_endpoints=frozenset({"fixtures", "statistics"}),
        )
        self.repository = repository or FutureRefreshDbRepository()
        self.now = now or datetime.now(UTC)
        entries = CompetitionRegistry().entries()
        self._provider_league_by_competition = {
            competition_id: str(
                entries[competition_id].provider_mapping["api_football_league_id"]
            )
            for competition_id in PRO_BACKFILL_BATCHES[config.batch]
        }
        self._competition_by_scope = {
            (
                str(entries[competition_id].provider_mapping["api_football_league_id"]),
                str(
                    entries[competition_id].provider_mapping.get("api_football_season")
                    or entries[competition_id].season
                ),
            ): competition_id
            for competition_id in PRO_BACKFILL_BATCHES[config.batch]
        }

    def run(self) -> ProStatisticsBackfillResult:
        fixture_manifest_request_count, raw_fixtures_added = self._ensure_fixture_manifests()
        targets = self._target_fixtures()
        cached = self.repository.raw_statistics_fixture_ids()
        raw_before = self.repository.raw_payload_count("statistics")
        requested: list[str] = []
        raw_hashes: list[str] = []
        verified: set[str] = set()
        skipped: set[str] = set()
        blockers: list[str] = []
        remaining_quota: int | None = None
        day_start = self.now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        statistics_requests_today = self.repository.provider_live_request_count_since(
            endpoint="statistics",
            since=day_start,
        )
        request_budget = min(
            self.config.request_budget,
            max(self.config.daily_request_limit - statistics_requests_today, 0),
        )
        if request_budget == 0:
            blockers.append("PRO_STATISTICS_DAILY_CAP_REACHED")

        uncached_by_competition: dict[str, list[dict[str, Any]]] = {}
        for fixture in targets:
            fixture_id = fixture_id_from_payload(fixture)
            if fixture_id in cached:
                continue
            competition_id = self._competition_id(fixture)
            if competition_id:
                uncached_by_competition.setdefault(competition_id, []).append(fixture)

        pilot_size_by_competition: dict[str, int] = {}
        for competition_id in PRO_BACKFILL_BATCHES[self.config.batch]:
            if request_budget == 0:
                break
            fixtures = uncached_by_competition.get(competition_id, [])
            if not fixtures:
                verified.add(competition_id)
                continue
            pilot_size = (
                min(self.config.pilot_per_competition, len(fixtures))
                if self.config.batch in {2, 3}
                else 0
            )
            pilot_size_by_competition[competition_id] = pilot_size
            pilot = fixtures[:pilot_size]
            if pilot:
                pilot_xg_count = 0
                for fixture in pilot:
                    if len(requested) >= request_budget:
                        blockers.append("PRO_STATISTICS_DAILY_CAP_REACHED")
                        break
                    digest, has_xg, remaining_quota = self._fetch_and_persist(fixture)
                    requested.append(fixture_id_from_payload(fixture))
                    raw_hashes.append(digest)
                    pilot_xg_count += int(has_xg)
                    self._throttle()
                if blockers and blockers[-1] == "PRO_STATISTICS_DAILY_CAP_REACHED":
                    break
                if pilot_xg_count != len(pilot):
                    skipped.add(competition_id)
                    blockers.append(f"PRO_STATISTICS_XG_PILOT_EMPTY:{competition_id}")
                    continue
                verified.add(competition_id)
            else:
                verified.add(competition_id)

        for competition_id in PRO_BACKFILL_BATCHES[self.config.batch]:
            if (
                competition_id not in verified
                or blockers
                and blockers[-1] == "PRO_STATISTICS_DAILY_CAP_REACHED"
            ):
                continue
            fixtures = uncached_by_competition.get(competition_id, [])
            pilot_size = pilot_size_by_competition.get(competition_id, 0)
            for fixture in fixtures[pilot_size:]:
                if len(requested) >= request_budget:
                    blockers.append("PRO_STATISTICS_DAILY_CAP_REACHED")
                    break
                digest, _has_xg, remaining_quota = self._fetch_and_persist(fixture)
                requested.append(fixture_id_from_payload(fixture))
                raw_hashes.append(digest)
                self._throttle()
            if blockers and blockers[-1] == "PRO_STATISTICS_DAILY_CAP_REACHED":
                break

        raw_after = self.repository.raw_payload_count("statistics")
        raw_added = raw_after - raw_before
        if raw_added != len(raw_hashes):
            raise XgBackfillError(
                f"PRO_STATISTICS_RAW_COUNT_MISMATCH:{raw_before}:{raw_after}:{len(raw_hashes)}"
            )
        if any(
            not self.repository.raw_payload_exists(sha256=digest, endpoint="statistics")
            for digest in raw_hashes
        ):
            raise XgBackfillError("PRO_STATISTICS_RAW_HASH_MISSING")
        requested_ids = set(requested)
        remaining = sum(
            1
            for rows in uncached_by_competition.values()
            for fixture in rows
            if fixture_id_from_payload(fixture) not in requested_ids
        )
        return ProStatisticsBackfillResult(
            generated_at_utc=self.now,
            batch=self.config.batch,
            fixture_manifest_request_count=fixture_manifest_request_count,
            raw_fixtures_added=raw_fixtures_added,
            manifest_fixture_count=len(targets),
            cached_fixture_count=sum(
                fixture_id_from_payload(fixture) in cached for fixture in targets
            ),
            requested_fixture_count=len(requested),
            raw_statistics_before=raw_before,
            raw_statistics_after=raw_after,
            raw_statistics_added=raw_added,
            raw_payload_sha256=tuple(raw_hashes),
            pilot_xg_verified_competitions=tuple(sorted(verified)),
            skipped_competitions=tuple(sorted(skipped)),
            remaining_fixture_count=remaining,
            remaining_quota=remaining_quota,
            blockers=tuple(blockers),
        )

    def _ensure_fixture_manifests(self) -> tuple[int, int]:
        if not self.config.ensure_fixture_manifests:
            return 0, 0
        cached_scopes: set[tuple[str, str]] = set()
        for raw in self.repository.raw_payloads("fixtures"):
            payload = raw.get("payload") if isinstance(raw, dict) else None
            parameters = payload.get("parameters") if isinstance(payload, dict) else None
            if not isinstance(parameters, dict):
                continue
            league_id = str(parameters.get("league") or "")
            season = str(parameters.get("season") or "")
            if league_id and season:
                cached_scopes.add((league_id, season))
        raw_before = self.repository.raw_payload_count("fixtures")
        hashes: list[str] = []
        for competition_id in PRO_BACKFILL_BATCHES[self.config.batch]:
            league_id = self._provider_league_by_competition[competition_id]
            for season in sorted(PRO_BACKFILL_SEASONS):
                if (league_id, season) in cached_scopes:
                    continue
                response = self.client.request_live(
                    "fixtures",
                    {"league": league_id, "season": season},
                )
                if response.status_code >= 400:
                    raise XgBackfillError(
                        f"PRO_FIXTURE_MANIFEST_HTTP_{response.status_code}:"
                        f"{competition_id}:{season}"
                    )
                provider_errors = response.payload.get("errors")
                if provider_errors not in (None, {}, [], ""):
                    raise XgBackfillError(
                        f"PRO_FIXTURE_MANIFEST_PROVIDER_ERROR:{competition_id}:{season}"
                    )
                parameters = response.payload.get("parameters")
                if not isinstance(parameters, dict) or (
                    str(parameters.get("league") or "") != league_id
                    or str(parameters.get("season") or "") != season
                ):
                    raise XgBackfillError(
                        f"PRO_FIXTURE_MANIFEST_IDENTITY_MISMATCH:{competition_id}:{season}"
                    )
                digest = self._persist_response("fixtures", response)
                hashes.append(digest)
                self._quota_guard(response)
                self._throttle()
        raw_after = self.repository.raw_payload_count("fixtures")
        if raw_after - raw_before != len(hashes):
            raise XgBackfillError(
                f"PRO_FIXTURE_MANIFEST_RAW_COUNT_MISMATCH:"
                f"{raw_before}:{raw_after}:{len(hashes)}"
            )
        if any(
            not self.repository.raw_payload_exists(sha256=digest, endpoint="fixtures")
            for digest in hashes
        ):
            raise XgBackfillError("PRO_FIXTURE_MANIFEST_RAW_HASH_MISSING")
        return len(hashes), len(hashes)

    def _target_fixtures(self) -> list[dict[str, Any]]:
        fixtures: dict[str, dict[str, Any]] = {}
        for fixture in self.repository.fixture_payloads():
            fixture_id = fixture_id_from_payload(fixture)
            fixture_data = fixture.get("fixture") if isinstance(fixture, dict) else None
            league = fixture.get("league") if isinstance(fixture, dict) else None
            status = fixture_data.get("status") if isinstance(fixture_data, dict) else None
            season = str(league.get("season") or "") if isinstance(league, dict) else ""
            if (
                fixture_id
                and isinstance(status, dict)
                and str(status.get("short") or "") in FINISHED_STATUS
                and season in PRO_BACKFILL_SEASONS
                and self._competition_id(fixture)
            ):
                fixtures[fixture_id] = fixture
        return sorted(
            fixtures.values(),
            key=lambda item: (
                str(item.get("league", {}).get("id") or ""),
                str(item.get("league", {}).get("season") or ""),
                str(item.get("fixture", {}).get("date") or ""),
                fixture_id_from_payload(item),
            ),
        )

    def _competition_id(self, fixture: dict[str, Any]) -> str:
        league = fixture.get("league") if isinstance(fixture, dict) else None
        if not isinstance(league, dict):
            return ""
        league_id = str(league.get("id") or "")
        season = str(league.get("season") or "")
        direct = self._competition_by_scope.get((league_id, season))
        if direct:
            return direct
        for (scope_league, _scope_season), competition_id in self._competition_by_scope.items():
            if scope_league == league_id and season in PRO_BACKFILL_SEASONS:
                return competition_id
        return ""

    def _fetch_and_persist(
        self,
        fixture: dict[str, Any],
    ) -> tuple[str, bool, int | None]:
        fixture_id = fixture_id_from_payload(fixture)
        response = self.client.request_live("statistics", {"fixture": fixture_id})
        if response.status_code >= 400:
            raise XgBackfillError(f"PRO_STATISTICS_HTTP_{response.status_code}:{fixture_id}")
        payload_fixture = XgHistoryBackfillService._statistics_fixture_id(response.payload)
        if payload_fixture != fixture_id:
            raise XgBackfillError(
                f"PRO_STATISTICS_FIXTURE_IDENTITY_MISMATCH:{fixture_id}:{payload_fixture}"
            )
        digest = self._persist_response("statistics", response)
        provider_errors = response.payload.get("errors")
        if provider_errors not in (None, {}, [], ""):
            raise XgBackfillError(f"PRO_STATISTICS_PROVIDER_ERROR:{fixture_id}")
        quota = self._quota_guard(response)
        rows = parse_team_xg_matches(
            fixture_payload=fixture,
            statistics_payload=response.payload,
            captured_at=response.captured_at,
            raw_payload_sha256=digest,
        )
        return digest, len(rows) == 2, quota.daily_remaining

    def _persist_response(self, endpoint: str, response: LiveApiFootballResponse) -> str:
        digest = sha256_payload(
            response.payload,
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        )
        self.repository.save_raw_payload(
            sha256=digest,
            endpoint=endpoint,
            captured_at=response.captured_at,
            payload=response.payload,
        )
        if not self.repository.raw_payload_exists(sha256=digest, endpoint=endpoint):
            raise XgBackfillError(f"PRO_RAW_WRITE_GUARD_FAILED:{endpoint}:{digest}")
        return digest

    def _quota_guard(self, response: LiveApiFootballResponse) -> ProviderQuota:
        quota = parse_api_football_quota(
            headers=response.headers,
            payload=response.payload,
            observed_at=response.captured_at,
        )
        if quota.daily_remaining is not None and quota.daily_remaining <= self.config.quota_reserve:
            raise XgBackfillError("BACKFILL_QUOTA_GUARD")
        return quota

    def _throttle(self) -> None:
        time.sleep(60 / self.config.requests_per_minute)


def run_xg_history_backfill(
    *,
    competition_id: str | None = None,
    client: LiveApiFootballPort | None = None,
    repository: XgBackfillRepository | None = None,
    now: datetime | None = None,
) -> XgBackfillResult:
    requested_competition_id = (
        competition_id or os.environ.get("W2_XG_BACKFILL_COMPETITION_ID", "")
    ).strip()
    if requested_competition_id not in REQUIRED_MATCHDAY_COMPETITIONS:
        raise XgBackfillError("XG_LIVE_COMPETITION_EXACT13_REQUIRED")
    return XgHistoryBackfillService(
        client=client,
        repository=repository,
        now=now,
        config=XgBackfillConfig(
            competition_ids=(requested_competition_id,),
            recent_match_count=int(os.environ.get("W2_XG_BACKFILL_RECENT_MATCHES", "5")),
            request_budget=int(os.environ.get("W2_XG_BACKFILL_REQUEST_BUDGET", "120")),
            quota_reserve=int(os.environ.get("W2_API_MINIMUM_RESERVE", "1500")),
            daily_hard_cap=env_int("W2_PROVIDER_DAILY_HARD_CAP", default=7500),
            daily_reserve=env_int("W2_PROVIDER_DAILY_RESERVE", default=1500),
            statistics_daily_hard_cap=env_int(
                "W2_STATISTICS_DAILY_HARD_CAP",
                default=5500,
            ),
            source_revision=os.environ.get("W2_SERVICE_VERSION", "LOCAL_UNDEPLOYED"),
        ),
    ).run()


def materialize_saved_xg(
    *,
    repository: XgBackfillRepository | None = None,
    now: datetime | None = None,
    persist: bool = True,
) -> XgBackfillResult:
    return XgHistoryBackfillService(
        repository=repository,
        now=now,
        config=XgBackfillConfig(
            competition_ids=tuple(sorted(REQUIRED_MATCHDAY_COMPETITIONS)),
            min_rolling_matches=int(os.environ.get("W2_XG_MIN_ROLLING_MATCHES", "3")),
            max_rolling_matches=int(os.environ.get("W2_XG_MAX_ROLLING_MATCHES", "5")),
            source_revision=os.environ.get("W2_SERVICE_VERSION", "LOCAL_UNDEPLOYED"),
        ),
    ).run_saved_raw(persist=persist)


def write_backfill_report(path: Path, result: XgBackfillResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(result.as_dict()) + "\n", encoding="utf-8")
