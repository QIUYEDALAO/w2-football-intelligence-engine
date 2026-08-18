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
            capture_id="quote-capture-1" if official else None,
            model_forecast_capture_identity_hash="capture-hash-A" if official else None,
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
        model_forecast_capture_identity_hash="capture-hash-A",
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


def test_defective_official_row_reports_invalid_not_absent() -> None:
    """A row claiming to be official and failing the contract is a defect.

    Reporting it as NOT_MEASURABLE would say "nothing has happened yet" about a
    writer that is actively producing broken records -- the same failure-as-
    absence mistake this rework exists to remove.
    """

    from w2.api.repository import _model_forecast_market_evaluation_funnel

    captures = [SimpleNamespace(fixture_id="api_football:1494246")]

    typo = _model_forecast_market_evaluation_funnel(captures, [_opportunity("T44_ODDS")], set())
    assert typo["measurement_status"] == "INVALID"
    assert typo["invalid_opportunity_reasons"] == {"SLOT_NOT_REGISTERED": 1}

    wrong_market = _model_forecast_market_evaluation_funnel(
        captures, [_opportunity("T15_ODDS", market="1X2")], set()
    )
    assert wrong_market["measurement_status"] == "INVALID"
    assert wrong_market["invalid_opportunity_reasons"] == {"MARKET_NOT_REGISTERED": 1}


def test_official_row_without_forecast_capture_identity_is_invalid() -> None:
    """The odds-snapshot capture cannot stand in for the model track.

    Two tracks reading the same quote would otherwise share an opportunity, and
    a retry reading a different snapshot would split one in two.
    """

    from w2.api.repository import _model_forecast_market_evaluation_funnel

    row = _opportunity("T15_ODDS")
    row.model_forecast_capture_identity_hash = None
    row.capture_id = "quote-capture-1"

    funnel = _model_forecast_market_evaluation_funnel(
        [SimpleNamespace(fixture_id="api_football:1494246")], [row], set()
    )
    assert funnel["measurement_status"] == "INVALID"
    assert funnel["invalid_opportunity_reasons"] == {"FORECAST_CAPTURE_IDENTITY_MISSING": 1}


def test_two_model_tracks_sharing_a_quote_stay_separate_opportunities() -> None:
    """Same fixture, slot, market and quote -- but two frozen tracks."""

    from w2.api.repository import _model_forecast_market_evaluation_funnel

    first = _opportunity("T15_ODDS")
    second = _opportunity("T15_ODDS")
    second.evaluation_id = "eval-track-b"
    second.model_forecast_capture_identity_hash = "capture-hash-B"

    funnel = _model_forecast_market_evaluation_funnel(
        [SimpleNamespace(fixture_id="api_football:1494246")], [first, second], set()
    )
    assert funnel["measurement_status"] == "MEASURABLE"
    assert funnel["opportunity_count"] == 2


def _repository_evaluation(
    *,
    fixture_id: str,
    slot: str,
    market: str,
    capture_hash: str,
    source_event: str,
    quote_hash: str,
):
    from datetime import UTC, datetime

    from w2.prematch.lifecycle import (
        DynamicEvaluationInput,
        EvaluationOpportunityContext,
        bind_evaluation_opportunity,
        classify_evaluation,
    )

    evaluated_at = datetime(2026, 8, 18, 6, 0, tzinfo=UTC)
    version = classify_evaluation(
        DynamicEvaluationInput(
            fixture_id=fixture_id,
            market=market,
            selection="HOME" if market == "ASIAN_HANDICAP" else "OVER",
            exact_line=0.0 if market == "ASIAN_HANDICAP" else 2.5,
            bookmaker_id="book-1",
            capture_id="odds-capture",
            quote_identity_hash=quote_hash,
            model_input_hash="pre-bind-model-input",
            evaluated_at=evaluated_at,
            checkpoint=slot,
            capture_at=evaluated_at,
            model_probability=0.5,
            market_probability=0.5,
            expected_value=0.0,
            ev_se=0.01,
            decimal_odds=2.0,
            bookmaker_count=3,
            mainline_parsed=True,
            denominator_scope="CHECKPOINT_EVALUATION_OPPORTUNITY_V2",
        )
    )
    return bind_evaluation_opportunity(
        version,
        EvaluationOpportunityContext(
            model_forecast_capture_identity_hash=capture_hash,
            model_input_hash=f"model-{capture_hash}",
            evaluation_policy_version="candidate-eval.v1",
            evaluation_slot_id=slot,
            scheduled_checkpoint_at=evaluated_at,
            checkpoint_plan_identity=f"plan-{slot}",
            source_event_identity=source_event,
        ),
    )


def _opportunity_test_engine():
    from sqlalchemy import create_engine

    from w2.infrastructure.database import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _persist_tracks(engine, tracks: tuple[str, ...], *, retry: bool = False) -> None:
    from w2.prematch.repository import DynamicPrematchRepository

    repository = DynamicPrematchRepository(engine)
    for track in tracks:
        for slot in evaluation_slots():
            for market in ("ASIAN_HANDICAP", "TOTALS"):
                repository.append_evaluation(
                    _repository_evaluation(
                        fixture_id="1494246",
                        slot=slot,
                        market=market,
                        capture_hash=track,
                        source_event=f"event-{track}-{slot}",
                        quote_hash=f"quote-{track}-{slot}-{market}",
                    )
                )
    if retry:
        repository.append_evaluation(
            _repository_evaluation(
                fixture_id="1494246",
                slot="T15_ODDS",
                market="ASIAN_HANDICAP",
                capture_hash=tracks[0],
                source_event="event-retry",
                quote_hash="quote-retry",
            )
        )


def _repository_counts(engine) -> tuple[int, int, int]:
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from w2.infrastructure.persistence.dynamic_prematch_models import (
        DynamicPrematchEvaluationModel,
        DynamicPrematchOpportunityModel,
        DynamicPrematchSupersessionModel,
    )

    with Session(engine) as session:
        return (
            int(session.scalar(select(func.count()).select_from(DynamicPrematchOpportunityModel))),
            int(session.scalar(select(func.count()).select_from(DynamicPrematchEvaluationModel))),
            int(session.scalar(select(func.count()).select_from(DynamicPrematchSupersessionModel))),
        )


def test_repository_writes_five_slots_by_two_markets_as_ten_opportunities() -> None:
    engine = _opportunity_test_engine()
    _persist_tracks(engine, ("track-a",))
    assert _repository_counts(engine) == (10, 10, 0)


def test_repository_keeps_two_capture_tracks_as_twenty_opportunities() -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from w2.api.repository import _model_forecast_market_evaluation_funnel
    from w2.infrastructure.persistence.dynamic_prematch_models import (
        DynamicPrematchEvaluationModel,
        DynamicPrematchSupersessionModel,
    )

    engine = _opportunity_test_engine()
    _persist_tracks(engine, ("track-a", "track-b"))
    assert _repository_counts(engine) == (20, 20, 0)
    with Session(engine) as session:
        rows = list(session.scalars(select(DynamicPrematchEvaluationModel)))
        superseded = set(
            session.scalars(select(DynamicPrematchSupersessionModel.superseded_evaluation_id))
        )
    funnel = _model_forecast_market_evaluation_funnel(
        [SimpleNamespace(fixture_id="1494246")], rows, superseded
    )
    assert funnel["measurement_status"] == "MEASURABLE"
    assert funnel["opportunity_count"] == 20


def test_repository_does_not_merge_a_second_model_family_on_shared_quote() -> None:
    engine = _opportunity_test_engine()
    from w2.prematch.repository import DynamicPrematchRepository

    repository = DynamicPrematchRepository(engine)
    for track in ("exact-dc", "baseline-dc"):
        repository.append_evaluation(
            _repository_evaluation(
                fixture_id="1494246",
                slot="T15_ODDS",
                market="TOTALS",
                capture_hash=track,
                source_event=f"event-{track}",
                quote_hash="shared-quote",
            )
        )
    assert _repository_counts(engine) == (2, 2, 0)


def test_retry_keeps_twenty_opportunities_and_supersedes_one_of_twenty_one_attempts() -> None:
    engine = _opportunity_test_engine()
    _persist_tracks(engine, ("track-a", "track-b"), retry=True)
    assert _repository_counts(engine) == (20, 21, 1)


def test_ordinary_dynamic_row_cannot_supersede_official_attempt() -> None:
    from dataclasses import replace

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from w2.infrastructure.persistence.dynamic_prematch_models import (
        DynamicPrematchSupersessionModel,
    )
    from w2.prematch.repository import DynamicPrematchRepository

    engine = _opportunity_test_engine()
    official = _repository_evaluation(
        fixture_id="1494246",
        slot="T15_ODDS",
        market="TOTALS",
        capture_hash="track-a",
        source_event="official",
        quote_hash="quote-official",
    )
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(official)
    repository.append_evaluation(
        replace(
            official,
            evaluation_id="ordinary-eval",
            identity_hash="ordinary-identity",
            denominator_scope=None,
            measurement_semantics=None,
            official_funnel_eligible=None,
            evaluation_policy_version=None,
            evaluation_slot_id=None,
            model_forecast_capture_identity_hash=None,
            opportunity_identity_hash=None,
            attempt_identity_hash=None,
            scheduled_checkpoint_at=None,
            checkpoint_plan_identity=None,
            source_event_identity=None,
            opportunity_state=None,
        )
    )
    with Session(engine) as session:
        superseded = set(
            session.scalars(select(DynamicPrematchSupersessionModel.superseded_evaluation_id))
        )
    assert official.evaluation_id not in superseded


def test_writer_rejects_bad_slot_without_writing_and_reader_marks_direct_bad_row_invalid() -> None:
    from datetime import UTC, datetime

    from sqlalchemy.orm import Session

    from w2.api.repository import _model_forecast_market_evaluation_funnel
    from w2.infrastructure.persistence.dynamic_prematch_models import (
        DynamicPrematchEvaluationModel,
    )
    from w2.prematch.evaluation_slots import EvaluationSlotError

    engine = _opportunity_test_engine()
    with pytest.raises(EvaluationSlotError, match="NOT_REGISTERED"):
        _repository_evaluation(
            fixture_id="1494246",
            slot="T44_ODDS",
            market="TOTALS",
            capture_hash="track-a",
            source_event="bad-slot",
            quote_hash="bad-quote",
        )
    assert _repository_counts(engine) == (0, 0, 0)

    now = datetime(2026, 8, 18, 6, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            DynamicPrematchEvaluationModel(
                evaluation_id="bad-direct-row",
                identity_hash="bad-direct-identity",
                fixture_id="1494246",
                market="TOTALS",
                selection="OVER",
                checkpoint="T44_ODDS",
                evaluated_at=now,
                original_state="NO_EDGE_CURRENT",
                denominator_scope="CHECKPOINT_EVALUATION_OPPORTUNITY_V2",
                measurement_semantics="CHECKPOINT_EVALUATION_OPPORTUNITY",
                official_funnel_eligible=True,
                evaluation_policy_version="candidate-eval.v1",
                evaluation_slot_id="T44_ODDS",
                model_forecast_capture_identity_hash="track-a",
                payload={"state": "NO_EDGE_CURRENT"},
            )
        )
        session.commit()
        row = session.get(DynamicPrematchEvaluationModel, "bad-direct-row")
        assert row is not None
        funnel = _model_forecast_market_evaluation_funnel(
            [SimpleNamespace(fixture_id="1494246")], [row], set()
        )
    assert funnel["measurement_status"] == "INVALID"
    assert funnel["invalid_opportunity_reasons"] == {"SLOT_NOT_REGISTERED": 1}
