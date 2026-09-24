from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.api.repository import _apply_repository_v4_authority
from w2.dashboard.day_view import build_dashboard_day_view
from w2.domain.recommendation_decision_v4 import build_recommendation_decision_v4
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CandidateNotificationOutboxModel,
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
)
from w2.infrastructure.persistence.league_models import LeagueSeasonModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.infrastructure.persistence.models import ResultModel
from w2.prematch import candidate_notifications
from w2.prematch.candidate_notifications import (
    DELIVERED,
    FAILED,
    RETRY_PENDING,
    deliver_pending_notifications,
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
    selection: str = "HOME_AH",
):  # type: ignore[no-untyped-def]
    version = classify_evaluation(
        DynamicEvaluationInput(
            fixture_id="1523202",
            market=market,
            selection=selection,
            exact_line=line,
            bookmaker_id="book-1",
            capture_id=f"capture-{suffix}",
            quote_identity_hash=hashlib.sha256(suffix.encode()).hexdigest(),
            model_input_hash="2" * 64,
            evaluated_at=NOW + timedelta(minutes=len(suffix)),
            checkpoint=slot,
            capture_at=NOW,
            model_probability=0.60,
            market_probability=0.50,
            expected_value=ev,
            cashflow_price_edge=0.10,
            ev_se=0.01,
            decimal_odds=odds,
            bookmaker_count=depth,
            mainline_parsed=True,
            # these tests are about notification transitions, so they declare a
            # validated calibration; the calibration gate has its own tests
            calibration_status="PRODUCTION_VALIDATED",
            denominator_scope=CHECKPOINT_OPPORTUNITY_SCOPE,
            # likewise the factor gate: ASIAN_HANDICAP candidacy now also needs
            # an admitted, direction consistent factor verdict
            factor_decision_status="ADMITTED",
            factor_direction="HOME",
            factor_input_identity="f" * 64,
            factor_input_identity_hash="f" * 64,
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


def _v4(version):  # type: ignore[no-untyped-def]
    if version.opportunity_state is not OpportunityState.EVALUATED_CANDIDATE:
        return build_recommendation_decision_v4(
            {
                "fixture_id": version.fixture_id,
                "competition_id": "chinese_super_league",
                "kickoff_utc": "2026-08-21T12:00:00Z",
            }
        ).as_dict()
    odds = Decimal(str(version.decimal_odds))
    return build_recommendation_decision_v4(
        {
            "fixture_id": version.fixture_id,
            "competition_id": "chinese_super_league",
            "season": "2026",
            "kickoff_utc": "2026-08-21T12:00:00Z",
            "kickoff_revision_or_fixture_identity_hash": "d" * 64,
            "provider": "api-football",
            "bookmaker_id": version.bookmaker_id,
            "market": version.market,
            "selection": str(version.selection).removesuffix("_AH"),
            "exact_line": str(version.exact_line),
            "capture_id": version.capture_id,
            "captured_at": version.capture_at.isoformat(),
            "decision_evaluated_at": version.evaluated_at.isoformat(),
            "quote_observation_ids": {"home": "obs-home", "away": "obs-away"},
            "raw_payload_sha256": "a" * 64,
            "source_revision": "e" * 40,
            "model_version": "model-v1",
            "calibration_version": "calibration-v1",
            "serializer_version": "w2.canonical-json.v2",
            "recommendation_schema_version": "w2.recommendation_decision.v4",
            "quote_schema_version": "w2.quote_identity.v1",
            "model_input_manifest_hash": "b" * 64,
            "decimal_odds": str(odds),
            "canonical_mainline_identity": {
                "market": version.market,
                "line": str(version.exact_line),
                "selected_side_line": str(version.exact_line),
                "candidate_role": "MARKET_MAINLINE",
                "quote_identity_hash": version.quote_identity_hash,
            },
            "settlement_distribution": {
                "WIN": "0.6",
                "HALF_WIN": "0",
                "PUSH": "0",
                "HALF_LOSS": "0",
                "LOSS": "0.4",
            },
            "fair_odds": "1.6666666667",
            "expected_value": str(odds * Decimal("0.6") - 1),
            "uncertainty": "0.01",
            "readiness": {
                "status": "READY",
                "quote_identity_status": "COMPLETE",
                "quote_freshness_status": "COMPLETE",
                "quote_freshness_policy_version": "w2.quote_freshness.v1",
                "quote_age_seconds": 60,
                "quote_max_age_seconds": 1800,
                "model_status": "READY",
            },
            "capability_status": "ANALYSIS_ONLY",
            "formal_admission": {
                "status": "DISABLED",
                "readiness_hash": None,
                "approval_hash": None,
                "candidate_identity_hash": None,
            },
            "model_probability": "0.6",
            "market_probability": "0.5",
            "probability_delta_diagnostic": "0.1",
        }
    ).as_dict()


def _append(repository: DynamicPrematchRepository, version):  # type: ignore[no-untyped-def]
    return repository.append_evaluation(
        version,
        recommendation_decision_v4=_v4(version),
    )


def _materialize_validation_samples(engine, *, now: datetime | None = None) -> None:
    """物化 validation_samples 表（PERF-01 阶段2：读取路径读表前的测试辅助）。"""
    from w2.prematch.candidate_notifications import materialize_validation_samples

    with Session(engine) as session:
        materialize_validation_samples(
            session,
            now=now or NOW,
            window_before_days=3650,
            window_after_days=3650,
        )
        session.commit()


def test_same_frozen_v4_pick_reaches_api_dashboard_and_notification() -> None:
    engine = _engine()
    attempt = _attempt("T15_ODDS", "three-exits", line=-0.5, odds=1.95)
    decision = _v4(attempt)

    api_card = _apply_repository_v4_authority(
        {
            "fixture_id": attempt.fixture_id,
            "competition_id": "chinese_super_league",
            "kickoff_utc": "2026-08-21T12:00:00Z",
            "recommendation_decision_v4": deepcopy(decision),
        }
    )
    legacy_contract = {
        "decision_tier": "WATCH",
        "data_status": "PARTIAL",
        "lifecycle_status": "DRAFT",
        "outcome_tracked": False,
        "lock_eligible": False,
        "recommendation_id": None,
        "lineup_requirement": "ADVISORY",
        "risk_reason_codes": ["LINEUP_UNOBSERVABLE"],
        "pick": None,
        "non_pick": {
            "reason_code": "LEGACY_WATCH",
            "reason_human": "legacy",
            "action": "wait",
            "next_eval_at": None,
        },
    }
    dashboard = build_dashboard_day_view(
        {
            "generated_at": NOW.isoformat(),
            "date": "2026-08-20",
            "selected_football_day": "2026-08-20",
            "all": [
                {
                    "fixture_id": attempt.fixture_id,
                    "competition_id": "chinese_super_league",
                    "kickoff_utc": "2026-08-21T12:00:00Z",
                    "decision_contract": legacy_contract,
                    "recommendation_decision_v4": deepcopy(decision),
                }
            ],
        },
        environment="staging",
    )["cards"][0]
    _append(DynamicPrematchRepository(engine), attempt)
    notification = _events(engine)[0].payload

    assert api_card["decision_tier"] == dashboard["decision_tier"] == "ANALYSIS_PICK"
    assert (
        api_card["pick"]["market"],
        api_card["pick"]["selection"],
        api_card["pick"]["line"],
        api_card["pick"]["odds"],
    ) == (
        dashboard["pick"]["market"],
        dashboard["pick"]["selection"],
        dashboard["pick"]["line"],
        dashboard["pick"]["odds"],
    )
    assert notification["market"] == api_card["pick"]["market"]
    assert (
        str(notification["direction"]).removesuffix("_AH")
        == api_card["pick"]["selection"]
    )
    assert float(notification["line"]) == float(api_card["pick"]["line"])
    assert float(notification["decimal_odds"]) == float(api_card["pick"]["odds"])



def test_delivery_health_keeps_failure_distinct_from_zero_candidates() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    _append(repository, _attempt("T15_ODDS", "a"))
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
        _append(repository, _attempt("T15_ODDS", "a"))
    except RuntimeError as exc:
        assert str(exc) == "OUTBOX_WRITE_FAILED"
    else:
        raise AssertionError("transaction must fail closed")

    with Session(engine) as session:
        assert session.scalar(select(DynamicPrematchEvaluationModel)) is None
        assert session.scalar(select(DynamicPrematchOpportunityModel)) is None
        assert session.scalar(select(CandidateNotificationOutboxModel)) is None


def test_non_t15_attempts_do_not_enqueue_push_events() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)

    _append(repository, _attempt("T3_ODDS", "early"))
    _append(repository, _attempt("T-30m_VALIDATION_LOCK", "lock"))

    assert _events(engine) == []


def test_v4_attempt_identity_guard_still_rolls_back_evaluation() -> None:
    engine = _engine()
    version = _attempt("T3_ODDS", "mismatch", line=-0.5)
    decision = _v4(_attempt("T3_ODDS", "different", line=-0.25))

    with pytest.raises(ValueError, match="CANDIDATE_NOTIFICATION_V4_ATTEMPT_IDENTITY_MISMATCH"):
        DynamicPrematchRepository(engine).append_evaluation(
            version, recommendation_decision_v4=decision
        )

    with Session(engine) as session:
        assert session.scalar(select(DynamicPrematchEvaluationModel)) is None


def test_retired_events_are_suppressed_and_excluded_from_health(monkeypatch) -> None:
    engine = _engine()
    retired = (
        "CANDIDATE_FORMED",
        "CANDIDATE_MATERIAL_CHANGE",
        "CANDIDATE_WITHDRAWN",
        "CANDIDATE_T30_CONFIRMED",
        "PREMATCH_PLAN_SUMMARY",
        "FOOTBALL_DAY_CLOSEOUT_SUMMARY",
        "CANDIDATE_BREWING_DIGEST",
    )
    with Session(engine) as session:
        for index, event_type in enumerate(retired):
            session.add(
                CandidateNotificationOutboxModel(
                    notification_event_id=f"retired-{index}",
                    opportunity_identity_hash=None,
                    attempt_identity_hash=None,
                    event_type=event_type,
                    previous_state=None,
                    current_state="HISTORICAL",
                    payload={"event_type": event_type},
                    created_at=NOW,
                    delivered_at=None,
                    delivery_status="PENDING",
                    delivery_attempt_count=0,
                    last_error=None,
                )
            )
        session.commit()
        health = notification_health_in_session(session, now=NOW)
    assert health["outbox_event_count"] == 0

    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "owner-device-test-key")
    sent: list[Mapping[str, object]] = []
    result = deliver_pending_notifications(now=NOW, engine=engine, sender=sent.append)
    assert result["delivered"] == 0
    assert result["suppressed"] == len(retired)
    assert sent == []
    assert all(row.delivery_status == candidate_notifications.SUPPRESSED for row in _events(engine))

    for event_type in retired:
        with pytest.raises(ValueError, match="NOTIFICATION_EVENT_TYPE_RETIRED"):
            render_bark_message({"event_type": event_type})


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


def test_bark_configuration_parses_multiple_trimmed_device_keys(monkeypatch) -> None:
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", " first-key , second-key ")
    assert candidate_notifications._bark_configuration() == (["first-key", "second-key"], None)

    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "first-key, ,second-key")
    assert candidate_notifications._bark_configuration() == ([], "BARK_DEVICE_KEY_INVALID")


def test_bark_single_key_keeps_original_failure_code(monkeypatch) -> None:
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "single-key")

    class Response:
        status = 200

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def read(self, _limit: int) -> bytes:
            return b'{"code":500}'

    monkeypatch.setattr(candidate_notifications, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(RuntimeError, match="^BARK_REJECTED$"):
        candidate_notifications._send_bark({"event_type": candidate_notifications.TEST_MESSAGE})


def test_bark_partial_failure_attempts_every_device_and_records_outbox_error(monkeypatch) -> None:
    engine = _engine()
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", " first-key, broken-key, last-key ")
    attempted: list[str] = []
    broken = {"value": True}

    class Response:
        status = 200

        def __init__(self, code: int) -> None:
            self.code = code

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def read(self, _limit: int) -> bytes:
            return json.dumps({"code": self.code}).encode()

    def open_request(request, *, timeout):  # type: ignore[no-untyped-def]
        assert timeout == candidate_notifications.DELIVERY_TIMEOUT_SECONDS
        key = json.loads(request.data)["device_key"]
        attempted.append(key)
        return Response(500 if broken["value"] and key == "broken-key" else 200)

    monkeypatch.setattr(candidate_notifications, "urlopen", open_request)
    enqueue_test_message(request_id="multi-device", created_at=NOW, engine=engine)

    result = deliver_pending_notifications(now=NOW, engine=engine)

    assert attempted == ["first-key", "broken-key", "last-key"]
    assert result["delivered"] == 0
    assert result["failed_attempts"] == 1
    event = _events(engine)[0]
    assert event.delivery_status == RETRY_PENDING
    assert event.last_error.startswith("BARK_DEVICE_DELIVERY_FAILED:1/3:BARK_REJECTED")
    assert all(key not in event.last_error for key in attempted)

    broken["value"] = False
    attempted.clear()
    retry = deliver_pending_notifications(now=NOW + timedelta(seconds=5), engine=engine)
    assert retry["delivered"] == 1
    assert attempted == ["broken-key"]


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


def _lock_then_change(engine) -> None:  # type: ignore[no-untyped-def]
    repository = DynamicPrematchRepository(engine)
    _append(repository, _attempt("T3_ODDS", "a"))
    _append(repository, _attempt("T60_ODDS_LINEUPS", "bb", line=-0.5))
    _append(repository, _attempt("T-30m_VALIDATION_LOCK", "ddd", line=-0.5))
    _append(repository, _attempt("T15_ODDS", "eeee", line=-0.75))


def _insert_enabled_competition(
    session: Session, competition_id: str = "chinese_super_league"
) -> None:
    session.add(
        LeagueSeasonModel(
            competition_id=competition_id,
            season="2026",
            lifecycle="ACTIVE",
            payload={"enabled": True},
        )
    )


def _insert_fixture_identity(
    session: Session, *, fixture_id: str = "1523202", kickoff_utc: datetime
) -> None:
    session.add(
        MatchdayFixtureIdentityModel(
            fixture_id=f"api_football:{fixture_id}",
            provider="api_football",
            provider_fixture_id=fixture_id,
            competition_id="chinese_super_league",
            provider_league_id="169",
            season="2026",
            kickoff_utc=kickoff_utc,
            fixture_status="NS",
            home_provider_team_id="1",
            away_provider_team_id="2",
            home_w2_team_id=None,
            away_w2_team_id=None,
            team_identity_status="PROVIDER_ONLY",
            raw_payload_sha256="3" * 64,
            endpoint_capture_id=None,
            captured_at=kickoff_utc - timedelta(days=1),
            identity_hash="4" * 64,
            payload={"home_team_name": "上海海港", "away_team_name": "大连英博"},
        )
    )


def _insert_model_track(
    session: Session, *, fixture_id: str = "1523202", kickoff_utc: datetime
) -> None:
    session.add(
        ModelForecastCaptureModel(
            capture_identity_hash="7" * 64,
            fixture_id=f"api_football:{fixture_id}",
            competition_id="chinese_super_league",
            kickoff_utc=kickoff_utc,
            captured_at=kickoff_utc - timedelta(hours=4),
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
            inserted_at=kickoff_utc - timedelta(hours=4),
        )
    )


def _insert_t3_plan(
    session: Session, *, fixture_id: str = "1523202", scheduled_at: datetime
) -> None:
    session.add(
        MatchdayCheckpointPlanModel(
            plan_id="plan-T3",
            fixture_id=f"api_football:{fixture_id}",
            competition_id="chinese_super_league",
            season="2026",
            policy_version="w2.matchday_intake_policy.v2",
            checkpoint="T3_ODDS",
            kickoff_utc=scheduled_at + timedelta(hours=3),
            scheduled_at=scheduled_at,
            window_start=scheduled_at,
            window_end=scheduled_at + timedelta(minutes=5),
            endpoints=["odds"],
            status="PLANNED",
            attempt_count=0,
            test_only=False,
            blockers=[],
            plan_hash="5" * 64,
        )
    )


def _due_at_for_kickoff(kickoff_utc: datetime, day: date) -> datetime:
    engine = _engine()
    with Session(engine) as session:
        _insert_fixture_identity(session, kickoff_utc=kickoff_utc)
        _insert_model_track(session, kickoff_utc=kickoff_utc)
        # SQLite stores datetimes naive; persist the T3 plan time in UTC so the
        # timezone-aware logic reads back the wall clock it meant to schedule.
        _insert_t3_plan(
            session, scheduled_at=kickoff_utc.astimezone(UTC) - timedelta(hours=3)
        )
        session.commit()
        return candidate_notifications._daily_candidate_list_due_at(
            session, day=day, candidate_fixture_ids={"1523202"}
        )


def test_daily_candidate_list_due_time_rules() -> None:
    beijing = candidate_notifications.BEIJING
    day = date(2026, 8, 20)
    default_due = datetime.combine(day, time(14, 0), tzinfo=beijing).astimezone(UTC)

    # 首场北京 01:00（次日凌晨）→ T3 当日 22:00，不早于 14:30 → 14:00
    assert _due_at_for_kickoff(datetime(2026, 8, 21, 1, 0, tzinfo=beijing), day) == default_due
    # 首场北京 16:30 → T3 13:30，早于 14:30 → 提前到 13:00
    assert _due_at_for_kickoff(datetime(2026, 8, 20, 16, 30, tzinfo=beijing), day) == (
        datetime(2026, 8, 20, 13, 30, tzinfo=beijing) - timedelta(minutes=30)
    ).astimezone(UTC)


def test_daily_candidate_list_no_fixtures_defaults_to_14() -> None:
    engine = _engine()
    day = date(2026, 8, 20)
    with Session(engine) as session:
        due = candidate_notifications._daily_candidate_list_due_at(
            session, day=day, candidate_fixture_ids=set()
        )
    assert due == datetime.combine(
        day, time(14, 0), tzinfo=candidate_notifications.BEIJING
    ).astimezone(UTC)


def test_daily_candidate_list_enqueues_and_renders_n0() -> None:
    engine = _engine()
    day = date(2026, 8, 20)
    # 14:00 on the football day: no candidate fixtures → N=0 message.
    now = datetime.combine(day, time(14, 0), tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        event_id = candidate_notifications.enqueue_daily_candidate_list_in_session(
            session, now=now
        )
        assert event_id is not None
        event = session.get(CandidateNotificationOutboxModel, event_id)
        assert event.payload["match_count"] == 0
        rendered = render_bark_message(event.payload)
        assert rendered["title"] == "[今日候选] 8月20日 共 0 场待评估"
        session.commit()

    # Idempotent: a second call in the same day does not re-enqueue.
    with Session(engine) as session:
        assert (
            candidate_notifications.enqueue_daily_candidate_list_in_session(session, now=now)
            is None
        )


def test_validation_sample_confirmed_only_when_final_state_is_candidate() -> None:
    # T3 candidate, T15 no-edge → final is NO_EDGE → 不推
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    _append(repository, _attempt("T3_ODDS", "a"))
    _append(repository, _attempt("T15_ODDS", "b", ev=-0.01))
    assert not any(
        event.event_type == candidate_notifications.VALIDATION_SAMPLE_CONFIRMED
        for event in _events(engine)
    )

    # T3 no-edge, T15 candidate → final is CANDIDATE → 推
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    _append(repository, _attempt("T3_ODDS", "a", ev=-0.01))
    _append(repository, _attempt("T15_ODDS", "b"))
    confirmed = [
        event
        for event in _events(engine)
        if event.event_type == candidate_notifications.VALIDATION_SAMPLE_CONFIRMED
    ]
    assert len(confirmed) == 1
    assert confirmed[0].payload["decimal_odds"] == 1.91
    assert confirmed[0].payload["market"] == "ASIAN_HANDICAP"


def test_validation_sample_confirmed_is_idempotent() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    _append(repository, _attempt("T3_ODDS", "a", ev=-0.01))
    _append(repository, _attempt("T15_ODDS", "b"))  # triggers ②
    confirmed = [
        event
        for event in _events(engine)
        if event.event_type == candidate_notifications.VALIDATION_SAMPLE_CONFIRMED
    ]
    assert len(confirmed) == 1

    # A manual re-enqueue is a no-op (per fixture x market).
    with Session(engine) as session:
        assert (
            candidate_notifications.enqueue_validation_sample_confirmed_in_session(
                session, fixture_id="1523202", market="ASIAN_HANDICAP", now=NOW
            )
            is None
        )
        session.commit()
    assert (
        len(
            [
                event
                for event in _events(engine)
                if event.event_type == candidate_notifications.VALIDATION_SAMPLE_CONFIRMED
            ]
        )
        == 1
    )


def test_validation_sample_fallback_uses_last_real_evaluation_at_kickoff_minus_5() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    kickoff = NOW + timedelta(hours=2)
    with Session(engine) as session:
        _insert_enabled_competition(session)
        _insert_fixture_identity(session, kickoff_utc=kickoff)
        session.commit()
    _append(repository, _attempt("T3_ODDS", "a"))  # last real evaluation is a candidate
    repository.record_opportunity_without_attempt(
        fixture_id="1523202",
        market="ASIAN_HANDICAP",
        context=_context("T15_ODDS", "missed"),
        state=OpportunityState.MISSED_CHECKPOINT,
        recorded_at=kickoff - timedelta(minutes=10),
        blocker="CHECKPOINT_WINDOW_MISSED",
    )

    # Before kickoff-5min, nothing is emitted.
    with Session(engine) as session:
        assert (
            candidate_notifications.enqueue_validation_sample_fallbacks_in_session(
                session, now=kickoff - timedelta(minutes=10)
            )
            == []
        )
    # At kickoff-5min the last real evaluation confirms the sample.
    with Session(engine) as session:
        inserted = candidate_notifications.enqueue_validation_sample_fallbacks_in_session(
            session, now=kickoff - timedelta(minutes=5)
        )
        assert len(inserted) == 1
        session.commit()
    confirmed = next(
        event
        for event in _events(engine)
        if event.event_type == candidate_notifications.VALIDATION_SAMPLE_CONFIRMED
    )
    assert confirmed.payload["decimal_odds"] == 1.91


def test_worker_heavy_push_schedule_runs_validation_sample_fallback(monkeypatch) -> None:
    # RESULT-STUCK：CAP-MISS 之后推送排程移到 worker-heavy 的
    # w2.candidate_notification_schedule 任务；确认该入口 enqueue_scheduled_notifications
    # 仍然会触发 ② fallback（T15 缺评估时按最后一次真实评估推送），而不是被重构遗漏。
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    kickoff = NOW + timedelta(hours=2)
    with Session(engine) as session:
        _insert_enabled_competition(session)
        _insert_fixture_identity(session, kickoff_utc=kickoff)
        session.commit()
    _append(repository, _attempt("T3_ODDS", "a"))  # last real evaluation is a candidate
    repository.record_opportunity_without_attempt(
        fixture_id="1523202",
        market="ASIAN_HANDICAP",
        context=_context("T15_ODDS", "missed"),
        state=OpportunityState.MISSED_CHECKPOINT,
        recorded_at=kickoff - timedelta(minutes=10),
        blocker="CHECKPOINT_WINDOW_MISSED",
    )

    # 隔离 ① ③，只验证排程入口对 ② fallback 的调用链。
    monkeypatch.setattr(
        candidate_notifications,
        "enqueue_daily_candidate_list_in_session",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        candidate_notifications,
        "enqueue_daily_settlement_in_session",
        lambda *args, **kwargs: None,
    )

    inserted = candidate_notifications.enqueue_scheduled_notifications(
        now=kickoff - timedelta(minutes=5), engine=engine
    )
    assert inserted
    assert any(
        event.event_type == candidate_notifications.VALIDATION_SAMPLE_CONFIRMED
        for event in _events(engine)
    )


def test_daily_settlement_settles_and_marks_pending() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    # kickoff in football day 8/19 window: [8/19 12:00, 8/20 12:00) Beijing
    kickoff = datetime(2026, 8, 19, 20, 0, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        _insert_enabled_competition(session)
        _insert_fixture_identity(session, kickoff_utc=kickoff)
        session.commit()
    _append(repository, _attempt("T3_ODDS", "a", selection="HOME"))
    _materialize_validation_samples(engine, now=NOW)

    # Before Beijing 12:00, nothing is emitted.
    before = datetime(2026, 8, 20, 11, 0, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        assert (
            candidate_notifications.enqueue_daily_settlement_in_session(session, now=before) is None
        )

    # No result yet → 待结算.
    now = datetime(2026, 8, 20, 12, 0, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        event_id = candidate_notifications.enqueue_daily_settlement_in_session(session, now=now)
        assert event_id is not None
        event = session.get(CandidateNotificationOutboxModel, event_id)
        assert event.payload["item_count"] == 1
        assert event.payload["items"][0]["competition"] == "中超"
        assert event.payload["items"][0]["profit_units"] is None
        assert event.payload["pending"] == [
            {"fixture_id": "1523202", "market": "ASIAN_HANDICAP"}
        ]
        assert event.payload["total_profit_units"] == 0.0
        session.commit()

    # Add the result, then the next day's settlement carries it as 补结算.
    with Session(engine) as session:
        session.add(
            ResultModel(
                id="result-1523202",
                fixture_id="api_football:1523202",
                home_goals=2,
                away_goals=1,
                result_status="FT",
                confirmed_at=kickoff + timedelta(hours=2),
                source_payload_sha256="c" * 64,
                source_capture_id=None,
                result_hash="d" * 64,
            )
        )
        session.commit()
    _materialize_validation_samples(engine, now=NOW)  # 重新物化，反映新 result 的结算

    next_day = datetime(2026, 8, 21, 12, 0, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        event_id = candidate_notifications.enqueue_daily_settlement_in_session(
            session, now=next_day
        )
        assert event_id is not None
        event = session.get(CandidateNotificationOutboxModel, event_id)
        assert event.payload["item_count"] == 1
        item = event.payload["items"][0]
        assert item["supplementary"] is True
        assert item["settlement"] == "WIN"
        assert item["profit_units"] == 0.91
        assert event.payload["win_count"] == 1
        assert event.payload["total_profit_units"] == 0.91
        session.commit()


def test_daily_settlement_triggers_at_1130() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    kickoff = datetime(2026, 8, 19, 20, 0, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        _insert_enabled_competition(session)
        _insert_fixture_identity(session, kickoff_utc=kickoff)
        session.commit()
    _append(repository, _attempt("T3_ODDS", "a"))

    before = datetime(2026, 8, 20, 11, 29, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        assert (
            candidate_notifications.enqueue_daily_settlement_in_session(session, now=before)
            is None
        )
    at = datetime(2026, 8, 20, 11, 30, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        assert (
            candidate_notifications.enqueue_daily_settlement_in_session(session, now=at)
            is not None
        )
        session.commit()


def test_daily_settlement_zero_note_day() -> None:
    engine = _engine()
    at = datetime(2026, 8, 20, 11, 30, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        event_id = candidate_notifications.enqueue_daily_settlement_in_session(session, now=at)
        assert event_id is not None
        event = session.get(CandidateNotificationOutboxModel, event_id)
        rendered = render_bark_message(event.payload)
        assert rendered["title"] == "[结算] 8月19日 当天无推荐"
        assert "累计：0 注 +0.00 单位" in rendered["body"]
        session.commit()


def test_validation_sample_fallback_skips_out_of_day_samples() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    old_kickoff = NOW - timedelta(days=3)
    with Session(engine) as session:
        _insert_enabled_competition(session)
        _insert_fixture_identity(session, kickoff_utc=old_kickoff)
        session.commit()
    _append(repository, _attempt("T3_ODDS", "a"))
    repository.record_opportunity_without_attempt(
        fixture_id="1523202",
        market="ASIAN_HANDICAP",
        context=_context("T15_ODDS", "missed"),
        state=OpportunityState.MISSED_CHECKPOINT,
        recorded_at=old_kickoff - timedelta(minutes=10),
        blocker="CHECKPOINT_WINDOW_MISSED",
    )

    with Session(engine) as session:
        assert (
            candidate_notifications.enqueue_validation_sample_fallbacks_in_session(
                session, now=NOW
            )
            == []
        )


def test_validation_sample_fallback_skips_after_kickoff_past_30min() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    kickoff = NOW - timedelta(minutes=60)
    with Session(engine) as session:
        _insert_enabled_competition(session)
        _insert_fixture_identity(session, kickoff_utc=kickoff)
        session.commit()
    _append(repository, _attempt("T3_ODDS", "a"))
    repository.record_opportunity_without_attempt(
        fixture_id="1523202",
        market="ASIAN_HANDICAP",
        context=_context("T15_ODDS", "missed"),
        state=OpportunityState.MISSED_CHECKPOINT,
        recorded_at=kickoff - timedelta(minutes=10),
        blocker="CHECKPOINT_WINDOW_MISSED",
    )

    with Session(engine) as session:
        assert (
            candidate_notifications.enqueue_validation_sample_fallbacks_in_session(
                session, now=NOW
            )
            == []
        )


def test_notif04_titles_and_bodies_render() -> None:
    test_message = render_bark_message({"event_type": candidate_notifications.TEST_MESSAGE})
    assert test_message["title"] == "[测试] W2 Bark 通道"

    candidate_list = render_bark_message(
        {
            "event_type": candidate_notifications.DAILY_CANDIDATE_LIST,
            "football_day": "2026-08-20",
            "match_count": 1,
            "matches": [
                {
                    "kickoff_local_hm": "08-20 20:30",
                    "competition": "中超",
                    "home": "上海海港",
                    "away": "大连英博",
                }
            ],
        }
    )
    assert candidate_list["title"] == "[今日候选] 8月20日 共 1 场待评估"
    assert "开球前 3 小时" in candidate_list["body"]
    assert "推荐会逐条推送" in candidate_list["body"]
    assert "08-20 20:30 中超 上海海港 vs 大连英博" in candidate_list["body"]

    confirmed = render_bark_message(
        {
            "event_type": candidate_notifications.VALIDATION_SAMPLE_CONFIRMED,
            "competition": "中超",
            "match": {"home": "上海海港", "away": "大连英博"},
            "kickoff_local": "2026-08-20T20:30:00+08:00",
            "market": "ASIAN_HANDICAP",
            "direction": "HOME_AH",
            "line": -0.5,
            "decimal_odds": 1.92,
            "bookmaker": {"name": "Bet365"},
            "quote_captured_at": "2026-08-20T12:20:00Z",
            "current_ev": 0.069,
        }
    )
    assert confirmed["title"] == "[推荐] 中超 上海海港vs大连英博 20:30 主-0.5 @1.92"
    assert "机构：Bet365" in confirmed["body"]
    assert "推荐 让球 -0.5 · 主 / 赔率 1.92 · EV +6.9%" in confirmed["body"]

    settlement = render_bark_message(
        {
            "event_type": candidate_notifications.DAILY_SETTLEMENT,
            "football_day": "2026-08-19",
            "item_count": 1,
            "win_count": 1,
            "push_count": 0,
            "loss_count": 0,
            "total_profit_units": 0.91,
            "cumulative_settled_count": 1,
            "cumulative_profit_units": 0.91,
            "items": [
                {
                    "competition": "中超",
                    "home": "上海海港",
                    "away": "大连英博",
                    "market": "ASIAN_HANDICAP",
                    "direction": "HOME_AH",
                    "line": -0.25,
                    "decimal_odds": 1.91,
                    "score": "2-1",
                    "settlement": "WIN",
                    "profit_units": 0.91,
                    "supplementary": False,
                }
            ],
        }
    )
    assert settlement["title"] == "[结算] 8月19日 1场 1赢 0输 +0.91单位"
    assert "累计：1 注 +0.91 单位" in settlement["body"]
    assert (
        "中超 上海海港 vs 大连英博　推荐 主队 -0.25 @1.91　比分 2-1　赢 +0.91"
        in settlement["body"]
    )
    assert "当天：1 注　赢 1 / 走水 0 / 输 0　+0.91 单位" in settlement["body"]


def test_dashboard_projection_does_not_detach_capture_at() -> None:
    """回归：dashboard 投影在会话关闭后访问 deferred capture_at 会 500。

    repository 对 dynamic_evaluations defer 了 capture_at，但
    official_funnel_recommendations 在会话关闭后读取 capture_at，触发
    DetachedInstanceError。修复是去掉该 defer；此测试走真实 dashboard 路径。
    """
    from w2.api.repository import ReadModelRepository

    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    kickoff = NOW + timedelta(hours=2)
    with Session(engine) as session:
        _insert_enabled_competition(session)
        _insert_fixture_identity(session, kickoff_utc=kickoff)
        session.commit()
    _append(repository, _attempt("T3_ODDS", "a"))
    _materialize_validation_samples(engine, now=NOW)

    result = ReadModelRepository(engine=engine).dashboard_model_forecast_validation_progress()
    assert len(result["official_recommendations"]) >= 1
