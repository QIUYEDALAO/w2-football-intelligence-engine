from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from w2.competitions.league_whitelist_scope import load_league_whitelist_scope
from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryEntry
from w2.ingestion.authoritative_lineup import (
    AuthoritativeLineupError,
    validate_authoritative_lineup,
)
from w2.ingestion.free_fixture_bridge import (
    FREE_MIN_PROVIDER_REMAINING,
    FREE_PROVIDER_DAILY_LIMIT,
    FREE_W2_DAILY_CALL_CEILING,
    FreeFixtureBridgeConfig,
    PlannedFreeCall,
    plan_fixture_discovery,
    plan_fixture_followups,
)
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.matchday.intake_v2 import (
    MatchdayCheckpoint,
    MatchdayCompetitionPolicy,
    build_checkpoint_plans,
    endpoint_capture_contract,
    normalize_matchday_odds_payload,
    parse_utc,
    request_task_key,
    sanitize_params,
    stable_hash,
)
from w2.matchday.repository import MatchdayRuntimeRepository
from w2.matchday.timezone import BeijingOperationalDayPolicy
from w2.prematch.read_model_projection import ProjectionSourceEvent
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse
from w2.providers.quota import parse_api_football_quota, provider_daily_hard_cap_decision

FREE_BRIDGE_OFF = "OFF"
FREE_BRIDGE_SHADOW_ONLY = "SHADOW_ONLY"
FREE_BRIDGE_EXPECTED_WHITELIST_SIZE = 13
FREE_BRIDGE_LINEUP_CACHE_SECONDS = 600
FINISHED_FIXTURE_STATUSES = frozenset({"FT", "AET", "PEN"})


class UsageRepository(Protocol):
    def request_count_since(self, since: datetime, *, include_quota_usage: bool = True) -> int: ...

    def provider_quota_snapshot(self, day_start: datetime) -> dict[str, int | None]: ...

    def write_run_audit(self, payload: dict[str, Any]) -> None: ...


class EvidenceRepository(Protocol):
    def save_raw_payload(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: Mapping[str, Any],
    ) -> bool: ...

    def insert_endpoint_capture(self, capture: Mapping[str, Any]) -> str: ...

    def latest_endpoint_capture(
        self,
        *,
        request_task_key: str,
        since: datetime,
    ) -> dict[str, Any] | None: ...

    def upsert_fixture_identities_with_business_changes(
        self,
        fixtures: Sequence[Mapping[str, Any]],
    ) -> tuple[int, list[str]]: ...

    def insert_market_observations(self, observations: Sequence[Mapping[str, Any]]) -> int: ...

    def upsert_checkpoint_plan(self, plan: Mapping[str, Any] | Any) -> str: ...

    def transition_checkpoint(
        self,
        *,
        fixture_id: str,
        competition_id: str,
        season: str,
        checkpoint: str,
        policy_version: str,
        status: str,
        capture_id: str | None = None,
        now: datetime | None = None,
        claim_token: str | None = None,
    ) -> None: ...

    def link_endpoint_capture_plans(
        self,
        *,
        capture_id: str,
        plan_ids: Sequence[str],
        endpoint: str,
        linked_at: datetime,
    ) -> list[dict[str, Any]]: ...


class LineupRepository(Protocol):
    def save_lineup_snapshots(
        self,
        *,
        fixture_id: str,
        captured_at: datetime,
        raw_sha256: str,
        payload: dict[str, Any],
        materialize_baselines: bool = True,
        kickoff_at: datetime | None = None,
        source_capture_id: str | None = None,
        expected_team_ids: tuple[str, str] | None = None,
    ) -> int: ...


@dataclass(frozen=True)
class BridgeFixture:
    provider_fixture_id: str
    fixture_id: str
    competition_id: str
    season: str
    kickoff_utc: datetime
    fixture_status: str
    home_provider_team_id: str
    away_provider_team_id: str
    payload: dict[str, Any]
    policy: MatchdayCompetitionPolicy


class BridgeHardStop(RuntimeError):
    pass


def free_fixture_bridge_mode() -> str:
    return os.environ.get("W2_FREE_BRIDGE_MODE", FREE_BRIDGE_OFF).strip().upper()


def free_fixture_bridge_enabled() -> bool:
    return free_fixture_bridge_mode() == FREE_BRIDGE_SHADOW_ONLY


def run_free_fixture_bridge_shadow(
    *,
    now: datetime | None = None,
    client: ApiFootballClient | None = None,
    usage_repository: UsageRepository | None = None,
    evidence_repository: EvidenceRepository | None = None,
    lineup_repository: LineupRepository | None = None,
    registry: CompetitionRegistry | None = None,
    mode: str | None = None,
    source_revision: str | None = None,
    expected_whitelist_size: int = FREE_BRIDGE_EXPECTED_WHITELIST_SIZE,
    require_persistent_ledger: bool = True,
    materialize_public_artifacts: Callable[[list[ProjectionSourceEvent]], list[str]] | None = None,
) -> dict[str, Any]:
    selected_mode = (mode or free_fixture_bridge_mode()).strip().upper()
    if selected_mode == FREE_BRIDGE_OFF:
        return _disabled_result()
    if selected_mode != FREE_BRIDGE_SHADOW_ONLY:
        return _blocked_result("FREE_BRIDGE_MODE_INVALID")
    if require_persistent_ledger and os.environ.get(
        "W2_PROVIDER_REQUEST_LEDGER_ENABLED", "false"
    ).lower() != "true":
        return _blocked_result("PERSISTENT_PROVIDER_LEDGER_REQUIRED")

    current = (now or datetime.now(UTC)).astimezone(UTC)
    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    usage = usage_repository or FutureRefreshDbRepository()
    evidence = evidence_repository or MatchdayRuntimeRepository()
    lineups = lineup_repository or FutureRefreshDbRepository()
    provider = client or ApiFootballClient(allow_live=True)
    source = source_revision or os.environ.get("W2_GIT_SHA", "UNKNOWN")
    requests: list[dict[str, Any]] = []
    blockers: list[str] = []
    provider_calls = 0
    observations_written = 0
    lineups_written = 0
    identities_written = 0
    selected_fixture_ids: list[str] = []
    collection_states: dict[str, list[str]] = {}
    actual_calls_today = 0
    provider_remaining: int | None = None
    provider_limit: int | None = None
    policies: dict[str, MatchdayCompetitionPolicy] = {}
    fixtures: list[BridgeFixture] = []
    projection_events: list[ProjectionSourceEvent] = []

    try:
        policies = _runtime_policies(
            registry or CompetitionRegistry(),
            expected_whitelist_size=expected_whitelist_size,
        )
        allowed_league_ids = frozenset(policy.provider_league_id for policy in policies.values())
        actual_calls_today = usage.request_count_since(day_start)
        quota_snapshot = usage.provider_quota_snapshot(day_start)
        provider_remaining = quota_snapshot.get("remaining")
        provider_limit = quota_snapshot.get("daily_limit")

        def call(
            endpoint: str,
            params: dict[str, str],
            *,
            priority: str,
            fixture: BridgeFixture | None = None,
            matching_plans: Sequence[Mapping[str, Any]] = (),
            allow_unknown_quota: bool = False,
        ) -> tuple[LiveApiFootballResponse, dict[str, Any], int, int | None]:
            nonlocal actual_calls_today, provider_calls, provider_limit, provider_remaining
            if not allow_unknown_quota:
                decision = provider_daily_hard_cap_decision(
                    actual_calls_today=actual_calls_today,
                    planned_calls=1,
                    daily_cap=FREE_W2_DAILY_CALL_CEILING,
                    reserve_bucket=0,
                    provider_remaining=provider_remaining,
                    min_provider_remaining=FREE_MIN_PROVIDER_REMAINING,
                    require_provider_remaining=True,
                )
                if not decision["allowed"]:
                    raise BridgeHardStop(str(decision["blocker"]))
            elif actual_calls_today >= FREE_W2_DAILY_CALL_CEILING:
                raise BridgeHardStop("DAILY_PROVIDER_HARD_CAP_EXCEEDED")
            daily_index = actual_calls_today + 1
            try:
                response = provider.request_live(endpoint, params)
            except Exception as exc:
                provider_calls += 1
                actual_calls_today += 1
                requests.append(
                    _request_audit(
                        endpoint=endpoint,
                        params=params,
                        priority=priority,
                        fixture_id=fixture.provider_fixture_id if fixture else None,
                        daily_index=daily_index,
                        daily_count_after=actual_calls_today,
                        status_code=None,
                        provider_remaining=provider_remaining,
                        error_code=exc.__class__.__name__,
                    )
                )
                raise BridgeHardStop(f"PROVIDER_TRANSPORT_{exc.__class__.__name__}") from exc
            provider_calls += 1
            actual_calls_today = max(
                actual_calls_today + 1,
                usage.request_count_since(day_start),
            )
            error_code = _response_error(response)
            if error_code is None and fixture is not None and endpoint == "odds":
                try:
                    _validate_fixture_scoped_payload(
                        response.payload,
                        fixture.provider_fixture_id,
                    )
                except BridgeHardStop as exc:
                    error_code = str(exc)
            if (
                error_code is None
                and fixture is not None
                and endpoint == "lineups"
                and response.payload.get("response")
            ):
                try:
                    validate_authoritative_lineup(
                        response.payload["response"],
                        expected_team_ids=(
                            fixture.home_provider_team_id,
                            fixture.away_provider_team_id,
                        ),
                        captured_at=response.captured_at,
                        kickoff_utc=fixture.kickoff_utc,
                    )
                except AuthoritativeLineupError as exc:
                    error_code = exc.code
            capture = _persist_response(
                response,
                evidence=evidence,
                fixture=fixture,
                matching_plans=matching_plans,
                error_code=error_code,
            )
            quota = parse_api_football_quota(
                headers=response.headers,
                payload=response.payload,
                observed_at=response.captured_at,
            )
            observed_remaining = quota.daily_remaining
            estimated_remaining = (
                max(provider_remaining - 1, 0) if provider_remaining is not None else None
            )
            candidates = [
                value for value in (observed_remaining, estimated_remaining) if value is not None
            ]
            provider_remaining = min(candidates) if candidates else None
            limits = [value for value in (provider_limit, quota.daily_limit) if value is not None]
            provider_limit = min(limits) if limits else None
            requests.append(
                _request_audit(
                    endpoint=endpoint,
                    params=params,
                    priority=priority,
                    fixture_id=fixture.provider_fixture_id if fixture else None,
                    daily_index=daily_index,
                    daily_count_after=actual_calls_today,
                    status_code=response.status_code,
                    provider_remaining=provider_remaining,
                    error_code=error_code,
                    captured_at=response.captured_at,
                    capture_id=str(capture["capture_id"]),
                )
            )
            if error_code is not None:
                raise BridgeHardStop(error_code)
            if provider_remaining is None:
                raise BridgeHardStop("DAILY_QUOTA_UNKNOWN")
            if provider_limit != FREE_PROVIDER_DAILY_LIMIT:
                raise BridgeHardStop("FREE_PROVIDER_DAILY_LIMIT_MISMATCH")
            if provider_remaining < FREE_MIN_PROVIDER_REMAINING:
                raise BridgeHardStop("PROVIDER_RESERVE_BREACHED")
            return response, capture, actual_calls_today, provider_remaining

        if provider_remaining is None or provider_limit is None:
            call("status", {}, priority="P0", allow_unknown_quota=True)
        if provider_limit != FREE_PROVIDER_DAILY_LIMIT:
            raise BridgeHardStop("FREE_PROVIDER_DAILY_LIMIT_MISMATCH")

        discovery_date = (
            BeijingOperationalDayPolicy()
            .current_window(now_utc=current)
            .local_date.isoformat()
        )
        discovery_params = {"date": discovery_date}
        discovery_key = request_task_key("fixtures", discovery_params)
        cached_discovery = evidence.latest_endpoint_capture(
            request_task_key=discovery_key,
            since=day_start,
        )
        if cached_discovery is None:
            discovery_plan = plan_fixture_discovery(
                date_utc=discovery_date,
                actual_calls_today=actual_calls_today,
                provider_remaining=provider_remaining,
                config=FreeFixtureBridgeConfig(enabled=True),
            )
            if discovery_plan["planned_calls"] != 1:
                raise BridgeHardStop(str(discovery_plan["status"]))
            discovery_response, discovery_capture, _, _ = call(
                "fixtures",
                discovery_params,
                priority="P0",
            )
            fixture_payload = discovery_response.payload
        else:
            fixture_payload = dict(cached_discovery["payload"])
            discovery_capture = dict(cached_discovery["capture"])
            requests.append(
                _skip_audit(
                    endpoint="fixtures",
                    params=discovery_params,
                    reason="DISCOVERY_CACHED_NO_CALL",
                )
            )

        fixtures = _target_fixtures(fixture_payload, policies)
        identities = _fixture_identities(
            fixtures,
            raw_payload_sha256=str(discovery_capture["raw_payload_sha256"]),
            endpoint_capture_id=str(discovery_capture["capture_id"]),
            captured_at=parse_utc(discovery_capture["provider_captured_at"]) or current,
        )
        identities_written, changed = evidence.upsert_fixture_identities_with_business_changes(
            identities
        )
        for identity in identities:
            if str(identity["fixture_id"]) not in changed:
                continue
            projection_events.append(
                ProjectionSourceEvent.create(
                    fixture_id=str(identity["provider_fixture_id"]),
                    event_type="FIXTURE_CHANGED",
                    event_id=f"fixture:{identity['identity_hash']}",
                    event_at=parse_utc(discovery_capture["provider_captured_at"]) or current,
                    payload=identity,
                )
            )

        calls: dict[str, tuple[PlannedFreeCall, BridgeFixture, list[dict[str, Any]]]] = {}
        for fixture in fixtures:
            states, plans = _collection_states(fixture, now=current)
            collection_states[fixture.fixture_id] = states
            for plan in plans:
                evidence.upsert_checkpoint_plan(plan)
            odds_plans = [
                plan for plan in plans if plan["status"] == "DUE" and "odds" in plan["endpoints"]
            ]
            lineup_plans = [
                plan
                for plan in plans
                if plan["status"] == "DUE" and "lineups" in plan["endpoints"]
            ]
            if not odds_plans and not lineup_plans:
                continue
            selected_fixture_ids.append(fixture.provider_fixture_id)
            cached_keys: set[str] = set()
            odds_key = request_task_key("odds", {"fixture": fixture.provider_fixture_id})
            odds_since = max(
                current - timedelta(seconds=fixture.policy.odds_max_age_seconds),
                min(
                    (parse_utc(plan["window_start"]) or current for plan in odds_plans),
                    default=current - timedelta(seconds=fixture.policy.odds_max_age_seconds),
                ),
            )
            cached_odds = evidence.latest_endpoint_capture(
                request_task_key=odds_key,
                since=odds_since,
            )
            if cached_odds is not None:
                cached_keys.add(odds_key)
                _complete_plans(
                    evidence,
                    fixture=fixture,
                    plans=odds_plans,
                    endpoint="odds",
                    capture=dict(cached_odds["capture"]),
                    now=current,
                )
                requests.append(
                    _skip_audit(
                        endpoint="odds",
                        params={"fixture": fixture.provider_fixture_id},
                        reason="FRESH_CAPTURE_CACHE_HIT",
                        fixture_id=fixture.provider_fixture_id,
                    )
                )
            lineup_key = request_task_key("lineups", {"fixture": fixture.provider_fixture_id})
            lineup_since = max(
                current - timedelta(seconds=FREE_BRIDGE_LINEUP_CACHE_SECONDS),
                min(
                    (parse_utc(plan["window_start"]) or current for plan in lineup_plans),
                    default=current - timedelta(seconds=FREE_BRIDGE_LINEUP_CACHE_SECONDS),
                ),
            )
            cached_lineups = evidence.latest_endpoint_capture(
                request_task_key=lineup_key,
                since=lineup_since,
            )
            if cached_lineups is not None:
                cached_keys.add(lineup_key)
                _complete_plans(
                    evidence,
                    fixture=fixture,
                    plans=lineup_plans,
                    endpoint="lineups",
                    capture=dict(cached_lineups["capture"]),
                    now=current,
                )
                requests.append(
                    _skip_audit(
                        endpoint="lineups",
                        params={"fixture": fixture.provider_fixture_id},
                        reason="FRESH_CAPTURE_CACHE_HIT",
                        fixture_id=fixture.provider_fixture_id,
                    )
                )
            fixture_plan = plan_fixture_followups(
                fixture_payload=fixture_payload,
                allowed_league_ids=allowed_league_ids,
                due_fixture_ids=[fixture.provider_fixture_id],
                actual_calls_today=actual_calls_today,
                provider_remaining=provider_remaining,
                enrichment_endpoints=("lineups",) if lineup_plans else (),
                cached_request_keys=frozenset(cached_keys),
                config=FreeFixtureBridgeConfig(enabled=True),
            )
            for planned in fixture_plan["calls"]:
                matching = odds_plans if planned.request.endpoint == "odds" else lineup_plans
                calls.setdefault(planned.cache_key, (planned, fixture, matching))

        if not selected_fixture_ids:
            requests.append(
                _skip_audit(
                    endpoint="fixture_followups",
                    params={},
                    reason="NO_DUE_TARGET_FIXTURES_NO_IDLE_POLLING",
                )
            )

        priority_order = {"P0": 0, "P1": 1, "P2": 2}
        ordered_calls = sorted(
            calls.values(),
            key=lambda item: (
                priority_order[item[0].priority],
                item[1].kickoff_utc,
                item[1].provider_fixture_id,
                item[0].request.endpoint,
            ),
        )
        for planned, fixture, matching_plans in ordered_calls:
            response, capture, _, _ = call(
                planned.request.endpoint,
                dict(planned.request.params),
                priority=planned.priority,
                fixture=fixture,
                matching_plans=matching_plans,
            )
            raw_sha = str(capture["raw_payload_sha256"])
            if planned.request.endpoint == "odds":
                _validate_fixture_scoped_payload(response.payload, fixture.provider_fixture_id)
                rows, rejections = normalize_matchday_odds_payload(
                    response.payload,
                    captured_at=response.captured_at,
                    ingested_at=response.captured_at,
                    raw_payload_sha256=raw_sha,
                    source_revision=source,
                    capture_id=str(capture["capture_id"]),
                    competition_id=fixture.competition_id,
                )
                if any(
                    item.get("reason") == "OBSERVATION_IDENTITY_CONFLICT"
                    for item in rejections
                ):
                    raise BridgeHardStop("OBSERVATION_NORMALIZATION_CONFLICT")
                inserted = evidence.insert_market_observations(rows)
                observations_written += inserted
                if inserted > 0:
                    projection_events.append(
                        ProjectionSourceEvent.create(
                            fixture_id=fixture.provider_fixture_id,
                            event_type="ODDS_CHANGED",
                            event_id=f"odds:{capture['capture_id']}",
                            event_at=response.captured_at,
                            payload={
                                "observation_ids": sorted(
                                    str(row["observation_id"]) for row in rows
                                ),
                                "inserted": inserted,
                            },
                        )
                    )
            elif planned.request.endpoint == "lineups":
                _validate_fixture_scoped_payload(
                    response.payload,
                    fixture.provider_fixture_id,
                    require_fixture_wrapper=False,
                )
                if response.payload.get("response"):
                    lineups_written += lineups.save_lineup_snapshots(
                        fixture_id=fixture.fixture_id,
                        captured_at=response.captured_at,
                        raw_sha256=raw_sha,
                        payload=response.payload,
                        kickoff_at=fixture.kickoff_utc,
                        source_capture_id=str(capture["capture_id"]),
                        expected_team_ids=(
                            fixture.home_provider_team_id,
                            fixture.away_provider_team_id,
                        ),
                    )
            _complete_plans(
                evidence,
                fixture=fixture,
                plans=matching_plans,
                endpoint=planned.request.endpoint,
                capture=capture,
                now=current,
            )
    except BridgeHardStop as exc:
        blockers.append(str(exc))
    except (TypeError, ValueError) as exc:
        blockers.append(str(exc) or exc.__class__.__name__)

    materialized_fixture_ids: list[str] = []
    if projection_events and materialize_public_artifacts is not None:
        try:
            materialized_fixture_ids = materialize_public_artifacts(projection_events)
        except Exception as exc:
            blockers.append(f"PROJECTION_MATERIALIZATION_FAILED:{exc.__class__.__name__}")

    result = {
        "schema_version": "w2.free_fixture_bridge_runtime.v1",
        "status": "BLOCKED" if blockers else "SHADOW_COMPLETE",
        "mode": FREE_BRIDGE_SHADOW_ONLY,
        "provider_calls": provider_calls,
        "actual_calls_today": actual_calls_today,
        "provider_daily_limit": provider_limit,
        "provider_remaining": provider_remaining,
        "active_whitelist_count": len(policies),
        "fixture_identity_count": len(fixtures),
        "fixture_identities_written": identities_written,
        "market_observations_written": observations_written,
        "lineup_snapshots_written": lineups_written,
        "selected_fixture_ids": sorted(set(selected_fixture_ids)),
        "materialized_fixture_ids": materialized_fixture_ids,
        "collection_states": collection_states,
        "requests": requests,
        "blockers": blockers,
        "automatic_retries": 0,
        "provider_ids_batching": False,
        "candidate": False,
        "formal_recommendation": False,
        "recommendation_lock": False,
        "production": False,
        "round_3_started": False,
    }
    usage.write_run_audit(
        {
            "generated_at_utc": current.isoformat().replace("+00:00", "Z"),
            "competition_id": "free_plan_fixture_bridge",
            "request_count": provider_calls,
            "remaining_quota": result["provider_remaining"],
            "fixture_count": result["fixture_identity_count"],
            "mapping_count": 0,
            "market_snapshot_count": observations_written,
            "ledger_appended_count": observations_written,
            "selected_market_fixture_ids": result["selected_fixture_ids"],
            "blockers": blockers,
            "requests": requests,
        }
    )
    return result


def _runtime_policies(
    registry: CompetitionRegistry,
    *,
    expected_whitelist_size: int,
) -> dict[str, MatchdayCompetitionPolicy]:
    scope = load_league_whitelist_scope(registry)
    if len(scope.all_whitelist) != expected_whitelist_size:
        raise BridgeHardStop("FREE_BRIDGE_WHITELIST_SIZE_MISMATCH")
    policies = {
        competition_id: _policy_from_entry(scope.entries[competition_id])
        for competition_id in scope.all_whitelist
    }
    league_ids = [policy.provider_league_id for policy in policies.values()]
    if any(not value for value in league_ids) or len(set(league_ids)) != len(league_ids):
        raise BridgeHardStop("FREE_BRIDGE_PROVIDER_LEAGUE_MAPPING_UNSAFE")
    return policies


def _policy_from_entry(entry: CompetitionRegistryEntry) -> MatchdayCompetitionPolicy:
    source = dict(entry.matchday_policy or {})
    checkpoints = tuple(
        MatchdayCheckpoint(
            name=str(item["name"]),
            offset_seconds_before_kickoff=int(item["offset_seconds_before_kickoff"]),
            endpoints=tuple(str(value) for value in item.get("endpoints") or ()),
            grace_seconds=int(item.get("grace_seconds") or 0),
            enabled=bool(item.get("enabled") is True),
        )
        for item in source.get("checkpoints") or _operational_checkpoints()
        if isinstance(item, Mapping)
    )
    return MatchdayCompetitionPolicy(
        competition_id=entry.competition_id,
        enabled=True,
        provider="api_football",
        provider_league_id=str(entry.provider_mapping.get("api_football_league_id") or ""),
        season=str(entry.provider_mapping.get("api_football_season") or entry.season),
        discovery_horizon_hours=int(source.get("discovery_horizon_hours") or 24),
        fixture_status_allowlist=tuple(source.get("fixture_status_allowlist") or ("NS", "TBD")),
        checkpoints=checkpoints,
        endpoint_matrix={
            str(key): tuple(str(value) for value in values)
            for key, values in dict(source.get("endpoint_matrix") or {}).items()
        },
        odds_max_age_seconds=int(source.get("odds_max_age_seconds") or 3600),
        lineup_requirement=str(source.get("lineup_requirement") or "ADVISORY"),
        request_caps={"tick_hard_cap": 20, "daily_hard_cap": 80, "quota_reserve": 20},
        provider_allowlist=("status", "fixtures", "odds", "lineups"),
        feature_enrichment_policy={
            "injuries": "DISABLED_BY_POLICY",
            "statistics": "POSTMATCH_STATE_ONLY_NOT_AUTOMATIC",
        },
    )


def _operational_checkpoints() -> tuple[dict[str, Any], ...]:
    return (
        _checkpoint("T12_ODDS", 12 * 3600, ("odds",), 1800),
        _checkpoint("T6_ODDS", 6 * 3600, ("odds",), 1800),
        _checkpoint("T3_ODDS", 3 * 3600, ("odds",), 1800),
        _checkpoint("T60_ODDS_LINEUPS", 3600, ("odds", "lineups"), 1200),
        _checkpoint("T30_LINEUPS", 1800, ("lineups",), 900),
    )


def _checkpoint(
    name: str,
    offset: int,
    endpoints: tuple[str, ...],
    grace: int,
) -> dict[str, Any]:
    return {
        "name": name,
        "offset_seconds_before_kickoff": offset,
        "endpoints": list(endpoints),
        "grace_seconds": grace,
        "enabled": True,
    }


def _target_fixtures(
    payload: Mapping[str, Any],
    policies: Mapping[str, MatchdayCompetitionPolicy],
) -> list[BridgeFixture]:
    response = payload.get("response")
    if not isinstance(response, list) or any(not isinstance(row, Mapping) for row in response):
        raise BridgeHardStop("FREE_BRIDGE_SCHEMA_UNSAFE")
    by_league = {policy.provider_league_id: policy for policy in policies.values()}
    fixtures: dict[str, BridgeFixture] = {}
    for source_row in response:
        row = dict(source_row)
        league = row.get("league")
        fixture = row.get("fixture")
        teams = row.get("teams")
        if not isinstance(league, Mapping):
            continue
        policy = by_league.get(str(league.get("id") or ""))
        if policy is None:
            continue
        if not isinstance(fixture, Mapping) or not isinstance(teams, Mapping):
            raise BridgeHardStop("FREE_BRIDGE_SCHEMA_UNSAFE")
        provider_fixture_id = str(fixture.get("id") or "")
        kickoff = parse_utc(fixture.get("date"))
        home = teams.get("home")
        away = teams.get("away")
        if (
            not provider_fixture_id
            or kickoff is None
            or not isinstance(home, Mapping)
            or not isinstance(away, Mapping)
            or not home.get("id")
            or not away.get("id")
        ):
            raise BridgeHardStop("FREE_BRIDGE_EMPTY_OR_INVALID_FIXTURE_ID")
        candidate = BridgeFixture(
            provider_fixture_id=provider_fixture_id,
            fixture_id=f"api_football:{provider_fixture_id}",
            competition_id=policy.competition_id,
            season=str(league.get("season") or policy.season),
            kickoff_utc=kickoff,
            fixture_status=str(
                fixture.get("status", {}).get("short")
                if isinstance(fixture.get("status"), Mapping)
                else ""
            ),
            home_provider_team_id=str(home["id"]),
            away_provider_team_id=str(away["id"]),
            payload=row,
            policy=policy,
        )
        existing = fixtures.get(provider_fixture_id)
        if existing is not None and stable_hash(existing.payload) != stable_hash(row):
            raise BridgeHardStop("FREE_BRIDGE_FIXTURE_IDENTITY_CONFLICT")
        fixtures[provider_fixture_id] = candidate
    return sorted(fixtures.values(), key=lambda item: (item.kickoff_utc, item.fixture_id))


def _fixture_identities(
    fixtures: Sequence[BridgeFixture],
    *,
    raw_payload_sha256: str,
    endpoint_capture_id: str,
    captured_at: datetime,
) -> list[dict[str, Any]]:
    rows = []
    for fixture in fixtures:
        body = {
            "fixture_id": fixture.fixture_id,
            "provider": "api_football",
            "provider_fixture_id": fixture.provider_fixture_id,
            "competition_id": fixture.competition_id,
            "provider_league_id": fixture.policy.provider_league_id,
            "season": fixture.season,
            "kickoff_utc": fixture.kickoff_utc.isoformat().replace("+00:00", "Z"),
            "fixture_status": fixture.fixture_status,
            "home_provider_team_id": fixture.home_provider_team_id,
            "away_provider_team_id": fixture.away_provider_team_id,
            "home_w2_team_id": None,
            "away_w2_team_id": None,
            "team_identity_status": "REVIEW_REQUIRED",
            "raw_payload_sha256": raw_payload_sha256,
            "endpoint_capture_id": endpoint_capture_id,
            "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
            "payload": fixture.payload,
            "schema_version": "MatchdayFixtureIdentityV1",
        }
        rows.append({**body, "identity_hash": stable_hash(body)})
    return rows


def _collection_states(
    fixture: BridgeFixture,
    *,
    now: datetime,
) -> tuple[list[str], list[dict[str, Any]]]:
    states = ["DISCOVERY"]
    if fixture.fixture_status in FINISHED_FIXTURE_STATUSES:
        states.append("POSTMATCH_STATISTICS")
        return states, []
    if fixture.fixture_status not in fixture.policy.fixture_status_allowlist:
        return states, []
    plans = [
        plan.as_dict()
        for plan in build_checkpoint_plans(
            fixture_id=fixture.fixture_id,
            competition_id=fixture.competition_id,
            season=fixture.season,
            kickoff_utc=fixture.kickoff_utc,
            now=now,
            policy=fixture.policy,
        )
    ]
    due_endpoints = {
        endpoint
        for plan in plans
        if plan["status"] == "DUE"
        for endpoint in plan["endpoints"]
    }
    if "odds" in due_endpoints:
        states.append("PREMATCH_MARKET")
    if "lineups" in due_endpoints:
        states.append("LINEUP_WINDOW")
    return states, plans


def _persist_response(
    response: LiveApiFootballResponse,
    *,
    evidence: EvidenceRepository,
    fixture: BridgeFixture | None,
    matching_plans: Sequence[Mapping[str, Any]],
    error_code: str | None,
) -> dict[str, Any]:
    payload = dict(response.payload)
    raw_sha = stable_hash(payload)
    evidence.save_raw_payload(
        sha256=raw_sha,
        endpoint=response.endpoint,
        captured_at=response.captured_at,
        payload=payload,
    )
    quota = parse_api_football_quota(
        headers=response.headers,
        payload=payload,
        observed_at=response.captured_at,
    )
    plan_ids = [_plan_id(plan) for plan in matching_plans]
    capture = endpoint_capture_contract(
        endpoint=response.endpoint,
        params=response.params,
        requested_at=response.requested_at or response.captured_at,
        provider_captured_at=response.captured_at,
        status_code=response.status_code,
        elapsed_ms=response.elapsed_ms,
        payload=payload,
        fixture_id=fixture.fixture_id if fixture else None,
        competition_id=fixture.competition_id if fixture else None,
        checkpoint=",".join(str(plan["checkpoint"]) for plan in matching_plans) or None,
        checkpoint_plan_ids=plan_ids,
        quota_values={
            "daily_remaining": quota.daily_remaining,
            "daily_limit": quota.daily_limit,
            "burst_remaining": quota.burst_remaining,
            "observed_at": quota.observed_at.isoformat().replace("+00:00", "Z"),
            "daily_source": quota.daily_source,
            "daily_limit_source": quota.daily_limit_source,
            "burst_source": quota.burst_source,
        },
    )
    if error_code is not None:
        capture.pop("capture_id", None)
        capture["capture_status"] = "FAILED"
        capture["error_code"] = error_code
        capture["capture_id"] = stable_hash(capture)
    evidence.insert_endpoint_capture(capture)
    return capture


def _complete_plans(
    evidence: EvidenceRepository,
    *,
    fixture: BridgeFixture,
    plans: Sequence[Mapping[str, Any]],
    endpoint: str,
    capture: Mapping[str, Any],
    now: datetime,
) -> None:
    status = "PROVIDER_EMPTY" if capture["capture_status"] == "PROVIDER_EMPTY" else "CAPTURED"
    plan_ids = [_plan_id(plan) for plan in plans if endpoint in plan["endpoints"]]
    if plan_ids:
        evidence.link_endpoint_capture_plans(
            capture_id=str(capture["capture_id"]),
            plan_ids=plan_ids,
            endpoint=endpoint,
            linked_at=parse_utc(capture["provider_captured_at"]) or now,
        )
    for plan in plans:
        if endpoint not in plan["endpoints"]:
            continue
        evidence.transition_checkpoint(
            fixture_id=fixture.fixture_id,
            competition_id=fixture.competition_id,
            season=fixture.season,
            checkpoint=str(plan["checkpoint"]),
            policy_version=str(plan["policy_version"]),
            status=status,
            capture_id=str(capture["capture_id"]),
            now=now,
        )


def _plan_id(plan: Mapping[str, Any]) -> str:
    return stable_hash(
        ":".join(
            str(plan[key])
            for key in (
                "fixture_id",
                "competition_id",
                "season",
                "checkpoint",
                "policy_version",
            )
        )
    )


def _validate_fixture_scoped_payload(
    payload: Mapping[str, Any],
    fixture_id: str,
    *,
    require_fixture_wrapper: bool = True,
) -> None:
    response = payload.get("response")
    if not isinstance(response, list) or any(not isinstance(row, Mapping) for row in response):
        raise BridgeHardStop("FREE_BRIDGE_SCHEMA_UNSAFE")
    if not require_fixture_wrapper:
        return
    returned = set()
    for row in response:
        fixture = row.get("fixture")
        if not isinstance(fixture, Mapping) or not fixture.get("id"):
            raise BridgeHardStop("FREE_BRIDGE_EMPTY_OR_INVALID_FIXTURE_ID")
        returned.add(str(fixture["id"]))
    if returned and returned != {fixture_id}:
        raise BridgeHardStop("FREE_BRIDGE_OUT_OF_WHITELIST_FIXTURE")


def _response_error(response: LiveApiFootballResponse) -> str | None:
    if response.status_code == 429:
        return "PROVIDER_HTTP_429"
    if response.status_code >= 400:
        return f"PROVIDER_HTTP_{response.status_code}"
    errors = response.payload.get("errors")
    if errors not in (None, {}, []):
        serialized = str(errors).lower()
        return "PLAN_RESTRICTED" if "plan" in serialized else "PROVIDER_PAYLOAD_ERROR"
    response_payload = response.payload.get("response")
    expected_type = dict if response.endpoint == "status" else list
    if not isinstance(response_payload, expected_type):
        return "FREE_BRIDGE_SCHEMA_UNSAFE"
    return None


def _request_audit(
    *,
    endpoint: str,
    params: Mapping[str, str],
    priority: str,
    fixture_id: str | None,
    daily_index: int,
    daily_count_after: int,
    status_code: int | None,
    provider_remaining: int | None,
    error_code: str | None,
    captured_at: datetime | None = None,
    capture_id: str | None = None,
) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "params": sanitize_params(params),
        "request_task_key": request_task_key(endpoint, params),
        "fixture_id": fixture_id,
        "priority": priority,
        "actual_call_index": daily_index,
        "daily_count_after": daily_count_after,
        "status_code": status_code,
        "provider_remaining": provider_remaining,
        "captured_at_utc": (
            captured_at.isoformat().replace("+00:00", "Z") if captured_at else None
        ),
        "capture_id": capture_id,
        "error_code": error_code,
        "provider_call": True,
    }


def _skip_audit(
    *,
    endpoint: str,
    params: Mapping[str, str],
    reason: str,
    fixture_id: str | None = None,
) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "params": sanitize_params(params),
        "request_task_key": request_task_key(endpoint, params),
        "fixture_id": fixture_id,
        "skip_reason": reason,
        "provider_call": False,
    }


def _disabled_result() -> dict[str, Any]:
    return {
        "status": "DISABLED",
        "mode": FREE_BRIDGE_OFF,
        "provider_calls": 0,
        "candidate": False,
        "formal_recommendation": False,
        "recommendation_lock": False,
        "production": False,
        "round_3_started": False,
    }


def _blocked_result(blocker: str) -> dict[str, Any]:
    return {
        **_disabled_result(),
        "status": "BLOCKED",
        "mode": free_fixture_bridge_mode(),
        "blockers": [blocker],
    }
