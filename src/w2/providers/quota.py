from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ProviderQuota:
    daily_remaining: int | None
    daily_limit: int | None
    burst_remaining: int | None
    burst_limit: int | None
    observed_at: datetime
    daily_source: str | None
    daily_limit_source: str | None
    burst_source: str | None
    burst_limit_source: str | None


DAILY_HEADER_SOURCES = {
    "x-ratelimit-requests-remaining",
    "x-apisports-requests-remaining",
}
DAILY_LIMIT_HEADER_SOURCES = {
    "x-ratelimit-requests-limit",
    "x-apisports-requests-limit",
}
BURST_HEADER_SOURCES = {
    "x-ratelimit-remaining",
}
BURST_LIMIT_HEADER_SOURCES = {
    "x-ratelimit-limit",
}
API_FOOTBALL_DAILY_BUDGET = 7500
API_FOOTBALL_RESERVE_BUCKET = 1500
API_FOOTBALL_FREE_DAILY_LIMIT = 100
API_FOOTBALL_FREE_DAILY_LIMIT_SOURCE = "x-ratelimit-requests-limit"
API_FOOTBALL_FREE_DAILY_LIMIT_OBSERVED_AT = "2026-08-16T03:30:27.493845Z"
API_FOOTBALL_FREE_MINUTE_LIMIT = 10
API_FOOTBALL_FREE_UNALLOCATED_BUFFER = 10
GENERAL_PROVIDER_DAILY_HARD_CAP = 70
POSTMATCH_RESULT_DAILY_HARD_CAP = 20
API_FOOTBALL_UPGRADE_EVALUATION_DAILY_BUDGET = 75000
API_FOOTBALL_BACKFILL_STOP_RATIO = 0.15
API_FOOTBALL_CORE_ONLY_RATIO = 0.10
API_FOOTBALL_CORE_TASKS = {
    "future_refresh",
    "status",
    "fixtures",
    "odds",
    "lineups",
    "live_odds",
    "live_lineups",
}
API_FOOTBALL_BACKFILL_TASKS = {"xg_backfill", "historical_backfill", "statistics_backfill"}


@dataclass(frozen=True)
class ProviderDailyQuotaPool:
    name: str
    env_var: str
    default_limit: int
    budget_basis: str


REGISTERED_PROVIDER_DAILY_QUOTA_POOLS = (
    ProviderDailyQuotaPool(
        name="GENERAL",
        env_var="W2_PROVIDER_DAILY_HARD_CAP",
        default_limit=GENERAL_PROVIDER_DAILY_HARD_CAP,
        budget_basis="PROVIDER_BILLABLE_HEADER",
    ),
    ProviderDailyQuotaPool(
        name="POSTMATCH_RESULT",
        env_var="W2_POSTMATCH_RESULT_DAILY_HARD_CAP",
        default_limit=POSTMATCH_RESULT_DAILY_HARD_CAP,
        budget_basis="POSTMATCH_REQUEST_ATTEMPTS",
    ),
)


def provider_daily_budget_contract(
    *,
    pool_limits: Mapping[str, int] | None = None,
    unallocated_buffer: int = API_FOOTBALL_FREE_UNALLOCATED_BUFFER,
    provider_limit: int = API_FOOTBALL_FREE_DAILY_LIMIT,
) -> dict[str, Any]:
    overrides = pool_limits or {}
    registered = {
        pool.name: max(int(overrides.get(pool.name, pool.default_limit)), 0)
        for pool in REGISTERED_PROVIDER_DAILY_QUOTA_POOLS
    }
    billable = {
        pool.name: registered[pool.name]
        for pool in REGISTERED_PROVIDER_DAILY_QUOTA_POOLS
        if pool.budget_basis == "PROVIDER_BILLABLE_HEADER"
    }
    attempt = {
        pool.name: registered[pool.name]
        for pool in REGISTERED_PROVIDER_DAILY_QUOTA_POOLS
        if pool.budget_basis == "POSTMATCH_REQUEST_ATTEMPTS"
    }
    allocated = sum(billable.values())
    buffer = max(int(unallocated_buffer), 0)
    total = allocated + buffer
    return {
        "pool_limits": billable,
        "orthogonal_attempt_pool_limits": attempt,
        "allocated_budget": allocated,
        "unallocated_buffer": buffer,
        "configured_total": total,
        "provider_limit": provider_limit,
        "valid": total <= provider_limit,
    }


def parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_api_football_quota(
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    observed_at: datetime,
) -> ProviderQuota:
    daily_remaining: int | None = None
    daily_limit: int | None = None
    burst_remaining: int | None = None
    burst_limit: int | None = None
    daily_source: str | None = None
    daily_limit_source: str | None = None
    burst_source: str | None = None
    burst_limit_source: str | None = None
    for raw_key, raw_value in headers.items():
        key = raw_key.lower()
        if daily_remaining is None and key in DAILY_HEADER_SOURCES:
            daily_remaining = parse_int(raw_value)
            daily_source = raw_key if daily_remaining is not None else None
        if daily_limit is None and key in DAILY_LIMIT_HEADER_SOURCES:
            daily_limit = parse_int(raw_value)
            daily_limit_source = raw_key if daily_limit is not None else None
        if burst_remaining is None and key in BURST_HEADER_SOURCES:
            burst_remaining = parse_int(raw_value)
            burst_source = raw_key if burst_remaining is not None else None
        if burst_limit is None and key in BURST_LIMIT_HEADER_SOURCES:
            burst_limit = parse_int(raw_value)
            burst_limit_source = raw_key if burst_limit is not None else None
    if daily_remaining is None:
        response = payload.get("response")
        if isinstance(response, dict):
            requests = response.get("requests")
        else:
            requests = None
        if isinstance(requests, dict):
            daily_remaining = parse_int(requests.get("remaining"))
            if daily_remaining is not None:
                daily_source = "response.requests.remaining"
            if daily_limit is None:
                for key in ("limit", "limit_day", "daily_limit", "requests_limit"):
                    daily_limit = parse_int(requests.get(key))
                    if daily_limit is not None:
                        daily_limit_source = f"response.requests.{key}"
                        break
    return ProviderQuota(
        daily_remaining=daily_remaining,
        daily_limit=daily_limit,
        burst_remaining=burst_remaining,
        burst_limit=burst_limit,
        observed_at=observed_at.astimezone(UTC),
        daily_source=daily_source,
        daily_limit_source=daily_limit_source,
        burst_source=burst_source,
        burst_limit_source=burst_limit_source,
    )


def api_football_quota_policy(remaining_quota: int | None) -> dict[str, Any]:
    available_after_reserve = (
        max(remaining_quota - API_FOOTBALL_RESERVE_BUCKET, 0)
        if remaining_quota is not None
        else None
    )
    return {
        "provider": "api_football",
        "daily_budget": API_FOOTBALL_DAILY_BUDGET,
        "reserve_bucket": API_FOOTBALL_RESERVE_BUCKET,
        "available_after_reserve": available_after_reserve,
        "reserve_locked": (
            remaining_quota <= API_FOOTBALL_RESERVE_BUCKET if remaining_quota is not None else None
        ),
        "upgrade_evaluation_daily_budget": API_FOOTBALL_UPGRADE_EVALUATION_DAILY_BUDGET,
        "upgrade_enabled": False,
    }


def quota_guard_decision(
    *,
    remaining_quota: int | None,
    task_type: str,
    daily_budget: int = API_FOOTBALL_DAILY_BUDGET,
    reserve_bucket: int = API_FOOTBALL_RESERVE_BUCKET,
) -> dict[str, Any]:
    if remaining_quota is None:
        return {
            "allowed": False,
            "mode": "BLOCKED",
            "blocker": "DAILY_QUOTA_UNKNOWN",
            "remaining_quota": None,
            "daily_budget": daily_budget,
            "reserve_bucket": reserve_bucket,
            "available_after_reserve": None,
            "reserve_locked": None,
        }
    backfill_stop = int(daily_budget * API_FOOTBALL_BACKFILL_STOP_RATIO)
    core_only = int(daily_budget * API_FOOTBALL_CORE_ONLY_RATIO)
    available_after_reserve = max(remaining_quota - reserve_bucket, 0)
    reserve_locked = remaining_quota <= reserve_bucket
    normalized_task = task_type.lower()
    is_core = normalized_task in API_FOOTBALL_CORE_TASKS
    is_backfill = normalized_task in API_FOOTBALL_BACKFILL_TASKS or "backfill" in normalized_task
    if remaining_quota <= 0:
        allowed = False
        blocker = "DAILY_QUOTA_EXHAUSTED"
        mode = "BLOCKED"
    elif is_backfill and remaining_quota < max(reserve_bucket, backfill_stop):
        allowed = False
        blocker = "BACKFILL_QUOTA_GUARD"
        mode = "BACKFILL_STOPPED"
    elif remaining_quota < core_only and not is_core:
        allowed = False
        blocker = "QUOTA_CRITICAL_CORE_ONLY"
        mode = "CORE_ONLY"
    elif reserve_locked and not is_core:
        allowed = False
        blocker = "QUOTA_BELOW_RESERVE"
        mode = "RESERVE_LOCKED"
    else:
        allowed = True
        blocker = None
        mode = "CORE_ONLY" if remaining_quota < core_only else "NORMAL"
    return {
        "allowed": allowed,
        "mode": mode,
        "blocker": blocker,
        "remaining_quota": remaining_quota,
        "daily_budget": daily_budget,
        "reserve_bucket": reserve_bucket,
        "available_after_reserve": available_after_reserve,
        "reserve_locked": reserve_locked,
        "backfill_stop_threshold": backfill_stop,
        "core_only_threshold": core_only,
        "task_type": task_type,
    }


def provider_daily_hard_cap_decision(
    *,
    actual_calls_today: int,
    planned_calls: int,
    daily_cap: int = API_FOOTBALL_DAILY_BUDGET,
    reserve_bucket: int = API_FOOTBALL_RESERVE_BUCKET,
    provider_remaining: int | None = None,
    min_provider_remaining: int = 0,
    require_provider_remaining: bool = False,
    provider_limit: int | None = None,
) -> dict[str, Any]:
    actual = max(actual_calls_today, 0)
    planned = max(planned_calls, 0)
    projected_total = actual + planned
    remaining_after_plan = daily_cap - projected_total
    provider_remaining_after_plan = (
        provider_remaining - planned if provider_remaining is not None else None
    )
    if provider_limit is not None and daily_cap > provider_limit:
        allowed = False
        blocker = "PROVIDER_DAILY_CAP_EXCEEDS_OBSERVED_LIMIT"
        mode = "BLOCKED"
    elif projected_total > daily_cap:
        allowed = False
        blocker = "DAILY_PROVIDER_HARD_CAP_EXCEEDED"
        mode = "HARD_CAP"
    elif require_provider_remaining and provider_remaining is None:
        allowed = False
        blocker = "DAILY_QUOTA_UNKNOWN"
        mode = "BLOCKED"
    elif (
        provider_remaining_after_plan is not None
        and provider_remaining_after_plan < min_provider_remaining
    ):
        allowed = False
        blocker = "PROVIDER_RESERVE_PROTECTED"
        mode = "RESERVE_PROTECTED"
    elif remaining_after_plan < reserve_bucket:
        allowed = False
        blocker = "PROVIDER_RESERVE_PROTECTED"
        mode = "RESERVE_PROTECTED"
    else:
        allowed = True
        blocker = None
        mode = "NORMAL"
    return {
        "allowed": allowed,
        "mode": mode,
        "blocker": blocker,
        "actual_calls_today": actual,
        "billable_calls_today": actual,
        "budget_basis": "PROVIDER_BILLABLE_HEADER",
        "planned_calls": planned,
        "projected_total": projected_total,
        "daily_cap": daily_cap,
        "reserve_bucket": reserve_bucket,
        "remaining_after_plan": remaining_after_plan,
        "provider_remaining": provider_remaining,
        "provider_limit": provider_limit,
        "min_provider_remaining": min_provider_remaining,
        "provider_remaining_after_plan": provider_remaining_after_plan,
    }


def postmatch_result_quota_decision(
    *,
    actual_calls_today: int,
    planned_calls: int,
    reserved_capture_calls: int = 0,
    daily_cap: int = POSTMATCH_RESULT_DAILY_HARD_CAP,
) -> dict[str, Any]:
    actual = max(actual_calls_today, 0)
    planned = max(planned_calls, 0)
    reserved = max(reserved_capture_calls, 0)
    projected_total = actual + planned + reserved
    allowed = projected_total <= daily_cap
    operational_status = (
        "POSTMATCH_POOL_RESERVED_SATURATED"
        if daily_cap > 0 and reserved * 4 > daily_cap * 3
        else None
    )
    return {
        "allowed": allowed,
        "mode": "RESULT_RESERVE" if allowed else "RESULT_HARD_CAP",
        "blocker": None if allowed else "RESULT_QUOTA_EXHAUSTED",
        "actual_calls_today": actual,
        "postmatch_request_attempts_today": actual,
        "budget_basis": "POSTMATCH_REQUEST_ATTEMPTS",
        "planned_calls": planned,
        "reserved_capture_calls": reserved,
        "projected_total": projected_total,
        "daily_cap": daily_cap,
        "reserve_bucket": daily_cap,
        "remaining_after_plan": daily_cap - projected_total,
        "quota_scope": "POSTMATCH_RESULT",
        "operational_status": operational_status,
    }
