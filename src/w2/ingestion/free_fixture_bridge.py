from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from w2.ingestion.ports import ProviderRequest
from w2.ingestion.raw_store import RawPayloadStore
from w2.matchday.intake_v2 import (
    MatchdayCompetitionPolicy,
    endpoint_capture_contract,
    fixture_discovery_from_payloads,
    normalize_matchday_odds_payload,
    request_task_key,
)
from w2.providers.quota import provider_daily_hard_cap_decision

FREE_PROVIDER_DAILY_LIMIT = 100
FREE_W2_DAILY_CALL_CEILING = 80
FREE_MIN_PROVIDER_REMAINING = 20
MAX_FIXTURE_IDS_PER_REQUEST = 20


@dataclass(frozen=True)
class FreeFixtureBridgeConfig:
    enabled: bool = False
    provider_ids_batching: bool = False
    provider_daily_limit: int = FREE_PROVIDER_DAILY_LIMIT
    w2_daily_call_ceiling: int = FREE_W2_DAILY_CALL_CEILING
    min_provider_remaining: int = FREE_MIN_PROVIDER_REMAINING


DEFAULT_FREE_FIXTURE_BRIDGE_CONFIG = FreeFixtureBridgeConfig()


@dataclass(frozen=True)
class PlannedFreeCall:
    priority: str
    request: ProviderRequest
    fixture_ids: tuple[str, ...]
    cache_key: str


def plan_fixture_discovery(
    *,
    date_utc: str,
    actual_calls_today: int,
    provider_remaining: int | None = None,
    cached_request_keys: frozenset[str] = frozenset(),
    config: FreeFixtureBridgeConfig = DEFAULT_FREE_FIXTURE_BRIDGE_CONFIG,
) -> dict[str, Any]:
    if not config.enabled:
        return _plan("DISABLED_BY_DEFAULT", (), actual_calls_today, config)
    call = _call("P0", "fixtures", {"date": date_utc})
    if call.cache_key in cached_request_keys:
        return _plan("DISCOVERY_CACHED_NO_CALL", (), actual_calls_today, config)
    return _bounded_plan((call,), actual_calls_today, provider_remaining, config)


def plan_fixture_followups(
    *,
    fixture_payload: Mapping[str, Any],
    allowed_league_ids: frozenset[str],
    due_fixture_ids: Sequence[str],
    actual_calls_today: int,
    provider_remaining: int | None = None,
    fixture_detail_required_ids: Sequence[str] = (),
    enrichment_endpoints: tuple[str, ...] = (),
    cached_request_keys: frozenset[str] = frozenset(),
    config: FreeFixtureBridgeConfig = DEFAULT_FREE_FIXTURE_BRIDGE_CONFIG,
) -> dict[str, Any]:
    if not config.enabled:
        return _plan("DISABLED_BY_DEFAULT", (), actual_calls_today, config)
    allowed_enrichment = {"injuries", "lineups", "statistics"}
    if not set(enrichment_endpoints) <= allowed_enrichment:
        raise ValueError("FREE_BRIDGE_ENDPOINT_NOT_ALLOWED")
    discovered = _target_fixture_ids(fixture_payload, allowed_league_ids)
    due = tuple(dict.fromkeys(str(item) for item in due_fixture_ids if str(item)))
    selected = tuple(item for item in due if item in discovered)
    if not selected:
        return _plan("NO_DUE_TARGET_FIXTURES_NO_IDLE_POLLING", (), actual_calls_today, config)

    detail_ids = tuple(
        item for item in dict.fromkeys(fixture_detail_required_ids) if item in selected
    )
    calls = list(_fixture_detail_calls(detail_ids, config.provider_ids_batching))
    for fixture_id in selected:
        calls.append(_call("P1", "odds", {"fixture": fixture_id}, (fixture_id,)))
    for endpoint in enrichment_endpoints:
        calls.extend(
            _call("P2", endpoint, {"fixture": fixture_id}, (fixture_id,))
            for fixture_id in selected
        )
    uncached = tuple(call for call in calls if call.cache_key not in cached_request_keys)
    if not uncached:
        return _plan("FOLLOWUPS_CACHED_NO_CALL", (), actual_calls_today, config)
    return _bounded_plan(uncached, actual_calls_today, provider_remaining, config)


def materialize_bridge_evidence(
    *,
    fixture_payload: Mapping[str, Any],
    fixture_params: Mapping[str, str],
    odds_payloads: Mapping[str, Mapping[str, Any]],
    policies: Mapping[str, MatchdayCompetitionPolicy],
    captured_at: datetime,
    source_revision: str,
    raw_store: RawPayloadStore | None = None,
) -> dict[str, Any]:
    store = raw_store or RawPayloadStore()
    fixtures = dict(fixture_payload)
    fixture_rows = _required_response_rows(fixtures)
    stored_fixture = store.save(
        provider="api_football",
        endpoint="fixtures",
        payload=fixtures,
        captured_at=captured_at,
    )
    fixture_capture = endpoint_capture_contract(
        endpoint="fixtures",
        params=fixture_params,
        requested_at=captured_at,
        provider_captured_at=captured_at,
        status_code=200,
        elapsed_ms=0,
        payload=fixtures,
    )
    discovery = fixture_discovery_from_payloads(
        fixture_rows,
        policies=policies,
        captured_at=captured_at,
        source_payload_sha256=stored_fixture.reference.sha256,
    )
    captures = [fixture_capture]
    observations: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for fixture_id, source_payload in odds_payloads.items():
        competition_id = _competition_for_fixture(discovery, fixture_id)
        payload = dict(source_payload)
        odds_rows = _required_response_rows(payload)
        returned_ids = {_provider_fixture_id(row) for row in odds_rows}
        if returned_ids and returned_ids != {fixture_id}:
            raise ValueError("FREE_BRIDGE_ODDS_FIXTURE_ID_MISMATCH")
        stored = store.save(
            provider="api_football",
            endpoint="odds",
            payload=payload,
            captured_at=captured_at,
        )
        capture = endpoint_capture_contract(
            endpoint="odds",
            params={"fixture": fixture_id},
            requested_at=captured_at,
            provider_captured_at=captured_at,
            status_code=200,
            elapsed_ms=0,
            payload=payload,
            fixture_id=f"api_football:{fixture_id}",
        )
        rows, rejected = normalize_matchday_odds_payload(
            payload,
            captured_at=captured_at,
            ingested_at=captured_at,
            raw_payload_sha256=stored.reference.sha256,
            source_revision=source_revision,
            capture_id=str(capture["capture_id"]),
            competition_id=competition_id,
        )
        captures.append(capture)
        observations.extend(rows)
        rejections.extend(rejected)
    return {
        "raw_payload_count": store.count(),
        "endpoint_captures": captures,
        "fixture_discovery": discovery,
        "market_observations": observations,
        "normalization_rejections": rejections,
    }


def _bounded_plan(
    calls: tuple[PlannedFreeCall, ...],
    actual_calls_today: int,
    provider_remaining: int | None,
    config: FreeFixtureBridgeConfig,
) -> dict[str, Any]:
    local_capacity = max(config.w2_daily_call_ceiling - actual_calls_today, 0)
    provider_capacity = (
        max(provider_remaining - config.min_provider_remaining, 0)
        if provider_remaining is not None
        else 0
    )
    capacity = min(local_capacity, provider_capacity)
    selected = calls[:capacity]
    requested = selected or calls[:1]
    quota = provider_daily_hard_cap_decision(
        actual_calls_today=actual_calls_today,
        planned_calls=len(requested),
        daily_cap=config.w2_daily_call_ceiling,
        reserve_bucket=0,
        provider_remaining=provider_remaining,
        min_provider_remaining=config.min_provider_remaining,
        require_provider_remaining=True,
    )
    status = "PLANNED" if len(selected) == len(calls) else "QUOTA_TRUNCATED"
    if not selected:
        status = str(quota["blocker"] or "FREE_DAILY_CALL_CAPACITY_EXHAUSTED")
    return _plan(status, selected, actual_calls_today, config, quota=quota)


def _plan(
    status: str,
    calls: Sequence[PlannedFreeCall],
    actual_calls_today: int,
    config: FreeFixtureBridgeConfig,
    *,
    quota: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "enabled": config.enabled,
        "calls": list(calls),
        "planned_calls": len(calls),
        "actual_calls_today": actual_calls_today,
        "provider_daily_limit": config.provider_daily_limit,
        "w2_daily_call_ceiling": config.w2_daily_call_ceiling,
        "min_provider_remaining": config.min_provider_remaining,
        "quota": dict(quota or {}),
    }


def _fixture_detail_calls(
    fixture_ids: tuple[str, ...], provider_ids_batching: bool
) -> tuple[PlannedFreeCall, ...]:
    if not provider_ids_batching:
        return tuple(_call("P0", "fixtures", {"id": item}, (item,)) for item in fixture_ids)
    return tuple(
        _call("P0", "fixtures", {"ids": "-".join(batch)}, batch)
        for batch in _chunks(fixture_ids, MAX_FIXTURE_IDS_PER_REQUEST)
    )


def _call(
    priority: str,
    endpoint: str,
    params: dict[str, str],
    fixture_ids: tuple[str, ...] = (),
) -> PlannedFreeCall:
    return PlannedFreeCall(
        priority=priority,
        request=ProviderRequest(endpoint=endpoint, params=params, live=True),
        fixture_ids=fixture_ids,
        cache_key=request_task_key(endpoint, params),
    )


def _target_fixture_ids(
    payload: Mapping[str, Any], allowed_league_ids: frozenset[str]
) -> frozenset[str]:
    fixture_ids: set[str] = set()
    for row in _required_response_rows(payload):
        league = row.get("league")
        fixture = row.get("fixture")
        if not isinstance(league, Mapping) or not isinstance(fixture, Mapping):
            raise ValueError("FREE_BRIDGE_SCHEMA_UNSAFE")
        if str(league.get("id") or "") not in allowed_league_ids:
            continue
        fixture_id = str(fixture.get("id") or "")
        if not fixture_id:
            raise ValueError("FREE_BRIDGE_EMPTY_FIXTURE_ID")
        fixture_ids.add(fixture_id)
    return frozenset(fixture_ids)


def _required_response_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response")
    if not isinstance(response, list) or any(not isinstance(row, Mapping) for row in response):
        raise ValueError("FREE_BRIDGE_SCHEMA_UNSAFE")
    return [dict(row) for row in response]


def _provider_fixture_id(row: Mapping[str, Any]) -> str:
    fixture = row.get("fixture")
    if not isinstance(fixture, Mapping) or not fixture.get("id"):
        raise ValueError("FREE_BRIDGE_SCHEMA_UNSAFE")
    return str(fixture["id"])


def _chunks(values: tuple[str, ...], size: int) -> tuple[tuple[str, ...], ...]:
    return tuple(values[index : index + size] for index in range(0, len(values), size))


def _competition_for_fixture(discovery: Mapping[str, Any], fixture_id: str) -> str:
    if not fixture_id:
        raise ValueError("FREE_BRIDGE_EMPTY_FIXTURE_ID")
    canonical_id = f"api_football:{fixture_id}"
    for row in discovery.get("candidate_fixtures", []):
        if row.get("fixture_id") == canonical_id:
            return str(row.get("competition_id") or "UNKNOWN")
    raise ValueError("FREE_BRIDGE_OUT_OF_WHITELIST_FIXTURE")
