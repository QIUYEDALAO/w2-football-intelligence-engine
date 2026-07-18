from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.domain.decision_adapter import build_decision_contract_fields
from w2.domain.enums import DataStatus, DecisionReasonCode, DecisionTier

NOW = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=4)


def _complete_quote_audit() -> dict[str, object]:
    identity = {
        "identity_status": "COMPLETE",
        "freshness_status": "COMPLETE",
    }
    return {"ah": dict(identity), "ou": dict(identity)}


def _fields(
    *,
    card: dict[str, object] | None = None,
    market: dict[str, object] | None = None,
    recommendation: dict[str, object] | None = None,
    readiness: dict[str, object] | None = None,
    environment: str = "staging",
) -> dict[str, object]:
    card_payload: dict[str, object] = {
        "source": "unit",
        "quote_identity_audit": _complete_quote_audit(),
    }
    card_payload.update(card or {})
    return build_decision_contract_fields(
        card=card_payload,
        market=market,
        recommendation=recommendation,
        readiness=readiness or {"status": "PARTIAL", "blockers": []},
        environment=environment,
        as_of=NOW,
        kickoff_utc=KICKOFF,
        competition_id="world_cup_2026",
        fixture_id="fixture-1",
    )


def test_missing_lineups_soft_gate_forces_watch_without_pick() -> None:
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

    assert fields["decision_tier"] == DecisionTier.WATCH.value
    assert fields["data_status"] == DataStatus.PARTIAL.value
    assert fields["outcome_tracked"] is False
    assert fields["reason_code"] == DecisionReasonCode.LINEUPS_PENDING.value
    assert fields["action"] == "等官方首发"
    assert fields["missing_fields"] == ["lineups", "xg", "ratings", "team_value"]
    assert fields["pick"] is None
    assert fields["non_pick"] is not None


def test_totals_pick_uses_totals_pricing_shadow_not_ah_lines() -> None:
    fields = _fields(
        card={
            "pricing_shadow": {
                "fair_ah": "-1",
                "market_ah": "-1",
                "edge_ah": 0,
                "fair_ou": "2.75",
                "market_ou": "2.25",
                "edge_ou": -0.5,
            },
        },
        market={
            "market": "TOTALS",
            "decision": "PICK",
            "tendency": "OVER",
            "line": "2.25",
            "odds": "2.03",
        },
        readiness={"status": "READY", "blockers": []},
    )

    pick = fields["pick"]
    assert isinstance(pick, dict)
    assert pick["market"] == "TOTALS"
    assert pick["line"] == "2.25"
    assert pick["fair_line"] == "2.75"
    assert pick["market_line"] == "2.25"
    assert pick["value_edge"] == -0.5
    divergence = fields["model_market_divergence"]
    assert isinstance(divergence, dict)
    assert divergence["model_fair_line"] == "2.75"
    assert divergence["market_line"] == "2.25"


def test_edge_and_market_and_data_blockers_map_to_reason_codes() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "WATCH",
        "line": "-0.25",
        "odds": "1.95",
    }
    assert (
        _fields(
            card={"pricing_shadow": {"formal_blockers": ["AH_EV_BELOW_FORMAL_THRESHOLD"]}},
            market=market,
            readiness={"status": "READY", "blockers": []},
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
        _fields(
            market=market,
            readiness={
                "status": "PARTIAL",
                "blockers": ["DATA_INSUFFICIENT"],
                "available_inputs": {"lineups": True},
            },
        )["reason_code"]
        == DecisionReasonCode.DATA_MISSING_XG.value
    )


def test_readiness_status_mapping_is_not_optimistic() -> None:
    ready_market = {
        "market": "ASIAN_HANDICAP",
        "decision": "WATCH",
        "line": "-0.25",
        "odds": "1.95",
    }
    assert _fields(market=ready_market, readiness={"status": "READY", "blockers": []})[
        "data_status"
    ] == (
        DataStatus.READY.value
    )
    assert _fields(
        market=ready_market,
        readiness={"status": "PARTIAL", "blockers": ["MISSING_LINEUPS"]},
    )["data_status"] == DataStatus.PARTIAL.value
    assert _fields(
        market=ready_market,
        readiness={"status": "PARTIAL", "blockers": ["PROVIDER_BUDGET_EXHAUSTED"]},
    )["data_status"] == DataStatus.STALE.value


def test_blocked_data_status_downgrades_explicit_pick_tiers() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }

    analysis = _fields(
        market={**market, "decision_tier": "ANALYSIS_PICK"},
        readiness={
            "data_readiness": {
                "source": "w2.readiness.data_gate.v1",
                "data_status": "BLOCKED",
                "missing_fields": ["market"],
                "stale_fields": [],
                "reason_code": "MARKET_UNAVAILABLE",
                "reason_human": "盘口未就绪",
                "action": "等盘口开出或刷新",
                "next_eval_at": "2026-07-05T00:30:00Z",
                "provider_budget_status": "AVAILABLE",
                "field_statuses": [],
            }
        },
    )
    recommend = _fields(
        market={**market, "decision_tier": "RECOMMEND"},
        readiness={
            "data_readiness": {
                "source": "w2.readiness.data_gate.v1",
                "data_status": "BLOCKED",
                "missing_fields": ["market"],
                "stale_fields": [],
                "reason_code": "MARKET_UNAVAILABLE",
                "reason_human": "盘口未就绪",
                "action": "等盘口开出或刷新",
                "next_eval_at": "2026-07-05T00:30:00Z",
                "provider_budget_status": "AVAILABLE",
                "field_statuses": [],
            }
        },
    )

    assert analysis["decision_tier"] == DecisionTier.NOT_READY.value
    assert recommend["decision_tier"] == DecisionTier.NOT_READY.value
    assert analysis["reason_code"] == DecisionReasonCode.MARKET_UNAVAILABLE.value
    assert recommend["reason_code"] == DecisionReasonCode.MARKET_UNAVAILABLE.value
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
    assert staging["lock_eligible"] is False
    assert production["lock_eligible"] is False
    assert staging["card_hash"] == production["card_hash"]
    assert "分析参考" in staging["pick"]["disclaimer"]  # type: ignore[index]
    assert "非稳赢" in staging["pick"]["disclaimer"]  # type: ignore[index]


def test_partial_readiness_forces_watch_and_clears_pick() -> None:
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

    assert fields["decision_tier"] == DecisionTier.WATCH.value
    assert fields["pick"] is None
    assert fields["non_pick"] is not None
    assert fields["outcome_tracked"] is False
    assert fields["lock_eligible"] is False
    assert fields["data_status"] == DataStatus.PARTIAL.value


def test_no_edge_analysis_stays_non_pick_with_edge_reason() -> None:
    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "NO_EDGE",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.2,
        },
        readiness={"status": "READY", "blockers": []},
    )

    assert fields["decision_tier"] == DecisionTier.WATCH.value
    assert fields["reason_code"] == DecisionReasonCode.EDGE_INSUFFICIENT.value
    assert fields["pick"] is None
    assert fields["non_pick"] is not None
    assert fields["outcome_tracked"] is False


def test_low_confidence_pick_is_fail_closed_to_watch() -> None:
    fields = _fields(
        market={
            "market": "TOTALS",
            "decision": "PICK",
            "tendency": "OVER",
            "line": "2.5",
            "odds": "1.90",
            "confidence": 0.49,
        },
        readiness={"status": "READY", "blockers": []},
    )

    assert fields["decision_tier"] == DecisionTier.WATCH.value
    assert fields["reason_code"] == DecisionReasonCode.EDGE_INSUFFICIENT.value
    assert fields["pick"] is None
    assert fields["non_pick"] is not None


def test_decision_contract_exposes_probability_source_and_divergence() -> None:
    fields = _fields(
        card={
            "current_odds": {"ah": {"home_line": "-0.25"}},
            "market_divergence": {
                "status": "READY",
                "magnitude": 0.18,
                "lock_divergence": -0.18,
                "calibration_status": "UNVALIDATED",
                "direction_allowed": False,
            },
            "pricing_shadow": {"fair_ah": -0.5, "market_ah": -0.25},
        },
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.72,
        },
        readiness={"status": "PARTIAL", "blockers": []},
    )

    assert fields["probability_source"] == "MARKET_DEVIG"
    assert fields["decision_contract"]["probability_source"] == "MARKET_DEVIG"  # type: ignore[index]
    divergence = fields["model_market_divergence"]
    assert divergence["status"] == "READY"  # type: ignore[index]
    assert divergence["magnitude"] == 0.18  # type: ignore[index]
    assert divergence["model_fair_line"] == "-0.5"  # type: ignore[index]
    assert fields["decision_contract"]["model_market_divergence"] == divergence  # type: ignore[index]


def test_market_anchor_display_flag_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("W2_MARKET_ANCHOR_DISPLAY_ENABLED", raising=False)

    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.72,
        },
        readiness={"status": "READY", "blockers": []},
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["pick"] is not None


def test_market_anchor_display_requires_market_probability(monkeypatch) -> None:
    monkeypatch.setenv("W2_MARKET_ANCHOR_DISPLAY_ENABLED", "true")

    fields = _fields(
        card={
            "probability_source": "MODEL_FALLBACK",
            "model_market_divergence": {
                "status": "READY",
                "magnitude": 0.2,
                # 未来生产者契约:当前无生产路径置真;放行规则见契约 V2 预注册节。
                "direction_allowed": True,
            },
        },
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.72,
        },
        readiness={"status": "READY", "blockers": []},
    )

    assert fields["probability_source"] == "MODEL_FALLBACK"
    assert fields["decision_tier"] == DecisionTier.WATCH.value
    assert fields["reason_code"] == DecisionReasonCode.EDGE_INSUFFICIENT.value
    assert fields["pick"] is None
    assert fields["non_pick"] is not None


def test_market_anchor_display_requires_actionable_divergence(monkeypatch) -> None:
    monkeypatch.setenv("W2_MARKET_ANCHOR_DISPLAY_ENABLED", "true")

    fields = _fields(
        card={
            "probability_source": "MARKET_DEVIG",
            "model_market_divergence": {
                "status": "READY",
                "magnitude": 0.2,
                "direction_allowed": False,
            },
        },
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.72,
        },
        readiness={"status": "READY", "blockers": []},
    )

    assert fields["decision_tier"] == DecisionTier.WATCH.value
    assert fields["reason_code"] == DecisionReasonCode.EDGE_INSUFFICIENT.value
    assert fields["pick"] is None


def test_market_anchor_display_allows_significant_market_divergence(monkeypatch) -> None:
    monkeypatch.setenv("W2_MARKET_ANCHOR_DISPLAY_ENABLED", "true")

    fields = _fields(
        card={
            "probability_source": "MARKET_DEVIG",
            "model_market_divergence": {
                "status": "READY",
                "magnitude": 0.2,
                # 未来生产者契约:当前无生产路径置真;放行规则见契约 V2 预注册节。
                "direction_allowed": True,
            },
        },
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "confidence": 0.72,
        },
        readiness={"status": "READY", "blockers": []},
    )

    assert fields["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
    assert fields["pick"] is not None
    assert fields["non_pick"] is None


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
    assert complete["lock_eligible"] is False
    assert production_analysis["lock_eligible"] is False


def test_recommend_requires_prerequisites_before_lock_eligible() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision_tier": "RECOMMEND",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }
    readiness = {"status": "READY", "blockers": []}

    without_evidence = _fields(
        recommendation={"recommendation_id": "rec-1"},
        market=market,
        readiness=readiness,
        environment="staging",
    )
    with_evidence = _fields(
        card={"forward_ev_evidence_satisfied": True},
        recommendation={"recommendation_id": "rec-1"},
        market=market,
        readiness=readiness,
        environment="staging",
    )

    assert without_evidence["lock_eligible"] is False
    assert without_evidence["decision_tier"] == DecisionTier.WATCH.value
    assert without_evidence["recommendation_id"] is None
    assert with_evidence["decision_tier"] == DecisionTier.RECOMMEND.value
    assert with_evidence["lock_eligible"] is True


def test_legacy_formal_is_analysis_pick_with_compatibility_marker() -> None:
    fields = _fields(
        card={"formal_recommendation": True, "recommendation_id": "rec-legacy"},
        market={"market": "ASIAN_HANDICAP", "line": "-0.25", "odds": "1.95"},
        recommendation={"tier": "FORMAL", "formal_recommendation": True},
        readiness={"status": "READY", "blockers": []},
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
        market={"market": "ASIAN_HANDICAP", "decision": "WATCH", "line": "-0.25", "odds": "1.95"},
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
        readiness={"status": "BLOCKED", "blockers": ["FIXTURE_NOT_UPCOMING"]},
    )

    assert analysis["decision_tier"] == DecisionTier.WATCH.value
    assert analysis["pick"] is None
    assert analysis["non_pick"] is not None
    assert watch["decision_tier"] == DecisionTier.WATCH.value
    assert watch["pick"] is None
    assert watch["non_pick"] is not None
    assert blocked["decision_tier"] == DecisionTier.NOT_READY.value
    assert blocked["pick"] is None
    assert blocked["non_pick"] is not None


def test_incomplete_or_conflicting_quote_provenance_forces_not_ready() -> None:
    market = {
        "market": "ASIAN_HANDICAP",
        "decision": "PICK",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
    }
    missing = _fields(
        card={"quote_identity_audit": {}},
        market=market,
        readiness={"status": "READY", "blockers": []},
    )
    conflict = _fields(
        card={
            "recommendation_id": "rec-conflict",
            "quote_identity_audit": {
                "ah": {"identity_status": "CONFLICT", "freshness_status": "INCOMPLETE"}
            },
        },
        market=market,
        readiness={"status": "READY", "blockers": []},
    )

    for fields in (missing, conflict):
        assert fields["decision_tier"] == DecisionTier.NOT_READY.value
        assert fields["pick"] is None
        assert fields["recommendation_id"] is None
        assert fields["outcome_tracked"] is False
        assert fields["lock_eligible"] is False


def test_stale_quote_provenance_forces_watch_and_clears_executable_odds() -> None:
    fields = _fields(
        card={
            "recommendation_id": "rec-stale",
            "quote_identity_audit": {
                "ah": {"identity_status": "COMPLETE", "freshness_status": "STALE"}
            },
        },
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness={"status": "READY", "blockers": []},
    )

    assert fields["decision_tier"] == DecisionTier.WATCH.value
    assert fields["pick"] is None
    assert fields["recommendation_id"] is None
    assert fields["outcome_tracked"] is False
    assert fields["lock_eligible"] is False


def test_provider_budget_exhausted_is_stale_readiness() -> None:
    fields = _fields(
        market={
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
        },
        readiness={"status": "PARTIAL", "blockers": ["PROVIDER_BUDGET_EXHAUSTED"]},
    )

    assert fields["data_status"] == DataStatus.STALE.value
    assert fields["reason_code"] == DecisionReasonCode.PROVIDER_BUDGET_EXHAUSTED.value
    assert fields["provider_budget_status"] == "EXHAUSTED"


def test_data_gate_fields_pass_through_decision_contract() -> None:
    fields = _fields(
        market={"market": "ASIAN_HANDICAP", "decision": "WATCH"},
        readiness={
            "data_readiness": {
                "source": "w2.readiness.data_gate.v1",
                "data_status": "STALE",
                "missing_fields": ["xg"],
                "stale_fields": ["odds"],
                "reason_code": "DATA_STALE_ODDS",
                "reason_human": "盘口数据陈旧",
                "action": "触发盘口刷新或等下一 tick",
                "next_eval_at": "2026-07-05T00:30:00Z",
                "provider_budget_status": "AVAILABLE",
                "field_statuses": [],
            }
        },
    )

    assert fields["data_status"] == DataStatus.STALE.value
    assert fields["missing_fields"] == ["xg"]
    assert fields["stale_fields"] == ["odds"]
    assert fields["decision_contract"]["data_readiness"]["source"] == (  # type: ignore[index]
        "w2.readiness.data_gate.v1"
    )
