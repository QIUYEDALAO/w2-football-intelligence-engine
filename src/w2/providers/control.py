from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from w2.config import Settings, get_settings

PROVIDER_CALLS_DISABLED = "PROVIDER_CALLS_DISABLED"
PROVIDER_SCHEDULER_DISABLED = "SKIPPED_PROVIDER_SCHEDULER_DISABLED"
PROVIDER_SCHEDULER_DEDUP_UNAVAILABLE = "PROVIDER_SCHEDULER_DEDUP_UNAVAILABLE"
DUPLICATE_TASK_KEY_SUPPRESSED = "DUPLICATE_TASK_KEY_SUPPRESSED"
MAX_PROVIDER_HTTP_ATTEMPTS = 3


class ProviderCallsDisabledError(RuntimeError):
    pass


def env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, *, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_csv_set(name: str, *, default: set[str] | frozenset[str]) -> frozenset[str]:
    raw = os.environ.get(name)
    if raw is None:
        return frozenset(default)
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def provider_calls_disabled() -> bool:
    return env_flag("W2_PROVIDER_CALLS_DISABLED", default=False)


def provider_scheduler_enabled() -> bool:
    return env_flag("W2_PROVIDER_SCHEDULER_ENABLED", default=False)


def provider_endpoint_allowlist() -> frozenset[str]:
    return env_csv_set(
        "W2_PROVIDER_ENDPOINT_ALLOWLIST",
        default={"status", "fixtures", "odds", "lineups"},
    )


def provider_refresh_min_interval_seconds() -> int:
    return max(env_int("W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS", default=900), 1)


def provider_refresh_tick_hard_cap() -> int:
    return max(env_int("W2_PROVIDER_REFRESH_TICK_HARD_CAP", default=30), 0)


def provider_http_max_attempts() -> int:
    return min(
        max(env_int("W2_PROVIDER_HTTP_MAX_ATTEMPTS", default=1), 1),
        MAX_PROVIDER_HTTP_ATTEMPTS,
    )


@dataclass(frozen=True)
class ProviderTaskKeyGate:
    allowed: bool
    status: str
    task_key: str
    ttl_seconds: int
    backend: str | None = None


def provider_task_key_gate(
    *,
    task_key: str,
    settings: Settings | None = None,
    redis_client: Any | None = None,
    ttl_seconds: int | None = None,
) -> ProviderTaskKeyGate:
    ttl = ttl_seconds or env_int("W2_PROVIDER_TASK_KEY_DEDUP_TTL_SECONDS", default=1800)
    key = f"w2:provider-task-key:{task_key}"
    client = redis_client
    if client is None:
        resolved = settings or get_settings()
        if resolved.redis_url is None:
            return ProviderTaskKeyGate(
                allowed=False,
                status=PROVIDER_SCHEDULER_DEDUP_UNAVAILABLE,
                task_key=task_key,
                ttl_seconds=ttl,
                backend=None,
            )
        client = Redis.from_url(
            resolved.redis_url.get_secret_value(),
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    try:
        acquired = bool(client.set(key, "1", nx=True, ex=ttl))
    except RedisError:
        return ProviderTaskKeyGate(
            allowed=False,
            status=PROVIDER_SCHEDULER_DEDUP_UNAVAILABLE,
            task_key=task_key,
            ttl_seconds=ttl,
            backend="redis",
        )
    if acquired:
        return ProviderTaskKeyGate(
            allowed=True,
            status="ACQUIRED",
            task_key=task_key,
            ttl_seconds=ttl,
            backend="redis",
        )
    return ProviderTaskKeyGate(
        allowed=False,
        status=DUPLICATE_TASK_KEY_SUPPRESSED,
        task_key=task_key,
        ttl_seconds=ttl,
        backend="redis",
    )


def provider_scheduler_skip_payload(reason: str = PROVIDER_SCHEDULER_DISABLED) -> dict[str, object]:
    return {
        "status": reason,
        "blockers": [reason],
        "candidate": False,
        "formal_recommendation": False,
        "provider_calls": 0,
    }
