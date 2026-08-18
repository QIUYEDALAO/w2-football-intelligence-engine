from __future__ import annotations

import json
from pathlib import Path

import pytest

from w2.prematch.evaluation_slots import (
    CURRENT_EVALUATION_POLICY,
    EVALUATION_SLOTS,
    EvaluationSlotError,
    evaluation_slots,
    expected_opportunity_count,
    is_evaluation_slot,
    require_evaluation_slot,
)

ROOT = Path(__file__).resolve().parents[2]


def test_every_slot_exists_in_the_collection_ladder() -> None:
    """A slot the scheduler never runs would be an opportunity that cannot occur."""

    policy = json.loads(
        (ROOT / "config/policies/matchday_intake.v2.json").read_text(encoding="utf-8")
    )
    ladder = set(policy["canonical_checkpoints"])
    for version, slots in EVALUATION_SLOTS.items():
        unknown = sorted(set(slots) - ladder)
        assert not unknown, f"{version} references checkpoints outside the ladder: {unknown}"


def test_lineup_only_checkpoints_are_not_opportunities() -> None:
    """Lineup retries feed a slot; they are not decision points themselves.

    Counting them would inflate the denominator with moments the system never
    committed to evaluating at, which is the difference between measuring a
    match's chances and measuring the scheduler's cadence.
    """

    for lineup_only in ("T45_LINEUPS_RETRY", "T30_LINEUPS_RETRY", "LINEUP_CONFIRMED"):
        assert not is_evaluation_slot(lineup_only)


def test_fixture_1494246_denominator_is_five_slots_per_market() -> None:
    """Pinned against the first fixture that completed the chain end to end.

    It evaluated at T-3h, T-60m, T-45m, T-30m and T-15m across two markets --
    ten opportunities, not fourteen ladder entries.
    """

    assert len(evaluation_slots()) == 5
    assert expected_opportunity_count(markets=2) == 10


def test_unresolved_checkpoint_fails_closed() -> None:
    """The old path fell back to the literal "capture" and invented history."""

    with pytest.raises(EvaluationSlotError, match="UNRESOLVED"):
        require_evaluation_slot(None)
    with pytest.raises(EvaluationSlotError, match="UNRESOLVED"):
        require_evaluation_slot("")
    with pytest.raises(EvaluationSlotError, match="NOT_REGISTERED"):
        require_evaluation_slot("capture")


def test_unknown_policy_version_fails_closed() -> None:
    with pytest.raises(EvaluationSlotError, match="POLICY_NOT_REGISTERED"):
        evaluation_slots("candidate-eval.v99")


def test_current_policy_is_registered() -> None:
    assert CURRENT_EVALUATION_POLICY in EVALUATION_SLOTS


def test_posthoc_snapshot_rows_are_barred_from_the_funnel() -> None:
    """The sweep rows stay queryable but must not reach any pass-rate.

    Their gate verdicts describe the moment the scan ran, not the checkpoint they
    name, so letting even one through makes every rate unfounded.  With the row
    excluded the unit still counts toward the denominator -- it simply has no
    verdict, which is the honest state.
    """

    from w2.api.repository import _model_forecast_market_evaluation_funnel

    class _Capture:
        fixture_id = "api_football:1494246"

    class _Row:
        def __init__(self, *, eligible: bool | None) -> None:
            self.evaluation_id = f"eval-{eligible}"
            self.fixture_id = "api_football:1494246"
            self.market = "ASIAN_HANDICAP"
            self.denominator_scope = "MODEL_FORECAST_CAPTURE_MARKET_V1"
            self.official_funnel_eligible = eligible
            self.evaluated_at = None
            self.original_state = "NOT_READY_MODEL_INPUT"
            self.recorded_at = None
            self.bookmaker_count = 0
            self.first_failed_gate = "MAINLINE_PARSED"
            self.gate_results = None
            self.payload = {"state": "NOT_READY_MODEL_INPUT"}

    captures = [_Capture()]

    excluded = _model_forecast_market_evaluation_funnel(captures, [_Row(eligible=False)], set())
    included = _model_forecast_market_evaluation_funnel(captures, [_Row(eligible=True)], set())

    # The denominator is unchanged: the opportunity existed either way.
    assert excluded["market_unit_count"] == included["market_unit_count"] == 2
    # But the sweep row contributes no verdict and no persisted unit.
    assert excluded["persisted_market_unit_count"] == 0
    assert included["persisted_market_unit_count"] == 1
