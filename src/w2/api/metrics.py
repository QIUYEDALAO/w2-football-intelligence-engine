from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic

from w2.operations.observability import (
    OperationalMetricRegistry,
    default_metric_registry,
)


@dataclass
class ApiMetricSink:
    registry: OperationalMetricRegistry = field(default_factory=default_metric_registry)

    def record(self, endpoint: str, status_code: int, started: float) -> None:
        self.record_elapsed(endpoint, status_code, (monotonic() - started) * 1000)

    def record_elapsed(self, endpoint: str, status_code: int, elapsed_ms: float) -> None:
        labels = {"route": endpoint, "status": str(status_code)}
        self.registry.inc("w2_api_requests_total")
        self.registry.inc("w2_api_requests_total", labels=labels)
        if status_code >= 400:
            self.registry.inc("w2_api_errors_total")
            self.registry.inc("w2_api_errors_total", labels=labels)
        self.registry.gauge(
            "w2_api_last_status",
            status_code,
            labels={"route": endpoint},
        )
        self.registry.observe(
            "w2_api_latency_ms",
            max(0.0, elapsed_ms),
            labels={"route": endpoint},
        )


metrics = ApiMetricSink()
