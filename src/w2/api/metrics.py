from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


@dataclass
class ApiMetricSink:
    request_count: int = 0
    error_count: int = 0
    latency_ms: list[int] = field(default_factory=list)
    endpoint_status: dict[str, int] = field(default_factory=dict)

    def record(self, endpoint: str, status_code: int, started: float) -> None:
        self.request_count += 1
        if status_code >= 400:
            self.error_count += 1
        self.endpoint_status[endpoint] = status_code
        self.latency_ms.append(int((monotonic() - started) * 1000))


metrics = ApiMetricSink()
