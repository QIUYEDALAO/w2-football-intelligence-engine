from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.exc import SQLAlchemyError

import w2.api.repository as repository_module
from w2.api.repository import ReadModelRepository, ReadModelService
from w2.dashboard.day_view import build_dashboard_day_view


class _FailingFutureRepository:
    def fixture_payloads(self) -> list[dict[str, Any]]:
        raise SQLAlchemyError("database unavailable")


def test_fixture_reader_preserves_checkpoint_fallback_when_database_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ReadModelRepository()
    monkeypatch.setattr(
        repository,
        "dashboard_latest_fixtures",
        lambda: [{"fixture_id": "fallback-1"}],
    )
    monkeypatch.setattr(
        repository,
        "_dashboard_fixture_to_provider_payload",
        lambda item: {
            "fixture": {"id": item["fixture_id"], "date": "2026-07-15T12:00:00Z"}
        },
    )
    monkeypatch.setattr(
        repository_module,
        "future_refresh_db_repository",
        lambda: _FailingFutureRepository(),
    )

    payloads, status = repository.fixture_payloads_with_status()

    assert [item["fixture"]["id"] for item in payloads] == ["fallback-1"]
    assert status == {
        "degraded_source": "fixture_payloads",
        "failed_source": "future_refresh_db.fixture_payloads",
        "error_class": "SQLAlchemyError",
        "fallback_source": "dashboard_checkpoint",
        "data_completeness": "FALLBACK_ONLY",
    }


def test_day_view_reports_reader_failure_instead_of_empty_day() -> None:
    view = build_dashboard_day_view(
        {
            "generated_at": "2026-07-15T00:00:00Z",
            "date": "2026-07-15",
            "selected_football_day": "2026-07-15",
            "timezone": "Asia/Shanghai",
            "window": "today",
            "version": {},
            "all": [],
            "read_degradation": {
                "degraded_source": "fixture_payloads",
                "failed_source": "future_refresh_db.fixture_payloads",
                "error_class": "OperationalError",
                "fallback_source": None,
                "data_completeness": "EMPTY_AFTER_SOURCE_FAILURE",
            },
        },
        environment="staging",
    )

    assert view["degradation"]["state"] == "DEGRADED_READ"
    assert view["degradation"]["reason_code"] == "READ_MODEL_SOURCE_FAILURE"
    assert view["degradation"]["failed_source"] == "future_refresh_db.fixture_payloads"
    assert view["degradation"]["error_class"] == "OperationalError"
    assert view["degradation"]["data_completeness"] == "EMPTY_AFTER_SOURCE_FAILURE"


def test_service_keeps_fixture_read_diagnostics_in_request_scope(tmp_path: Path) -> None:
    status = {
        "degraded_source": "fixture_payloads",
        "failed_source": "future_refresh_db.fixture_payloads",
        "error_class": "OperationalError",
        "fallback_source": "dashboard_checkpoint",
        "data_completeness": "FALLBACK_ONLY",
    }

    class _Repository:
        def fixture_payloads_with_status(
            self,
        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            return ([{"fixture": {"id": "fallback-1"}}], status)

    service = ReadModelService(
        repository=cast(Any, _Repository()),
        r4_1_artifact_root=tmp_path,
    )

    with service._read_request_scope():
        assert service._cached_fixture_payloads() == [{"fixture": {"id": "fallback-1"}}]
        assert service._fixture_read_status_cache == status
