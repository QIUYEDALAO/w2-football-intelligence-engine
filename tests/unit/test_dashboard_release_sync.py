from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.api import routers
from w2.api.repository import ReadModelService


class EmptyReleaseRepository:
    def release_counts(self) -> dict[str, int]:
        return {
            "read_model_fixture_count": 0,
            "matchday_card_count": 0,
            "future_fixture_count": 0,
            "result_event_count": 0,
        }

    def staging_seed_dashboard(self) -> dict[str, Any] | None:
        return None

    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        return []

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return []

    def result_events(self) -> list[dict[str, Any]]:
        return []


def test_version_is_unknown_safe_for_empty_environment(monkeypatch) -> None:
    monkeypatch.delenv("W2_GIT_SHA", raising=False)
    monkeypatch.delenv("W2_BUILD_TIME", raising=False)
    monkeypatch.delenv("W2_RELEASE_ID", raising=False)
    service = ReadModelService(repository=cast(Any, EmptyReleaseRepository()))

    payload = service.version()

    assert payload["api_git_sha"] == "UNKNOWN"
    assert payload["data_profile"] == "empty"
    assert payload["data_source"] == "empty"
    assert payload["database_ready"] is True
    assert payload["read_model_fixture_count"] == 0


def test_dashboard_empty_response_has_actionable_diagnostics() -> None:
    service = ReadModelService(repository=cast(Any, EmptyReleaseRepository()))

    payload = service.dashboard(target_date="2026-06-26", window="today")

    assert payload["data_profile"] == "empty"
    assert payload["all"] == []
    debug = payload["debug"]
    assert debug["empty_reason"] == "READ_MODEL_EMPTY"
    assert debug["read_model_fixture_count"] == 0
    assert debug["matchday_card_count"] == 0
    assert debug["future_fixture_count"] == 0
    assert debug["result_event_count"] == 0
    assert debug["selected_date"] == "2026-06-26"
    assert debug["suggested_actions"]


def test_public_release_sync_endpoints_are_available(monkeypatch) -> None:
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(repository=cast(Any, EmptyReleaseRepository())),
    )
    client = TestClient(app)

    version = client.get("/v1/version").json()
    dashboard = client.get("/v1/dashboard?date=2026-06-26&window=today").json()

    assert version["api_git_sha"] == "UNKNOWN"
    assert dashboard["debug"]["empty_reason"] == "READ_MODEL_EMPTY"
    assert dashboard["all"] == []


def test_frontend_uses_release_sync_endpoints_and_demo_is_explicit() -> None:
    body = Path("apps/web/src/lib/dashboardApi.ts").read_text(encoding="utf-8")

    assert 'getJSON("/meta.json")' in body
    assert 'getJSON(`${API_BASE}/version`)' in body
    assert '`${API_BASE}/dashboard?' in body
    assert 'params.get("demo") === "1"' in body
    assert 'VITE_DASHBOARD_DATA_MODE === "demo"' in body
    assert "DEMO DATA" in body
