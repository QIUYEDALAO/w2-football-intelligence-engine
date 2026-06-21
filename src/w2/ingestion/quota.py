from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QuotaPolicy:
    daily_limit: int
    reserve_for_high_priority: int
    degrade_after_remaining: int


@dataclass
class QuotaManager:
    policy: QuotaPolicy
    used: int = 0
    usage_by_endpoint: dict[str, int] = field(default_factory=dict)

    def remaining(self) -> int:
        return max(self.policy.daily_limit - self.used, 0)

    def allow(self, endpoint: str, priority: int) -> bool:
        remaining = self.remaining()
        if remaining <= 0:
            return False
        if priority > 5 and remaining <= self.policy.reserve_for_high_priority:
            return False
        if priority > 8 and remaining <= self.policy.degrade_after_remaining:
            return False
        self.used += 1
        self.usage_by_endpoint[endpoint] = self.usage_by_endpoint.get(endpoint, 0) + 1
        return True

