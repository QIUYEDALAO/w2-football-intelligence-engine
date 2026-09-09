"""Test matrix 15-18 and 20, all offline: fixtures and an in-memory database.

15  nothing settled at or after a record's evaluated_at may train its temperature
16  both markets of one fixture are resampled together, never independently
17  a temperature-scaled five-state distribution still normalises within 1e-9
18  the four-track EV comes from the canonical Decimal authority, not a copy
20  replay, duplicate writes and readback leave every stored row untouched
"""
from __future__ import annotations

import ast
import importlib.util
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from w2.domain.five_state_pricing import (
    PROBABILITY_TOLERANCE,
    SettlementDistribution,
    expected_value,
)
from w2.infrastructure.database import Base
from w2.prematch.lifecycle import (
    CHECKPOINT_OPPORTUNITY_SCOPE,
    DynamicEvaluationInput,
    EvaluationOpportunityContext,
    bind_evaluation_opportunity,
    classify_evaluation,
)
from w2.prematch.repository import DynamicPrematchRepository

_FOUR_TRACK_PATH = Path(__file__).resolve().parents[1] / "official_candidate_four_track.py"
_spec = importlib.util.spec_from_file_location("w2_four_track_under_test", _FOUR_TRACK_PATH)
assert _spec is not None and _spec.loader is not None
four_track = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(four_track)

NOW = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
FLAT = {"WIN": 0.5, "HALF_WIN": 0.0, "PUSH": 0.05, "HALF_LOSS": 0.0, "LOSS": 0.45}


def _row(evaluation_id: str, *, evaluated_at: str, result_available_at: str | None,
         market: str = "ASIAN_HANDICAP", fixture_id: str = "f1",
         settlement: str = "WIN", profit: str = "0.91") -> dict:
    return {
        "evaluation_id": evaluation_id,
        "fixture_id": fixture_id,
        "market": market,
        "selection": "HOME",
        "kickoff_utc": evaluated_at,
        "evaluated_at": evaluated_at,
        "result_available_at": result_available_at,
        "settlement": settlement,
        "profit_units": profit,
        "decimal_odds": 1.91,
        "dist": dict(FLAT),
        "ev_se": 0.01,
        "cashflow_price_edge": 0.10,
    }


# --- 15: no future, in-play or unsettled record may train a temperature ------
def test_15_only_results_authoritatively_available_before_evaluation_may_train() -> None:
    subject = _row("subject", evaluated_at="2026-08-20T12:00:00Z",
                   result_available_at="2026-08-21T12:00:00Z")

    settled_before = _row("earlier", evaluated_at="2026-08-19T12:00:00Z",
                          result_available_at="2026-08-19T20:00:00Z")
    settled_after = _row("after", evaluated_at="2026-08-19T12:00:00Z",
                         result_available_at="2026-08-20T20:00:00Z")
    settled_at_the_same_instant = _row("same", evaluated_at="2026-08-19T12:00:00Z",
                                       result_available_at="2026-08-20T12:00:00Z")
    never_settled = _row("unknown", evaluated_at="2026-08-19T12:00:00Z",
                         result_available_at=None)
    other_market = _row("totals", evaluated_at="2026-08-19T12:00:00Z",
                        result_available_at="2026-08-19T20:00:00Z", market="TOTALS")

    assert four_track.trainable_for(settled_before, subject) is True
    assert four_track.trainable_for(settled_after, subject) is False
    assert four_track.trainable_for(settled_at_the_same_instant, subject) is False
    assert four_track.trainable_for(never_settled, subject) is False
    assert four_track.trainable_for(other_market, subject) is False


def test_15_a_later_record_never_reaches_an_earlier_temperature() -> None:
    """End to end through build_tracks: the first record has nothing to train on."""
    rows = [
        _row("first", evaluated_at="2026-08-20T12:00:00Z",
             result_available_at="2026-08-20T20:00:00Z"),
        _row("second", evaluated_at="2026-08-21T12:00:00Z",
             result_available_at="2026-08-21T20:00:00Z", fixture_id="f2"),
    ]

    _tracks, log = four_track.build_tracks(rows)

    by_id = {entry["evaluation_id"]: entry for entry in log}
    assert by_id["first"]["training_rows"] == 0
    assert by_id["second"]["training_rows"] == 1
    # under MIN_TRAIN neither may move off the neutral temperature
    assert by_id["first"]["temperature"] == 1.0
    assert by_id["second"]["temperature"] == 1.0


# --- 16: a fixture is the resampling unit, so its two markets move together --
def test_16_both_markets_of_a_fixture_are_resampled_as_one_cluster(monkeypatch) -> None:
    rows = [
        _row("a-ah", evaluated_at="2026-08-20T12:00:00Z", fixture_id="fa",
             result_available_at="2026-08-20T20:00:00Z", settlement="WIN"),
        _row("a-totals", evaluated_at="2026-08-20T12:00:00Z", fixture_id="fa",
             market="TOTALS", result_available_at="2026-08-20T20:00:00Z",
             settlement="LOSS"),
        _row("b-ah", evaluated_at="2026-08-21T12:00:00Z", fixture_id="fb",
             result_available_at="2026-08-21T20:00:00Z", settlement="LOSS"),
    ]

    class _FirstKeyRNG:
        def __init__(self, _seed: int) -> None:
            pass

        def choice(self, seq):  # type: ignore[no-untyped-def]
            return seq[0]

    monkeypatch.setattr(four_track.random, "Random", _FirstKeyRNG)
    result = four_track.calibration_bootstrap(rows, seed=1)

    # every draw is fixture "fa", whose two markets grade 1.0 and 0.0
    assert result["clusters"] == 2
    assert result["actual_graded_rate_ci95"] == [0.5, 0.5], (
        "a sample of only fixture fa must contain both of its markets; 1.0 would "
        "mean the AH row was resampled without its TOTALS partner"
    )


def test_16_the_cluster_count_is_fixtures_not_rows() -> None:
    rows = [
        _row("a-ah", evaluated_at="2026-08-20T12:00:00Z", fixture_id="fa",
             result_available_at="2026-08-20T20:00:00Z"),
        _row("a-totals", evaluated_at="2026-08-20T12:00:00Z", fixture_id="fa",
             market="TOTALS", result_available_at="2026-08-20T20:00:00Z",
             settlement="LOSS"),
    ]

    result = four_track.calibration_bootstrap(rows, seed=1)

    assert (result["clusters"], result["decisive_rows"]) == (1, 2)
    assert result["cluster_unit"] == "fixture_id"


# --- 17: a tempered distribution still normalises within 1e-9 ---------------
@pytest.mark.parametrize("dist", [
    FLAT,
    {"WIN": 0.9, "HALF_WIN": 0.02, "PUSH": 0.03, "HALF_LOSS": 0.02, "LOSS": 0.03},
    {"WIN": 0.001, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.999},
    {"WIN": 0.2, "HALF_WIN": 0.2, "PUSH": 0.2, "HALF_LOSS": 0.2, "LOSS": 0.2},
])
def test_17_every_temperature_on_the_frozen_grid_keeps_the_1e9_contract(dist) -> None:
    assert PROBABILITY_TOLERANCE == Decimal("1e-9")
    for temperature in four_track.T_GRID:
        calibrated = four_track.temper(dist, temperature)
        assert abs(sum(calibrated.values()) - 1.0) < 1e-9
        frozen = four_track.distribution_from(calibrated)
        total = sum(
            (getattr(frozen, name) for name in frozen.__dataclass_fields__), Decimal(0)
        )
        assert abs(total - 1) <= PROBABILITY_TOLERANCE, temperature


def test_17_a_distribution_that_misses_the_contract_is_refused_not_rounded() -> None:
    with pytest.raises(ValueError, match="CALIBRATED_DISTRIBUTION_FAILED_1E9_CONTRACT"):
        four_track.distribution_from(
            {"WIN": 0.5, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.0}
        )


# --- 18: the EV is the canonical authority's, never a second formula --------
def test_18_the_four_track_module_defines_no_ev_formula_of_its_own() -> None:
    tree = ast.parse(_FOUR_TRACK_PATH.read_text(encoding="utf-8"))

    imported_from = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and any(alias.name == "expected_value" for alias in node.names)
    }
    assert imported_from == {"w2.domain.five_state_pricing"}

    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    assert not {name for name in defined if "expected_value" in name or name == "ev"}


def test_18_the_calibrated_ev_equals_the_canonical_authority_recomputed() -> None:
    rows = [
        _row("only", evaluated_at="2026-08-20T12:00:00Z",
             result_available_at="2026-08-20T20:00:00Z"),
    ]

    tracks, _log = four_track.build_tracks(rows)
    emitted = tracks["INCUMBENT"][0]

    calibrated = four_track.temper(rows[0]["dist"], emitted["temperature"])
    expected = float(expected_value(
        Decimal(str(rows[0]["decimal_odds"])),
        SettlementDistribution(
            full_win_probability=Decimal(str(calibrated["WIN"])),
            half_win_probability=Decimal(str(calibrated["HALF_WIN"])),
            push_probability=Decimal(str(calibrated["PUSH"])),
            half_loss_probability=Decimal(str(calibrated["HALF_LOSS"])),
            full_loss_probability=Decimal(str(calibrated["LOSS"])),
        ).normalized(),
    ))
    assert emitted["calibrated_ev"] == expected


# --- 20: replay, duplicate writes and readback change nothing on disk -------
def _snapshot(engine) -> dict[str, list[tuple]]:  # type: ignore[no-untyped-def]
    """Every row of every table, so a change anywhere shows up."""
    snapshot: dict[str, list[tuple]] = {}
    with engine.connect() as connection:
        for name in sorted(inspect(engine).get_table_names()):
            rows = connection.execute(text(f'select * from "{name}"')).fetchall()  # noqa: S608
            snapshot[name] = sorted(repr(row) for row in rows)
    return snapshot


def _attempt(suffix: str, **verdict):  # type: ignore[no-untyped-def]
    value = DynamicEvaluationInput(
        fixture_id="1490401",
        market="ASIAN_HANDICAP",
        selection="HOME",
        exact_line=-0.25,
        bookmaker_id="book-1",
        capture_id=f"capture-{suffix}",
        quote_identity_hash=(suffix * 64)[:64],
        model_input_hash="2" * 64,
        evaluated_at=NOW + timedelta(minutes=len(suffix)),
        checkpoint="T15_ODDS",
        capture_at=NOW,
        model_probability=0.60,
        market_probability=0.50,
        expected_value=0.06,
        ev_se=0.01,
        cashflow_price_edge=0.10,
        decimal_odds=1.91,
        bookmaker_count=7,
        mainline_parsed=True,
        calibration_status="PRODUCTION_VALIDATED",
        denominator_scope=CHECKPOINT_OPPORTUNITY_SCOPE,
        **verdict,
    )
    return bind_evaluation_opportunity(
        classify_evaluation(value),
        EvaluationOpportunityContext(
            model_forecast_capture_identity_hash=(suffix * 64)[:64],
            model_input_hash="2" * 64,
            evaluation_policy_version="candidate-eval.v1",
            evaluation_slot_id="T15_ODDS",
            scheduled_checkpoint_at=NOW + timedelta(minutes=len(suffix)),
            checkpoint_plan_identity=f"plan-{suffix}",
            source_event_identity=f"event-{suffix}",
        ),
    )


def test_20_replaying_the_same_evaluation_leaves_every_stored_row_untouched() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = DynamicPrematchRepository(engine)
    admitted = _attempt(
        "a",
        factor_decision_status="ADMITTED",
        factor_direction="HOME",
        factor_input_identity="f" * 64,
        factor_input_identity_hash="f" * 64,
    )
    repository.append_evaluation(admitted)
    before = _snapshot(engine)
    assert any(rows for rows in before.values())

    for _ in range(3):
        rebuilt, created = repository.append_evaluation(admitted)
        assert created is False
        assert rebuilt.identity_hash == admitted.identity_hash

    assert _snapshot(engine) == before


def test_20_a_later_verdict_appends_a_new_row_without_editing_the_old_one() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = DynamicPrematchRepository(engine)
    from w2.infrastructure.persistence.dynamic_prematch_models import (
        DynamicPrematchEvaluationModel,
    )

    first = _attempt(
        "a",
        factor_decision_status="ADMITTED",
        factor_direction="HOME",
        factor_input_identity="f" * 64,
        factor_input_identity_hash="f" * 64,
    )
    repository.append_evaluation(first)
    with Session(engine) as session:
        original = session.scalar(
            select(DynamicPrematchEvaluationModel).where(
                DynamicPrematchEvaluationModel.identity_hash == first.identity_hash
            )
        )
        original_payload = dict(original.payload)

    second = _attempt(
        "a",
        factor_decision_status="VETOED",
        factor_direction="AWAY",
        ev_direction="HOME",
        factor_veto_code="FACTOR_EV_DIRECTION_CONFLICT",
        factor_input_identity="e" * 64,
        factor_input_identity_hash="e" * 64,
    )
    repository.append_evaluation(second)

    assert second.identity_hash != first.identity_hash
    with Session(engine) as session:
        rows = list(session.scalars(select(DynamicPrematchEvaluationModel)))
        kept = next(row for row in rows if row.identity_hash == first.identity_hash)
        assert dict(kept.payload) == original_payload
    assert len(rows) == 2
