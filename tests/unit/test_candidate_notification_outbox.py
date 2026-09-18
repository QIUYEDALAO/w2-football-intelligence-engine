from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

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


def test_candidate_event_uses_the_frozen_attempt_and_fails_closed_on_a_bad_v4() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    attempt = _attempt("T3_ODDS", "v4-gate")

    # The attempt carries its own frozen market, line and price, so it is enough
    # on its own. Production cards never carry a usable V4 candidate (measured
    # 2026-09-15: 1219/1219 are NOT_READY with selected_candidate null), and
    # requiring one silenced every candidate push from 2026-09-04 to 2026-09-15.
    repository.append_evaluation(attempt)
    assert [event.event_type for event in _events(engine)] == [CANDIDATE_FORMED]
    api_card = _apply_repository_v4_authority(
        {
            "fixture_id": attempt.fixture_id,
            "competition_id": "chinese_super_league",
            "kickoff_utc": "2026-08-21T12:00:00Z",
        }
    )
    legacy_pick = {
        "decision_tier": "ANALYSIS_PICK",
        "data_status": "READY",
        "lifecycle_status": "DRAFT",
        "outcome_tracked": True,
        "lock_eligible": False,
        "recommendation_id": None,
        "lineup_requirement": "ADVISORY",
        "risk_reason_codes": ["LINEUP_UNOBSERVABLE"],
        "pick": {
            "market": attempt.market,
            "selection": attempt.selection,
            "line": attempt.exact_line,
            "odds": attempt.decimal_odds,
        },
        "non_pick": None,
    }
    dashboard_card = build_dashboard_day_view(
        {
            "generated_at": NOW.isoformat(),
            "date": "2026-08-20",
            "selected_football_day": "2026-08-20",
            "all": [
                {
                    "fixture_id": attempt.fixture_id,
                    "competition_id": "chinese_super_league",
                    "kickoff_utc": "2026-08-21T12:00:00Z",
                    "decision_contract": legacy_pick,
                }
            ],
        },
        environment="staging",
    )["cards"][0]
    assert api_card["decision_tier"] == dashboard_card["decision_tier"] == "NOT_READY"
    assert api_card["pick"] is dashboard_card["pick"] is None
    _append(repository, _attempt("T60_ODDS_LINEUPS", "v4-ready"))
    assert [event.event_type for event in _events(engine)] == [CANDIDATE_FORMED]

    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    mismatched = _attempt("T3_ODDS", "other", line=-0.5)
    try:
        repository.append_evaluation(
            mismatched,
            recommendation_decision_v4=_v4(attempt),
        )
    except ValueError as exc:
        assert str(exc).startswith("CANDIDATE_NOTIFICATION_V4_ATTEMPT_IDENTITY_MISMATCH:")
    else:
        raise AssertionError("mismatched V4 identity must fail closed")

    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    invalid = _v4(_attempt("T3_ODDS", "invalid"))
    invalid["decision_hash"] = "0" * 64
    try:
        repository.append_evaluation(
            _attempt("T3_ODDS", "invalid"),
            recommendation_decision_v4=invalid,
        )
    except ValueError as exc:
        assert str(exc) == "CANDIDATE_NOTIFICATION_V4_INVALID"
    else:
        raise AssertionError("invalid V4 identity must fail closed")

    with Session(engine) as session:
        assert session.scalar(select(DynamicPrematchEvaluationModel)) is None


def test_same_frozen_v4_pick_reaches_api_dashboard_and_notification() -> None:
    engine = _engine()
    attempt = _attempt("T3_ODDS", "three-exits", line=-0.5, odds=1.95)
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
    ) == (
        notification["market"],
        notification["direction"],
        notification["line"],
        notification["decimal_odds"],
    )
    assert notification["recommendation_decision_v4_hash"] == decision["decision_hash"]
    assert notification["recommendation_authority"] == "IMMUTABLE_EVALUATION_ATTEMPT"


def test_attempt_events_are_transactional_idempotent_and_capture_transient_candidate() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)

    formed = _attempt("T3_ODDS", "a")
    _append(repository, formed)
    _append(repository, formed)
    _append(repository, _attempt("T60_ODDS_LINEUPS", "b"))
    _append(repository, _attempt("T45_ODDS", "c", ev=-0.01))

    events = _events(engine)
    assert [event.event_type for event in events] == [CANDIDATE_FORMED, CANDIDATE_WITHDRAWN]
    assert events[0].attempt_identity_hash == formed.attempt_identity_hash
    assert events[0].payload["decimal_odds"] == "1.91"
    assert events[0].payload["signal_semantics"].startswith("EARLY_SHADOW")
    assert events[1].previous_state == "EVALUATED_CANDIDATE"
    assert events[1].current_state == "EVALUATED_NO_EDGE"


def test_material_change_and_t30_confirmation_are_distinct_events() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    _append(repository, _attempt("T3_ODDS", "a"))
    _append(repository, _attempt("T60_ODDS_LINEUPS", "b", line=-0.5))
    _append(repository, _attempt("T-30m_VALIDATION_LOCK", "d", line=-0.5))

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
    _append(repository, _attempt("T3_ODDS", "a"))
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
    _append(repository, _attempt("T3_ODDS", "a"))
    context = _context("T-30m_VALIDATION_LOCK", "missed")
    repository.record_opportunity_without_attempt(
        fixture_id="1523202",
        market="ASIAN_HANDICAP",
        context=context,
        state=OpportunityState.MISSED_CHECKPOINT,
        recorded_at=NOW + timedelta(minutes=6),
        blocker="CHECKPOINT_WINDOW_MISSED",
    )

    _append(repository, _attempt("T15_ODDS", "laterlater"))

    events = _events(engine)
    assert sorted(event.event_type for event in events) == sorted(
        [
            CANDIDATE_FORMED,
            CANDIDATE_WITHDRAWN,
            CANDIDATE_MATERIAL_CHANGE,
            candidate_notifications.VALIDATION_SAMPLE_CONFIRMED,
        ]
    )
    reformed = next(event for event in events if event.event_type == CANDIDATE_MATERIAL_CHANGE)
    assert reformed.previous_state == "MISSED_CHECKPOINT"
    assert reformed.payload["reformed_after_state"] == "MISSED_CHECKPOINT"
    assert render_bark_message(reformed.payload)["title"].startswith("[恢复]")


def test_delivery_health_keeps_failure_distinct_from_zero_candidates() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    _append(repository, _attempt("T3_ODDS", "a"))
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
        _append(repository, _attempt("T3_ODDS", "a"))
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
    _append(repository, _attempt("T3_ODDS", "a", depth=0))
    _append(repository, _attempt("T3_ODDS", "b", market="TOTALS", ev=-0.01))
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
    assert formed["title"] == "[酝酿] 上海海港 vs 大连英博 08-20 20:30 让球-0.5 主 @1.92"
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
    _append(repository, _attempt("T-30m_VALIDATION_LOCK", "candidate"))
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
    _append(repository, _attempt("T-30m_VALIDATION_LOCK", "candidate"))
    _append(repository, _attempt("T15_ODDS", "later-no-edge", ev=-0.01))
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


def test_owner_stopped_types_are_suppressed_but_new_types_reach_the_phone() -> None:
    lock_at = datetime(2026, 8, 22, 16, 7, tzinfo=UTC)
    confirmed = {("1550092", "ASIAN_HANDICAP"): lock_at}

    def route(event_type: str, *, offset_minutes: int) -> tuple[str, str]:
        return candidate_notifications.delivery_route(
            _routing_row(event_type, created_at=lock_at + timedelta(minutes=offset_minutes)),
            confirmed_at=confirmed,
            withdrawals_pushed=set(),
        )

    # NOTIF-04: every legacy candidate/summary type is written for audit but
    # never delivered.
    for event_type in (
        CANDIDATE_FORMED,
        CANDIDATE_MATERIAL_CHANGE,
        CANDIDATE_WITHDRAWN,
        CANDIDATE_T30_CONFIRMED,
        PLAN_SUMMARY,
        DAY_CLOSEOUT_SUMMARY,
        candidate_notifications.CANDIDATE_BREWING_DIGEST,
    ):
        assert route(event_type, offset_minutes=0) == ("SUPPRESS", "OWNER_DECISION_STOP")
    # The three NOTIF-04 types still reach the phone.
    for event_type in (
        candidate_notifications.DAILY_CANDIDATE_LIST,
        candidate_notifications.VALIDATION_SAMPLE_CONFIRMED,
        candidate_notifications.DAILY_SETTLEMENT,
    ):
        assert route(event_type, offset_minutes=0) == ("SEND", "ACTIONABLE")


def test_owner_stopped_type_is_written_for_audit_but_not_delivered(monkeypatch) -> None:
    engine = _engine()
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "owner-device-test-key")
    with Session(engine) as session:
        session.add(
            CandidateNotificationOutboxModel(
                notification_event_id="formed-immediate",
                opportunity_identity_hash="a" * 64,
                attempt_identity_hash="b" * 64,
                event_type=CANDIDATE_FORMED,
                previous_state=None,
                current_state="EVALUATED_CANDIDATE",
                payload={
                    "event_type": CANDIDATE_FORMED,
                    "fixture_id": "1550092",
                    "market": "ASIAN_HANDICAP",
                    "match": {"home": "国际米兰", "away": "蒙扎"},
                    "kickoff_local": "2026-08-23T00:30:00+08:00",
                    "line": 0.25,
                    "direction": "HOME",
                    "decimal_odds": 1.92,
                },
                created_at=NOW,
                delivered_at=None,
                delivery_status=candidate_notifications.PENDING,
                delivery_attempt_count=0,
                last_error=None,
            )
        )
        session.commit()

    sent: list[dict[str, object]] = []
    result = deliver_pending_notifications(now=NOW, engine=engine, sender=sent.append)

    assert result["delivered"] == 0
    assert result["suppressed"] == 1
    assert sent == []
    assert _events(engine)[0].delivery_status == candidate_notifications.SUPPRESSED
    assert _events(engine)[0].last_error == "OWNER_DECISION_STOP"


def test_withdrawals_are_owner_stopped_regardless_of_lock_state() -> None:
    lock_at = datetime(2026, 8, 22, 16, 7, tzinfo=UTC)
    confirmed = {("1550092", "ASIAN_HANDICAP"): lock_at}
    assert candidate_notifications.delivery_route(
        _routing_row(CANDIDATE_WITHDRAWN, created_at=lock_at + timedelta(minutes=20)),
        confirmed_at=confirmed,
        withdrawals_pushed={("1550092", "ASIAN_HANDICAP")},
    ) == ("SUPPRESS", "OWNER_DECISION_STOP")
    # Even a different market on the same fixture is stopped the same way.
    assert candidate_notifications.delivery_route(
        _routing_row(
            CANDIDATE_WITHDRAWN, market="TOTALS", created_at=lock_at + timedelta(minutes=5)
        ),
        confirmed_at=confirmed,
        withdrawals_pushed=set(),
    ) == ("SUPPRESS", "OWNER_DECISION_STOP")


def _lock_then_change(engine) -> None:  # type: ignore[no-untyped-def]
    repository = DynamicPrematchRepository(engine)
    _append(repository, _attempt("T3_ODDS", "a"))
    _append(repository, _attempt("T60_ODDS_LINEUPS", "bb", line=-0.5))
    _append(repository, _attempt("T-30m_VALIDATION_LOCK", "ddd", line=-0.5))
    _append(repository, _attempt("T15_ODDS", "eeee", line=-0.75))


def test_legacy_candidate_events_are_suppressed_and_only_validation_sample_delivered(
    monkeypatch,
) -> None:
    engine = _engine()
    _lock_then_change(engine)
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "owner-device-test-key")
    sent: list[str] = []

    deliver_pending_notifications(
        now=NOW + timedelta(minutes=10),
        engine=engine,
        sender=lambda payload: sent.append(str(payload["event_type"])),
    )

    # NOTIF-04: only ② reaches the phone; every legacy candidate event stays in
    # the outbox for audit and is never delivered.
    assert sent == [candidate_notifications.VALIDATION_SAMPLE_CONFIRMED]
    events = _events(engine)
    legacy = [
        row
        for row in events
        if row.event_type != candidate_notifications.VALIDATION_SAMPLE_CONFIRMED
    ]
    assert legacy and all(
        row.delivery_status == candidate_notifications.SUPPRESSED for row in legacy
    )
    confirmation = next(
        row
        for row in events
        if row.event_type == candidate_notifications.VALIDATION_SAMPLE_CONFIRMED
    )
    assert confirmation.delivery_status == DELIVERED


def test_daily_brewing_digest_waits_for_its_day_to_close() -> None:
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

        # Still inside the Beijing day the candidates formed in: nothing is
        # emitted, so the Owner gets one "candidates formed" push per day rather
        # than one per candidate.
        assert (
            candidate_notifications.enqueue_brewing_digest_in_session(
                session, now=formed_at + timedelta(minutes=30)
            )
            == []
        )

        emitted = candidate_notifications.enqueue_brewing_digest_in_session(
            session, now=formed_at + timedelta(hours=24)
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


def _insert_enabled_competition(session: Session, competition_id: str = "chinese_super_league") -> None:
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
        assert rendered["title"] == "[今日评估] 比赛日 08-20 今天没有可评估的比赛"
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

    # Before Beijing 12:00, nothing is emitted.
    before = datetime(2026, 8, 20, 11, 0, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        assert candidate_notifications.enqueue_daily_settlement_in_session(session, now=before) is None

    # No result yet → 待结算.
    now = datetime(2026, 8, 20, 12, 0, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        event_id = candidate_notifications.enqueue_daily_settlement_in_session(session, now=now)
        assert event_id is not None
        event = session.get(CandidateNotificationOutboxModel, event_id)
        assert event.payload["item_count"] == 1
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

    next_day = datetime(2026, 8, 21, 12, 0, tzinfo=candidate_notifications.BEIJING)
    with Session(engine) as session:
        event_id = candidate_notifications.enqueue_daily_settlement_in_session(session, now=next_day)
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
        assert rendered["title"] == "[结算] 08-19 当天无验证样本"
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
    beijing = candidate_notifications.BEIJING
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
    assert candidate_list["title"] == (
        "[今日评估] 比赛日 08-20 共 1 场（北京 08-20 12:00 – 08-21 12:00）"
    )
    assert "开球前 3 小时" in candidate_list["body"]
    assert "08-20 20:30 中超 上海海港 vs 大连英博" in candidate_list["body"]

    confirmed = render_bark_message(
        {
            "event_type": candidate_notifications.VALIDATION_SAMPLE_CONFIRMED,
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
    assert confirmed["title"] == "[验证样本] 上海海港 vs 大连英博 08-20 20:30 让球-0.5 主 @1.92"
    assert "机构：Bet365" in confirmed["body"]
    assert "EV：+6.9%" in confirmed["body"]

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
    assert settlement["title"] == "[结算] 08-19 当天 +0.91 单位"
    assert "累计：1 注 +0.91 单位" in settlement["body"]
    assert "上海海港 vs 大连英博　推荐 主队 -0.25 @1.91　比分 2-1　赢 +0.91" in settlement["body"]
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

    result = ReadModelRepository(engine=engine).dashboard_model_forecast_validation_progress()
    assert len(result["official_recommendations"]) >= 1
