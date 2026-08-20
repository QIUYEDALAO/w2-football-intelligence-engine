from __future__ import annotations

import json
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
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.infrastructure.persistence.models import ResultModel
from w2.prematch import candidate_notifications
from w2.prematch.candidate_notifications import (
    CANDIDATE_FORMED,
    CANDIDATE_MATERIAL_CHANGE,
    CANDIDATE_T30_CONFIRMED,
    CANDIDATE_WITHDRAWN,
    DAY_CLOSEOUT_SUMMARY,
    DELIVERED,
    FAILED,
    PLAN_SUMMARY,
    RETRY_PENDING,
    deliver_pending_notifications,
    enqueue_operational_summaries,
    enqueue_test_message,
    notification_health_in_session,
    record_delivery_result_in_session,
    render_bark_message,
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

    event = next(
        row for row in _events(engine) if row.event_type == CANDIDATE_WITHDRAWN
    )
    assert event.event_type == CANDIDATE_WITHDRAWN
    assert event.attempt_identity_hash is None
    assert event.current_state == "MISSED_CHECKPOINT"
    assert event.payload["source_kind"] == "OPPORTUNITY_CLOSEOUT_WITHOUT_ATTEMPT"


def test_candidate_reformed_after_missed_closeout_is_not_silenced() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("T3_ODDS", "a"))
    context = _context("T-30m_VALIDATION_LOCK", "missed")
    repository.record_opportunity_without_attempt(
        fixture_id="1523202",
        market="ASIAN_HANDICAP",
        context=context,
        state=OpportunityState.MISSED_CHECKPOINT,
        recorded_at=NOW + timedelta(minutes=6),
        blocker="CHECKPOINT_WINDOW_MISSED",
    )

    repository.append_evaluation(_attempt("T15_ODDS", "laterlater"))

    events = _events(engine)
    assert sorted(event.event_type for event in events) == sorted(
        [
            CANDIDATE_FORMED,
            CANDIDATE_WITHDRAWN,
            CANDIDATE_MATERIAL_CHANGE,
        ]
    )
    reformed = next(event for event in events if event.event_type == CANDIDATE_MATERIAL_CHANGE)
    assert reformed.previous_state == "MISSED_CHECKPOINT"
    assert reformed.payload["reformed_after_state"] == "MISSED_CHECKPOINT"
    assert render_bark_message(reformed.payload)["title"].startswith("[恢复]")


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
        session.add(
            ModelForecastCaptureModel(
                capture_identity_hash="7" * 64,
                fixture_id="api_football:1523202",
                competition_id="chinese_super_league",
                kickoff_utc=kickoff,
                captured_at=kickoff - timedelta(hours=4),
                lead_time_seconds=4 * 60 * 60,
                lead_time_bucket="T3_PLUS",
                model_family="test",
                model_version="test.v1",
                capture_policy="FIRST_ELIGIBLE_FREEZE_IMMUTABLE",
                horizon_id="NONE",
                model_input_manifest_hash="8" * 64,
                four_field_xg_identity_hash="9" * 64,
                score_matrix_hash="a" * 64,
                payload={},
                payload_sha256="b" * 64,
                inserted_at=kickoff - timedelta(hours=4),
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

    plan_due = kickoff - timedelta(hours=2)
    inserted = enqueue_operational_summaries(now=plan_due, engine=engine)
    assert len(inserted) == 1
    assert _events(engine)[0].event_type == PLAN_SUMMARY
    assert _events(engine)[0].payload["summary_timing"] == "TWO_HOURS_BEFORE_FIRST_KICKOFF"
    assert _events(engine)[0].payload["candidate_track_fixture_count"] == 1
    assert _events(engine)[0].payload["candidate_track_matches"][0]["home"] == "上海海港"

    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("T3_ODDS", "a", depth=0))
    repository.append_evaluation(
        _attempt("T3_ODDS", "b", market="TOTALS", ev=-0.01)
    )
    result_confirmed_at = kickoff + timedelta(hours=2)
    with Session(engine) as session:
        session.add(
            ResultModel(
                id="result-1523202",
                fixture_id="api_football:1523202",
                home_goals=2,
                away_goals=1,
                result_status="FT",
                confirmed_at=result_confirmed_at,
                source_payload_sha256="c" * 64,
                source_capture_id=None,
                result_hash="d" * 64,
            )
        )
        session.commit()
    inserted = enqueue_operational_summaries(
        now=result_confirmed_at,
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


def test_bark_titles_are_executable_and_keep_fixture_deep_link() -> None:
    base = {
        "match": {"home": "上海海港", "away": "大连英博"},
        "kickoff_local": "2026-08-20T20:30:00+08:00",
        "market": "ASIAN_HANDICAP",
        "direction": "HOME_AH",
        "line": -0.5,
        "decimal_odds": 1.92,
        "current_ev": 0.069,
        "dashboard_url": "https://w2.example/?date=2026-08-20&fixture_id=1523202",
        "bookmaker": {"name": "Bet365"},
        "quote_captured_at": "2026-08-20T12:20:00Z",
        "quote_age_seconds": 60,
        "slot": "T60_ODDS_LINEUPS",
        "candidate_status": "EVALUATED_CANDIDATE",
        "valid_until": "2026-08-20T12:50:00Z",
        "next_review_at": "2026-08-20T12:45:00Z",
    }

    formed = render_bark_message({**base, "event_type": CANDIDATE_FORMED})
    assert formed["title"] == "[阵容] 上海海港 vs 大连英博 20:30 让球-0.5 主 @1.92"
    assert formed["url"].endswith("fixture_id=1523202")
    assert formed["url"] in formed["body"]

    changed = render_bark_message(
        {
            **base,
            "event_type": CANDIDATE_MATERIAL_CHANGE,
            "line": -0.75,
            "change": {
                "previous": {"exact_line": -0.5, "decimal_odds": 1.92},
                "current": {"exact_line": -0.75, "decimal_odds": 1.91},
            },
        }
    )
    assert changed["title"] == "[变盘] 上海海港 vs 大连英博 让球 -0.5 → -0.75"

    withdrawn = render_bark_message(
        {**base, "event_type": CANDIDATE_WITHDRAWN, "first_failed_gate": "QUOTE_FRESHNESS"}
    )
    assert withdrawn["title"] == "[撤回] 上海海港 vs 大连英博 让球 原因：报价过期"

    confirmed = render_bark_message({**base, "event_type": CANDIDATE_T30_CONFIRMED})
    assert confirmed["title"] == (
        "[确认] 上海海港 vs 大连英博 T-30m 锁定 让球-0.5 主 @1.92 EV+6.9%"
    )


def test_unconfigured_bark_keeps_outbox_pending(monkeypatch) -> None:
    engine = _engine()
    monkeypatch.delenv("W2_BARK_ENDPOINT", raising=False)
    monkeypatch.delenv("W2_BARK_DEVICE_KEY", raising=False)
    enqueue_test_message(request_id="unconfigured", created_at=NOW, engine=engine)

    result = deliver_pending_notifications(now=NOW, engine=engine)

    assert result["status"] == "CHANNEL_NOT_CONFIGURED"
    event = _events(engine)[0]
    assert event.delivery_status == "PENDING"
    assert event.delivery_attempt_count == 0
    with Session(engine) as session:
        health = notification_health_in_session(session, now=NOW)
    assert health["channel"] == "bark"
    assert health["delivery_mode"] == "AT_LEAST_ONCE"
    assert health["status"] == "CHANNEL_NOT_CONFIGURED"


def test_bark_retries_three_times_then_degrades_after_five_continuous_failures(
    monkeypatch,
) -> None:
    engine = _engine()
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "owner-device-test-key")
    enqueue_test_message(request_id="first", created_at=NOW, engine=engine)

    def fail(_payload):  # type: ignore[no-untyped-def]
        raise TimeoutError

    for offset in (0, 5, 15, 35):
        deliver_pending_notifications(
            now=NOW + timedelta(seconds=offset),
            engine=engine,
            sender=fail,
        )
    first = _events(engine)[0]
    assert first.delivery_status == FAILED
    assert first.delivery_attempt_count == 4

    enqueue_test_message(
        request_id="second",
        created_at=NOW + timedelta(seconds=40),
        engine=engine,
    )
    deliver_pending_notifications(
        now=NOW + timedelta(seconds=40),
        engine=engine,
        sender=fail,
    )
    with Session(engine) as session:
        health = notification_health_in_session(session, now=NOW + timedelta(seconds=40))
    assert health["consecutive_failure_count"] == 5
    assert health["status"] == "DEGRADED"


def test_successful_delivery_records_p95_latency_and_resets_failure_streak(
    monkeypatch,
) -> None:
    engine = _engine()
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "owner-device-test-key")
    enqueue_test_message(request_id="success", created_at=NOW, engine=engine)
    sent = []

    deliver_pending_notifications(
        now=NOW + timedelta(seconds=20),
        engine=engine,
        sender=sent.append,
    )

    assert len(sent) == 1
    with Session(engine) as session:
        health = notification_health_in_session(session, now=NOW + timedelta(seconds=20))
    assert health["status"] == "READY"
    assert health["delivery_latency_p95_seconds"] == 20
    assert health["consecutive_failure_count"] == 0


def test_bark_sender_posts_device_key_in_json_not_url(monkeypatch) -> None:
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "owner-device-test-key")
    observed = {}

    class Response:
        status = 200

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def read(self, _limit):  # type: ignore[no-untyped-def]
            return b'{"code":200}'

    def open_request(request, *, timeout):  # type: ignore[no-untyped-def]
        observed["url"] = request.full_url
        observed["json"] = json.loads(request.data)
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(candidate_notifications, "urlopen", open_request)
    candidate_notifications._send_bark(
        {
            "event_type": "TEST_MESSAGE",
            "dashboard_url": "https://w2.example/?fixture_id=1523202",
        }
    )

    assert observed["url"] == "https://api.day.app/push"
    assert "owner-device-test-key" not in observed["url"]
    assert observed["json"]["device_key"] == "owner-device-test-key"
    assert observed["json"]["group"] == "W2候选"
    assert observed["json"]["level"] == "timeSensitive"
    assert observed["json"]["url"].endswith("fixture_id=1523202")


def test_closeout_settles_candidate_direction_without_writing_settlement() -> None:
    engine = _engine()
    DynamicPrematchRepository(engine).append_evaluation(_attempt("T3_ODDS", "candidate"))
    result = ResultModel(
        id="result-candidate",
        fixture_id="api_football:1523202",
        home_goals=2,
        away_goals=1,
        result_status="FT",
        confirmed_at=NOW + timedelta(hours=4),
        source_payload_sha256="e" * 64,
        source_capture_id=None,
        result_hash="f" * 64,
    )
    with Session(engine) as session:
        session.add(result)
        session.commit()
        recommendations = candidate_notifications._closeout_recommendations(
            session,
            fixture_aliases={"1523202", "api_football:1523202"},
            results_by_fixture={"1523202": result},
        )

    assert len(recommendations) == 1
    assert recommendations[0]["direction"] == "HOME_AH"
    assert recommendations[0]["score"] == "2-1"
    assert recommendations[0]["settlement"] == "WIN"
