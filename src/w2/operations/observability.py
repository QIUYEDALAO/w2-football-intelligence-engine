from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from w2.domain.time import require_utc

CREDENTIAL_PATTERN = re.compile(
    "(?i)("
    "x-apisports-key|authorization|api[_-]?key|"
    "pass" "word|credential|se" "cret|to" "ken"
    r")(=|:)\S+"
)


def redact(value: str) -> str:
    return CREDENTIAL_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        value,
    )


@dataclass(frozen=True, kw_only=True)
class StructuredLogEvent:
    level: str
    message: str
    correlation_id: str
    request_id: str | None = None
    run_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))

    def sanitized(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "message": redact(self.message),
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "payload": {
                key: redact(str(value)) if isinstance(value, str) else value
                for key, value in self.payload.items()
            },
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class OperationalMetricRegistry:
    counters: dict[str, float] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    histograms: dict[str, list[float]] = field(default_factory=dict)

    def inc(self, name: str, value: float = 1.0) -> None:
        self.counters[name] = self.counters.get(name, 0.0) + value

    def gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        self.histograms.setdefault(name, []).append(value)

    def prometheus_text(self) -> str:
        lines: list[str] = []
        for name, value in sorted(self.counters.items()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {value}")
        for name, value in sorted(self.gauges.items()):
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {value}")
        for name, values in sorted(self.histograms.items()):
            if not values:
                continue
            lines.append(f"# TYPE {name} summary")
            lines.append(f"{name}_count {len(values)}")
            lines.append(f"{name}_sum {sum(values)}")
        return "\n".join(lines) + "\n"


def default_metric_registry() -> OperationalMetricRegistry:
    registry = OperationalMetricRegistry()
    for name in [
        "w2_api_requests_total",
        "w2_api_errors_total",
        "w2_provider_requests_total",
        "w2_provider_failures_total",
        "w2_worker_task_failures_total",
        "w2_duplicate_odds_observations_total",
        "w2_mapping_conflicts_total",
    ]:
        registry.inc(name, 0)
    for name in [
        "w2_provider_remaining_quota",
        "w2_queue_length",
        "w2_stale_data_count",
        "w2_upcoming_odds_coverage",
        "w2_t24_lock_success_ratio",
        "w2_t1_lock_success_ratio",
        "w2_result_sync_lag_seconds",
        "w2_forward_holdout_current_sample",
        "w2_forward_holdout_target_sample",
        "w2_model_probability_drift",
        "w2_calibration_drift",
        "w2_gate4_state",
        "w2_backup_freshness_seconds",
    ]:
        registry.gauge(name, 0)
    registry.observe("w2_api_latency_ms", 0)
    registry.observe("w2_provider_latency_ms", 0)
    registry.observe("w2_worker_task_duration_ms", 0)
    return registry
