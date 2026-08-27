from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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
            # these tests are about notification transitions, so they declare a
            # validated calibration; the calibration gate has its own tests
            calibration_status="PRODUCTION_VALIDATED",
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

    event = next(row for row in _events(engine) if row.event_type == CANDIDATE_WITHDRAWN)
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
    repository.append_evaluation(_attempt("T3_ODDS", "b", market="TOTALS", ev=-0.01))
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
    assert formed["title"] == "[酝酿] 上海海港 vs 大连英博 20:30 让球-0.5 主 @1.92"
    assert formed["url"].endswith("fixture_id=1523202")
    assert formed["url"] not in formed["body"]
    assert "报价年龄：1 分 0 秒" in formed["body"]
    assert "状态：已形成候选" in formed["body"]
    assert formed["body"].count("2026-08-20T12:45:00Z") == 1
    assert "有效期" not in formed["body"]

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
        recommendations = candidate_notifications._closeout_recommendations(session)

    assert len(recommendations) == 1
    assert recommendations[0]["direction"] == "HOME_AH"
    assert recommendations[0]["score"] == "2-1"
    assert recommendations[0]["settlement"] == "WIN"
    assert recommendations[0]["profit_units"] == 0.91


def test_closeout_uses_last_real_evaluation_not_no_attempt_withdrawal() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("T-30m_VALIDATION_LOCK", "candidate"))
    repository.record_opportunity_without_attempt(
        fixture_id="1523202",
        market="ASIAN_HANDICAP",
        context=_context("T15_ODDS", "missed-later"),
        state=OpportunityState.MISSED_CHECKPOINT,
        recorded_at=NOW + timedelta(hours=2),
        blocker="CHECKPOINT_WINDOW_MISSED",
    )
    with Session(engine) as session:
        recommendations = candidate_notifications._closeout_recommendations(session)

    assert len(recommendations) == 1
    assert recommendations[0]["final_candidate_status"] == "EVALUATED_CANDIDATE"


def test_closeout_excludes_candidate_when_later_real_evaluation_is_no_edge() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("T-30m_VALIDATION_LOCK", "candidate"))
    repository.append_evaluation(_attempt("T15_ODDS", "later-no-edge", ev=-0.01))
    with Session(engine) as session:
        recommendations = candidate_notifications._closeout_recommendations(session)

    assert recommendations == []


def test_notification_names_use_reviewed_chinese_then_mark_unresolved_provider_id() -> None:
    identity = MatchdayFixtureIdentityModel(
        fixture_id="api_football:1570351",
        provider="api_football",
        provider_fixture_id="1570351",
        competition_id="la_liga",
        provider_league_id="140",
        season="2026",
        kickoff_utc=NOW,
        fixture_status="NS",
        home_provider_team_id="728",
        away_provider_team_id="542",
        home_w2_team_id="w2:team:api_football:728",
        away_w2_team_id="w2:team:api_football:542",
        team_identity_status="CANONICAL",
        raw_payload_sha256="1" * 64,
        endpoint_capture_id=None,
        captured_at=NOW,
        identity_hash="2" * 64,
        payload={
            "teams": {
                "home": {"name": "Rayo Vallecano"},
                "away": {"name": "Alaves"},
            }
        },
    )
    assert candidate_notifications._summary_fixture(identity)["home"] == "巴列卡诺"
    identity.home_w2_team_id = None
    identity.payload = {}
    assert candidate_notifications._summary_fixture(identity)["home"] == (
        "球队ID 728（身份未解析）"
    )


def test_closeout_waits_for_result_materialization_after_terminal_fixture() -> None:
    identity = SimpleNamespace(fixture_status="FT", captured_at=NOW)
    result = SimpleNamespace(confirmed_at=NOW + timedelta(seconds=2))

    assert candidate_notifications._fixture_closeout_time(identity, None) == (
        NOW + timedelta(seconds=candidate_notifications.CLOSEOUT_RESULT_GRACE_SECONDS)
    )
    assert candidate_notifications._fixture_closeout_time(identity, result) == (result.confirmed_at)


def test_closeout_copy_prioritizes_recommendations_and_marks_missing_result() -> None:
    rendered = render_bark_message(
        {
            "event_type": DAY_CLOSEOUT_SUMMARY,
            "operational_football_day": "2026-08-20",
            "daily_recommendation_count": 1,
            "daily_settled_count": 0,
            "daily_profit_units": 0,
            "cumulative_recommendation_count": 15,
            "cumulative_settled_count": 14,
            "cumulative_profit_units": 2.995,
            "recommendations": [
                {
                    "home": "巴列卡诺",
                    "away": "阿拉维斯",
                    "market": "TOTALS",
                    "line": 2.0,
                    "direction": "OVER",
                    "decimal_odds": 1.82,
                    "score": None,
                    "settlement": "RESULT_NOT_COLLECTED",
                    "profit_units": None,
                }
            ],
            "formal_opportunity_count": 10,
            "complete_evaluation_count": 8,
            "blocked_by_gate_count": 0,
            "evaluation_error_count": 0,
            "missed_checkpoint_count": 2,
            "no_edge_count": 4,
            "candidate_count": 4,
            "invalid_count": 0,
        }
    )
    assert rendered["body"].splitlines()[0] == "当日推荐 1 注；已结算 0 注；当日 0.000 单位"
    assert "巴列卡诺 vs 阿拉维斯 大小球2 大 @1.82：赛果未采集" in rendered["body"]
    assert "待结算" not in rendered["body"]
    assert rendered["body"].splitlines()[-1].startswith("漏斗审计：")


def test_notification_raw_values_are_humanized() -> None:
    assert candidate_notifications._format_duration(2024.05) == "33 分钟"
    assert candidate_notifications._format_duration(149.112) == "2 分 29 秒"
    assert candidate_notifications._opportunity_state_label("MISSED_CHECKPOINT") == "检查点错过"
    assert candidate_notifications._opportunity_state_label("EVALUATED_CANDIDATE") == "已形成候选"


def _routing_row(
    event_type: str,
    *,
    fixture_id: str = "1550092",
    market: str = "ASIAN_HANDICAP",
    created_at: datetime,
) -> SimpleNamespace:
    return SimpleNamespace(
        event_type=event_type,
        created_at=created_at,
        payload={"fixture_id": fixture_id, "market": market, "event_type": event_type},
    )


def test_only_actionable_events_reach_the_phone() -> None:
    lock_at = datetime(2026, 8, 22, 16, 7, tzinfo=UTC)
    confirmed = {("1550092", "ASIAN_HANDICAP"): lock_at}
    pushed: set[tuple[str, str]] = set()

    def route(event_type: str, *, offset_minutes: int) -> tuple[str, str]:
        return candidate_notifications.delivery_route(
            _routing_row(event_type, created_at=lock_at + timedelta(minutes=offset_minutes)),
            confirmed_at=confirmed,
            withdrawals_pushed=pushed,
        )

    # The lock is the recommendation and carries a 15 minute validity window.
    assert route(CANDIDATE_T30_CONFIRMED, offset_minutes=0)[0] == "SEND"
    # A candidate still forming hours out is information, not an interruption.
    assert route(CANDIDATE_FORMED, offset_minutes=-120) == (
        "DIGEST",
        "BREWING_NOT_TIME_CRITICAL",
    )
    # Nothing to act on yet, so a pre-lock change stays out of the push channel.
    assert route(CANDIDATE_MATERIAL_CHANGE, offset_minutes=-30) == (
        "SUPPRESS",
        "NO_LOCK_PUSHED_FOR_THIS_MARKET",
    )
    # After the lock the Owner is holding a position, so both matter.
    assert route(CANDIDATE_MATERIAL_CHANGE, offset_minutes=5)[0] == "SEND"
    assert route(CANDIDATE_WITHDRAWN, offset_minutes=5)[0] == "SEND"


def test_a_withdrawal_is_pushed_at_most_once_per_market() -> None:
    lock_at = datetime(2026, 8, 22, 16, 7, tzinfo=UTC)
    confirmed = {("1550092", "ASIAN_HANDICAP"): lock_at}
    pushed = {("1550092", "ASIAN_HANDICAP")}
    assert candidate_notifications.delivery_route(
        _routing_row(CANDIDATE_WITHDRAWN, created_at=lock_at + timedelta(minutes=20)),
        confirmed_at=confirmed,
        withdrawals_pushed=pushed,
    ) == ("SUPPRESS", "WITHDRAWAL_ALREADY_PUSHED")


def test_an_unrelated_market_on_a_locked_fixture_is_not_pushed() -> None:
    lock_at = datetime(2026, 8, 22, 16, 7, tzinfo=UTC)
    confirmed = {("1550092", "ASIAN_HANDICAP"): lock_at}
    route, reason = candidate_notifications.delivery_route(
        _routing_row(
            CANDIDATE_WITHDRAWN, market="TOTALS", created_at=lock_at + timedelta(minutes=5)
        ),
        confirmed_at=confirmed,
        withdrawals_pushed=set(),
    )
    assert (route, reason) == ("SUPPRESS", "NO_LOCK_PUSHED_FOR_THIS_MARKET")


def _lock_then_change(engine) -> None:  # type: ignore[no-untyped-def]
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("T3_ODDS", "a"))
    repository.append_evaluation(_attempt("T60_ODDS_LINEUPS", "bb", line=-0.5))
    repository.append_evaluation(_attempt("T-30m_VALIDATION_LOCK", "ddd", line=-0.5))
    repository.append_evaluation(_attempt("T15_ODDS", "eeee", line=-0.75))


def test_change_is_suppressed_when_the_lock_push_failed(monkeypatch) -> None:
    engine = _engine()
    _lock_then_change(engine)
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "owner-device-test-key")
    sent: list[str] = []

    def fail_lock(payload) -> None:  # type: ignore[no-untyped-def]
        sent.append(str(payload["event_type"]))
        if payload["event_type"] == CANDIDATE_T30_CONFIRMED:
            raise TimeoutError

    deliver_pending_notifications(now=NOW + timedelta(minutes=10), engine=engine, sender=fail_lock)

    assert sent == [CANDIDATE_T30_CONFIRMED]
    events = _events(engine)
    lock = next(row for row in events if row.event_type == CANDIDATE_T30_CONFIRMED)
    changes = [row for row in events if row.event_type == CANDIDATE_MATERIAL_CHANGE]
    assert lock.delivery_status == RETRY_PENDING
    assert changes[-1].delivery_status == candidate_notifications.SUPPRESSED


def test_successful_lock_unlocks_a_later_change_in_the_same_batch(monkeypatch) -> None:
    engine = _engine()
    _lock_then_change(engine)
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "owner-device-test-key")
    sent: list[dict[str, object]] = []

    deliver_pending_notifications(
        now=NOW + timedelta(minutes=10),
        engine=engine,
        sender=sent.append,
    )

    assert [payload["event_type"] for payload in sent] == [
        CANDIDATE_T30_CONFIRMED,
        CANDIDATE_MATERIAL_CHANGE,
    ]


def test_brewing_digest_waits_for_its_window_to_close() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    formed_at = datetime(2026, 8, 22, 16, 30, tzinfo=UTC)
    with Session(engine) as session:
        for index, market in enumerate(("ASIAN_HANDICAP", "TOTALS")):
            session.add(
                CandidateNotificationOutboxModel(
                    notification_event_id=f"formed-{index}",
                    opportunity_identity_hash=None,
                    attempt_identity_hash=None,
                    event_type=CANDIDATE_FORMED,
                    previous_state=None,
                    current_state="EVALUATED_CANDIDATE",
                    payload={
                        "fixture_id": "1550092",
                        "market": market,
                        "event_type": CANDIDATE_FORMED,
                        "match": {"home": "国际米兰", "away": "蒙扎"},
                        "kickoff_local": "2026-08-23T00:30:00+08:00",
                        "line": 2.0,
                        "direction": "AWAY",
                        "decimal_odds": 1.92,
                    },
                    created_at=formed_at,
                    delivered_at=None,
                    delivery_status=candidate_notifications.DIGEST_PENDING,
                    delivery_attempt_count=0,
                    last_error=None,
                )
            )
        session.commit()

        # Still inside the window the candidates formed in: nothing is emitted,
        # so an early candidate waits for the rest of its window.
        assert (
            candidate_notifications.enqueue_brewing_digest_in_session(
                session, now=formed_at + timedelta(minutes=30)
            )
            == []
        )

        emitted = candidate_notifications.enqueue_brewing_digest_in_session(
            session, now=formed_at + timedelta(hours=2)
        )
        session.commit()
        assert len(emitted) == 1

        digest = session.get(CandidateNotificationOutboxModel, emitted[0])
        assert digest is not None
        # Both markets of one fixture arrive as a single line, not two pushes.
        assert digest.payload["fixture_count"] == 1
        assert digest.payload["candidate_count"] == 2
        assert all(
            session.get(CandidateNotificationOutboxModel, f"formed-{index}").delivery_status
            == candidate_notifications.DIGESTED
            for index in range(2)
        )

        rendered = candidate_notifications.render_bark_message(digest.payload)
        assert rendered["title"] == "[酝酿] 1 场 2 个候选"
        assert "国际米兰 vs 蒙扎" in rendered["body"]

        # A second call in the same window must not re-emit the digest.
        assert (
            candidate_notifications.enqueue_brewing_digest_in_session(
                session, now=formed_at + timedelta(hours=2, minutes=10)
            )
            == []
        )
