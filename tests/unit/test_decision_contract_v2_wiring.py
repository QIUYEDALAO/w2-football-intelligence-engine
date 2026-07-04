from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.domain.decision_adapter import build_decision_contract_fields
from w2.domain.enums import DataStatus, DecisionReasonCode, DecisionTier

NOW = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=4)


def _fields(
    *,
    card: dict[str, object] | None = None,
    market: dict[str, object] | None = None,
    recommendation: dict[str, object] | None = None,
    readiness: dict[str, object] | None = None,
    environment: str = "staging",
) -> dict[str, object]:
    return build_decision_contract_fields(
        card=card or {"source": "unit"},
        market=market,
        recommendation=recommendation,
        readiness=readiness or {"status": "PARTIAL", "blockers": []},
        environment=environment,
        as_of=NOW,
        kickoff_utc=KICKOFF,
        competition_id="world_cup_2026",
        fixture_id="fixture-1",
    )


def test_missing_lineups_maps_to_non_pick_reason() -> None:
    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness={"status": "BLOCKED", "blockers": ["MISSING_LINEUPS"]},
    )

    assert fields["decision_tier"] == DecisionTier.NOT_READY.value
    assert fields["outcome_tracked"] is False
    assert fields["reason_code"] == DecisionReasonCode.LINEUPS_PENDING.value
    assert fields["action"] == "等官方首发"
    assert fields["non_pick"]["reason_human"] == "首发未出"  # type: ignore[index]
    assert fields["pick"] is None


def test_edge_and_market_and_data_blockers_map_to_reason_codes() -> None:
    assert (
        _fields(
            card={"pricing_shadow": {"formal_blockers": ["AH_EV_BELOW_FORMAL_THRESHOLD"]}},
        )["reason_code"]
        == DecisionReasonCode.EDGE_INSUFFICIENT.value
    )
    assert (
        _fields(
            card={"pricing_shadow": {"formal_blockers": ["MARKET_NOT_READY"]}},
        )["reason_code"]
        == DecisionReasonCode.MARKET_UNAVAILABLE.value
    )
    assert (
        _fields(readiness={"status": "BLOCKED", "blockers": ["DATA_INSUFFICIENT"]})[
            "reason_code"
        ]
        == DecisionReasonCode.DATA_MISSING_XG.value
    )


def test_readiness_status_mapping_is_not_optimistic() -> None:
    assert _fields(readiness={"status": "READY", "blockers": []})["data_status"] == (
        DataStatus.READY.value
    )
    assert _fields(readiness={"status": "PARTIAL", "blockers": ["MISSING_LINEUPS"]})[
        "data_status"
    ] == DataStatus.PARTIAL.value
    assert _fields(readiness={"status": "PARTIAL", "blockers": ["PROVIDER_BUDGET_EXHAUSTED"]})[
        "data_status"
    ] == DataStatus.STALE.value


def test_blocked_data_status_downgrades_explicit_pick_tiers() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }

    analysis = _fields(
        market={**market, "decision_tier": "ANALYSIS_PICK"},
        readiness={"status": "BLOCKED", "blockers": ["MISSING_LINEUPS"]},
    )
    recommend = _fields(
        market={**market, "decision_tier": "RECOMMEND"},
        readiness={"status": "BLOCKED", "blockers": ["MISSING_LINEUPS"]},
    )

    assert analysis["decision_tier"] == DecisionTier.NOT_READY.value
    assert recommend["decision_tier"] == DecisionTier.NOT_READY.value
    assert analysis["reason_code"] == DecisionReasonCode.LINEUPS_PENDING.value
    assert recommend["reason_code"] == DecisionReasonCode.LINEUPS_PENDING.value
    assert analysis["pick"] is None
    assert recommend["pick"] is None


def test_analysis_pick_and_lock_policy_are_environmental() -> None:
    card = {
        "source": "unit",
        "data_status": "READY",
    }
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }
    readiness = {"status": "READY", "blockers": []}

    staging = _fields(card=card, market=market, readiness=readiness, environment="staging")
    production = _fields(card=card, market=market, readiness=readiness, environment="production")

    assert staging["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert staging["outcome_tracked"] is True
    assert staging["lock_eligible"] is True
    assert production["lock_eligible"] is False
    assert staging["card_hash"] == production["card_hash"]
    assert "分析参考" in staging["pick"]["disclaimer"]  # type: ignore[index]
    assert "非稳赢" in staging["pick"]["disclaimer"]  # type: ignore[index]


def test_partial_readiness_keeps_analysis_pick_for_staging_analysis() -> None:
    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness={"status": "PARTIAL", "blockers": ["MISSING_LINEUPS"]},
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["pick"] is not None
    assert fields["non_pick"] is None
    assert fields["data_status"] == DataStatus.PARTIAL.value


def test_staging_lock_requires_market_line_and_odds() -> None:
    ready = {"status": "READY", "blockers": []}
    base_market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
    }

    missing_odds = _fields(
        market={**base_market, "line": "-0.25"},
        readiness=ready,
        environment="staging",
    )
    missing_line = _fields(
        market={**base_market, "odds": "1.95"},
        readiness=ready,
        environment="staging",
    )
    complete = _fields(
        market={**base_market, "line": "-0.25", "odds": "1.95"},
        readiness=ready,
        environment="staging",
    )
    production_analysis = _fields(
        market={**base_market, "line": "-0.25", "odds": "1.95"},
        readiness=ready,
        environment="production",
    )

    assert missing_odds["lock_eligible"] is False
    assert missing_line["lock_eligible"] is False
    assert complete["lock_eligible"] is True
    assert production_analysis["lock_eligible"] is False


def test_production_recommend_requires_explicit_tier_and_ev_evidence() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision_tier": "RECOMMEND",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }
    readiness = {"status": "READY", "blockers": []}

    without_evidence = _fields(market=market, readiness=readiness, environment="production")
    with_evidence = _fields(
        card={"forward_ev_evidence_satisfied": True},
        market=market,
        readiness=readiness,
        environment="production",
    )

    assert without_evidence["lock_eligible"] is False
    assert with_evidence["decision_tier"] == DecisionTier.RECOMMEND.value
    assert with_evidence["lock_eligible"] is True


def test_legacy_formal_is_analysis_pick_with_compatibility_marker() -> None:
    fields = _fields(
        card={"formal_recommendation": True, "recommendation_id": "rec-legacy"},
        recommendation={"tier": "FORMAL", "formal_recommendation": True},
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["legacy_formal"] is True
    assert fields["recommendation_id"] == "rec-legacy"


def test_adapter_outputs_valid_decision_card_shapes() -> None:
    analysis = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness={"status": "PARTIAL", "blockers": []},
    )
    watch = _fields(
        market={"market": "ASIAN_HANDICAP", "decision": "WATCH"},
        readiness={"status": "PARTIAL", "blockers": ["AH_EV_BELOW_FORMAL_THRESHOLD"]},
    )
    blocked = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision_tier": "ANALYSIS_PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness={"status": "BLOCKED", "blockers": ["MISSING_LINEUPS"]},
    )

    assert analysis["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert analysis["pick"] is not None
    assert analysis["non_pick"] is None
    assert "分析参考" in analysis["pick"]["disclaimer"]  # type: ignore[index]
    assert "非稳赢" in analysis["pick"]["disclaimer"]  # type: ignore[index]
    assert watch["decision_tier"] == DecisionTier.WATCH.value
    assert watch["pick"] is None
    assert watch["non_pick"] is not None
    assert blocked["decision_tier"] == DecisionTier.NOT_READY.value
    assert blocked["pick"] is None
    assert blocked["non_pick"] is not None
