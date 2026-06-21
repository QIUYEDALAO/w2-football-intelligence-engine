from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


class CircuitOpenError(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    failure_threshold: int
    failures: int = 0
    opened: bool = False

    def before_call(self) -> None:
        if self.opened:
            raise CircuitOpenError("circuit breaker is open")

    def record_success(self) -> None:
        self.failures = 0
        self.opened = False

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened = True


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.1
    multiplier: float = 2.0

    def delays(self) -> list[float]:
        return [
            self.base_delay_seconds * (self.multiplier**attempt)
            for attempt in range(max(self.max_attempts - 1, 0))
        ]


def call_with_retry[T](
    operation: Callable[[], T],
    policy: RetryPolicy,
    breaker: CircuitBreaker,
    sleep: Callable[[float], None] | None = None,
) -> T:
    sleeper = sleep or (lambda _delay: None)
    last_error: Exception | None = None
    for attempt in range(policy.max_attempts):
        breaker.before_call()
        try:
            result = operation()
            breaker.record_success()
            return result
        except Exception as exc:
            last_error = exc
            breaker.record_failure()
            if attempt < policy.max_attempts - 1:
                sleeper(policy.delays()[attempt])
    if last_error is None:
        raise RuntimeError("retry operation failed without an exception")
    raise last_error
