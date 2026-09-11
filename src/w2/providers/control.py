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
MAX_PROVIDER_REQUEST_TIMEOUT_SECONDS = 60

# Exact fixture scopes observed returning API-Football's Free-plan season-access
# error on 2026-08-16. Unknown league/season pairs must still be dispatched.
_FREE_PLAN_FIXTURE_SCOPE_EVIDENCE: dict[tuple[str, str], dict[str, Any]] = {
    ("39", "2026"): {
        "competition_id": "premier_league",
        "sample_count": 15,
        "observed_at_utc": "2026-08-16T00:01:06Z/2026-08-16T03:30:26Z",
        "payload_sha256": "2739a8f2f211430a100d3fde0f4f708ec1eb5d6b77444cfcc20eb15f24ebae2e",
    },
    ("61", "2026"): {
        "competition_id": "ligue_1",
        "sample_count": 15,
        "observed_at_utc": "2026-08-16T00:01:05Z/2026-08-16T03:30:24Z",
        "payload_sha256": "5095d515a8a0f720a298e97879e2b60657d30d71e4a4abecc202345ca6c8a918",
    },
    ("78", "2026"): {
        "competition_id": "bundesliga",
        "sample_count": 15,
        "observed_at_utc": "2026-08-16T00:01:03Z/2026-08-16T03:30:22Z",
        "payload_sha256": "be4119484e19c0a515f0d6f06c3a4d12892917d16b3099c8368e5a320498f6e0",
    },
    ("135", "2026"): {
        "competition_id": "serie_a",
        "sample_count": 15,
        "observed_at_utc": "2026-08-16T00:01:08Z/2026-08-16T03:30:28Z",
        "payload_sha256": "d9d1e2ce489de52e78ac1999c980a2c758e3b6ad67958f7f2d828478313f5b64",
    },
    ("140", "2026"): {
        "competition_id": "la_liga",
        "sample_count": 3,
        "observed_at_utc": "2026-08-12T05:54:21Z/2026-08-14T00:01:01Z",
        "payload_sha256": "1ab19d614ffaa2fd97cd2abddaeaa6e199ddc5de2e6a6b29606833704cf98ab8",
    },
}
_FREE_PLAN_FIXTURE_SCOPE_ERROR = (
    "Free plans do not have access to this season, try from 2022 to 2024."
)


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
    raw = os.environ.get("W2_PROVIDER_CALLS_DISABLED")
    if raw is None:
        return True
    normalized = raw.strip().lower()
    if normalized in {"0", "false", "no", "off"}:
        return False
    return True


def provider_scheduler_enabled() -> bool:
    return env_flag("W2_PROVIDER_SCHEDULER_ENABLED", default=False)


def provider_endpoint_allowlist() -> frozenset[str]:
    return env_csv_set(
        "W2_PROVIDER_ENDPOINT_ALLOWLIST",
        default=set(),
    )


def provider_refresh_min_interval_seconds() -> int:
    return max(env_int("W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS", default=900), 1)


def provider_refresh_tick_hard_cap() -> int:
    return max(env_int("W2_PROVIDER_REFRESH_TICK_HARD_CAP", default=30), 0)


def provider_quota_authority_max_age_seconds() -> int:
    return max(env_int("W2_PROVIDER_QUOTA_AUTHORITY_MAX_AGE_SECONDS", default=7200), 60)


def provider_http_max_attempts() -> int:
    return min(
        max(env_int("W2_PROVIDER_HTTP_MAX_ATTEMPTS", default=1), 1),
        MAX_PROVIDER_HTTP_ATTEMPTS,
    )


def provider_timeout_max_attempts() -> int:
    return min(
        max(env_int("W2_PROVIDER_TIMEOUT_MAX_ATTEMPTS", default=1), 1),
        MAX_PROVIDER_HTTP_ATTEMPTS,
    )


def provider_request_max_attempts() -> int:
    return max(provider_http_max_attempts(), provider_timeout_max_attempts())


def provider_request_timeout_seconds() -> int:
    return min(
        max(env_int("W2_PROVIDER_REQUEST_TIMEOUT_SECONDS", default=45), 1),
        MAX_PROVIDER_REQUEST_TIMEOUT_SECONDS,
    )


def provider_timeout_retry_backoff_seconds() -> int:
    return min(max(env_int("W2_PROVIDER_TIMEOUT_RETRY_BACKOFF_SECONDS", default=2), 0), 30)


def free_plan_fixture_scope_restriction(params: dict[str, str]) -> dict[str, Any] | None:
    if "id" in params or "fixture" in params:
        return None
    scope = (str(params.get("league") or ""), str(params.get("season") or ""))
    evidence = _FREE_PLAN_FIXTURE_SCOPE_EVIDENCE.get(scope)
    return {**evidence, "provider_error": _FREE_PLAN_FIXTURE_SCOPE_ERROR} if evidence else None


def is_free_plan_fixture_scope_restricted(payload: dict[str, Any]) -> bool:
    errors = payload.get("errors")
    return isinstance(errors, dict) and errors.get("plan") == _FREE_PLAN_FIXTURE_SCOPE_ERROR


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
