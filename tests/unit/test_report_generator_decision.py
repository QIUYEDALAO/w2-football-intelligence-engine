from __future__ import annotations

from w2.reporting import MatchDecisionState, decide_match


def _match(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "status": "NS",
        "pricing_shadow": {
            "status": "READY",
            "independent_signal_count": 5,
            "fair_ah": -1.25,
            "market_ah": -0.75,
            "edge_ah": 0.5,
        },
        "recommendation": {
            "tier": "FORMAL",
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "line": -0.75,
        },
    }
    base.update(overrides)
    return base


def test_decide_match_returns_locked_after_kickoff() -> None:
    decision = decide_match(_match(status="LIVE"))

    assert decision.state == MatchDecisionState.LOCKED
    assert decision.reason == "MATCH_STARTED_OR_SETTLEMENT_PRESENT"


def test_decide_match_separates_data_insufficient_from_market_not_ready() -> None:
    data_decision = decide_match(
        _match(pricing_shadow={"status": "READY", "independent_signal_count": 2}),
    )
    market_decision = decide_match(
        _match(
            pricing_shadow={
                "status": "READY",
                "independent_signal_count": 5,
                "fair_ah": -1.25,
                "edge_ah": 0.5,
            },
        ),
    )

    assert data_decision.state == MatchDecisionState.DATA_INSUFFICIENT
    assert data_decision.label_cn == "数据不足"
    assert market_decision.state == MatchDecisionState.MARKET_NOT_READY
    assert market_decision.reason == "MISSING_MARKET_AH"


def test_five_signals_with_ah_mainline_blocker_is_market_not_ready() -> None:
    decision = decide_match(
        _match(
            pricing_shadow={
                "status": "READY",
                "independent_signal_count": 5,
                "fair_ah": -1.25,
                "market_ah": -0.75,
                "edge_ah": 0.5,
                "canonical_ah_market_blocker": "AH_MAINLINE_AMBIGUOUS",
            },
        ),
    )

    assert decision.state == MatchDecisionState.MARKET_NOT_READY
    assert decision.reason == "AH_MAINLINE_AMBIGUOUS"


def test_decide_match_watch_when_edge_below_threshold() -> None:
    decision = decide_match(
        _match(
            pricing_shadow={
                "status": "READY",
                "independent_signal_count": 5,
                "fair_ah": -1.0,
                "market_ah": -0.9,
                "edge_ah": 0.1,
            },
        ),
    )

    assert decision.state == MatchDecisionState.WATCH
    assert decision.reason == "EDGE_BELOW_FORMAL_THRESHOLD"


def test_decide_match_formal_when_data_market_and_edge_are_ready() -> None:
    decision = decide_match(_match())

    assert decision.state == MatchDecisionState.FORMAL
    assert decision.reason == "FORMAL_REPORTABLE"


def test_decide_match_downgrades_formal_when_recommendation_selection_is_invalid() -> None:
    decision = decide_match(
        _match(
            formal_recommendation=True,
            recommendation={
                "tier": "FORMAL",
                "market": "ASIAN_HANDICAP",
                "selection": "UNKNOWN",
                "line": 2.5,
                "odds": 1.87,
            },
        ),
    )

    assert decision.state == MatchDecisionState.WATCH
    assert decision.reason == "INVALID_FORMAL_RECOMMENDATION_PAYLOAD"


def test_decide_match_does_not_infer_formal_from_edge_without_formal_payload() -> None:
    decision = decide_match(
        _match(
            formal_recommendation=False,
            recommendation={
                "tier": "ANALYSIS_PICK",
                "market": "TOTALS",
                "selection": "OVER",
                "line": 1.5,
                "odds": 1.87,
            },
        ),
    )

    assert decision.state == MatchDecisionState.WATCH
    assert decision.reason == "NO_FORMAL_RECOMMENDATION_PAYLOAD"


def test_decide_match_downgrades_formal_when_recommendation_line_is_missing() -> None:
    decision = decide_match(
        _match(
            formal_recommendation=True,
            recommendation={
                "tier": "FORMAL",
                "market": "ASIAN_HANDICAP",
                "selection": "HOME_AH",
                "odds": 1.87,
            },
        ),
    )

    assert decision.state == MatchDecisionState.WATCH
    assert decision.reason == "INVALID_FORMAL_RECOMMENDATION_PAYLOAD"


def test_decide_match_downgrades_formal_when_recommendation_market_is_not_ah() -> None:
    decision = decide_match(
        _match(
            formal_recommendation=True,
            recommendation={
                "tier": "FORMAL",
                "market": "OVER_UNDER",
                "selection": "HOME_AH",
                "line": -0.75,
                "odds": 1.87,
            },
        ),
    )

    assert decision.state == MatchDecisionState.WATCH
    assert decision.reason == "INVALID_FORMAL_RECOMMENDATION_PAYLOAD"
