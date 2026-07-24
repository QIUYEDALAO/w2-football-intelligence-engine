from __future__ import annotations

import urllib.error

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.api.metrics import ApiMetricSink
from w2.operations.observability import (
    BoundedHistogram,
    OperationalMetricRegistry,
    default_metric_registry,
)
from w2.prematch.analysis_calculator import ReadModelService
from w2.providers.api_football import ApiFootballClient


def test_default_registry_is_process_singleton_and_api_sink_exports_to_it() -> None:
    registry = default_metric_registry()
    before = registry.counters["w2_api_requests_total"]
    ApiMetricSink().record_elapsed("/contract", 200, 12.5)

    assert default_metric_registry() is registry
    assert registry.counters["w2_api_requests_total"] == before + 1
    output = registry.prometheus_text()
    assert 'w2_api_requests_total{route="/contract",status="200"}' in output
    assert 'w2_api_latency_ms_count{route="/contract"} 1' in output


def test_histogram_memory_is_bounded_by_fixed_bucket_count() -> None:
    registry = OperationalMetricRegistry()
    for value in range(20_000):
        registry.observe("latency", float(value))

    histogram = registry.histograms["latency"]
    assert isinstance(histogram, BoundedHistogram)
    assert histogram.count == 20_000
    assert len(histogram.bucket_counts) == len(histogram.bounds)
    assert not hasattr(histogram, "samples")
    output = registry.prometheus_text()
    assert "latency_count 20000" in output
    assert 'latency_bucket{le="+Inf"} 20000' in output


def test_http_middleware_records_templated_route_status_and_latency() -> None:
    registry = default_metric_registry()
    before_requests = registry.counters["w2_api_requests_total"]
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert registry.counters["w2_api_requests_total"] == before_requests + 1
    output = registry.prometheus_text()
    assert 'w2_api_requests_total{route="/health",status="200"}' in output
    assert 'w2_api_latency_ms_count{route="/health"}' in output


def test_provider_transport_failure_is_counted(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-only")
    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    registry = default_metric_registry()
    key = (
        "w2_provider_failures_total",
        (("endpoint", "status"), ("provider", "api_football")),
    )
    before = registry.labelled_counters.get(key, 0)

    try:
        ApiFootballClient(allow_live=True).request_live("status", {})
    except urllib.error.URLError:
        pass
    else:
        raise AssertionError("transport failure must propagate")

    assert registry.labelled_counters[key] == before + 1


def test_bounded_public_reader_block_is_counted_without_global_call() -> None:
    class Repository:
        def future_market_observations(self):  # type: ignore[no-untyped-def]
            raise AssertionError("global reader must remain blocked")

    registry = default_metric_registry()
    key = (
        "w2_public_tripwire_blocks_total",
        (("reader", "global_observation"),),
    )
    before = registry.labelled_counters.get(key, 0)
    service = ReadModelService(repository=Repository())  # type: ignore[arg-type]
    service._bounded_public_request = True

    assert service._cached_future_market_observations() == []
    assert registry.labelled_counters[key] == before + 1
