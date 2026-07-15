from __future__ import annotations

from typing import Any

from apps.api.main import app
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from w2.api import routers


def test_dayview_repository_path_does_not_use_full_ledger_loader() -> None:
    from pathlib import Path

    source = (Path(__file__).parents[2] / "src/w2/api/repository.py").read_text()
    dayview = source.split("def _build_dashboard_day_view_payload", 1)[1].split(
        "def _day_view_unavailable_card", 1
    )[0]
    assert "load_forward_ledger_records" not in dayview
    assert "**dict(capture)" not in dayview


class RecordingDashboardService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def dashboard(
        self,
        *,
        target_date: str | None = None,
        window: str = "today",
        timezone: str = "Asia/Shanghai",
        include_debug: bool = True,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "target_date": target_date,
                "window": window,
                "timezone": timezone,
                "include_debug": include_debug,
            }
        )
        return {
            "generated_at": "2026-07-05T00:00:00Z",
            "date": target_date or "2026-07-05",
            "selected_football_day": target_date or "2026-07-05",
            "timezone": timezone,
            "window": window,
            "version": {"api_git_sha": "sha"},
            "debug": {},
            "performance": {
                "dayview_cache_metrics": {
                    "dayview_cache_status": "HIT",
                    "fixture_window_read_seconds": 0.01,
                    "capture_index_build_seconds": 0.02,
                    "market_observation_read_seconds": 0.03,
                    "ledger_summary_seconds": 0.04,
                    "page_projection_seconds": 0.05,
                    "dayview_serialization_seconds": 0.006,
                }
            },
            "recommendations": [{"fixture_id": "not-counted", "decision_tier": "RECOMMEND"}],
            "all": [
                {
                    "fixture_id": "fixture-1",
                    "kickoff_utc": "2026-07-05T10:00:00Z",
                    "competition_id": "world_cup_2026",
                    "home_team_id": "15",
                    "away_team_id": "8",
                    "home_team_name": "Switzerland",
                    "away_team_name": "Colombia",
                    "decision_tier": "NOT_READY",
                    "data_status": "BLOCKED",
                    "lifecycle_status": "DRAFT",
                    "outcome_tracked": False,
                    "lock_eligible": False,
                    "reason_code": "LINEUPS_PENDING",
                    "pricing_shadow": {
                        "simulation": {
                            "status": "READY",
                            "scoreline_picks": [{"scoreline": "1-0", "probability": 0.2}],
                        }
                    },
                    "scoreline_readiness": {"status": "READY", "source": "formal_simulation"},
                    "non_pick": {
                        "reason_code": "LINEUPS_PENDING",
                        "reason_human": "首发未出",
                        "action": "等官方首发",
                        "next_eval_at": None,
                    },
                }
            ],
        }

    def dashboard_day_view(
        self,
        *,
        target_date: str | None = None,
        window: str = "today",
        timezone: str = "Asia/Shanghai",
        page_size: int = 20,
        cursor: str | None = None,
        sort: str = "BOSS_PRIORITY_KICKOFF",
    ) -> dict[str, Any]:
        from w2.dashboard.day_view import build_dashboard_day_view

        payload = self.dashboard(
            target_date=target_date,
            window=window,
            timezone=timezone,
            include_debug=False,
        )
        view = build_dashboard_day_view(
            payload,
            environment="staging",
            active_whitelist_count=13,
        )
        view["performance"] = payload["performance"]
        view["page_counts"] = view["counts"]
        view["pagination"] = {
            "schema_version": "w2.day_view_page.v1",
            "snapshot_id": "dv_test",
            "sort": sort,
            "total_count": len(view["cards"]),
            "returned_count": len(view["cards"]),
            "page_size": page_size,
            "has_more": False,
            "next_cursor": None,
            "truncated_by_byte_budget": False,
        }
        return view


class DirectOnlyDashboardService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def dashboard(self, **_: Any) -> dict[str, Any]:
        raise AssertionError("DayView must not call the full Dashboard builder")

    def dashboard_day_view(
        self,
        *,
        target_date: str | None = None,
        window: str = "today",
        timezone: str = "Asia/Shanghai",
        page_size: int = 20,
        cursor: str | None = None,
        sort: str = "BOSS_PRIORITY_KICKOFF",
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "target_date": target_date,
                "window": window,
                "timezone": timezone,
                "page_size": page_size,
                "cursor": cursor,
                "sort": sort,
            }
        )
        football_day = target_date or "2026-07-05"
        return {
            "generated_at": "2026-07-05T00:00:00Z",
            "date": football_day,
            "football_day": football_day,
            "selected_football_day": football_day,
            "environment": "staging",
            "active_whitelist_count": 13,
            "environment_policy": {},
            "timezone": timezone,
            "window": window,
            "source": "direct_day_view_projection",
            "version": {"api_git_sha": "sha"},
            "checkpoint_key": f"dashboard:day_view:{football_day}",
            "would_write_checkpoint": False,
            "provider_calls": 0,
            "db_writes": 0,
            "counts": {"total": 0},
            "page_counts": {"total": 0},
            "pagination": {
                "schema_version": "w2.day_view_page.v1",
                "snapshot_id": "dv_test",
                "sort": sort,
                "total_count": 0,
                "returned_count": 0,
                "page_size": page_size,
                "has_more": False,
                "next_cursor": None,
                "truncated_by_byte_budget": False,
            },
            "freshness": {},
            "navigation": {},
            "degradation": {},
            "performance": {},
            "cards": [],
        }


def test_dashboard_day_view_endpoint_reads_requested_window(
    monkeypatch: MonkeyPatch,
) -> None:
    service = RecordingDashboardService()
    monkeypatch.setattr(routers, "service", service)
    client = TestClient(app)

    response = client.get("/v1/dashboard/day-view?date=2026-07-05&window=future&timezone=UTC")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=30"
    assert response.headers["x-w2-dayview-cache"] == "HIT"
    assert response.headers["x-w2-dayview-snapshot"] == "dv_test"
    assert "route;dur=" in response.headers["server-timing"]
    assert "fixture;dur=10.000" in response.headers["server-timing"]
    assert response.headers["content-encoding"] == "gzip"
    payload = response.json()
    assert service.calls == [
        {
            "target_date": "2026-07-05",
            "window": "future",
            "timezone": "UTC",
            "include_debug": False,
        }
    ]
    assert payload["request_id"]
    assert payload["football_day"] == "2026-07-05"
    assert payload["window"] == "future"
    assert payload["active_whitelist_count"] == 13
    assert payload["navigation"]["current_date"] == "2026-07-05"
    assert payload["navigation"]["fallback_mode"] == "read_model"
    assert payload["cards"][0]["scoreline_picks"] == []
    assert payload["cards"][0]["scoreline_readiness"]["status"] == "READY"
    assert payload["degradation"]["state"] == "BLOCKED_DAY"
    assert payload["counts"]["total"] == 1
    assert payload["counts"]["not_ready"] == 1
    assert payload["counts"]["by_decision_tier"]["RECOMMEND"] == 0
    assert payload["cards"][0]["source"] == "decision_contract"
    assert payload["cards"][0]["home_team_display_name"] == "瑞士"
    assert payload["cards"][0]["away_team_display_name"] == "哥伦比亚"
    assert payload["cards"][0]["home_team_provider_name"] == "Switzerland"
    assert payload["cards"][0]["away_team_provider_name"] == "Colombia"
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["would_write_checkpoint"] is False


def test_dashboard_day_view_endpoint_does_not_call_full_dashboard(
    monkeypatch: MonkeyPatch,
) -> None:
    service = DirectOnlyDashboardService()
    monkeypatch.setattr(routers, "service", service)
    client = TestClient(app)

    response = client.get("/v1/dashboard/day-view?date=2026-07-05&window=future&timezone=UTC")

    assert response.status_code == 200
    assert response.json()["source"] == "direct_day_view_projection"
    assert service.calls == [
        {
            "target_date": "2026-07-05",
            "window": "future",
            "timezone": "UTC",
            "page_size": 20,
            "cursor": None,
            "sort": "BOSS_PRIORITY_KICKOFF",
        }
    ]


def test_default_page_size_is_twenty_and_above_fifty_is_rejected(
    monkeypatch: MonkeyPatch,
) -> None:
    service = DirectOnlyDashboardService()
    monkeypatch.setattr(routers, "service", service)
    client = TestClient(app)
    assert client.get("/v1/dashboard/day-view").status_code == 200
    assert service.calls[-1]["page_size"] == 20
    assert client.get("/v1/dashboard/day-view?page_size=51").status_code == 422


def test_analysis_card_endpoint_reports_l2_build_seconds(
    monkeypatch: MonkeyPatch,
) -> None:
    class AnalysisService:
        def frozen_analysis_card(self, fixture_id: str) -> dict[str, Any]:
            return {"fixture_id": fixture_id, "decision": "SKIP"}

    monkeypatch.setattr(routers, "service", AnalysisService())
    response = TestClient(app).get("/v1/fixtures/fixture-1/analysis-card")

    assert response.status_code == 200
    assert response.json()["performance"]["l2_analysis_build_seconds"] >= 0
