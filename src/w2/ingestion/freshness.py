from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from w2.domain.time import require_utc


@dataclass(frozen=True)
class FreshnessAlert:
    entity_type: str
    entity_id: str
    observed_at: datetime
    threshold_seconds: int
    severity: str
    message: str


@dataclass(frozen=True)
class FreshnessEvaluator:
    threshold_seconds: int

    def evaluate(
        self,
        *,
        entity_type: str,
        entity_id: str,
        observed_at: datetime,
        now: datetime,
    ) -> FreshnessAlert | None:
        observed_utc = require_utc(observed_at, "observed_at")
        now_utc = require_utc(now, "now")
        age = now_utc - observed_utc
        if age <= timedelta(seconds=self.threshold_seconds):
            return None
        return FreshnessAlert(
            entity_type=entity_type,
            entity_id=entity_id,
            observed_at=observed_utc,
            threshold_seconds=self.threshold_seconds,
            severity="WARN",
            message="freshness threshold exceeded",
        )

