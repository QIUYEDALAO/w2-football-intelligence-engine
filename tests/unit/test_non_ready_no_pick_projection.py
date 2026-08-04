from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.dashboard.day_view import build_dashboard_day_view
from w2.domain.decision_adapter import build_decision_contract_fields
from w2.domain.recommendation_decision_v4 import build_recommendation_decision_v4
from w2.prematch.analysis_calculator import _decision_contract_from_v4
from w2.replay.front_door import build_replay_front_door
from w2.tracking.forward_outcome_ledger import build_forward_outcome_records


def test_stale_decision_contract_projects_the_same_no_pick_semantics_everywhere() -> None:
    now = datetime(2026, 7, 18, 5, 0, tzinfo=UTC)
    legacy_decision = build_decision_contract_fields(
        card={
            "source": "unit",
            "recommendation_id": "legacy-rec",
            "quote_identity_audit": {
                "ah": {"identity_status": "COMPLETE", "freshness_status": "STALE"}
            },
        },
        market={
            "market": "ASIAN_HANDICAP",
            "decision_tier": "ANALYSIS_PICK",
            "selection": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        recommendation={"recommendation_id": "legacy-rec"},
        readiness={
            "data_readiness": {
                "source": "w2.readiness.data_gate.v1",
                "data_status": "STALE",
                "missing_fields": [],
                "stale_fields": ["odds"],
                "reason_code": "MARKET_UNAVAILABLE",
                "reason_human": "盘口已过期",
                "action": "等待刷新",
                "next_eval_at": "2026-07-18T05:30:00Z",
                "provider_budget_status": "AVAILABLE",
                "field_statuses": [],
            }
        },
        environment="staging",
        as_of=now,
        kickoff_utc=now + timedelta(hours=4),
        competition_id="competition-1",
        fixture_id="fixture-1",
    )
    decision_v4 = build_recommendation_decision_v4(
        {
            "fixture_id": "fixture-1",
            "competition_id": "competition-1",
            "season": "2026",
            "kickoff_utc": "2026-07-18T09:00:00Z",
        }
    )
    decision = _decision_contract_from_v4(legacy_decision, decision_v4)
    card = {
        "fixture_id": "fixture-1",
        "kickoff_utc": "2026-07-18T09:00:00Z",
        "current_odds": {"ah": {"home_line": "-0.25", "home_price": 1.95}},
        "recommendation_decision_v4": decision_v4.as_dict(),
        "recommendation_decision_v3": {
            "outcome": "ANALYSIS_PICK",
            "selected_candidate": {
                "market": "ASIAN_HANDICAP",
                "selection": "HOME",
                "line": "-0.25",
                "odds": "1.95",
            },
        },
        **decision,
    }
    day_view = build_dashboard_day_view(
        {
            "generated_at": now.isoformat(),
            "date": "2026-07-18",
            "selected_football_day": "2026-07-18",
            "all": [card],
        },
        environment="staging",
    )
    projected = day_view["cards"][0]
    replay = build_replay_front_door(
        football_day="2026-07-18",
        environment="staging",
        day_view=day_view,
        as_of=now,
    )["cards"][0]
    tracked = build_forward_outcome_records(day_view, captured_at=now)[0]

    assert legacy_decision["decision_tier"] == "WATCH"
    assert legacy_decision["pick"] is None
    for output in (decision, projected, replay, tracked):
        assert output["decision_tier"] == "NOT_READY"
        assert output["data_status"] == "BLOCKED"
        assert output["reason_code"] == "IDENTITY_NOT_READY"
        assert output["recommendation_id"] is None
        assert output["outcome_tracked"] is False
    assert decision["pick"] is None
    assert decision["lock_eligible"] is False
    assert projected["pick"] is None
    assert projected["lock_eligible"] is False
    assert projected["current_odds"] == {}
    assert projected["recommendation_decision_v3_role"] == "HISTORY_ONLY"
    assert tracked["pick"] == {}
    assert tracked["current_odds"] == {}
    assert tracked["decision_hash"] == decision_v4.decision_hash
