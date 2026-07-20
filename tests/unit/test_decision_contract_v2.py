from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from w2.domain.decision_card import DecisionCard, DecisionNonPick, DecisionPick
from w2.domain.decision_policy import (
    DecisionPolicyConfig,
    compute_lock_eligible,
    compute_outcome_tracked,
)
from w2.domain.enums import DataStatus, DecisionReasonCode, DecisionTier, LifecycleStatus
from w2.domain.legacy_decision_shim import legacy_decision_view


def _pick(disclaimer: str | None = None) -> DecisionPick:
    kwargs = {"disclaimer": disclaimer} if disclaimer is not None else {}
    return DecisionPick(
        market="ASIAN_HANDICAP",
        selection="HOME",
        line="-0.25",
        odds="1.95",
        fair_line="-0.5",
        market_line="-0.25",
        value_edge=0.04,
        key_factors=("xg", "market"),
        risks=("lineup",),
        invalidation="line moved past fair",
        **kwargs,
    )


def _non_pick() -> DecisionNonPick:
    return DecisionNonPick(
        reason_code=DecisionReasonCode.LINEUPS_PENDING,
        reason_human="Lineups are not available yet.",
        action="Wait for official lineups.",
        next_eval_at=datetime(2026, 7, 5, 1, 0, tzinfo=UTC),
    )


def _card(
    decision_tier: DecisionTier,
    *,
    pick: DecisionPick | None = None,
    non_pick: DecisionNonPick | None = None,
) -> DecisionCard:
    now = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
    return DecisionCard(
        fixture_id="fixture-1",
        competition_id="world_cup_2026",
        kickoff_utc=now + timedelta(hours=4),
        kickoff_beijing=(now + timedelta(hours=12)).astimezone(timezone(timedelta(hours=8))),
        decision_tier=decision_tier,
        data_status=DataStatus.READY,
        lifecycle_status=LifecycleStatus.DRAFT,
        outcome_tracked=compute_outcome_tracked(decision_tier),
        lock_eligible=False,
        recommendation_id="rec-1",
        model_version="dc-v2-test",
        provenance={"source": "unit"},
        environment="staging",
        pick=pick,
        non_pick=non_pick,
        one_liner="Home pressure creates a small edge.",
    )


def _pick_card(decision_tier: DecisionTier) -> DecisionCard:
    return _card(decision_tier, pick=_pick())


def test_decision_tier_values_are_domain_source_of_truth() -> None:
    assert {tier.value for tier in DecisionTier} == {
        "NOT_READY",
        "SKIP",
        "WATCH",
        "ANALYSIS_PICK",
        "RECOMMEND",
    }


def test_decision_card_tracks_analysis_pick_and_recommend_outcomes() -> None:
    analysis = _pick_card(DecisionTier.ANALYSIS_PICK)
    recommend = _pick_card(DecisionTier.RECOMMEND)

    assert analysis.outcome_tracked is True
    assert recommend.outcome_tracked is True
    assert compute_outcome_tracked(DecisionTier.WATCH) is False


def test_non_pick_requires_actionable_reason_fields() -> None:
    next_eval_at = datetime(2026, 7, 5, 1, 0, tzinfo=UTC)

    card = DecisionCard(
        fixture_id="fixture-2",
        competition_id="world_cup_2026",
        kickoff_utc=datetime(2026, 7, 5, 8, 0, tzinfo=UTC),
        kickoff_beijing=datetime(2026, 7, 5, 16, 0, tzinfo=timezone(timedelta(hours=8))),
        decision_tier=DecisionTier.NOT_READY,
        data_status=DataStatus.PARTIAL,
        lifecycle_status=LifecycleStatus.DRAFT,
        outcome_tracked=False,
        lock_eligible=False,
        recommendation_id=None,
        model_version="dc-v2-test",
        provenance={"source": "unit"},
        environment="staging",
        non_pick=DecisionNonPick(
            reason_code=DecisionReasonCode.LINEUPS_PENDING,
            reason_human="Lineups are not available yet.",
            action="Wait for official lineups.",
            next_eval_at=next_eval_at,
        ),
        one_liner="Waiting for lineups.",
    )

    assert card.non_pick is not None
    assert card.non_pick.reason_code is DecisionReasonCode.LINEUPS_PENDING
    assert card.non_pick.action == "Wait for official lineups."
    assert card.non_pick.next_eval_at == next_eval_at


def test_decision_card_rejects_pick_non_pick_tier_mismatches() -> None:
    with pytest.raises(ValueError):
        _card(DecisionTier.RECOMMEND, non_pick=_non_pick())
    with pytest.raises(ValueError):
        _card(DecisionTier.ANALYSIS_PICK)
    with pytest.raises(ValueError):
        _card(DecisionTier.WATCH, pick=_pick())
    with pytest.raises(ValueError):
        _card(DecisionTier.NOT_READY)


def test_decision_card_accepts_valid_pick_and_non_pick_tier_shapes() -> None:
    analysis = _card(DecisionTier.ANALYSIS_PICK, pick=_pick())
    watch = _card(DecisionTier.WATCH, non_pick=_non_pick())

    assert analysis.pick is not None
    assert analysis.non_pick is None
    assert watch.pick is None
    assert watch.non_pick is not None


def test_analysis_pick_default_disclaimer_is_staging_safe() -> None:
    assert "分析参考" in _pick().disclaimer
    assert "非稳赢" in _pick().disclaimer


def test_analysis_pick_rejects_missing_required_disclaimer_terms() -> None:
    with pytest.raises(ValueError):
        _card(
            DecisionTier.ANALYSIS_PICK,
            pick=_pick(disclaimer="分析参考；production 动作需 RECOMMEND"),
        )
    with pytest.raises(ValueError):
        _card(
            DecisionTier.ANALYSIS_PICK,
            pick=_pick(disclaimer="非稳赢；production 动作需 RECOMMEND"),
        )


@pytest.mark.parametrize("term", ["稳赢", "必中", "保证", "包赢"])
def test_pick_disclaimer_rejects_deterministic_claims(term: str) -> None:
    with pytest.raises(ValueError):
        _card(DecisionTier.RECOMMEND, pick=_pick(disclaimer=f"production recommend；{term}"))


def test_lock_eligible_is_recommend_only_and_keeps_core_hash_stable() -> None:
    card = _pick_card(DecisionTier.ANALYSIS_PICK)
    config = DecisionPolicyConfig(
        now_utc=datetime(2026, 7, 5, 0, 0, tzinfo=UTC),
        data_integrity_passed=True,
        market_complete=True,
        forward_ev_evidence_satisfied=False,
    )

    staging = compute_lock_eligible(card, "staging", config)
    production = compute_lock_eligible(card, "production", config)
    production_card = replace(card, environment="production", lock_eligible=production)
    staging_card = replace(card, lock_eligible=staging)

    assert staging is False
    assert production is False
    assert staging_card.card_hash == production_card.card_hash


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_recommend_requires_explicit_lock_gates(environment: str) -> None:
    card = _pick_card(DecisionTier.RECOMMEND)

    assert (
        compute_lock_eligible(
            card,
            environment,
            DecisionPolicyConfig(
                now_utc=datetime(2026, 7, 5, 0, 0, tzinfo=UTC),
                data_integrity_passed=False,
                market_complete=False,
                forward_ev_evidence_satisfied=False,
            ),
        )
        is False
    )
    assert (
        compute_lock_eligible(
            card,
            environment,
            DecisionPolicyConfig(
                recommendation_lock_feature_enabled=True,
                recommendation_lock_production_enabled=True,
                immutable_recommendation_identity_complete=True,
                production_recommendation_capability_enabled=True,
            ),
        )
        is True
    )


def test_legacy_shim_maps_historical_read_paths_without_mutating_payload() -> None:
    card = {"formal_recommendation": True, "recommendation_id": "rec-Legacy"}
    before = dict(card)
    formal = legacy_decision_view(card)

    assert formal.decision_tier is DecisionTier.ANALYSIS_PICK
    assert formal.lock_eligible is True
    assert formal.legacy_formal is True
    assert formal.recommendation_id == "rec-Legacy"
    assert card == before

    explicit = legacy_decision_view({"decision_tier": "RECOMMEND", "recommendation_id": "rec-new"})
    assert explicit.decision_tier is DecisionTier.RECOMMEND
    assert explicit.legacy_formal is False
    assert legacy_decision_view({"decision": "NO_RECOMMENDATION"}).decision_tier is (
        DecisionTier.SKIP
    )
    assert legacy_decision_view({"candidate": True}).decision_tier is DecisionTier.WATCH
