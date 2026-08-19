from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CandidateNotificationOutboxModel,
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayFixtureIdentityModel,
)
from w2.prematch.candidate_notifications import (
    CANDIDATE_FORMED,
    CANDIDATE_MATERIAL_CHANGE,
    CANDIDATE_T30_CONFIRMED,
    CANDIDATE_WITHDRAWN,
    DAY_CLOSEOUT_SUMMARY,
    DELIVERED,
    PLAN_SUMMARY,
    RETRY_PENDING,
    enqueue_operational_summaries,
    notification_health_in_session,
    record_delivery_result_in_session,
)
from w2.prematch.lifecycle import (
    CHECKPOINT_OPPORTUNITY_SCOPE,
    DynamicEvaluationInput,
    EvaluationOpportunityContext,
    OpportunityState,
    bind_evaluation_opportunity,
    classify_evaluation,
)
from w2.prematch.repository import DynamicPrematchRepository

NOW = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)


def _engine():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _context(slot: str, suffix: str) -> EvaluationOpportunityContext:
    return EvaluationOpportunityContext(
        model_forecast_capture_identity_hash="1" * 64,
        model_input_hash="2" * 64,
        evaluation_policy_version="candidate-eval.v1",
        evaluation_slot_id=slot,
        scheduled_checkpoint_at=NOW + timedelta(minutes=len(suffix)),
        checkpoint_plan_identity=f"plan-{suffix}",
        source_event_identity=f"event-{suffix}",
    )


def _attempt(
    slot: str,
    suffix: str,
    *,
    line: float = -0.25,
    odds: float = 1.91,
    ev: float = 0.06,
    market: str = "ASIAN_HANDICAP",
    depth: int = 7,
):  # type: ignore[no-untyped-def]
    version = classify_evaluation(
        DynamicEvaluationInput(
            fixture_id="1523202",
            market=market,
            selection="HOME_AH",
            exact_line=line,
            bookmaker_id="book-1",
            capture_id=f"capture-{suffix}",
            quote_identity_hash=(suffix * 64)[:64],
            model_input_hash="2" * 64,
            evaluated_at=NOW + timedelta(minutes=len(suffix)),
            checkpoint=slot,
            capture_at=NOW,
            model_probability=0.60,
            market_probability=0.50,
            expected_value=ev,
            ev_se=0.01,
            decimal_odds=odds,
            bookmaker_count=depth,
            mainline_parsed=True,
            denominator_scope=CHECKPOINT_OPPORTUNITY_SCOPE,
        )
    )
    return bind_evaluation_opportunity(version, _context(slot, suffix))


def _events(engine) -> list[CandidateNotificationOutboxModel]:  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        return list(
            session.scalars(
                select(CandidateNotificationOutboxModel).order_by(
                    CandidateNotificationOutboxModel.created_at,
                    CandidateNotificationOutboxModel.event_type,
                )
            )
        )


def test_attempt_events_are_transactional_idempotent_and_capture_transient_candidate() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)

    formed = _attempt("T3_ODDS", "a")
    repository.append_evaluation(formed)
    repository.append_evaluation(formed)
    repository.append_evaluation(_attempt("T60_ODDS_LINEUPS", "b"))
    repository.append_evaluation(_attempt("T45_ODDS", "c", ev=-0.01))

    events = _events(engine)
    assert [event.event_type for event in events] == [CANDIDATE_FORMED, CANDIDATE_WITHDRAWN]
    assert events[0].attempt_identity_hash == formed.attempt_identity_hash
    assert events[0].payload["decimal_odds"] == 1.91
    assert events[0].payload["signal_semantics"].startswith("EARLY_SHADOW")
    assert events[1].previous_state == "EVALUATED_CANDIDATE"
    assert events[1].current_state == "EVALUATED_NO_EDGE"


def test_material_change_and_t30_confirmation_are_distinct_events() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("T3_ODDS", "a"))
    repository.append_evaluation(_attempt("T60_ODDS_LINEUPS", "b", line=-0.5))
    repository.append_evaluation(_attempt("T-30m_VALIDATION_LOCK", "d", line=-0.5))

    events = _events(engine)
    assert [event.event_type for event in events] == [
        CANDIDATE_FORMED,
        CANDIDATE_MATERIAL_CHANGE,
        CANDIDATE_T30_CONFIRMED,
    ]
    assert events[1].payload["change"]["material_fields"] == ["exact_line"]
    assert events[2].payload["signal_semantics"] == "T30_VALIDATED_SHADOW_CANDIDATE"


def test_missed_closeout_withdrawal_uses_opportunity_identity_without_fake_attempt() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("T3_ODDS", "a"))
    context = _context("T60_ODDS_LINEUPS", "missed")

    assert repository.record_opportunity_without_attempt(
        fixture_id="1523202",
        market="ASIAN_HANDICAP",
        context=context,
        state=OpportunityState.MISSED_CHECKPOINT,
        recorded_at=NOW + timedelta(hours=2),
        blocker="CHECKPOINT_WINDOW_MISSED",
    )

    event = _events(engine)[-1]
    assert event.event_type == CANDIDATE_WITHDRAWN
    assert event.attempt_identity_hash is None
    assert event.current_state == "MISSED_CHECKPOINT"
    assert event.payload["source_kind"] == "OPPORTUNITY_CLOSEOUT_WITHOUT_ATTEMPT"


def test_delivery_health_keeps_failure_distinct_from_zero_candidates() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("T3_ODDS", "a"))
    event = _events(engine)[0]

    with Session(engine) as session:
        record_delivery_result_in_session(
            session,
            notification_event_id=event.notification_event_id,
            delivered=False,
            attempted_at=NOW + timedelta(seconds=10),
            error="channel timeout",
        )
        session.commit()
    assert _events(engine)[0].delivery_status == RETRY_PENDING

    with Session(engine) as session:
        record_delivery_result_in_session(
            session,
            notification_event_id=event.notification_event_id,
            delivered=True,
            attempted_at=NOW + timedelta(seconds=20),
        )
        session.commit()
        health = notification_health_in_session(session, now=NOW + timedelta(seconds=20))
    delivered = _events(engine)[0]
    assert delivered.delivery_status == DELIVERED
    assert delivered.delivery_attempt_count == 2
    assert health["retry_count"] == 1
    assert health["pending_backlog"] == 0


def test_outbox_write_rolls_back_with_evaluation_transaction(monkeypatch) -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)

    def fail(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("OUTBOX_WRITE_FAILED")

    monkeypatch.setattr("w2.prematch.candidate_notifications._insert", fail)
    try:
        repository.append_evaluation(_attempt("T3_ODDS", "a"))
    except RuntimeError as exc:
        assert str(exc) == "OUTBOX_WRITE_FAILED"
    else:
        raise AssertionError("transaction must fail closed")

    with Session(engine) as session:
        assert session.scalar(select(DynamicPrematchEvaluationModel)) is None
        assert session.scalar(select(DynamicPrematchOpportunityModel)) is None
        assert session.scalar(select(CandidateNotificationOutboxModel)) is None


def test_operational_summaries_use_football_day_and_split_zero_candidate_reasons() -> None:
    engine = _engine()
    kickoff = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id="api_football:1523202",
                provider="api_football",
                provider_fixture_id="1523202",
                competition_id="chinese_super_league",
                provider_league_id="169",
                season="2026",
                kickoff_utc=kickoff,
                fixture_status="NS",
                home_provider_team_id="1",
                away_provider_team_id="2",
                home_w2_team_id=None,
                away_w2_team_id=None,
                team_identity_status="PROVIDER_ONLY",
                raw_payload_sha256="3" * 64,
                endpoint_capture_id=None,
                captured_at=kickoff - timedelta(days=1),
                identity_hash="4" * 64,
                payload={"home_team_name": "上海海港", "away_team_name": "大连英博"},
            )
        )
        for checkpoint, scheduled, window_end in (
            ("T3_ODDS", kickoff - timedelta(hours=3), kickoff - timedelta(hours=2, minutes=55)),
            ("T15_ODDS", kickoff - timedelta(minutes=15), kickoff - timedelta(minutes=10)),
        ):
            session.add(
                MatchdayCheckpointPlanModel(
                    plan_id=f"plan-{checkpoint}",
                    fixture_id="api_football:1523202",
                    competition_id="chinese_super_league",
                    season="2026",
                    policy_version="w2.matchday_intake_policy.v2",
                    checkpoint=checkpoint,
                    kickoff_utc=kickoff,
                    scheduled_at=scheduled,
                    window_start=scheduled,
                    window_end=window_end,
                    endpoints=["odds"],
                    status="PLANNED",
                    attempt_count=0,
                    test_only=False,
                    blockers=[],
                    plan_hash=("5" if checkpoint == "T3_ODDS" else "6") * 64,
                )
            )
        session.commit()

    before_t3 = kickoff - timedelta(hours=3, minutes=10)
    inserted = enqueue_operational_summaries(now=before_t3, engine=engine)
    assert len(inserted) == 1
    assert _events(engine)[0].event_type == PLAN_SUMMARY
    assert _events(engine)[0].payload["summary_timing"] == "BEFORE_FIRST_T3"

    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("T3_ODDS", "a", depth=0))
    repository.append_evaluation(
        _attempt("T3_ODDS", "b", market="TOTALS", ev=-0.01)
    )
    inserted = enqueue_operational_summaries(
        now=kickoff - timedelta(minutes=10),
        engine=engine,
    )
    assert len(inserted) == 1
    closeout = next(event for event in _events(engine) if event.event_type == DAY_CLOSEOUT_SUMMARY)
    assert closeout.payload["candidate_count"] == 0
    assert closeout.payload["blocked_by_gate_count"] == 1
    assert closeout.payload["no_edge_count"] == 1
    assert (
        closeout.payload["zero_candidate_reason_by_market"]["ASIAN_HANDICAP"]["summary"]
        == "BLOCKED_BY_GATE:BOOKMAKER_DEPTH"
    )
    assert (
        closeout.payload["zero_candidate_reason_by_market"]["TOTALS"]["summary"]
        == "EVALUATED_NO_EDGE"
    )
