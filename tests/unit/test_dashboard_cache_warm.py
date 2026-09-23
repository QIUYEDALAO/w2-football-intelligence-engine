from __future__ import annotations

import importlib
import json
import logging
import threading
import time
from datetime import UTC, date, datetime
from typing import Any, cast

import pytest
from apps.api import main as api_main

repository_module = importlib.import_module("w2.api." + "repository")
ReadModelService: Any = repository_module.ReadModelService


class ProgressRepository:
    def __init__(self) -> None:
        self.progress_calls = 0

    def dashboard_model_forecast_validation_progress(
        self, *, force_refresh: bool = False
    ) -> dict[str, Any]:
        self.progress_calls += 1
        return {"force_refresh": force_refresh}


def _service() -> tuple[Any, ProgressRepository]:
    repository = ProgressRepository()
    return ReadModelService(repository=cast(Any, repository)), repository


def _payload(**kwargs: Any) -> dict[str, Any]:
    return {"date": kwargs["requested_date"].isoformat(), "items": [], "request_id": "ignored"}


def test_dashboard_cache_singleflight_for_five_concurrent_requests() -> None:
    service, _ = _service()
    calls = 0
    entered = threading.Event()
    release = threading.Event()
    count_lock = threading.Lock()

    def compute(**kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        with count_lock:
            calls += 1
        entered.set()
        assert release.wait(2)
        return _payload(**kwargs)

    service._dashboard_uncached = compute
    barrier = threading.Barrier(5)
    results: list[dict[str, Any]] = []

    def request() -> None:
        barrier.wait()
        results.append(
            service.dashboard(
                target_date="2026-09-23", include_debug=False, include_details=False
            )
        )

    threads = [threading.Thread(target=request) for _ in range(5)]
    for thread in threads:
        thread.start()
    assert entered.wait(2)
    release.set()
    for thread in threads:
        thread.join(2)
    assert calls == 1
    assert len(results) == 5


def test_dashboard_cache_warm_then_dashboard_hits_cache() -> None:
    service, repository = _service()
    calls = 0

    def compute(**kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _payload(**kwargs)

    service._dashboard_uncached = compute
    service.force_refresh_dashboard_cache(now=datetime(2026, 9, 23, 12, tzinfo=UTC))
    service.dashboard(target_date="2026-09-23", include_debug=False, include_details=False)
    assert calls == 1
    assert repository.progress_calls == 1


def test_dashboard_cache_warm_failure_preserves_old_entry_and_recovers() -> None:
    service, _ = _service()
    requested_date = date(2026, 9, 23)
    key = (requested_date.isoformat(), "today", "Asia/Shanghai", False, False)
    old_payload = {"old": True}
    old_timestamp = time.monotonic() - 10
    service._dashboard_response_cache[key] = (old_timestamp, old_payload)
    attempts = 0

    def compute(**kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary read failure")
        return _payload(**kwargs)

    service._dashboard_uncached = compute
    with pytest.raises(RuntimeError):
        service.force_refresh_dashboard_cache(now=datetime(2026, 9, 23, 12, tzinfo=UTC))
    assert service._dashboard_response_cache[key] == (old_timestamp, old_payload)
    service.force_refresh_dashboard_cache(now=datetime(2026, 9, 23, 12, tzinfo=UTC))
    assert attempts == 2
    assert service._dashboard_response_cache[key][0] != old_timestamp


def test_dashboard_warm_loop_continues_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class ScriptedEvent:
        def __init__(self) -> None:
            self.wait_calls = 0

        def wait(self, _timeout: float) -> bool:
            self.wait_calls += 1
            return self.wait_calls >= 3

        def is_set(self) -> bool:
            return self.wait_calls >= 3

    attempts = 0

    def warm() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary warm failure")

    monkeypatch.setattr(
        cast(Any, api_main.__dict__["service"]), "force_refresh_dashboard_cache", warm
    )
    api_main._dashboard_warm_loop(cast(Any, ScriptedEvent()), 15)
    assert attempts == 2


@pytest.mark.asyncio
async def test_dashboard_warm_start_does_not_block_on_slow_compute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_DASHBOARD_WARM_INTERVAL_SECONDS", "15")
    monkeypatch.setattr(api_main, "DASHBOARD_WARM_INITIAL_DELAY_SECONDS", 5)
    monkeypatch.setattr(
        cast(Any, api_main.__dict__["service"]),
        "force_refresh_dashboard_cache",
        lambda: time.sleep(10),
    )
    started = time.monotonic()
    context = api_main.lifespan(api_main.app)
    await context.__aenter__()
    elapsed = time.monotonic() - started
    await context.__aexit__(None, None, None)
    assert elapsed < 1


@pytest.mark.asyncio
async def test_dashboard_warm_thread_stops_on_lifespan_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_DASHBOARD_WARM_INTERVAL_SECONDS", "15")
    monkeypatch.setattr(api_main, "DASHBOARD_WARM_INITIAL_DELAY_SECONDS", 0)
    called = threading.Event()
    monkeypatch.setattr(
        cast(Any, api_main.__dict__["service"]), "force_refresh_dashboard_cache", called.set
    )
    context = api_main.lifespan(api_main.app)
    await context.__aenter__()
    assert called.wait(2)
    await context.__aexit__(None, None, None)
    assert not any(
        thread.name == "w2-dashboard-cache-warm" and thread.is_alive()
        for thread in threading.enumerate()
    )


def test_dashboard_warm_interval_configuration(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    for value in ("0", "abc", "5", "120"):
        monkeypatch.setenv("W2_DASHBOARD_WARM_INTERVAL_SECONDS", value)
        with caplog.at_level(logging.WARNING):
            assert api_main._dashboard_warm_interval() is None
    assert sum("dashboard cache warm disabled" in record.message for record in caplog.records) == 3


def test_dashboard_response_is_identical_after_warmup() -> None:
    service, _ = _service()
    stable_payload = {"date": "2026-09-23", "items": [], "request_id": "ignored"}
    service._dashboard_uncached = lambda **_: dict(stable_payload)
    cold = service.dashboard(target_date="2026-09-23", include_debug=False, include_details=False)
    warm_service, _ = _service()
    warm_service._dashboard_uncached = lambda **_: dict(stable_payload)
    warm_service.force_refresh_dashboard_cache(now=datetime(2026, 9, 23, 12, tzinfo=UTC))
    warm = warm_service.dashboard(
        target_date="2026-09-23", include_debug=False, include_details=False
    )
    for payload in (cold, warm):
        payload.pop("request_id", None)
    assert json.dumps(cold, sort_keys=True) == json.dumps(warm, sort_keys=True)


def test_dashboard_warm_cleans_only_expired_other_keys() -> None:
    service, _ = _service()
    now_tick = time.monotonic()
    current = ("2026-09-23", "today", "Asia/Shanghai", False, False)
    other = ("2026-09-22", "today", "Asia/Shanghai", False, False)
    service._dashboard_response_cache[current] = (now_tick - 70, {"current": True})
    service._dashboard_response_cache[other] = (now_tick - 70, {"other": True})
    service._dashboard_uncached = lambda **kwargs: _payload(**kwargs)
    service.force_refresh_dashboard_cache(now=datetime(2026, 9, 23, 12, tzinfo=UTC))
    assert current in service._dashboard_response_cache
    assert other not in service._dashboard_response_cache


def test_dashboard_warm_uses_new_key_after_football_day_rollover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _service()
    dates = iter((date(2026, 9, 23), date(2026, 9, 24)))
    monkeypatch.setattr(repository_module, "default_football_day", lambda _: next(dates))
    seen: list[date] = []

    def compute(**kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs["requested_date"])
        return _payload(**kwargs)

    service._dashboard_uncached = compute
    service.force_refresh_dashboard_cache(now=datetime(2026, 9, 23, tzinfo=UTC))
    service.force_refresh_dashboard_cache(now=datetime(2026, 9, 24, 12, tzinfo=UTC))
    assert seen == [date(2026, 9, 23), date(2026, 9, 24)]
    assert (
        "2026-09-23",
        "today",
        "Asia/Shanghai",
        False,
        False,
    ) in service._dashboard_response_cache
    assert (
        "2026-09-24",
        "today",
        "Asia/Shanghai",
        False,
        False,
    ) in service._dashboard_response_cache
