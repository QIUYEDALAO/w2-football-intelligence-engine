from __future__ import annotations

from pathlib import Path

from w2.tracking.forward_ledger_performance_cache import ForwardLedgerPerformanceCache


def test_ledger_unchanged_hits_cache(tmp_path: Path) -> None:
    _ledger_file(tmp_path).write_text('{}\n', encoding="utf-8")
    calls = 0

    def build(_: Path, **__: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"source_read_status": "PASS", "record_count": 1}

    cache = ForwardLedgerPerformanceCache(builder=build)

    assert cache.get(tmp_path, result_events=[]) == cache.get(
        tmp_path, result_events=[]
    )
    assert calls == 1
    assert cache.metrics()["ledger_cache_hit"] == 1
    assert cache.metrics()["ledger_cache_miss"] == 1


def test_ledger_append_invalidates_cache(tmp_path: Path) -> None:
    path = _ledger_file(tmp_path)
    path.write_text('{}\n', encoding="utf-8")
    calls = 0

    def build(_: Path, **__: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"source_read_status": "PASS", "record_count": calls}

    cache = ForwardLedgerPerformanceCache(builder=build)
    first = cache.get(tmp_path, result_events=[])
    path.write_text('{}\n{}\n', encoding="utf-8")
    second = cache.get(tmp_path, result_events=[])

    assert first["record_count"] == 1
    assert second["record_count"] == 2
    assert calls == 2


def test_result_event_change_invalidates_cache(tmp_path: Path) -> None:
    _ledger_file(tmp_path).write_text('{}\n', encoding="utf-8")
    calls = 0

    def build(_: Path, **__: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"source_read_status": "PASS", "record_count": calls}

    cache = ForwardLedgerPerformanceCache(builder=build)
    cache.get(tmp_path, result_events=[{"fixture_id": "1", "status": "NS"}])
    cache.get(
        tmp_path,
        result_events=[
            {"fixture_id": "1", "status": "FT", "confirmed_at": "2026-07-15T01:00:00Z"}
        ],
    )

    assert calls == 2


def test_corrupt_ledger_status_is_not_hidden(tmp_path: Path) -> None:
    _ledger_file(tmp_path).write_text('{broken\n', encoding="utf-8")
    calls = 0

    def build(_: Path, **__: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "source_read_status": "DEGRADED",
            "source_corruption_count": calls,
            "record_count": 0,
        }

    cache = ForwardLedgerPerformanceCache(builder=build)
    first = cache.get(tmp_path, result_events=[])
    second = cache.get(tmp_path, result_events=[])

    assert first["source_corruption_count"] == 1
    assert second["source_corruption_count"] == 2
    assert calls == 2


def _ledger_file(runtime_root: Path) -> Path:
    root = runtime_root / "forward_outcome_ledger"
    root.mkdir()
    return root / "ledger.jsonl"
