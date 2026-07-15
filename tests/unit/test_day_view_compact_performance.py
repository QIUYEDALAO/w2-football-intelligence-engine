from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy.exc import SQLAlchemyError

from w2.api.repository import ReadModelService
from w2.config import Environment
from w2.tracking.forward_ledger_performance_cache import ForwardLedgerPerformanceCache


class _ResultRepository:
    def __init__(self) -> None:
        self.loads = 0

    def result_events_snapshot(self) -> list[dict[str, Any]]:
        self.loads += 1
        return []


class _UnavailableResultRepository:
    def result_events_snapshot(self) -> list[dict[str, Any]]:
        raise SQLAlchemyError("result source unavailable")


def _ledger_payload() -> dict[str, Any]:
    return {
        "source_read_status": "PASS",
        "record_count": 0,
        "fixture_count": 0,
        "validation_fixture_count": 0,
    }


def test_dayview_hot_path_never_calls_ledger_fixture_ids() -> None:
    source = Path("src/w2/api/repository.py").read_text(encoding="utf-8")
    method = source.split("def _day_view_performance", 1)[1].split(
        "def _compact_forward_ledger_summary", 1
    )[0]

    assert "ledger_fixture_ids" not in method


def test_result_raw_payloads_load_once_per_source_fingerprint(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    result_repository = _ResultRepository()
    ledger_builds = 0

    def build(_: Path, **__: Any) -> dict[str, Any]:
        nonlocal ledger_builds
        ledger_builds += 1
        return _ledger_payload()

    service = ReadModelService(
        repository=cast(Any, object()),
        forward_ledger_cache=ForwardLedgerPerformanceCache(builder=build),
    )
    service._future_refresh_repository_cache = cast(Any, result_repository)
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=tmp_path,
            environment=Environment.TEST,
        ),
    )
    watermark = {
        "result_event_count": 1,
        "result_event_max_confirmed_at": "2026-07-16T00:00:00Z",
        "result_event_source_hash": "event-a",
        "raw_result_count": 2,
        "raw_result_max_captured_at": "2026-07-16T00:00:00Z",
        "fixture_source_hash": "raw-a",
    }

    service._day_view_performance([], source_watermarks=watermark)
    service._day_view_performance([], source_watermarks=watermark)

    assert result_repository.loads == 1
    assert ledger_builds == 1


def test_result_source_watermark_change_invalidates_snapshot(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    result_repository = _ResultRepository()
    service = ReadModelService(repository=cast(Any, object()))
    service._future_refresh_repository_cache = cast(Any, result_repository)
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=tmp_path,
            environment=Environment.TEST,
        ),
    )

    service._day_view_performance([], source_watermarks={"result_event_count": 1})
    service._day_view_performance([], source_watermarks={"result_event_count": 2})

    assert result_repository.loads == 2


def test_unavailable_result_source_is_explicitly_degraded(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    service = ReadModelService(
        repository=cast(Any, object()),
        forward_ledger_cache=ForwardLedgerPerformanceCache(
            builder=lambda *_args, **_kwargs: _ledger_payload()
        ),
    )
    service._future_refresh_repository_cache = cast(Any, _UnavailableResultRepository())
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=tmp_path,
            environment=Environment.TEST,
        ),
    )

    payload = service._day_view_performance([], source_watermarks={})

    ledger = payload["forward_ledger"]
    assert ledger["result_source_status"] == "DEGRADED"
    assert ledger["performance_integrity"] == {
        "result_source_status": "DEGRADED",
        "result_source_reason": "RESULT_SOURCE_UNAVAILABLE",
    }
