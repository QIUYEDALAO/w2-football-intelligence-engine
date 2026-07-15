from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from time import sleep

import pytest

from w2.api.singleflight_cache import SingleFlightCache


def test_same_cold_key_computes_once_with_eight_threads() -> None:
    cache: SingleFlightCache[str, dict[str, int]] = SingleFlightCache()
    barrier = threading.Barrier(8)
    calls = 0
    lock = threading.Lock()

    def task() -> dict[str, int]:
        nonlocal calls
        barrier.wait()

        def compute() -> dict[str, int]:
            nonlocal calls
            with lock:
                calls += 1
            sleep(0.05)
            return {"value": 1}

        return cache.get_or_compute("cold", ttl_seconds=10, compute=compute)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: task(), range(8)))

    assert calls == 1
    assert results == [{"value": 1}] * 8
    assert cache.metrics()["singleflight_owner"] == 1
    assert cache.metrics()["singleflight_waiter"] == 7


def test_waiters_receive_equal_independent_copies() -> None:
    cache: SingleFlightCache[str, dict[str, list[int]]] = SingleFlightCache()
    barrier = threading.Barrier(2)

    def task() -> dict[str, list[int]]:
        barrier.wait()
        return cache.get_or_compute(
            "key", ttl_seconds=10, compute=lambda: {"items": [1]}
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: task(), range(2)))
    first["items"].append(2)

    assert second == {"items": [1]}
    assert first is not second


def test_different_keys_compute_concurrently() -> None:
    cache: SingleFlightCache[str, str] = SingleFlightCache()
    entered = threading.Barrier(2)

    def task(key: str) -> str:
        def compute() -> str:
            entered.wait(timeout=1)
            return key

        return cache.get_or_compute(key, ttl_seconds=10, compute=compute)

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert set(executor.map(task, ("a", "b"))) == {"a", "b"}


def test_owner_exception_reaches_waiters_and_cleans_flight() -> None:
    cache: SingleFlightCache[str, int] = SingleFlightCache()
    barrier = threading.Barrier(2)
    failure = ValueError("boom")

    def task() -> int:
        barrier.wait()

        def compute() -> int:
            sleep(0.05)
            raise failure

        return cache.get_or_compute("key", ttl_seconds=10, compute=compute)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(task) for _ in range(2)]
    errors = [future.exception() for future in futures]

    assert errors == [failure, failure]
    assert cache.metrics()["build_inflight"] == 0
    assert cache.get_or_compute("key", ttl_seconds=10, compute=lambda: 7) == 7


def test_recursive_same_key_does_not_deadlock() -> None:
    cache: SingleFlightCache[str, int] = SingleFlightCache()

    with pytest.raises(RuntimeError, match="recursive single-flight"):
        cache.get_or_compute(
            "key",
            ttl_seconds=10,
            compute=lambda: cache.get_or_compute(
                "key", ttl_seconds=10, compute=lambda: 1
            ),
        )


def test_expired_entries_are_pruned() -> None:
    now = [1.0]
    cache: SingleFlightCache[str, int] = SingleFlightCache(clock=lambda: now[0])

    assert cache.get_or_compute("key", ttl_seconds=1, compute=lambda: 1) == 1
    now[0] = 3.0
    assert cache.get_or_compute("key", ttl_seconds=1, compute=lambda: 2) == 2
    assert cache.metrics()["cache_miss"] == 2


def test_cache_max_size_is_enforced() -> None:
    cache: SingleFlightCache[str, int] = SingleFlightCache(max_entries=2)
    for index in range(3):
        cache.get_or_compute(str(index), ttl_seconds=10, compute=lambda i=index: i)

    assert cache.metrics()["cache_entry_count"] == 2
    assert cache.get_or_compute("0", ttl_seconds=10, compute=lambda: 9) == 9


def test_cache_reports_miss_then_hit_status() -> None:
    cache: SingleFlightCache[str, int] = SingleFlightCache()

    first, first_status = cache.get_or_compute_with_status(
        "key", ttl_seconds=10, compute=lambda: 1
    )
    second, second_status = cache.get_or_compute_with_status(
        "key", ttl_seconds=10, compute=lambda: 2
    )

    assert (first, first_status) == (1, "MISS")
    assert (second, second_status) == (1, "HIT")


def test_cache_reports_waiter_status() -> None:
    cache: SingleFlightCache[str, int] = SingleFlightCache()
    barrier = threading.Barrier(2)

    def task() -> tuple[int, str]:
        barrier.wait()
        return cache.get_or_compute_with_status(
            "key",
            ttl_seconds=10,
            compute=lambda: (sleep(0.05), 1)[1],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: task(), range(2)))

    assert sorted(status for _, status in results) == ["MISS", "WAITER"]
