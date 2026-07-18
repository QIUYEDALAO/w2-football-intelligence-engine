from __future__ import annotations

import json
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

    def future_market_observations(self) -> list[dict[str, Any]]:
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


class SplitPublicFixtureRepository(FutureFixtureRepository):
    def public_release_counts(self, *, limit: int) -> dict[str, int]:
        assert limit == 512
        return {
            "read_model_fixture_count": 0,
            "matchday_card_count": 0,
            "future_fixture_count": 1,
            "result_event_count": 0,
        }

    def public_fixture_payloads(self, *, limit: int) -> list[dict[str, Any]]:
        return self.fixture_payloads()[1:2][:limit]


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


def test_public_validation_summary_returns_layered_sample_status(monkeypatch) -> None:
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(repository=cast(Any, FutureFixtureRepository())),
    )
    client = TestClient(app)

    summary = client.get("/v1/validation/summary?date=2026-06-26&window=all").json()

    assert summary["date"] == "2026-06-26"
    assert summary["window"] == "all"
    assert summary["validation"]["beats_market"] is False
    assert summary["validation"]["official"]["hit_rate"] is None
    assert summary["validation"]["official"]["label"] == "official 样本不足，暂不计算命中率"
    assert (
        summary["validation"]["analysis_shadow"]["label"]
        == "analysis_shadow 样本不足，暂不计算命中率"
    )
    assert "all" not in summary
    assert "debug" not in summary


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


def test_dashboard_future_window_uses_full_cards_not_index_rows(monkeypatch) -> None:
    service = ReadModelService(repository=cast(Any, FutureFixtureRepository()))

    def full_card(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "fixture_id": str(row["fixture_id"]),
            "kickoff_utc": row.get("kickoff_utc"),
            "status": row.get("status"),
            "decision_tier": "WATCH",
            "data_status": "PARTIAL",
            "lifecycle_status": "DRAFT",
            "current_odds": {"ah": {"home_line": "-0.25"}},
            "decision_contract": {
                "decision_tier": "WATCH",
                "data_status": "PARTIAL",
                "lifecycle_status": "DRAFT",
            },
        }

    monkeypatch.setattr(service, "_dashboard_card_from_matchday", full_card)
    monkeypatch.setattr(
        service,
        "_dashboard_index_card_from_matchday",
        lambda row: {"fixture_id": row["fixture_id"], "index_only": True},
    )

    payload = service.dashboard(target_date="2026-06-26", window="future", include_debug=True)

    assert payload["window"] == "future"
    assert [card["fixture_id"] for card in payload["all"]] == ["9001", "9002"]
    assert payload["all"][0]["current_odds"]["ah"]["home_line"] == "-0.25"
    assert "index_only" not in payload["all"][0]


def test_dashboard_all_window_compacts_heavy_card_payload(monkeypatch) -> None:
    service = ReadModelService(repository=cast(Any, FutureFixtureRepository()))

    def heavy_card(row: dict[str, Any]) -> dict[str, Any]:
        fixture_id = str(row.get("fixture_id"))
        return {
            "fixture_id": fixture_id,
            "kickoff_utc": row.get("kickoff_utc"),
            "competition_name": "FIFA World Cup",
            "home_team_name": "Home",
            "away_team_name": "Away",
            "status": "NS",
            "analysis_readiness": {"status": "READY"},
            "data_refresh": {
                "odds_status": "READY",
                "lineups_status": "NOT_REQUIRED",
                "xg_status": "READY",
            },
            "recommendation": {
                "recommendation_id": f"rec-{fixture_id}",
                "id": f"rec-row-{fixture_id}",
                "tier": "FORMAL",
                "market": "ASIAN_HANDICAP",
                "selection": "HOME_AH",
                "line": -0.5,
                "formal_recommendation": True,
            },
            "formal_suppressed": False,
            "formal_suppressed_reason": None,
            "scoreline_reference": {"direction_top3": []},
            "result": None,
            "validation": {"settlement": None},
            "current_odds": {
                "ah": {
                    "line": 0.5,
                    "home_line": 0.5,
                    "away_line": -0.5,
                    "display_line_cn": "客队 -0.5",
                },
                "alternate_lines": [{"payload": "x" * 2000}],
            },
            "market_timeline": {
                "label": "盘口时间线 · 参照 · 未验证",
                "verified": False,
                "direction_allowed": False,
                "open": {"line": 0.5, "home_price": 1.9, "away_price": 1.9},
                "current": {"line": 0.5, "home_price": 1.91, "away_price": 1.89},
            },
            "market_strip": [{"payload": "x" * 5000}],
            "bookmaker_intent": {"payload": "x" * 5000},
            "bookmaker_hypothesis": {"payload": "x" * 5000},
            "pricing_shadow": {
                "status": "READY",
                "simulation_status": "READY",
                "fair_ah": 0.25,
                "market_ah": 0.5,
                "edge_ah": 0.25,
                "beats_market": False,
                "formal_enabled": False,
                "formal_eligible": False,
                "formal_blockers": ["W2_FORMAL_RECOMMENDATION_ENABLED=false"],
                "independent_signal_count": 4,
                "missing_independent_sources": [],
                "model_version": "model-v1",
                "calibration_version": "cal-v1",
                "canonical_ah_market": {
                    "home_line": 0.5,
                    "away_line": -0.5,
                    "home_price": 1.91,
                    "away_price": 1.89,
                    "source": "timeline",
                    "validation_status": "READY",
                    "blocker": None,
                    "display_line_cn": "客队 -0.5",
                },
                "canonical_ah_market_source": "timeline",
                "canonical_ah_market_blocker": None,
                "canonical_ah_market_validation_status": "READY",
                "simulation": {"score_matrix": ["x" * 20000]},
                "factors": [{"payload": "x" * 5000}],
            },
            "missing_inputs": [],
            "candidate": False,
            "formal_recommendation": False,
        }

    monkeypatch.setattr(service, "_dashboard_index_card_from_matchday", heavy_card)

    payload = service.dashboard(target_date="2026-06-26", window="all", include_debug=True)

    assert len(payload["all"]) == 2
    assert len(payload["upcoming"]) == 2
    card = payload["all"][0]
    upcoming_ref = payload["upcoming"][0]
    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    assert len(encoded) < 6500
    assert card["recommendation"] == {
        "recommendation_id": f"rec-{card['fixture_id']}",
        "id": f"rec-row-{card['fixture_id']}",
        "tier": "FORMAL",
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
        "line": -0.5,
        "formal_recommendation": True,
    }
    assert "recommendation_id" in upcoming_ref["recommendation"]
    assert upcoming_ref["recommendation"]["recommendation_id"] == (
        f"rec-{upcoming_ref['fixture_id']}"
    )
    assert "market_strip" not in card
    assert "bookmaker_intent" not in card
    assert "bookmaker_hypothesis" not in card
    assert "market_strip" not in upcoming_ref
    assert "simulation" not in card
    assert "factors" not in card
    assert "pricing_shadow" not in upcoming_ref
    assert "current_odds" not in upcoming_ref
    assert "market_timeline" not in card
    assert upcoming_ref["fixture_id"] == card["fixture_id"]
    assert "current_odds" not in card
    assert "pricing_shadow" not in card
    assert card["competition_name"] == "FIFA World Cup"
    assert card["recommendation"]["tier"] == "FORMAL"


def test_dashboard_all_window_index_contract_is_not_formal_authority(
    monkeypatch,
) -> None:
    service = ReadModelService(repository=cast(Any, FutureFixtureRepository()))

    def fail_full_card_build(row: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("window=all must not build full analysis cards")

    monkeypatch.setattr(service, "_dashboard_card_from_matchday", fail_full_card_build)

    payload = service.dashboard(target_date="2026-06-26", window="all", include_debug=True)

    assert len(payload["all"]) == 2
    assert payload["performance"]["all_window_surface"] == "INDEX_ONLY"
    assert (
        payload["performance"]["all_window_formal_monitor_contract"]
        == "NOT_AUTHORITATIVE"
    )
    assert (
        payload["performance"]["formal_candidate_detection"]
        == "USE_TODAY_NEXT36_OR_FULL_DETAIL"
    )
    assert payload["debug"]["all_window_surface"] == "INDEX_ONLY"
    assert payload["debug"]["all_window_formal_monitor_contract"] == "NOT_AUTHORITATIVE"
    assert payload["all"][0]["recommendation"] is None
    assert payload["all"][0]["formal_recommendation"] is False
    assert "current_odds" not in payload["all"][0]
    assert "pricing_shadow" not in payload["all"][0]


def test_dashboard_reuses_short_lived_cache_for_same_window() -> None:
    repository = CountingFutureFixtureRepository()
    service = ReadModelService(repository=cast(Any, repository))

    first = service.dashboard(target_date="2026-06-26", window="today", include_debug=False)
    second = service.dashboard(target_date="2026-06-26", window="today", include_debug=False)

    assert len(first["all"]) == 1
    assert second == first
    assert repository.fixture_payload_calls == 1


def test_unbounded_warm_cache_does_not_pollute_public_dashboard() -> None:
    service = ReadModelService(repository=cast(Any, SplitPublicFixtureRepository()))

    warmed = service.dashboard(
        target_date="2026-06-26",
        window="all",
        include_debug=False,
    )
    public = service.public_dashboard(
        target_date="2026-06-26",
        window="all",
        include_debug=False,
    )

    assert [card["fixture_id"] for card in warmed["all"]] == ["9001", "9002"]
    assert [card["fixture_id"] for card in public["all"]] == ["9001"]


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
