from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Any

from w2.api.singleflight_cache import SingleFlightCache
from w2.tracking.canonical_outcomes import CANONICAL_OUTCOME_PROJECTION_VERSION
from w2.tracking.forward_ledger_performance import forward_ledger_performance

LEDGER_PERFORMANCE_CACHE_POLICY = "w2.forward_ledger_performance_cache.v1"


class ForwardLedgerPerformanceCache:
    def __init__(
        self,
        *,
        builder: Callable[..., dict[str, Any]] = forward_ledger_performance,
        ttl_seconds: float = 300.0,
        max_entries: int = 4,
    ) -> None:
        self._builder = builder
        self._ttl_seconds = ttl_seconds
        self._cache: SingleFlightCache[tuple[Any, ...], dict[str, Any]] = (
            SingleFlightCache(max_entries=max_entries)
        )
        self._lock = RLock()
        self._build_seconds = 0.0
        self._build_count = 0
        self._last_record_count = 0

    def get(
        self,
        runtime_root: Path,
        *,
        result_events: Sequence[Mapping[str, Any]] | None,
    ) -> dict[str, Any]:
        key = self.fingerprint(runtime_root, result_events=result_events)

        def build() -> dict[str, Any]:
            started = monotonic()
            payload = self._builder(runtime_root, result_events=result_events)
            with self._lock:
                self._build_seconds += monotonic() - started
                self._build_count += 1
                self._last_record_count = int(payload.get("record_count") or 0)
            return payload

        payload = self._cache.get_or_compute(
            key,
            ttl_seconds=self._ttl_seconds,
            compute=build,
        )
        if str(payload.get("source_read_status") or "PASS") != "PASS":
            self._cache.clear()
        return deepcopy(payload)

    def fingerprint(
        self,
        runtime_root: Path,
        *,
        result_events: Sequence[Mapping[str, Any]] | None,
    ) -> tuple[Any, ...]:
        root = (runtime_root / "forward_outcome_ledger").resolve()
        files: list[tuple[str, int, int]] = []
        try:
            for path in sorted(root.glob("*.jsonl")):
                stat = path.stat()
                files.append((path.name, stat.st_size, stat.st_mtime_ns))
            source_status = "PRESENT" if root.exists() else "MISSING"
        except OSError as error:
            source_status = f"STAT_ERROR:{type(error).__name__}"
        return (
            LEDGER_PERFORMANCE_CACHE_POLICY,
            CANONICAL_OUTCOME_PROJECTION_VERSION,
            str(root),
            source_status,
            tuple(files),
            _result_event_fingerprint(result_events),
        )

    def clear(self) -> None:
        self._cache.clear()

    def metrics(self) -> dict[str, int | float]:
        cache_metrics = self._cache.metrics()
        with self._lock:
            return {
                "ledger_cache_hit": cache_metrics["cache_hit"],
                "ledger_cache_miss": cache_metrics["cache_miss"],
                "ledger_singleflight_owner": cache_metrics["singleflight_owner"],
                "ledger_singleflight_waiter": cache_metrics["singleflight_waiter"],
                "ledger_build_inflight": cache_metrics["build_inflight"],
                "ledger_build_seconds": round(self._build_seconds, 6),
                "ledger_build_count": self._build_count,
                "ledger_record_count": self._last_record_count,
            }


def _result_event_fingerprint(
    result_events: Sequence[Mapping[str, Any]] | None,
) -> str:
    if result_events is None:
        return "RESULT_SOURCE_UNAVAILABLE"
    rows = []
    for event in result_events:
        encoded = json.dumps(
            dict(event),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        rows.append(
            {
                "fixture_id": str(event.get("fixture_id") or ""),
                "status": str(event.get("status") or ""),
                "confirmed_at": str(event.get("confirmed_at") or ""),
                "event_identity": str(
                    event.get("raw_payload_hash")
                    or event.get("event_id")
                    or hashlib.sha256(encoded).hexdigest()
                ),
            }
        )
    encoded_rows = json.dumps(
        sorted(rows, key=lambda row: tuple(row.values())),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded_rows).hexdigest()
