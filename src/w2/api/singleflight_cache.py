from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from threading import Event, RLock, get_ident
from time import monotonic
from typing import TypeVar, cast

K = TypeVar("K", bound=Hashable)
T = TypeVar("T")


@dataclass
class _Flight[T]:
    owner_thread_id: int
    event: Event
    result: T | None = None
    error: BaseException | None = None


class SingleFlightCache[K, T]:
    def __init__(
        self,
        *,
        max_entries: int = 32,
        max_wait_seconds: float = 60.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._max_wait_seconds = max_wait_seconds
        self._clock = clock
        self._lock = RLock()
        self._cache: OrderedDict[K, tuple[float, T]] = OrderedDict()
        self._flights: dict[K, _Flight[T]] = {}
        self._counters = {
            "cache_hit": 0,
            "cache_miss": 0,
            "singleflight_owner": 0,
            "singleflight_waiter": 0,
        }

    def get_or_compute(
        self,
        key: K,
        *,
        ttl_seconds: float,
        compute: Callable[[], T],
    ) -> T:
        thread_id = get_ident()
        with self._lock:
            now = self._clock()
            self._prune_expired(now)
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                self._counters["cache_hit"] += 1
                return deepcopy(cached[1])
            self._counters["cache_miss"] += 1
            flight = self._flights.get(key)
            if flight is not None:
                if flight.owner_thread_id == thread_id:
                    raise RuntimeError("recursive single-flight call for the same key")
                self._counters["singleflight_waiter"] += 1
                owner = False
            else:
                flight = _Flight(owner_thread_id=thread_id, event=Event())
                self._flights[key] = flight
                self._counters["singleflight_owner"] += 1
                owner = True

        if not owner:
            if not flight.event.wait(self._max_wait_seconds):
                raise TimeoutError("single-flight owner did not complete before timeout")
            if flight.error is not None:
                raise flight.error
            return deepcopy(cast(T, flight.result))

        try:
            result = compute()
        except BaseException as error:
            with self._lock:
                flight.error = error
                flight.event.set()
                self._flights.pop(key, None)
            raise
        with self._lock:
            flight.result = deepcopy(result)
            self._cache[key] = (self._clock() + max(ttl_seconds, 0.0), deepcopy(result))
            self._cache.move_to_end(key)
            self._enforce_max_entries()
            flight.event.set()
            self._flights.pop(key, None)
        return deepcopy(result)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def metrics(self) -> Mapping[str, int]:
        with self._lock:
            return {
                **self._counters,
                "cache_entry_count": len(self._cache),
                "build_inflight": len(self._flights),
            }

    def _prune_expired(self, now: float) -> None:
        expired = [key for key, (expires_at, _) in self._cache.items() if expires_at <= now]
        for key in expired:
            self._cache.pop(key, None)

    def _enforce_max_entries(self) -> None:
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)
