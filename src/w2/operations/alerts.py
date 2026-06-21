from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from w2.domain.time import require_utc
from w2.models.independent import artifact_hash


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True, kw_only=True)
class OperationalAlert:
    alert_key: str
    severity: AlertSeverity
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        if self.resolved_at is not None:
            object.__setattr__(self, "resolved_at", require_utc(self.resolved_at, "resolved_at"))

    def event_hash(self) -> str:
        return artifact_hash(
            {
                "alert_key": self.alert_key,
                "severity": self.severity,
                "reason": self.reason,
                "payload": self.payload,
            }
        )


class AlertStore:
    def __init__(self) -> None:
        self.alerts: dict[str, OperationalAlert] = {}
        self.audit: list[dict[str, Any]] = []

    def raise_alert(self, alert: OperationalAlert) -> OperationalAlert:
        existing = self.alerts.get(alert.alert_key)
        if existing and existing.severity == alert.severity and existing.reason == alert.reason:
            self.audit.append({"event": "alert_idempotent", "alert_key": alert.alert_key})
            return existing
        self.alerts[alert.alert_key] = alert
        self.audit.append({"event": "alert_raised", "alert_key": alert.alert_key})
        return alert

    def resolve(self, alert_key: str, *, resolved_at: datetime) -> OperationalAlert | None:
        existing = self.alerts.get(alert_key)
        if existing is None:
            return None
        resolved = OperationalAlert(
            alert_key=existing.alert_key,
            severity=AlertSeverity.RESOLVED,
            reason=existing.reason,
            payload=existing.payload,
            created_at=existing.created_at,
            resolved_at=resolved_at,
        )
        self.alerts[alert_key] = resolved
        self.audit.append({"event": "alert_resolved", "alert_key": alert_key})
        return resolved


ALERT_RULES = [
    "upcoming_fixture_without_odds",
    "stale_data",
    "bookmaker_count_drop",
    "provider_failure",
    "low_quota",
    "scheduler_heartbeat_missing",
    "mapping_conflict",
    "closing_snapshot_missing",
    "result_sync_delay",
    "frozen_manifest_hash_mismatch",
    "backup_stale",
]
