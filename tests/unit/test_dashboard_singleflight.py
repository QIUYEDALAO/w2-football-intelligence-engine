from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from typing import Any, cast

from w2.api.repository import ReadModelService
from w2.config import Environment
from w2.tracking.forward_ledger_performance_cache import ForwardLedgerPerformanceCache


class _EmptyRepository:
    def release_counts(self) -> dict[str, int]:
        return {
            "read_model_fixture_count": 0,
            "matchday_card_count": 0,
            "future_fixture_count": 0,
            "result_event_count": 0,
        }

    def staging_seed_dashboard(self) -> None:
        return None

    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        return []

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return []

    def result_events(self) -> list[dict[str, Any]]:
        return []

    def future_market_observations(self) -> list[dict[str, Any]]:
        return []


def test_cold_dashboard_concurrency_does_not_multiply_build() -> None:
    service = ReadModelService(repository=cast(Any, _EmptyRepository()))
    barrier = threading.Barrier(8)
    lock = threading.Lock()
    calls = 0

    def build(**_: object) -> dict[str, Any]:
        nonlocal calls
        with lock:
            calls += 1
        sleep(0.05)
        return {"performance": {}, "all": []}

    service._build_dashboard_payload = build  # type: ignore[attr-defined,method-assign]

    def task(_: int) -> dict[str, Any]:
        barrier.wait()
        return service.dashboard(target_date="2026-07-15", window="future")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(task, range(8)))

    assert calls == 1
    assert all(
        row["performance"]["dashboard_cache_metrics"]["dashboard_singleflight_owner"]
        == 1
        for row in results
    )
    assert max(
        row["performance"]["dashboard_cache_metrics"]["dashboard_singleflight_waiter"]
        for row in results
    ) == 7
    results[0]["all"].append({"fixture_id": "mutated"})
    assert results[1]["all"] == []


def test_cold_dayview_concurrency_does_not_multiply_build() -> None:
    service = ReadModelService(repository=cast(Any, _EmptyRepository()))
    barrier = threading.Barrier(8)
    lock = threading.Lock()
    calls = 0

    def build(**_: object) -> dict[str, Any]:
        nonlocal calls
        with lock:
            calls += 1
        sleep(0.05)
        return {"performance": {}, "cards": []}

    service._build_dashboard_day_view_payload = build  # type: ignore[method-assign]

    def task(_: int) -> dict[str, Any]:
        barrier.wait()
        return service.dashboard_day_view(target_date="2026-07-15", window="future")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(task, range(8)))

    assert calls == 1
    assert all("dayview_cache_metrics" in row["performance"] for row in results)
    assert max(
        row["performance"]["dayview_cache_metrics"]["dayview_singleflight_waiter"]
        for row in results
    ) == 7


def test_dayview_cache_identity_includes_release_sha(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    service = ReadModelService(repository=cast(Any, _EmptyRepository()))
    calls = 0

    def build(**_: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"performance": {}, "cards": []}

    service._build_dashboard_day_view_payload = build  # type: ignore[method-assign]
    monkeypatch.setenv("W2_GIT_SHA", "release-a")
    service.dashboard_day_view(target_date="2026-07-15", window="future")
    monkeypatch.setenv("W2_GIT_SHA", "release-b")
    service.dashboard_day_view(target_date="2026-07-15", window="future")

    assert calls == 2


def test_dayview_reports_critical_path_metrics(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    service = ReadModelService(repository=cast(Any, _EmptyRepository()))
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=tmp_path,
            environment=Environment.TEST,
        ),
    )

    payload = service.dashboard_day_view(target_date="2026-07-15", window="future")
    metrics = payload["performance"]["dayview_cache_metrics"]

    for field in (
        "fixture_read_seconds",
        "market_observation_read_seconds",
        "compact_card_projection_seconds",
        "ledger_summary_seconds",
        "dayview_serialization_seconds",
        "response_bytes",
    ):
        assert field in metrics


def test_today_and_future_share_ledger_projection(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = 0

    def build(_: Path, **__: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "source_read_status": "PASS",
            "record_count": 0,
            "fixture_count": 0,
            "validation_fixture_count": 0,
        }

    ledger_cache = ForwardLedgerPerformanceCache(builder=build)
    service = ReadModelService(
        repository=cast(Any, _EmptyRepository()),
        forward_ledger_cache=ledger_cache,
    )
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=tmp_path,
            environment=Environment.TEST,
        ),
    )

    service.dashboard(target_date="2026-07-15", window="today")
    service.dashboard(target_date="2026-07-15", window="future")

    assert calls == 1
    assert ledger_cache.metrics()["ledger_build_count"] == 1
    assert ledger_cache.metrics()["ledger_cache_hit"] == 1


def test_cold_dashboard_concurrency_does_not_multiply_ledger_parse(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    barrier = threading.Barrier(8)
    calls = 0
    lock = threading.Lock()

    def build(_: Path, **__: object) -> dict[str, Any]:
        nonlocal calls
        with lock:
            calls += 1
        sleep(0.05)
        return {
            "source_read_status": "PASS",
            "record_count": 0,
            "fixture_count": 0,
            "validation_fixture_count": 0,
        }

    ledger_cache = ForwardLedgerPerformanceCache(builder=build)
    service = ReadModelService(
        repository=cast(Any, _EmptyRepository()),
        forward_ledger_cache=ledger_cache,
    )
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=tmp_path,
            environment=Environment.TEST,
        ),
    )

    def task(_: int) -> dict[str, Any]:
        barrier.wait()
        return service.dashboard(target_date="2026-07-15", window="future")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(task, range(8)))

    assert calls == 1
    metrics = ledger_cache.metrics()
    assert metrics["ledger_build_count"] == 1
