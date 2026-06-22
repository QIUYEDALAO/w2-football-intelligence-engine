from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from scripts.run_stage9a_shadow_replay import demo_inputs

from w2.strategy.shadow import (
    ShadowAction,
    ShadowStrategyEngine,
    ShadowStrategyLedger,
    StrategyInput,
    adjusted_minimum_odds,
)


def test_shadow_strategy_every_fixture_decision_and_gate4_cap() -> None:
    decision = ShadowStrategyEngine().evaluate(demo_inputs()[0])
    payload = decision.as_dict()
    assert payload["most_likely_outcome"] == "HOME_WIN"
    assert payload["public_decision"] in {"NOT_READY", "SKIP", "WATCH"}
    assert payload["published_grade"] not in {"A", "B"}
    assert payload["formal_recommendation"] is False
    assert payload["candidate"] is False


def test_adjusted_minimum_odds_is_not_model_fair_odds() -> None:
    decision = ShadowStrategyEngine().evaluate(demo_inputs()[0])
    assert decision.primary is not None
    opportunity = decision.primary.opportunity
    assert opportunity.adjusted_minimum_odds is not None
    assert opportunity.model_fair_odds is not None
    assert opportunity.adjusted_minimum_odds >= opportunity.model_fair_odds


def test_kickoff_after_asof_is_blocked() -> None:
    item = demo_inputs()[0]
    blocked = StrategyInput(
        fixture_id=item.fixture_id,
        phase=item.phase,
        kickoff_utc=datetime(2026, 6, 22, 21, 0, tzinfo=UTC),
        as_of_time=datetime(2026, 6, 22, 21, 1, tzinfo=UTC),
        score_matrix=item.score_matrix,
        independent_probabilities=item.independent_probabilities,
        quotes=item.quotes,
        most_likely_outcome=item.most_likely_outcome,
    )
    decision = ShadowStrategyEngine().evaluate(blocked)
    assert decision.shadow_action == ShadowAction.SHADOW_NOT_READY
    assert decision.public_decision == "NOT_READY"
    assert decision.raw_grade == "X"


def test_shadow_lock_is_idempotent_and_immutable() -> None:
    engine = ShadowStrategyEngine()
    decision = engine.evaluate(demo_inputs()[0])
    ledger = ShadowStrategyLedger()
    first = ledger.lock(decision)
    second = ledger.lock(decision)
    assert first.decision_hash == second.decision_hash
    changed = ShadowStrategyEngine(uncertainty_penalty=Decimal("0.001")).evaluate(demo_inputs()[0])
    with pytest.raises(ValueError, match="IMMUTABILITY"):
        ledger.lock(changed)


def test_adjusted_minimum_odds_formula_for_quarter_style_distribution() -> None:
    decision = ShadowStrategyEngine().evaluate(demo_inputs()[0])
    assert decision.primary is not None
    distribution = decision.primary.opportunity.settlement_distribution
    minimum = adjusted_minimum_odds(distribution, Decimal("0.035"))
    assert minimum > Decimal("1")
