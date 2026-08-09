from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from w2.dashboard.day_view import _dashboard_card_order, build_dashboard_day_view
from w2.dashboard.intelligence import (
    INTELLIGENCE_STATES,
    RISK_DIMENSIONS,
    build_intelligence_projection,
)


def _base_card() -> dict[str, Any]:
    return {
        "competition_id": "premier_league",
        "data_status": "READY",
        "simulation": {"status": "READY", "simulation": {"status": "READY"}},
        "missing_fields": [],
        "missing_inputs": [],
        "stale_fields": [],
        "risk_reason_codes": [],
        "model_market_divergence": {},
        "market_movement": {"status": "READY", "pattern": "STABLE", "line_moved": False},
        "market_radar": {
            "statistical_anomaly": {
                "calibration_status": "NOT_CALIBRATED",
                "detected": False,
            },
            "markets": {
                "ASIAN_HANDICAP": {
                    "current": {"freshness": {"status": "FRESH"}},
                    "movement": {"status": "STABLE"},
                },
                "TOTALS": {
                    "current": {"freshness": {"status": "FRESH"}},
                    "movement": {"status": "STABLE"},
                },
            },
        },
        "data_refresh": {
            "odds_status": "READY",
            "last_refresh_hint": "2026-08-09T10:00:00Z",
        },
        "model_lab": {
            "markets": {
                "ASIAN_HANDICAP": {
                    "market": "ASIAN_HANDICAP",
                    "status": "COMPARABLE_WITHIN_MARKET_RANGE",
                },
                "TOTALS": {
                    "market": "TOTALS",
                    "status": "COMPARABLE_WITHIN_MARKET_RANGE",
                },
            }
        },
    }


@pytest.mark.parametrize(
    ("expected", "changes"),
    [
        ("MARKET_STABLE", {}),
        (
            "MARKET_MOVEMENT",
            {
                "market_radar": {
                    "markets": {"ASIAN_HANDICAP": {"movement": {"status": "PRICE_MOVEMENT"}}}
                }
            },
        ),
        (
            "MODEL_MARKET_DISAGREEMENT",
            {
                "model_lab": {
                    "markets": {
                        "ASIAN_HANDICAP": {
                            "market": "ASIAN_HANDICAP",
                            "status": "MODEL_OUTSIDE_MARKET_RANGE",
                        }
                    }
                }
            },
        ),
        (
            "MARKET_ANOMALY",
            {
                "market_radar": {
                    "statistical_anomaly": {
                        "calibration_status": "CALIBRATED",
                        "detected": True,
                    }
                }
            },
        ),
        ("MODEL_DIAGNOSTIC_WARNING", {"simulation": {"status": "UNAVAILABLE"}}),
        ("DATA_INCOMPLETE", {"data_status": "BLOCKED"}),
        ("COLLECTION_INCIDENT", {"provider_budget_status": "EXHAUSTED"}),
    ],
)
def test_seven_intelligence_states_are_deterministic(
    expected: str,
    changes: dict[str, Any],
) -> None:
    projection = build_intelligence_projection({**_base_card(), **changes})

    assert projection["intelligence_state"] == expected
    assert projection["recommendation_decision_v4_role"] == (
        "DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY"
    )


def test_frozen_precedence_and_reason_order_are_deterministic() -> None:
    card = {
        **_base_card(),
        "provider_budget_status": "EXHAUSTED",
        "data_status": "BLOCKED",
        "simulation": {"status": "UNAVAILABLE"},
        "market_radar": {
            "statistical_anomaly": {"calibration_status": "CALIBRATED", "detected": True},
            "markets": {"ASIAN_HANDICAP": {"movement": {"status": "LINE_MOVEMENT"}}},
        },
        "model_lab": {
            "markets": {
                "ASIAN_HANDICAP": {
                    "market": "ASIAN_HANDICAP",
                    "status": "MODEL_OUTSIDE_MARKET_RANGE",
                }
            }
        },
    }

    first = build_intelligence_projection(card)
    second = build_intelligence_projection(deepcopy(card))

    assert first == second
    assert first["intelligence_state"] == "COLLECTION_INCIDENT"
    assert first["intelligence_reason_codes"] == [
        "COLLECTION_PROVIDER_BUDGET_EXHAUSTED",
        "DATA_STATUS_BLOCKED",
        "MODEL_SIMULATION_NOT_READY",
        "MARKET_ANOMALY_CALIBRATED_DETECTION",
        "MODEL_MARKET_DISAGREEMENT_ASIAN_HANDICAP",
        "MARKET_MOVEMENT_LINE_MOVEMENT",
    ]
    assert INTELLIGENCE_STATES == (
        "COLLECTION_INCIDENT",
        "DATA_INCOMPLETE",
        "MODEL_DIAGNOSTIC_WARNING",
        "MARKET_ANOMALY",
        "MODEL_MARKET_DISAGREEMENT",
        "MARKET_MOVEMENT",
        "MARKET_STABLE",
    )


def test_attention_order_uses_only_precedence_kickoff_and_fixture_id() -> None:
    cards = [
        {
            "fixture_id": "z",
            "kickoff_utc": "2026-08-08T12:00:00Z",
            "intelligence_state": "MARKET_STABLE",
        },
        {
            "fixture_id": "b",
            "kickoff_utc": "2026-08-08T11:00:00Z",
            "intelligence_state": "DATA_INCOMPLETE",
        },
        {
            "fixture_id": "a",
            "kickoff_utc": "2026-08-08T11:00:00Z",
            "intelligence_state": "DATA_INCOMPLETE",
        },
        {
            "fixture_id": "c",
            "kickoff_utc": "2026-08-08T10:00:00Z",
            "intelligence_state": "COLLECTION_INCIDENT",
        },
    ]
    assert [card["fixture_id"] for card in sorted(cards, key=_dashboard_card_order)] == [
        "c",
        "a",
        "b",
        "z",
    ]


def test_day_view_passes_through_shared_football_day_boundary() -> None:
    view = build_dashboard_day_view(
        {
            "generated_at": "2026-08-09T04:00:00Z",
            "date": "2026-08-09",
            "selected_football_day": "2026-08-09",
            "football_day_timezone": "Asia/Shanghai",
            "football_day_cutoff_hour": 12,
            "football_day_start_utc": "2026-08-09T04:00:00Z",
            "football_day_end_utc": "2026-08-10T04:00:00Z",
            "all": [],
        },
        environment="staging",
    )

    assert view["football_day_timezone"] == "Asia/Shanghai"
    assert view["football_day_cutoff_hour"] == 12
    assert view["football_day_start_utc"] == "2026-08-09T04:00:00Z"
    assert view["football_day_end_utc"] == "2026-08-10T04:00:00Z"


def test_sparse_timeline_never_defaults_to_market_stable() -> None:
    card = {
        **_base_card(),
        "market_radar": {
            "statistical_anomaly": {"calibration_status": "NOT_CALIBRATED", "detected": False},
            "markets": {
                "ASIAN_HANDICAP": {"movement": {"status": "INSUFFICIENT"}},
                "TOTALS": {"movement": {"status": "INSUFFICIENT"}},
            },
        },
    }

    projection = build_intelligence_projection(card)

    assert projection["intelligence_state"] == "DATA_INCOMPLETE"
    assert "DATA_MARKET_TIMELINE_INSUFFICIENT" in projection["intelligence_reason_codes"]


def test_four_risk_dimensions_remain_independent() -> None:
    projection = build_intelligence_projection(
        {
            **_base_card(),
            "data_status": "BLOCKED",
            "simulation": {"status": "UNAVAILABLE"},
            "risk_reason_codes": ["INJURY_CONFIRMED", "SCHEMA_ERROR"],
            "model_lab": {
                "markets": {
                    "ASIAN_HANDICAP": {
                        "market": "ASIAN_HANDICAP",
                        "status": "MODEL_OUTSIDE_MARKET_RANGE",
                    }
                }
            },
        }
    )
    risks = projection["risk_dimensions"]

    assert tuple(risks) == RISK_DIMENSIONS
    assert risks["EVENT_RISK"]["status"] == "INCIDENT"
    assert risks["DATA_RISK"]["status"] == "INCIDENT"
    assert risks["MODEL_RISK"]["status"] == "INCIDENT"
    assert risks["COLLECTION_RISK"]["status"] == "INCIDENT"
    assert set(risks["EVENT_RISK"]["reason_codes"]).isdisjoint(
        risks["COLLECTION_RISK"]["reason_codes"]
    )


def test_collection_risk_without_assessment_evidence_is_not_green_or_incident() -> None:
    card = _base_card()
    card.pop("data_refresh")

    projection = build_intelligence_projection(card)
    collection = projection["risk_dimensions"]["COLLECTION_RISK"]

    assert projection["intelligence_state"] == "MARKET_STABLE"
    assert collection["status"] == "ATTENTION"
    assert collection["assessment_status"] == "UNASSESSED"
    assert collection["reason_codes"] == ["COLLECTION_ASSESSMENT_NOT_AVAILABLE"]


def test_collection_risk_requires_fresh_persisted_capture_for_ok() -> None:
    collection = build_intelligence_projection(_base_card())["risk_dimensions"][
        "COLLECTION_RISK"
    ]

    assert collection == {
        "dimension": "COLLECTION_RISK",
        "status": "OK",
        "reason_codes": [],
        "explanation": "采集状态已有新鲜持久化证据",
        "assessment_status": "ASSESSED_CURRENT",
        "evidence_basis": "PERSISTED_ODDS_CAPTURE_AND_MARKET_FRESHNESS",
        "source_as_of": "2026-08-09T10:00:00Z",
    }


def test_collection_incident_requires_persisted_incident_reason() -> None:
    card = _base_card()
    card["data_refresh"] = {
        "odds_status": "PROVIDER_EMPTY",
        "last_refresh_hint": "2026-08-09T10:00:00Z",
    }

    projection = build_intelligence_projection(card)
    collection = projection["risk_dimensions"]["COLLECTION_RISK"]

    assert projection["intelligence_state"] == "COLLECTION_INCIDENT"
    assert collection["status"] == "INCIDENT"
    assert collection["assessment_status"] == "ASSESSED_INCIDENT"
    assert collection["reason_codes"] == ["COLLECTION_PROVIDER_EMPTY"]


def test_not_ready_does_not_become_event_risk_and_market_facts_remain_visible() -> None:
    contract = {
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
            "reason_code": "MODEL_NOT_READY",
            "reason_human": "模型未就绪",
            "action": "WAIT",
            "next_eval_at": None,
        },
        "reason_code": "MODEL_NOT_READY",
        "action": "WAIT",
        "next_eval_at": None,
    }
    current_odds = {"ou": {"line": "2.5", "over_price": 1.93, "under_price": 1.95}}
    view = build_dashboard_day_view(
        {
            "generated_at": "2026-08-07T00:00:00Z",
            "date": "2026-08-07",
            "selected_football_day": "2026-08-07",
            "all": [
                {
                    "fixture_id": "fixture-1",
                    "kickoff_utc": "2026-08-07T12:00:00Z",
                    "competition_id": "premier_league",
                    "current_odds": current_odds,
                    "simulation": {"status": "INSUFFICIENT_INPUTS"},
                    **contract,
                    "decision_contract": deepcopy(contract),
                }
            ],
        },
        environment="staging",
    )
    card = view["cards"][0]

    assert card["current_odds"] == current_odds
    assert card["risk_dimensions"]["EVENT_RISK"]["status"] == "OK"
    assert card["risk_dimensions"]["DATA_RISK"]["status"] == "INCIDENT"
    assert card["risk_dimensions"]["MODEL_RISK"]["status"] == "INCIDENT"
    assert view["counts"]["monitored_fixtures"] == 1
    assert view["counts"]["market_complete_fixtures"] == 1


def test_market_stable_is_non_empty_and_zero_alerts_are_valid() -> None:
    contract = {
        "decision_tier": "SKIP",
        "data_status": "READY",
        "lifecycle_status": "DRAFT",
        "outcome_tracked": False,
        "lock_eligible": False,
        "recommendation_id": None,
        "lineup_requirement": "ADVISORY",
        "risk_reason_codes": ["LINEUP_UNOBSERVABLE"],
        "pick": None,
        "non_pick": {
            "reason_code": "OBSERVE",
            "reason_human": "观察",
            "action": "WAIT",
            "next_eval_at": None,
        },
        "reason_code": "OBSERVE",
        "action": "WAIT",
        "next_eval_at": None,
    }
    view = build_dashboard_day_view(
        {
            "generated_at": "2026-08-07T00:00:00Z",
            "date": "2026-08-07",
            "selected_football_day": "2026-08-07",
            "all": [
                {
                    "fixture_id": "stable-1",
                    "kickoff_utc": "2026-08-07T12:00:00Z",
                    "competition_id": "premier_league",
                    "simulation": {"status": "READY"},
                    "market_movement": {
                        "status": "READY",
                        "pattern": "STABLE",
                        "line_moved": False,
                    },
                    **contract,
                    "decision_contract": deepcopy(contract),
                }
            ],
        },
        environment="staging",
    )

    assert len(view["cards"]) == 1
    assert view["cards"][0]["intelligence_state"] == "MARKET_STABLE"
    assert view["cards"][0]["intelligence_reason_codes"] == ["MARKET_STABLE_NO_MATERIAL_ALERT"]
    assert view["counts"]["market_stable_fixtures"] == 1
    assert view["counts"]["market_movement_fixtures"] == 0
    assert view["counts"]["model_diagnostic_warnings"] == 0
    assert view["counts"]["data_incidents"] == 0
    assert view["counts"]["collection_incidents"] == 0
