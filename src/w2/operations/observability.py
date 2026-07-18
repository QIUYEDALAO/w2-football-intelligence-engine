from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from w2.domain.time import require_utc

CREDENTIAL_PATTERN = re.compile(
    "(?i)("
    "x-apisports-key|authorization|api[_-]?key|"
    "pass" "word|credential|se" "cret|to" "ken"
    r")(=|:)\S+"
)

DEFAULT_HISTOGRAM_BUCKETS = (
    1.0,
    2.5,
    5.0,
    10.0,
    25.0,
    50.0,
    100.0,
    250.0,
    500.0,
    1_000.0,
    2_500.0,
    5_000.0,
    10_000.0,
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
class BoundedHistogram:
    """Fixed-memory cumulative histogram; observations are never retained."""

    bounds: tuple[float, ...] = DEFAULT_HISTOGRAM_BUCKETS
    bucket_counts: list[int] = field(init=False)
    count: int = 0
    total: float = 0.0

    def __post_init__(self) -> None:
        self.bucket_counts = [0] * len(self.bounds)

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        for index, bound in enumerate(self.bounds):
            if value <= bound:
                self.bucket_counts[index] += 1


LabelKey = tuple[tuple[str, str], ...]
LabelledMetricKey = tuple[str, LabelKey]


def _label_key(labels: Mapping[str, str] | None) -> LabelKey:
    return tuple(sorted((str(key), str(value)) for key, value in (labels or {}).items()))


def _escaped_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _render_labels(labels: LabelKey, extra: tuple[str, str] | None = None) -> str:
    values = list(labels)
    if extra is not None:
        values.append(extra)
    if not values:
        return ""
    rendered = ",".join(f'{key}="{_escaped_label(value)}"' for key, value in values)
    return "{" + rendered + "}"


@dataclass
class OperationalMetricRegistry:
    counters: dict[str, float] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    histograms: dict[str, BoundedHistogram] = field(default_factory=dict)
    labelled_counters: dict[LabelledMetricKey, float] = field(default_factory=dict)
    labelled_gauges: dict[LabelledMetricKey, float] = field(default_factory=dict)
    labelled_histograms: dict[LabelledMetricKey, BoundedHistogram] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def inc(
        self,
        name: str,
        value: float = 1.0,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        with self._lock:
            if labels:
                key = (name, _label_key(labels))
                self.labelled_counters[key] = self.labelled_counters.get(key, 0.0) + value
            else:
                self.counters[name] = self.counters.get(name, 0.0) + value

    def gauge(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        with self._lock:
            if labels:
                self.labelled_gauges[(name, _label_key(labels))] = value
            else:
                self.gauges[name] = value

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        with self._lock:
            if labels:
                histogram = self.labelled_histograms.setdefault(
                    (name, _label_key(labels)), BoundedHistogram()
                )
            else:
                histogram = self.histograms.setdefault(name, BoundedHistogram())
            histogram.observe(value)

    def ensure_histogram(self, name: str) -> None:
        with self._lock:
            self.histograms.setdefault(name, BoundedHistogram())

    def prometheus_text(self) -> str:
        with self._lock:
            lines: list[str] = []
            counter_names = set(self.counters) | {name for name, _ in self.labelled_counters}
            for name in sorted(counter_names):
                lines.append(f"# TYPE {name} counter")
                if name in self.counters:
                    lines.append(f"{name} {self.counters[name]}")
                for (metric_name, labels), value in sorted(self.labelled_counters.items()):
                    if metric_name == name:
                        lines.append(f"{name}{_render_labels(labels)} {value}")
            gauge_names = set(self.gauges) | {name for name, _ in self.labelled_gauges}
            for name in sorted(gauge_names):
                lines.append(f"# TYPE {name} gauge")
                if name in self.gauges:
                    lines.append(f"{name} {self.gauges[name]}")
                for (metric_name, labels), value in sorted(self.labelled_gauges.items()):
                    if metric_name == name:
                        lines.append(f"{name}{_render_labels(labels)} {value}")
            histogram_names = set(self.histograms) | {
                name for name, _ in self.labelled_histograms
            }
            for name in sorted(histogram_names):
                lines.append(f"# TYPE {name} histogram")
                instances: list[tuple[LabelKey, BoundedHistogram]] = []
                if name in self.histograms:
                    instances.append(((), self.histograms[name]))
                instances.extend(
                    (labels, histogram)
                    for (metric_name, labels), histogram in sorted(
                        self.labelled_histograms.items()
                    )
                    if metric_name == name
                )
                for labels, histogram in instances:
                    for bound, count in zip(
                        histogram.bounds, histogram.bucket_counts, strict=True
                    ):
                        lines.append(
                            f'{name}_bucket{_render_labels(labels, ("le", str(bound)))} {count}'
                        )
                    lines.append(
                        f'{name}_bucket{_render_labels(labels, ("le", "+Inf"))} '
                        f"{histogram.count}"
                    )
                    lines.append(f"{name}_count{_render_labels(labels)} {histogram.count}")
                    lines.append(f"{name}_sum{_render_labels(labels)} {histogram.total}")
            return "\n".join(lines) + "\n"


def _new_default_metric_registry() -> OperationalMetricRegistry:
    registry = OperationalMetricRegistry()
    for name in [
        "w2_api_requests_total",
        "w2_api_errors_total",
        "w2_provider_requests_total",
        "w2_provider_failures_total",
        "w2_worker_task_failures_total",
        "w2_duplicate_odds_observations_total",
        "w2_mapping_conflicts_total",
        "w2_checkpoint_reads_total",
        "w2_public_tripwire_blocks_total",
        "w2_model_calls_total",
        "w2_materializer_results_total",
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
        "w2_readiness_status",
    ]:
        registry.gauge(name, 0)
    for name in [
        "w2_api_latency_ms",
        "w2_provider_latency_ms",
        "w2_worker_task_duration_ms",
    ]:
        registry.ensure_histogram(name)
    return registry


_DEFAULT_REGISTRY = _new_default_metric_registry()


def default_metric_registry() -> OperationalMetricRegistry:
    return _DEFAULT_REGISTRY
