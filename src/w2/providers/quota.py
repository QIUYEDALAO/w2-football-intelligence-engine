from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ProviderQuota:
    daily_remaining: int | None
    burst_remaining: int | None
    observed_at: datetime
    daily_source: str | None
    burst_source: str | None


DAILY_HEADER_SOURCES = {
    "x-ratelimit-requests-remaining",
    "x-apisports-requests-remaining",
}
BURST_HEADER_SOURCES = {
    "x-ratelimit-remaining",
}
API_FOOTBALL_DAILY_BUDGET = 7500
API_FOOTBALL_RESERVE_BUCKET = 1500
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
    burst_remaining: int | None = None
    daily_source: str | None = None
    burst_source: str | None = None
    for raw_key, raw_value in headers.items():
        key = raw_key.lower()
        if daily_remaining is None and key in DAILY_HEADER_SOURCES:
            daily_remaining = parse_int(raw_value)
            daily_source = raw_key if daily_remaining is not None else None
        if burst_remaining is None and key in BURST_HEADER_SOURCES:
            burst_remaining = parse_int(raw_value)
            burst_source = raw_key if burst_remaining is not None else None
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
    return ProviderQuota(
        daily_remaining=daily_remaining,
        burst_remaining=burst_remaining,
        observed_at=observed_at.astimezone(UTC),
        daily_source=daily_source,
        burst_source=burst_source,
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
            remaining_quota <= API_FOOTBALL_RESERVE_BUCKET
            if remaining_quota is not None
            else None
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
