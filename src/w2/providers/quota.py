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
