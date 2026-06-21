from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any

from w2.domain.time import require_utc
from w2.models.forward_automation import ForwardCircuitBreaker, NoOverlapLock
from w2.models.independent import artifact_hash


class ForwardRuntimeEnvironment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"


@dataclass(frozen=True, kw_only=True)
class ForwardAutorunSettings:
    environment: str
    autorun_enabled: bool
    network_enabled: bool
    deepseek_enabled: bool
    recommendation_enabled: bool
    daily_hard_budget: int = 6000
    minimum_reserve: int = 1500
    per_cycle_cap: int = 1000

    def validate(self) -> None:
        if self.environment not in {item.value for item in ForwardRuntimeEnvironment}:
            raise ValueError("forward autorun is only allowed for local or staging")
        if not self.autorun_enabled:
            raise ValueError("forward autorun must be explicitly enabled")
        if not self.network_enabled:
            raise ValueError("forward network must be explicitly enabled")
        if self.deepseek_enabled:
            raise ValueError("DeepSeek must remain disabled")
        if self.recommendation_enabled:
            raise ValueError("recommendation output must remain disabled")


@dataclass(kw_only=True)
class ForwardQuotaLedger:
    provider: str
    usage_date: date
    requests_used: int = 0
    reset_at: datetime | None = None

    def reset_if_needed(self, now: datetime) -> None:
        now = require_utc(now, "now")
        if self.usage_date != now.date():
            self.usage_date = now.date()
            self.requests_used = 0
            reset_day = now.date() + timedelta(days=1)
            self.reset_at = datetime.combine(reset_day, datetime.min.time(), UTC)

    def available(self, settings: ForwardAutorunSettings, provider_remaining: int | None) -> int:
        if provider_remaining is None:
            return 0
        if provider_remaining <= settings.minimum_reserve:
            return 0
        budget_left = max(settings.daily_hard_budget - self.requests_used, 0)
        provider_left = provider_remaining - settings.minimum_reserve
        return min(settings.per_cycle_cap, budget_left, provider_left)

    def record(self, count: int) -> None:
        self.requests_used += count


@dataclass(frozen=True, kw_only=True)
class ForwardSchedulerAudit:
    scheduler_run_id: str
    scheduled_at: datetime
    started_at: datetime
    finished_at: datetime
    request_count: int
    checkpoint_hash: str
    cycle_hash: str
    no_overlap: bool
    exit_status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "scheduled_at", require_utc(self.scheduled_at, "scheduled_at"))
        object.__setattr__(self, "started_at", require_utc(self.started_at, "started_at"))
        object.__setattr__(self, "finished_at", require_utc(self.finished_at, "finished_at"))


class ForwardRuntimeGuard:
    def __init__(self, settings: ForwardAutorunSettings) -> None:
        self.settings = settings
        self.circuit_breaker = ForwardCircuitBreaker()
        self.lock = NoOverlapLock()

    def check_startup(self) -> None:
        self.settings.validate()

    def check_response(self, status_code: int, remaining_quota: int | None) -> None:
        self.circuit_breaker.record_status(status_code, remaining_quota)
        if self.circuit_breaker.is_open:
            raise RuntimeError(f"FORWARD_AUTORUN_CIRCUIT_OPEN:{self.circuit_breaker.open_reason}")
        if remaining_quota is None:
            raise RuntimeError("FORWARD_AUTORUN_QUOTA_UNKNOWN")
        if remaining_quota <= self.settings.minimum_reserve:
            raise RuntimeError("FORWARD_AUTORUN_QUOTA_RESERVE_BREACH")

    def acquire(self) -> bool:
        return self.lock.acquire()

    def release(self) -> None:
        self.lock.release()


def scheduler_checkpoint_hash(payload: dict[str, Any]) -> str:
    return artifact_hash(payload)
