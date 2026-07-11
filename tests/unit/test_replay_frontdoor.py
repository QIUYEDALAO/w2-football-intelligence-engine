from __future__ import annotations

from copy import deepcopy

from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot
from w2.replay.front_door import build_replay_front_door, verify_replay_card_hash


def test_replay_frontdoor_no_inputs_is_side_effect_free() -> None:
    replay = build_replay_front_door(
        football_day="2026-07-05",
        environment="staging",
        as_of="2026-07-06T00:00:00Z",
    )

    assert replay["replay_status"] == "NO_REPLAY_INPUTS"
    assert replay["replay_gaps"] == [
        "MISSING_DAYVIEW",
        "MISSING_AUDIT_MANIFEST",
        "MISSING_AUDIT_TABLES",
        "MISSING_OUTCOMES",
    ]
    assert replay["provider_calls"] == 0
    assert replay["db_reads"] == 0
    assert replay["db_writes"] == 0
    assert replay["checkpoint_write"] is False
    assert replay["lock_snapshot_write"] is False
    assert replay["settlement_write"] is False


def test_replay_frontdoor_tracks_analysis_pick_without_outcomes() -> None:
    replay = build_replay_front_door(
        football_day="2026-07-05",
        environment="staging",
        day_view=_day_view(),
        as_of="2026-07-06T00:00:00Z",
    )

    assert replay["replay_status"] == "MISSING_OUTCOMES"
    assert replay["environment_policy"]["lock_policy"]["name"] == "staging_B"
    assert replay["decision_summary"]["by_decision_tier"]["ANALYSIS_PICK"] == 1
    assert replay["outcome_tracking_summary"]["tracked_count"] == 1
    assert replay["outcome_tracking_summary"]["tracked_fixture_ids"] == ["fixture-1"]
    assert replay["cards"][0]["outcome_status"] == "OUTCOMES_NOT_PROVIDED"
    assert replay["cards"][0]["decision_tier"] == "ANALYSIS_PICK"


def test_replay_frontdoor_resolves_immutable_estimate_by_id() -> None:
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="fixture-1",
        estimate=FairMarketEstimate(
            market="TOTALS",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=2.75,
            probabilities={"OVER": 0.52, "UNDER": 0.48},
            home_mu=1.6,
            away_mu=1.1,
            feature_as_of="2026-07-05T00:00:00Z",
            train_cutoff="2026-06-01T00:00:00Z",
            artifact_hash="artifact",
            artifact_version="v1",
        ),
        odds_snapshot={"ou": {"line": 2.5}},
        feature_snapshot={"home_xg": 1.6, "away_xg": 1.1},
        created_at="2026-07-05T00:00:00Z",
    ).as_dict()
    day_view = _day_view()
    card = day_view["cards"][0]  # type: ignore[index]
    card["fair_market_estimate_ids"] = [snapshot["estimate_id"]]  # type: ignore[index]
    card["fair_market_estimate_snapshots"] = [snapshot]  # type: ignore[index]

    replay = build_replay_front_door(
        football_day="2026-07-05",
        environment="staging",
        day_view=day_view,
        as_of="2026-07-06T00:00:00Z",
    )

    replay_card = replay["cards"][0]
    assert replay_card["fair_market_estimate_ids"] == [snapshot["estimate_id"]]
    assert replay_card["fair_market_estimate_snapshots"] == [snapshot]
    assert replay_card["estimate_replay"] == [
        {"estimate_id": snapshot["estimate_id"], "integrity_valid": True}
    ]


def test_replay_frontdoor_matches_outcomes_by_fixture_id_and_reports_missing() -> None:
    replay = build_replay_front_door(
        football_day="2026-07-05",
        environment="staging",
        day_view=_day_view(cards=[_card("fixture-1"), _card("fixture-2", card_hash=None)]),
        outcomes=[
            {
                "fixture_id": "fixture-1",
                "result_status": "FINAL",
                "settlement_status": "SETTLED",
                "score": "2-1",
                "unit_result": "WIN",
            }
        ],
        as_of="2026-07-06T00:00:00Z",
    )

    assert replay["replay_status"] == "READY"
    assert replay["cards"][0]["outcome_status"] == "MATCHED"
    assert replay["cards"][0]["outcome"]["score"] == "2-1"
    assert replay["cards"][1]["outcome_status"] == "MISSING_OUTCOME"
    assert replay["outcome_tracking_summary"]["matched_fixture_ids"] == ["fixture-1"]
    assert replay["outcome_tracking_summary"]["missing_outcome_fixture_ids"] == ["fixture-2"]
    assert replay["card_hash_checks"][1]["hash_status"] == "MISSING"


def test_replay_card_hash_verification_skeleton() -> None:
    assert verify_replay_card_hash({"fixture_id": "a"})["hash_status"] == "MISSING"
    assert (
        verify_replay_card_hash({"fixture_id": "a", "card_hash": "h"})["hash_status"]
        == "PRESENT_UNVERIFIED"
    )
    assert (
        verify_replay_card_hash(
            {"fixture_id": "a", "card_hash": "h", "expected_card_hash": "h"}
        )["hash_status"]
        == "PASS"
    )
    assert (
        verify_replay_card_hash(
            {"fixture_id": "a", "card_hash": "h", "expected_card_hash": "other"}
        )["hash_status"]
        == "MISMATCH"
    )


def test_replay_frontdoor_does_not_mutate_historical_cards() -> None:
    day_view = _day_view()
    original = deepcopy(day_view)

    build_replay_front_door(
        football_day="2026-07-05",
        environment="production",
        day_view=day_view,
        outcomes=[],
    )

    assert day_view == original


def test_replay_frontdoor_uses_production_policy_without_actionable_analysis_copy() -> None:
    replay = build_replay_front_door(
        football_day="2026-07-05",
        environment="production",
        day_view=_day_view(environment="production"),
        outcomes=[],
    )

    assert replay["environment_policy"]["lock_policy"]["name"] == "production_B"
    assert "ANALYSIS_PICK 非正式可动作" in replay["environment_policy"]["disclaimer"]
    assert "可买" not in str(replay)
    assert "稳赢" not in str(replay).replace("非稳赢", "")


def _day_view(
    *,
    environment: str = "staging",
    cards: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    actual_cards = cards if cards is not None else [_card("fixture-1")]
    return {
        "generated_at": "2026-07-05T00:00:00Z",
        "football_day": "2026-07-05",
        "environment": environment,
        "environment_policy": {
            "environment": environment,
            "policy_version": "w2.environment_policy.v1",
            "lock_policy": {
                "name": "production_B" if environment == "production" else "staging_B"
            },
            "disclaimer": "ANALYSIS_PICK 非正式可动作；production 仅 RECOMMEND 可锁"
            if environment == "production"
            else "staging-only；分析参考·非稳赢；非 production 可动作推荐",
        },
        "checkpoint_key": "dashboard:day_view:2026-07-05",
        "source": "dashboard_read_model",
        "counts": {"total": len(actual_cards), "analysis_pick": len(actual_cards)},
        "freshness": {"provider_budget_status": "OK"},
        "degradation": {"state": "OK"},
        "navigation": {"current_date": "2026-07-05"},
        "cards": actual_cards,
    }


def _card(fixture_id: str, *, card_hash: str | None = "hash-1") -> dict[str, object]:
    payload: dict[str, object] = {
        "fixture_id": fixture_id,
        "kickoff_utc": "2026-07-05T03:00:00Z",
        "decision_tier": "ANALYSIS_PICK",
        "data_status": "READY",
        "lock_eligible": True,
        "outcome_tracked": True,
        "recommendation_id": f"rec-{fixture_id}",
        "reason_code": "EDGE_OK",
        "action": "TRACK_OUTCOME",
        "one_liner": "分析参考。",
        "expected_card_hash": "hash-1",
        "source": "decision_contract",
    }
    if card_hash is not None:
        payload["card_hash"] = card_hash
    return payload
