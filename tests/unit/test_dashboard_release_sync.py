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


class FutureFixtureRepository(EmptyReleaseRepository):
    def release_counts(self) -> dict[str, int]:
        counts = super().release_counts()
        counts["future_fixture_count"] = 3
        return counts

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {"fixture": {"id": 9000, "status": {"short": "NS"}}},
            {
                "fixture": {
                    "id": 9001,
                    "date": "2026-06-26T10:00:00Z",
                    "status": {"short": "NS"},
                },
                "league": {"id": 1, "name": "FIFA World Cup"},
                "teams": {
                    "home": {"id": 1, "name": "Home"},
                    "away": {"id": 2, "name": "Away"},
                },
            },
            {
                "fixture": {
                    "id": 9002,
                    "date": "2026-06-28T10:00:00Z",
                    "status": {"short": "NS"},
                },
                "league": {"id": 1, "name": "FIFA World Cup"},
                "teams": {
                    "home": {"id": 3, "name": "Home 2"},
                    "away": {"id": 4, "name": "Away 2"},
                },
            },
        ]


class CountingFutureFixtureRepository(FutureFixtureRepository):
    def __init__(self) -> None:
        self.fixture_payload_calls = 0

    def fixture_payloads(self) -> list[dict[str, Any]]:
        self.fixture_payload_calls += 1
        return super().fixture_payloads()


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
    dashboard = client.get(
        "/v1/dashboard?date=2026-06-26&window=today&include_debug=true"
    ).json()

    assert version["api_git_sha"] == "UNKNOWN"
    assert dashboard["debug"]["empty_reason"] == "READ_MODEL_EMPTY"
    assert dashboard["all"] == []


def test_public_dashboard_defaults_to_lightweight_response(monkeypatch) -> None:
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(repository=cast(Any, EmptyReleaseRepository())),
    )
    client = TestClient(app)

    dashboard = client.get("/v1/dashboard?date=2026-06-26&window=today").json()

    assert dashboard["debug"] == {}
    assert dashboard["all"] == []


def test_public_dashboard_summary_returns_aggregate_without_cards(monkeypatch) -> None:
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(repository=cast(Any, FutureFixtureRepository())),
    )
    client = TestClient(app)

    summary = client.get("/v1/dashboard/summary?date=2026-06-26&window=all").json()

    assert summary["date"] == "2026-06-26"
    assert summary["window"] == "all"
    assert summary["totals"] == {
        "recommendations": 0,
        "upcoming": 2,
        "finished": 0,
        "all": 2,
    }
    assert "performance" in summary
    assert "debug" not in summary
    assert "all" not in summary
    assert "upcoming" not in summary
    assert "finished" not in summary


def test_dashboard_falls_back_to_future_fixture_payloads() -> None:
    service = ReadModelService(repository=cast(Any, FutureFixtureRepository()))

    today = service.dashboard(target_date="2026-06-26", window="today")
    all_payload = service.dashboard(target_date="2026-06-26", window="all")

    assert today["data_profile"] == "real-db"
    assert len(today["all"]) == 1
    assert today["debug"]["empty_reason"] is None
    assert today["debug"]["future_fixture_in_window_count"] == 1
    assert today["debug"]["future_fixture_parse_error_count"] == 1
    assert today["debug"]["future_fixture_status_distribution"] == {"NS": 2}
    assert today["debug"]["future_fixture_min_kickoff_utc"] == "2026-06-26T10:00:00Z"
    assert today["debug"]["future_fixture_max_kickoff_utc"] == "2026-06-28T10:00:00Z"
    assert today["debug"]["next_available_date"] == "2026-06-26"
    assert len(all_payload["all"]) == 2


def test_dashboard_reuses_short_lived_cache_for_same_window() -> None:
    repository = CountingFutureFixtureRepository()
    service = ReadModelService(repository=cast(Any, repository))

    first = service.dashboard(target_date="2026-06-26", window="today", include_debug=False)
    second = service.dashboard(target_date="2026-06-26", window="today", include_debug=False)

    assert len(first["all"]) == 1
    assert second == first
    assert repository.fixture_payload_calls == 1


def test_frontend_uses_release_sync_endpoints_and_demo_is_explicit() -> None:
    body = Path("apps/web/src/lib/dashboardApi.ts").read_text(encoding="utf-8")

    assert 'getJSON("/meta.json")' in body
    assert 'getJSON(`${API_BASE}/version`)' in body
    assert '`${API_BASE}/dashboard?' in body
    assert 'include_debug: includeDebug ? "true" : "false"' in body
    assert "getCachedDashboardView" in body
    assert 'params.get("demo") === "1"' in body
    assert 'VITE_DASHBOARD_DATA_MODE === "demo"' in body
    assert "DEMO DATA" in body
