from __future__ import annotations

from typing import Any

from apps.api.main import app
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from w2.api import routers


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
            "performance": {},
            "recommendations": [
                {"fixture_id": "not-counted", "decision_tier": "RECOMMEND"}
            ],
            "all": [
                {
                    "fixture_id": "fixture-1",
                    "kickoff_utc": "2026-07-05T10:00:00Z",
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


def test_dashboard_day_view_endpoint_reads_requested_window(
    monkeypatch: MonkeyPatch,
) -> None:
    service = RecordingDashboardService()
    monkeypatch.setattr(routers, "service", service)
    client = TestClient(app)

    response = client.get(
        "/v1/dashboard/day-view?date=2026-07-05&window=future&timezone=UTC"
    )

    assert response.status_code == 200
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
    assert payload["navigation"]["current_date"] == "2026-07-05"
    assert payload["navigation"]["fallback_mode"] == "read_model"
    assert payload["cards"][0]["scoreline_picks"][0]["scoreline"] == "1-0"
    assert payload["cards"][0]["scoreline_readiness"]["status"] == "READY"
    assert payload["degradation"]["state"] == "BLOCKED_DAY"
    assert payload["counts"]["total"] == 1
    assert payload["counts"]["not_ready"] == 1
    assert payload["counts"]["by_decision_tier"]["RECOMMEND"] == 0
    assert payload["cards"][0]["source"] == "decision_contract"
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["would_write_checkpoint"] is False
