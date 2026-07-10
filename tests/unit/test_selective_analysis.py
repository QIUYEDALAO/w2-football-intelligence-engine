from __future__ import annotations

from w2.domain.selective_analysis import apply_daily_analysis_pick_cap


def test_daily_analysis_pick_cap_keeps_three_strongest_without_lowering_threshold() -> None:
    cards = [_card(index, strength) for index, strength in enumerate((1.0, 4.0, 2.0, 5.0, 3.0))]

    selected = apply_daily_analysis_pick_cap(cards)

    picks = [card for card in selected if card["decision_tier"] == "ANALYSIS_PICK"]
    watches = [card for card in selected if card["decision_tier"] == "WATCH"]
    assert {card["fixture_id"] for card in picks} == {"fixture-1", "fixture-3", "fixture-4"}
    assert len(watches) == 2
    assert all(card["reason_code"] == "SELECTIVITY_DAILY_CAP" for card in watches)
    assert all(card["lock_eligible"] is False for card in selected)


def test_daily_analysis_pick_cap_allows_zero_signal_day() -> None:
    cards = [_card(1, 0.0)]
    cards[0]["decision_tier"] = "WATCH"
    cards[0]["decision_contract"]["decision_tier"] = "WATCH"  # type: ignore[index]

    selected = apply_daily_analysis_pick_cap(cards)

    assert selected[0]["decision_tier"] == "WATCH"


def test_daily_analysis_pick_cap_is_applied_per_football_day() -> None:
    cards = [_card(index, float(index + 1)) for index in range(4)]
    cards.extend(_card(index + 10, float(index + 1)) for index in range(4))
    for card in cards[4:]:
        card["football_day"] = "2026-07-11"

    selected = apply_daily_analysis_pick_cap(cards)

    picks_by_day = {
        day: len(
            [
                card
                for card in selected
                if card.get("football_day", "2026-07-10") == day
                and card["decision_tier"] == "ANALYSIS_PICK"
            ]
        )
        for day in ("2026-07-10", "2026-07-11")
    }
    assert picks_by_day == {"2026-07-10": 3, "2026-07-11": 3}


def test_daily_cap_keeps_legacy_recommendation_summary_consistent() -> None:
    cards = [_card(index, float(index)) for index in range(4)]
    for card in cards:
        card["recommendation"] = {"tier": "ANALYSIS_PICK"}

    selected = apply_daily_analysis_pick_cap(cards)

    downgraded = next(card for card in selected if card["decision_tier"] == "WATCH")
    assert downgraded["recommendation"] == {
        "tier": "WATCH",
        "decision_tier": "WATCH",
        "reason_code": "SELECTIVITY_DAILY_CAP",
    }


def _card(index: int, strength: float) -> dict[str, object]:
    contract: dict[str, object] = {
        "fixture_id": f"fixture-{index}",
        "competition_id": "allsvenskan",
        "kickoff_utc": f"2026-07-10T{10 + index:02d}:00:00Z",
        "decision_tier": "ANALYSIS_PICK",
        "data_status": "READY",
        "lifecycle_status": "DRAFT",
        "outcome_tracked": True,
        "lock_eligible": False,
        "recommendation_id": None,
        "model_version": "unit",
        "probability_source": "MARKET_DEVIG",
        "model_market_divergence": {},
        "analysis_gate": {
            "status": "ELIGIBLE",
            "strength_quarter_lines": strength,
        },
        "provenance": {},
        "environment": "staging",
        "pick": {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "line": "-0.25",
            "odds": "1.95",
            "fair_line": "-0.75",
            "market_line": "-0.25",
            "value_edge": None,
            "key_factors": [],
            "risks": [],
            "invalidation": None,
            "disclaimer": "分析参考·非稳赢；production 动作需 RECOMMEND",
        },
        "non_pick": None,
        "one_liner": "分析参考·非稳赢",
    }
    return {
        **contract,
        "analysis_gate": contract["analysis_gate"],
        "decision_contract": dict(contract),
    }
