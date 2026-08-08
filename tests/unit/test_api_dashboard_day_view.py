from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
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
            "recommendations": [{"fixture_id": "not-counted", "decision_tier": "RECOMMEND"}],
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
                    "action": "等官方首发",
                    "next_eval_at": None,
                    "decision_contract": {
                        "decision_tier": "NOT_READY",
                        "data_status": "BLOCKED",
                        "lifecycle_status": "DRAFT",
                        "outcome_tracked": False,
                        "lock_eligible": False,
                        "recommendation_id": None,
                        "lineup_requirement": "ADVISORY",
                        "risk_reason_codes": ["LINEUP_UNOBSERVABLE"],
                        "pick": None,
                        "non_pick": {
                            "reason_code": "LINEUPS_PENDING",
                            "reason_human": "首发未出",
                            "action": "等官方首发",
                            "next_eval_at": None,
                        },
                        "reason_code": "LINEUPS_PENDING",
                        "action": "等官方首发",
                        "next_eval_at": None,
                    },
                    "non_pick": {
                        "reason_code": "LINEUPS_PENDING",
                        "reason_human": "首发未出",
                        "action": "等官方首发",
                        "next_eval_at": None,
                    },
                }
            ],
        }

    def public_dashboard(self, **kwargs: Any) -> dict[str, Any]:
        return self.dashboard(**kwargs)


def test_dashboard_day_view_endpoint_reads_requested_window(
    monkeypatch: MonkeyPatch,
) -> None:
    service = RecordingDashboardService()
    monkeypatch.setattr(routers, "service", service)
    client = TestClient(app)

    response = client.get("/v1/dashboard/day-view?date=2026-07-05&window=future&timezone=UTC")

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
    assert payload["degradation"]["state"] == "BLOCKED_DAY"
    assert payload["counts"]["total"] == 1
    assert payload["counts"]["not_ready"] == 1
    assert payload["counts"]["by_decision_tier"]["RECOMMEND"] == 0
    assert payload["cards"][0]["source"] == "decision_contract"
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["would_write_checkpoint"] is False


def test_intelligence_workspace_twenty_reads_are_stable_and_side_effect_free(
    monkeypatch: MonkeyPatch,
) -> None:
    service = RecordingDashboardService()
    monkeypatch.setattr(routers, "service", service)
    client = TestClient(app)

    responses = [
        client.get(
            "/v1/dashboard/intelligence-workspace"
            "?date=2026-07-05&window=future&timezone=UTC"
        )
        for _ in range(20)
    ]
    payloads = [
        {key: value for key, value in response.json().items() if key != "request_id"}
        for response in responses
    ]

    assert {response.status_code for response in responses} == {200}
    assert all(payload == payloads[0] for payload in payloads)
    assert len(service.calls) == 20
    assert all(call["include_debug"] is False for call in service.calls)
    assert payloads[0]["read_contract"] == {
        "provider_calls": 0,
        "db_writes": 0,
        "would_write_checkpoint": False,
        "no_call_on_read": True,
    }
    assert payloads[0]["runtime"]["formal"] == "OFF"
    assert payloads[0]["matches"][0]["formal_recommendation"]["status"] == "OFF"


def test_dashboard_day_view_endpoint_missing_contract_is_system_degraded(
    monkeypatch: MonkeyPatch,
) -> None:
    service = RecordingDashboardService()
    original_dashboard = service.dashboard

    def dashboard_without_contract(**kwargs: Any) -> dict[str, Any]:
        payload = original_dashboard(**kwargs)
        payload["all"][0].pop("decision_contract")
        return payload

    monkeypatch.setattr(service, "public_dashboard", dashboard_without_contract)
    monkeypatch.setattr(routers, "service", service)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/v1/dashboard/day-view?date=2026-07-05&window=future&timezone=UTC")

    assert response.status_code == 503
    assert response.json()["code"] == "SYSTEM_DEGRADED"
    assert response.json()["message"] == ("DECISION_CONTRACT_MISSING:fixture-1")


@pytest.mark.parametrize(
    "case",
    [
        "missing_required",
        "bool_type",
        "pick_non_pick_conflict",
        "missing_non_pick",
        "top_level_pollution",
    ],
)
def test_dashboard_day_view_endpoint_malformed_contract_is_system_degraded(
    monkeypatch: MonkeyPatch,
    case: str,
) -> None:
    service = RecordingDashboardService()
    original_dashboard = service.dashboard

    def dashboard_with_malformed_contract(**kwargs: Any) -> dict[str, Any]:
        payload = original_dashboard(**kwargs)
        card = payload["all"][0]
        contract = card["decision_contract"]
        if case == "missing_required":
            contract.pop("outcome_tracked")
        elif case == "bool_type":
            contract["outcome_tracked"] = "false"
            card["outcome_tracked"] = "false"
        elif case == "pick_non_pick_conflict":
            pick = {"market": "ASIAN_HANDICAP", "selection": "HOME_AH"}
            contract["pick"] = pick
            card["pick"] = pick
        elif case == "missing_non_pick":
            contract["non_pick"] = None
            card["non_pick"] = None
        elif case == "top_level_pollution":
            card["reason_code"] = "POISONED_TOP_LEVEL_VALUE"
        return payload

    monkeypatch.setattr(service, "public_dashboard", dashboard_with_malformed_contract)
    monkeypatch.setattr(routers, "service", service)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/v1/dashboard/day-view?date=2026-07-05&window=future&timezone=UTC")

    assert response.status_code == 503
    assert response.json()["code"] == "SYSTEM_DEGRADED"
    assert response.json()["message"].startswith("DECISION_CONTRACT_")


def _attach_active_dynamic_evidence(card: dict[str, Any]) -> None:
    quote_hash = "quote-hash"
    evidence = {
        "status": "COMPLETE",
        "market": "ASIAN_HANDICAP",
        "selection": "AWAY",
        "line": "1.25",
        "quote_identity": {
            "quote_identity_hash": quote_hash,
            "identity_status": "COMPLETE",
            "freshness_status": "COMPLETE",
            "quotes": {"away": {"line": "1.25"}},
        },
        "market_probability": {"devig": {"HOME": 0.49, "AWAY": 0.51}},
        "model_probability": {
            "status": "READY",
            "effective_probability": 0.62,
            "expected_value": 0.20,
            "ev_se": 0.08,
        },
        "comparison": {
            "status": "READY",
            "analysis_direction_allowed": True,
            "current_ev": 0.20,
            "probability_delta": 0.11,
            "current_ev_minus_se": 0.12,
        },
    }
    evaluated = {
        "schema_version": "w2.market_candidate.v1",
        "market": "ASIAN_HANDICAP",
        "selection": "AWAY",
        "line": "1.25",
        "quote_identity": evidence["quote_identity"],
        "quotes": {
            "executable": {
                "line": "1.25",
                "decimal_odds": "1.90",
                "capture_id": "capture-1",
                "bookmaker_id": "11",
            }
        },
        "analysis_evidence": evidence,
    }
    card["recommendation_decision_v3"] = {
        "outcome": "NOT_READY",
        "evaluated_candidate": evaluated,
        "warnings": [],
    }
    card["dynamic_prematch"] = {
        "current": [
            {
                "schema_version": "w2.dynamic_quote_evaluation.v2",
                "evaluation_id": "evaluation-active",
                "identity_hash": "evaluation-hash",
                "fixture_id": "fixture-1",
                "evaluated_at": "2026-07-05T00:00:00Z",
                "state": "ANALYSIS_PICK_ACTIVE",
                "market": "ASIAN_HANDICAP",
                "selection": "AWAY",
                "exact_line": 1.25,
                "quote_identity_hash": quote_hash,
                "capture_id": "capture-1",
                "bookmaker_id": "11",
                "current_ev": 0.20,
                "current_delta": 0.11,
                "current_ev_minus_se": 0.12,
                "blockers": [],
                "superseded_by_evaluation_id": None,
                "immutable": True,
                "scoreline_reference": {
                    "source": "formal_simulation",
                    "label": "模拟比分参考",
                    "scoreline_projection": {
                        "status": "READY",
                        "decision_hash": "evaluation-hash",
                        "top3": [
                            {"scoreline": "0-1", "sample_count": 1200},
                            {"scoreline": "0-2", "sample_count": 900},
                            {"scoreline": "1-2", "sample_count": 800},
                        ],
                    },
                },
            }
        ]
    }


def test_day_view_does_not_rebuild_current_pick_from_historical_v3_evidence(
    monkeypatch: MonkeyPatch,
) -> None:
    service = RecordingDashboardService()
    original_dashboard = service.dashboard

    def dashboard_with_dynamic_evidence(**kwargs: Any) -> dict[str, Any]:
        payload = original_dashboard(**kwargs)
        card = payload["all"][0]
        _attach_active_dynamic_evidence(card)
        return payload

    monkeypatch.setattr(service, "public_dashboard", dashboard_with_dynamic_evidence)
    monkeypatch.setattr(routers, "service", service)
    response = TestClient(app).get(
        "/v1/dashboard/day-view?date=2026-07-05&window=future&timezone=UTC"
    )

    assert response.status_code == 200
    payload = response.json()
    card = payload["cards"][0]
    assert payload["counts"]["analysis_pick"] == 0
    assert payload["counts"]["not_ready"] == 1
    assert card["decision_tier"] == "NOT_READY"
    assert card["data_status"] == "BLOCKED"
    assert card["recommendation_decision_v3"]["outcome"] == "NOT_READY"
    assert card["recommendation_decision_v3_role"] == "HISTORY_ONLY"
    assert card["scoreline_reference"] == {}
    assert card["lock_eligible"] is False
    assert "decision_projection" not in card


def test_day_view_orders_legacy_dynamic_cards_by_kickoff_and_fixture_id(
    monkeypatch: MonkeyPatch,
) -> None:
    service = RecordingDashboardService()
    original_dashboard = service.dashboard

    def dashboard_with_unsorted_cards(**kwargs: Any) -> dict[str, Any]:
        payload = original_dashboard(**kwargs)
        pick = payload["all"][0]
        pick["kickoff_utc"] = "2026-07-05T12:00:00Z"
        _attach_active_dynamic_evidence(pick)
        earlier_b = deepcopy(pick)
        earlier_b["fixture_id"] = "fixture-b"
        earlier_b["kickoff_utc"] = "2026-07-05T08:00:00Z"
        earlier_b.pop("dynamic_prematch", None)
        earlier_b["recommendation_decision_v3"] = {"outcome": "NOT_READY"}
        earlier_a = deepcopy(earlier_b)
        earlier_a["fixture_id"] = "fixture-a"
        earlier_a["kickoff_utc"] = "2026-07-05T08:00:00Z"
        payload["all"] = [earlier_b, pick, earlier_a]
        return payload

    monkeypatch.setattr(service, "public_dashboard", dashboard_with_unsorted_cards)
    monkeypatch.setattr(routers, "service", service)

    payload = (
        TestClient(app)
        .get("/v1/dashboard/day-view?date=2026-07-05&window=future&timezone=UTC")
        .json()
    )

    assert [card["fixture_id"] for card in payload["cards"]] == [
        "fixture-a",
        "fixture-b",
        "fixture-1",
    ]
    assert all(card["decision_tier"] == "NOT_READY" for card in payload["cards"])


def test_day_view_keeps_identity_mismatched_dynamic_evidence_not_ready(
    monkeypatch: MonkeyPatch,
) -> None:
    service = RecordingDashboardService()
    original_dashboard = service.dashboard

    def dashboard_with_mismatch(**kwargs: Any) -> dict[str, Any]:
        payload = original_dashboard(**kwargs)
        card = payload["all"][0]
        _attach_active_dynamic_evidence(card)
        card["dynamic_prematch"]["current"][0]["quote_identity_hash"] = "mismatch"
        return payload

    monkeypatch.setattr(service, "public_dashboard", dashboard_with_mismatch)
    monkeypatch.setattr(routers, "service", service)
    payload = (
        TestClient(app)
        .get("/v1/dashboard/day-view?date=2026-07-05&window=future&timezone=UTC")
        .json()
    )

    assert payload["counts"]["analysis_pick"] == 0
    assert payload["counts"]["not_ready"] == 1
    assert payload["cards"][0]["decision_tier"] == "NOT_READY"
    assert "decision_projection" not in payload["cards"][0]
