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

FREE_DAILY_HARD_CAP = 80
FREE_DAILY_RESERVE = 20
MAX_FIXTURE_IDS_PER_REQUEST = 20


@dataclass(frozen=True)
class FreeFixtureBridgeConfig:
    enabled: bool = False
    provider_ids_batching: bool = False
    daily_hard_cap: int = FREE_DAILY_HARD_CAP
    daily_reserve: int = FREE_DAILY_RESERVE


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
    cached_request_keys: frozenset[str] = frozenset(),
    config: FreeFixtureBridgeConfig = DEFAULT_FREE_FIXTURE_BRIDGE_CONFIG,
) -> dict[str, Any]:
    if not config.enabled:
        return _plan("DISABLED_BY_DEFAULT", (), actual_calls_today, config)
    call = _call("P0", "fixtures", {"date": date_utc})
    if call.cache_key in cached_request_keys:
        return _plan("DISCOVERY_CACHED_NO_CALL", (), actual_calls_today, config)
    return _bounded_plan((call,), actual_calls_today, config)


def plan_fixture_followups(
    *,
    fixture_payload: Mapping[str, Any],
    allowed_league_ids: frozenset[str],
    due_fixture_ids: Sequence[str],
    actual_calls_today: int,
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

    calls = list(_fixture_detail_calls(selected, config.provider_ids_batching))
    for fixture_id in selected:
        calls.append(_call("P1", "odds", {"fixture": fixture_id}, (fixture_id,)))
        calls.extend(
            _call("P2", endpoint, {"fixture": fixture_id}, (fixture_id,))
            for endpoint in enrichment_endpoints
        )
    uncached = tuple(call for call in calls if call.cache_key not in cached_request_keys)
    if not uncached:
        return _plan("FOLLOWUPS_CACHED_NO_CALL", (), actual_calls_today, config)
    return _bounded_plan(uncached, actual_calls_today, config)


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
        _response_rows(fixtures),
        policies=policies,
        captured_at=captured_at,
        source_payload_sha256=stored_fixture.reference.sha256,
    )
    captures = [fixture_capture]
    observations: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for fixture_id, source_payload in odds_payloads.items():
        payload = dict(source_payload)
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
            competition_id=_competition_for_fixture(discovery, fixture_id),
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
    config: FreeFixtureBridgeConfig,
) -> dict[str, Any]:
    capacity = max(config.daily_hard_cap - config.daily_reserve - actual_calls_today, 0)
    selected = calls[:capacity]
    quota = provider_daily_hard_cap_decision(
        actual_calls_today=actual_calls_today,
        planned_calls=len(selected),
        daily_cap=config.daily_hard_cap,
        reserve_bucket=config.daily_reserve,
    )
    status = "PLANNED" if len(selected) == len(calls) else "QUOTA_TRUNCATED"
    if not selected:
        status = "FREE_DAILY_RESERVE_PROTECTED"
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
        "daily_hard_cap": config.daily_hard_cap,
        "daily_reserve": config.daily_reserve,
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
    return frozenset(
        str(fixture.get("id"))
        for row in _response_rows(payload)
        if str((row.get("league") or {}).get("id") or "") in allowed_league_ids
        and (fixture := row.get("fixture") or {}).get("id")
    )


def _response_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response")
    if not isinstance(response, list):
        return []
    return [dict(row) for row in response if isinstance(row, Mapping)]


def _chunks(values: tuple[str, ...], size: int) -> tuple[tuple[str, ...], ...]:
    return tuple(values[index : index + size] for index in range(0, len(values), size))


def _competition_for_fixture(discovery: Mapping[str, Any], fixture_id: str) -> str:
    canonical_id = f"api_football:{fixture_id}"
    for row in discovery.get("candidate_fixtures", []):
        if row.get("fixture_id") == canonical_id:
            return str(row.get("competition_id") or "UNKNOWN")
    return "UNKNOWN"
