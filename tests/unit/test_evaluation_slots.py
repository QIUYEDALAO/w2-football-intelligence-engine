from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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
    """The sweep rows stay queryable but must never reach a pass-rate.

    Their gate verdicts describe the moment the scan ran, not the checkpoint
    they name.  An official opportunity carrying the full contract is counted;
    the quarantined row is not, and its absence leaves the funnel honestly
    unmeasurable rather than reporting a fabricated failure.
    """

    from w2.api.repository import _model_forecast_market_evaluation_funnel

    class _Capture:
        fixture_id = "api_football:1494246"

    def _row(*, official: bool) -> object:
        return SimpleNamespace(
            evaluation_id=f"eval-{official}",
            fixture_id="api_football:1494246",
            market="ASIAN_HANDICAP",
            denominator_scope=(
                "CHECKPOINT_EVALUATION_OPPORTUNITY_V2"
                if official
                else "LEGACY_POSTHOC_DENOMINATOR_SNAPSHOT_V1"
            ),
            measurement_semantics=(
                "CHECKPOINT_EVALUATION_OPPORTUNITY"
                if official
                else "POSTHOC_CURRENT_STATE_SNAPSHOT"
            ),
            official_funnel_eligible=official,
            evaluation_policy_version="candidate-eval.v1" if official else None,
            evaluation_slot_id="T15_ODDS" if official else None,
            capture_id="capture-1494246" if official else None,
            evaluated_at=None,
            recorded_at=None,
            original_state="NO_EDGE_CURRENT",
            bookmaker_count=0,
            first_failed_gate=None,
            gate_results=None,
            payload={"state": "NO_EDGE_CURRENT"},
        )

    quarantined = _model_forecast_market_evaluation_funnel(
        [_Capture()], [_row(official=False)], set()
    )
    assert quarantined["measurement_status"] == "NOT_MEASURABLE"
    assert quarantined["opportunity_count"] == 0
    assert quarantined["gate_rates"] is None

    official = _model_forecast_market_evaluation_funnel([_Capture()], [_row(official=True)], set())
    assert official["measurement_status"] == "MEASURABLE"
    assert official["opportunity_count"] == 1


def _opportunity(slot: str, *, market: str = "ASIAN_HANDICAP", policy: str = "candidate-eval.v1"):
    return SimpleNamespace(
        evaluation_id=f"eval-{slot}-{market}",
        fixture_id="api_football:1494246",
        capture_id="capture-1494246",
        market=market,
        denominator_scope="CHECKPOINT_EVALUATION_OPPORTUNITY_V2",
        measurement_semantics="CHECKPOINT_EVALUATION_OPPORTUNITY",
        official_funnel_eligible=True,
        evaluation_policy_version=policy,
        evaluation_slot_id=slot,
        evaluated_at=None,
        recorded_at=None,
        original_state="NO_EDGE_CURRENT",
        bookmaker_count=9,
        first_failed_gate=None,
        gate_results=None,
        payload={"state": "NO_EDGE_CURRENT"},
    )


def test_five_slots_across_two_markets_are_ten_distinct_opportunities() -> None:
    """The red light for the opportunity writer.

    Keyed on fixture x market the five checkpoints collapse to two rows, which
    is exactly what 1494246 would have reported despite evaluating five times in
    each market.
    """

    from w2.api.repository import _model_forecast_market_evaluation_funnel

    rows = [
        _opportunity(slot, market=market)
        for slot in evaluation_slots()
        for market in ("ASIAN_HANDICAP", "TOTALS")
    ]
    funnel = _model_forecast_market_evaluation_funnel(
        [SimpleNamespace(fixture_id="api_football:1494246")], rows, set()
    )

    assert funnel["measurement_status"] == "MEASURABLE"
    assert funnel["opportunity_count"] == 10
    assert funnel["fixture_count"] == 1


def test_unregistered_slot_never_reaches_the_denominator() -> None:
    """A typo'd slot is a writer defect, not an opportunity."""

    from w2.api.repository import _model_forecast_market_evaluation_funnel

    funnel = _model_forecast_market_evaluation_funnel(
        [SimpleNamespace(fixture_id="api_football:1494246")],
        [_opportunity("T44_ODDS")],
        set(),
    )
    assert funnel["measurement_status"] == "NOT_MEASURABLE"


def test_unregistered_market_never_reaches_the_denominator() -> None:
    """The contract is five slots x two markets; 1X2 is not part of it."""

    from w2.api.repository import _model_forecast_market_evaluation_funnel

    funnel = _model_forecast_market_evaluation_funnel(
        [SimpleNamespace(fixture_id="api_football:1494246")],
        [_opportunity("T15_ODDS", market="1X2")],
        set(),
    )
    assert funnel["measurement_status"] == "NOT_MEASURABLE"
