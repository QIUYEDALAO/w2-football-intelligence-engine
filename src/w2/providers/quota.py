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
