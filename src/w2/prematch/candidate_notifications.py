from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.dashboard.date_window import football_day_for_kickoff
from w2.dashboard.results import normalize_match_status
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CandidateNotificationOutboxModel,
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.infrastructure.persistence.models import ResultModel
from w2.matchday.timezone import BeijingOperationalDayPolicy
from w2.prematch.evaluation_slots import evaluation_slots
from w2.prematch.lifecycle import (
    CHECKPOINT_OPPORTUNITY_SCOPE,
    CHECKPOINT_OPPORTUNITY_SEMANTICS,
    DynamicEvaluationState,
    DynamicEvaluationVersion,
    OpportunityState,
)

CANDIDATE_FORMED = "CANDIDATE_FORMED"
CANDIDATE_MATERIAL_CHANGE = "CANDIDATE_MATERIAL_CHANGE"
CANDIDATE_WITHDRAWN = "CANDIDATE_WITHDRAWN"
CANDIDATE_T30_CONFIRMED = "CANDIDATE_T30_CONFIRMED"
PLAN_SUMMARY = "PREMATCH_PLAN_SUMMARY"
DAY_CLOSEOUT_SUMMARY = "FOOTBALL_DAY_CLOSEOUT_SUMMARY"
TEST_MESSAGE = "TEST_MESSAGE"

PENDING = "PENDING"
RETRY_PENDING = "RETRY_PENDING"
DELIVERED = "DELIVERED"
FAILED = "FAILED"

BARK_CHANNEL = "bark"
AT_LEAST_ONCE = "AT_LEAST_ONCE"
MAX_DELIVERY_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = (5, 10, 20)
DELIVERY_TIMEOUT_SECONDS = 8

QUOTE_MAX_AGE_SECONDS = 1800
PRICE_CHANGE_THRESHOLD_RATIO = 0.02
# Notification noise threshold only. It does not change the Decision V4 gate.
EV_CHANGE_THRESHOLD = 0.01
T30_SLOT = "T-30m_VALIDATION_LOCK"
BEIJING = ZoneInfo("Asia/Shanghai")


def enqueue_attempt_notification_in_session(
    session: Session,
    version: DynamicEvaluationVersion,
) -> list[str]:
    """Create attempt-backed events in the evaluation transaction.

    This consumes the immutable attempt being appended. It never polls the
    mutable opportunity projection to discover a candidate transition.
    """

    if not _official(version) or version.attempt_identity_hash is None:
        return []
    previous_rows = list(
        session.scalars(
            select(DynamicPrematchEvaluationModel)
            .where(
                DynamicPrematchEvaluationModel.fixture_id == version.fixture_id,
                DynamicPrematchEvaluationModel.market == version.market,
                DynamicPrematchEvaluationModel.model_forecast_capture_identity_hash
                == version.model_forecast_capture_identity_hash,
                DynamicPrematchEvaluationModel.evaluation_policy_version
                == version.evaluation_policy_version,
                DynamicPrematchEvaluationModel.official_funnel_eligible.is_(True),
                DynamicPrematchEvaluationModel.measurement_semantics
                == CHECKPOINT_OPPORTUNITY_SEMANTICS,
                DynamicPrematchEvaluationModel.attempt_identity_hash
                != version.attempt_identity_hash,
            )
            .order_by(
                DynamicPrematchEvaluationModel.recorded_at.desc(),
                DynamicPrematchEvaluationModel.evaluated_at.desc(),
                DynamicPrematchEvaluationModel.evaluation_id.desc(),
            )
        )
    )
    previous = previous_rows[0] if previous_rows else None
    previous_candidate = next(
        (row for row in previous_rows if _opportunity_state(row) == "EVALUATED_CANDIDATE"),
        None,
    )
    current_state = version.opportunity_state
    if current_state is None:
        return []
    previous_opportunity = session.scalar(
        select(DynamicPrematchOpportunityModel)
        .where(
            DynamicPrematchOpportunityModel.fixture_id == version.fixture_id,
            DynamicPrematchOpportunityModel.market == version.market,
            DynamicPrematchOpportunityModel.model_forecast_capture_identity_hash
            == version.model_forecast_capture_identity_hash,
            DynamicPrematchOpportunityModel.evaluation_policy_version
            == version.evaluation_policy_version,
            DynamicPrematchOpportunityModel.scheduled_checkpoint_at
            < version.scheduled_checkpoint_at,
            DynamicPrematchOpportunityModel.opportunity_identity_hash
            != version.opportunity_identity_hash,
        )
        .order_by(
            DynamicPrematchOpportunityModel.scheduled_checkpoint_at.desc(),
            DynamicPrematchOpportunityModel.recorded_at.desc(),
            DynamicPrematchOpportunityModel.opportunity_identity_hash.desc(),
        )
        .limit(1)
    )
    previous_state = (
        previous_opportunity.state
        if previous_opportunity is not None
        else _opportunity_state(previous)
    )

    events: list[tuple[str, DynamicPrematchEvaluationModel | None, str | None]] = []
    if current_state == OpportunityState.EVALUATED_CANDIDATE:
        if previous_candidate is None:
            events.append((CANDIDATE_FORMED, None, previous_state))
        elif previous_state != "EVALUATED_CANDIDATE":
            events.append((CANDIDATE_MATERIAL_CHANGE, previous_candidate, previous_state))
        elif previous is not None and _materially_changed(previous.payload, version.as_dict()):
            events.append((CANDIDATE_MATERIAL_CHANGE, previous, previous_state))
        if version.evaluation_slot_id == T30_SLOT and previous_candidate is not None:
            events.append((CANDIDATE_T30_CONFIRMED, previous_candidate, previous_state))
    elif previous_state == "EVALUATED_CANDIDATE" and previous_candidate is not None:
        events.append((CANDIDATE_WITHDRAWN, previous_candidate, previous_state))

    inserted: list[str] = []
    for event_type, comparison, event_previous_state in events:
        outbox_created_at = datetime.now(UTC)
        payload = _attempt_payload(
            session,
            version,
            event_type=event_type,
            comparison=(comparison.payload if comparison is not None else None),
            outbox_created_at=outbox_created_at,
        )
        if (
            event_type == CANDIDATE_MATERIAL_CHANGE
            and event_previous_state
            and event_previous_state != "EVALUATED_CANDIDATE"
        ):
            payload["reformed_after_state"] = event_previous_state
        event_id = _event_id(version.attempt_identity_hash, event_type)
        if _insert(
            session,
            event_id=event_id,
            opportunity_identity_hash=version.opportunity_identity_hash,
            attempt_identity_hash=version.attempt_identity_hash,
            event_type=event_type,
            previous_state=event_previous_state,
            current_state=current_state.value,
            payload=payload,
            created_at=outbox_created_at,
        ):
            inserted.append(event_id)
    return inserted


def enqueue_closeout_withdrawal_in_session(
    session: Session,
    *,
    fixture_id: str,
    market: str,
    opportunity_identity_hash: str,
    model_forecast_capture_identity_hash: str,
    evaluation_policy_version: str,
    evaluation_slot_id: str,
    scheduled_checkpoint_at: datetime,
    current_state: OpportunityState,
    recorded_at: datetime,
    blocker: str,
) -> str | None:
    """Create a withdrawal directly from an immutable no-attempt closeout."""

    previous = session.scalar(
        select(DynamicPrematchEvaluationModel)
        .where(
            DynamicPrematchEvaluationModel.fixture_id == fixture_id,
            DynamicPrematchEvaluationModel.market == market,
            DynamicPrematchEvaluationModel.model_forecast_capture_identity_hash
            == model_forecast_capture_identity_hash,
            DynamicPrematchEvaluationModel.evaluation_policy_version
            == evaluation_policy_version,
            DynamicPrematchEvaluationModel.official_funnel_eligible.is_(True),
            DynamicPrematchEvaluationModel.measurement_semantics
            == CHECKPOINT_OPPORTUNITY_SEMANTICS,
        )
        .order_by(
            DynamicPrematchEvaluationModel.recorded_at.desc(),
            DynamicPrematchEvaluationModel.evaluated_at.desc(),
            DynamicPrematchEvaluationModel.evaluation_id.desc(),
        )
        .limit(1)
    )
    if previous is None or _opportunity_state(previous) != "EVALUATED_CANDIDATE":
        return None
    event_id = _event_id(opportunity_identity_hash, CANDIDATE_WITHDRAWN)
    previous_payload = dict(previous.payload)
    payload = _payload_from_mapping(
        session,
        previous_payload,
        event_type=CANDIDATE_WITHDRAWN,
        created_at=recorded_at,
    )
    payload.update(
        {
            "candidate_status": current_state.value,
            "slot": evaluation_slot_id,
            "scheduled_checkpoint_at": _iso(scheduled_checkpoint_at),
            "withdrawal_reason": blocker,
            "source_kind": "OPPORTUNITY_CLOSEOUT_WITHOUT_ATTEMPT",
        }
    )
    if not _insert(
        session,
        event_id=event_id,
        opportunity_identity_hash=opportunity_identity_hash,
        attempt_identity_hash=None,
        event_type=CANDIDATE_WITHDRAWN,
        previous_state="EVALUATED_CANDIDATE",
        current_state=current_state.value,
        payload=payload,
        created_at=recorded_at,
    ):
        return None
    return event_id


def notification_health_in_session(session: Session, *, now: datetime) -> dict[str, Any]:
    rows = list(session.scalars(select(CandidateNotificationOutboxModel)))
    delivered = [row for row in rows if row.delivery_status == DELIVERED]
    pending = [row for row in rows if row.delivery_status in {PENDING, RETRY_PENDING}]
    failed = [row for row in rows if row.delivery_status == FAILED]
    last_success = max((row.delivered_at for row in delivered if row.delivered_at), default=None)
    oldest_pending = min((row.created_at for row in pending), default=None)
    configured, configuration_error = _bark_configuration()
    consecutive_failures = _consecutive_failure_count(rows)
    delivery_latencies = sorted(
        max(_seconds(_utc(row.delivered_at) - _utc(row.created_at)), 0.0)
        for row in delivered
        if row.delivered_at is not None
    )
    delivery_p95 = (
        delivery_latencies[max((len(delivery_latencies) * 95 + 99) // 100 - 1, 0)]
        if delivery_latencies
        else None
    )
    pending_over_target = [
        row for row in pending if _seconds(now - _utc(row.created_at)) > 30
    ]
    status = (
        "CHANNEL_NOT_CONFIGURED"
        if not configured and configuration_error is None
        else "DEGRADED"
        if configuration_error
        or failed
        or consecutive_failures >= 5
        or pending_over_target
        or (delivery_p95 is not None and delivery_p95 > 30)
        else "READY"
    )
    return {
        "status": status,
        "channel": BARK_CHANNEL,
        "delivery_mode": AT_LEAST_ONCE,
        "configuration_error": configuration_error,
        "last_successful_delivery_at": _iso(last_success) if last_success else None,
        "failure_count": sum(
            max(row.delivery_attempt_count - int(row.delivery_status == DELIVERED), 0)
            for row in rows
        ),
        "retry_count": sum(max(row.delivery_attempt_count - 1, 0) for row in rows),
        "consecutive_failure_count": consecutive_failures,
        "consecutive_failure_degraded_threshold": 5,
        "pending_backlog": len(pending),
        "oldest_pending_age_seconds": (
            round(_seconds(now - _utc(oldest_pending)), 3) if oldest_pending else None
        ),
        "outbox_enqueue_slo_breach_count": sum(
            float((row.payload or {}).get("outbox_enqueue_latency_seconds") or 0) > 5
            for row in rows
        ),
        "delivery_target_breach_count": sum(
            _seconds(now - _utc(row.created_at)) > 30 for row in pending
        ),
        "delivery_slo_breach_count": sum(
            _seconds(now - _utc(row.created_at)) > 60 for row in pending
        ),
        "delivery_latency_p95_seconds": (
            round(delivery_p95, 3) if delivery_p95 is not None else None
        ),
        "delivery_latency_target_p95_seconds": 30,
        "outbox_event_count": len(rows),
    }


def notification_health(
    *,
    now: datetime | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    with Session(engine or create_engine()) as session:
        return notification_health_in_session(session, now=resolved_now)


def record_delivery_result_in_session(
    session: Session,
    *,
    notification_event_id: str,
    delivered: bool,
    attempted_at: datetime,
    error: str | None = None,
    retryable: bool = True,
) -> None:
    row = session.get(CandidateNotificationOutboxModel, notification_event_id)
    if row is None:
        raise ValueError("NOTIFICATION_EVENT_NOT_FOUND")
    if row.delivery_status == DELIVERED:
        return
    row.delivery_attempt_count += 1
    payload = dict(row.payload or {})
    delivery = dict(payload.get("_delivery") or {})
    previous_failures = _consecutive_failure_count(
        list(session.scalars(select(CandidateNotificationOutboxModel)))
    )
    delivery["last_attempted_at"] = _iso(attempted_at)
    if delivered:
        row.delivery_status = DELIVERED
        row.delivered_at = attempted_at
        row.last_error = None
        delivery["consecutive_failure_count"] = 0
        delivery.pop("next_attempt_at", None)
    else:
        retry = retryable and row.delivery_attempt_count < MAX_DELIVERY_ATTEMPTS
        row.delivery_status = RETRY_PENDING if retry else FAILED
        row.last_error = _safe_error(error)
        delivery["consecutive_failure_count"] = previous_failures + 1
        if retry:
            delivery["next_attempt_at"] = _iso(
                attempted_at
                + timedelta(
                    seconds=RETRY_BACKOFF_SECONDS[row.delivery_attempt_count - 1]
                )
            )
        else:
            delivery.pop("next_attempt_at", None)
    payload["_delivery"] = delivery
    row.payload = payload
    session.flush()


def deliver_pending_notifications(
    *,
    now: datetime | None = None,
    engine: Engine | None = None,
    sender: Callable[[Mapping[str, Any]], None] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Deliver due outbox rows; an absent Bark setting performs no writes."""

    resolved_now = now or datetime.now(UTC)
    configured, configuration_error = _bark_configuration()
    if not configured:
        return {
            "status": "CHANNEL_NOT_CONFIGURED"
            if configuration_error is None
            else "DEGRADED",
            "channel": BARK_CHANNEL,
            "delivered": 0,
            "failed_attempts": 0,
        }
    send = sender or _send_bark
    delivered_count = 0
    failed_count = 0
    with Session(engine or create_engine()) as session:
        rows = list(
            session.scalars(
                select(CandidateNotificationOutboxModel)
                .where(
                    CandidateNotificationOutboxModel.delivery_status.in_(
                        (PENDING, RETRY_PENDING)
                    )
                )
                .order_by(CandidateNotificationOutboxModel.created_at)
            )
        )
        due_rows = [row for row in rows if _delivery_due(row, resolved_now)][: max(limit, 1)]
        for row in due_rows:
            try:
                send(row.payload)
            except Exception as exc:  # sender boundary; persist only a safe class name
                failed_count += 1
                record_delivery_result_in_session(
                    session,
                    notification_event_id=row.notification_event_id,
                    delivered=False,
                    attempted_at=resolved_now,
                    error=_delivery_exception_name(exc),
                )
            else:
                delivered_count += 1
                record_delivery_result_in_session(
                    session,
                    notification_event_id=row.notification_event_id,
                    delivered=True,
                    attempted_at=resolved_now,
                )
            session.commit()
    return {
        "status": "DELIVERED"
        if delivered_count
        else "RETRY_SCHEDULED"
        if failed_count
        else "IDLE",
        "channel": BARK_CHANNEL,
        "delivered": delivered_count,
        "failed_attempts": failed_count,
    }


def enqueue_test_message_in_session(
    session: Session,
    *,
    request_id: str,
    created_at: datetime,
) -> str:
    if not request_id.strip():
        raise ValueError("TEST_REQUEST_ID_REQUIRED")
    event_id = _event_id(f"test:{request_id}", TEST_MESSAGE)
    _insert(
        session,
        event_id=event_id,
        opportunity_identity_hash=None,
        attempt_identity_hash=None,
        event_type=TEST_MESSAGE,
        previous_state=None,
        current_state="TEST",
        payload={
            "schema_version": "w2.candidate_notification.v1",
            "event_type": TEST_MESSAGE,
            "request_id": request_id,
            "created_at": _iso(created_at),
        },
        created_at=created_at,
    )
    return event_id


def enqueue_test_message(
    *,
    request_id: str,
    created_at: datetime | None = None,
    engine: Engine | None = None,
) -> str:
    resolved_at = created_at or datetime.now(UTC)
    with Session(engine or create_engine()) as session:
        event_id = enqueue_test_message_in_session(
            session,
            request_id=request_id,
            created_at=resolved_at,
        )
        session.commit()
    return event_id


def enqueue_operational_summaries_in_session(
    session: Session,
    *,
    now: datetime,
) -> list[str]:
    """Enqueue the two operational-football-day summaries idempotently."""

    window = BeijingOperationalDayPolicy().current_window(now_utc=now)
    identities = list(
        session.scalars(
            select(MatchdayFixtureIdentityModel)
            .where(
                MatchdayFixtureIdentityModel.kickoff_utc >= window.start_utc,
                MatchdayFixtureIdentityModel.kickoff_utc < window.end_utc,
            )
            .order_by(MatchdayFixtureIdentityModel.kickoff_utc)
        )
    )
    if not identities:
        return []
    canonical_ids = {row.fixture_id for row in identities}
    bare_ids = {row.provider_fixture_id for row in identities}
    fixture_aliases = canonical_ids | bare_ids
    plans = list(
        session.scalars(
            select(MatchdayCheckpointPlanModel)
            .where(MatchdayCheckpointPlanModel.fixture_id.in_(fixture_aliases))
            .order_by(MatchdayCheckpointPlanModel.scheduled_at)
        )
    )
    registered_slots = set(evaluation_slots())
    evaluation_plans = [
        row
        for row in plans
        if row.checkpoint in registered_slots and "odds" in list(row.endpoints or [])
    ]
    tracks = list(
        session.scalars(
            select(ModelForecastCaptureModel).where(
                ModelForecastCaptureModel.fixture_id.in_(fixture_aliases)
            )
        )
    )
    track_fixture_ids = {
        row.fixture_id.removeprefix("api_football:") for row in tracks
    }
    track_count_by_fixture: dict[str, int] = {}
    for row in tracks:
        fixture_id = row.fixture_id.removeprefix("api_football:")
        track_count_by_fixture[fixture_id] = track_count_by_fixture.get(fixture_id, 0) + 1
    plan_fixture_ids = {
        row.fixture_id.removeprefix("api_football:") for row in evaluation_plans
    }
    candidate_track_fixture_ids = track_fixture_ids & plan_fixture_ids
    candidate_track_matches = [
        _summary_fixture(identity)
        for identity in identities
        if identity.provider_fixture_id in candidate_track_fixture_ids
    ]

    inserted: list[str] = []
    if evaluation_plans:
        first_kickoff = min(_utc(row.kickoff_utc) for row in identities)
        plan_summary_due_at = first_kickoff - timedelta(hours=2)
        event_id = _event_id(window.operational_day_key, PLAN_SUMMARY)
        planned_opportunities = sum(
            2
            * track_count_by_fixture.get(
                row.fixture_id.removeprefix("api_football:"),
                0,
            )
            for row in evaluation_plans
        )
        if plan_summary_due_at <= now < plan_summary_due_at + timedelta(minutes=5) and _insert(
            session,
            event_id=event_id,
            opportunity_identity_hash=None,
            attempt_identity_hash=None,
            event_type=PLAN_SUMMARY,
            previous_state=None,
            current_state="PLANNED",
            payload={
                "schema_version": "w2.candidate_notification.v1",
                "event_type": PLAN_SUMMARY,
                "operational_football_day": window.operational_day_key,
                "heartbeat": True,
                "summary_timing": "TWO_HOURS_BEFORE_FIRST_KICKOFF",
                "summary_due_at": _iso(plan_summary_due_at),
                "monitoring_fixture_count": len(identities),
                "model_track_ready_fixture_count": len(track_fixture_ids),
                "candidate_track_fixture_count": len(candidate_track_fixture_ids),
                "candidate_track_matches": candidate_track_matches,
                "planned_evaluation_opportunity_count": planned_opportunities,
                "first_evaluation_at": _iso(
                    min(_utc(row.scheduled_at) for row in evaluation_plans)
                )
                if evaluation_plans
                else None,
                "last_evaluation_at": _iso(
                    max(_utc(row.scheduled_at) for row in evaluation_plans)
                )
                if evaluation_plans
                else None,
                "dashboard_url": _dashboard_day_url(window.operational_day_key),
                "created_at": _iso(now),
            },
            created_at=now,
        ):
            inserted.append(event_id)

    results = list(
        session.scalars(select(ResultModel).where(ResultModel.fixture_id.in_(fixture_aliases)))
    )
    results_by_fixture = {
        row.fixture_id.removeprefix("api_football:"): row for row in results
    }
    closed_evidence = [
        _fixture_closeout_time(identity, results_by_fixture.get(identity.provider_fixture_id))
        for identity in identities
    ]
    closeout_due_at = max((value for value in closed_evidence if value), default=None)
    # Do not turn deployment into a historical summary backfill. The scheduler
    # checks every 30 seconds, so a five-minute forward-only window tolerates a
    # restart without rewriting an already closed football day.
    if (
        closeout_due_at is not None
        and all(value is not None for value in closed_evidence)
        and closeout_due_at <= now <= closeout_due_at + timedelta(minutes=5)
    ):
        opportunities = list(
            session.scalars(
                select(DynamicPrematchOpportunityModel).where(
                    DynamicPrematchOpportunityModel.fixture_id.in_(fixture_aliases)
                )
            )
        )
        attempts = list(
            session.scalars(
                select(DynamicPrematchEvaluationModel).where(
                    DynamicPrematchEvaluationModel.fixture_id.in_(fixture_aliases),
                    DynamicPrematchEvaluationModel.official_funnel_eligible.is_(True),
                    DynamicPrematchEvaluationModel.measurement_semantics
                    == CHECKPOINT_OPPORTUNITY_SEMANTICS,
                )
            )
        )
        states = {state.value: 0 for state in OpportunityState}
        invalid = 0
        for opportunity in opportunities:
            if (
                not opportunity.opportunity_identity_hash
                or opportunity.state not in states
                or not opportunity.evaluation_slot_id
                or not opportunity.market
            ):
                invalid += 1
                continue
            states[opportunity.state] += 1
        reason_by_market = _zero_candidate_reasons(opportunities, attempts)
        recommendations = _closeout_recommendations(
            session,
            fixture_aliases=fixture_aliases,
            results_by_fixture=results_by_fixture,
        )
        event_id = _event_id(window.operational_day_key, DAY_CLOSEOUT_SUMMARY)
        if _insert(
            session,
            event_id=event_id,
            opportunity_identity_hash=None,
            attempt_identity_hash=None,
            event_type=DAY_CLOSEOUT_SUMMARY,
            previous_state=None,
            current_state="CLOSED",
            payload={
                "schema_version": "w2.candidate_notification.v1",
                "event_type": DAY_CLOSEOUT_SUMMARY,
                "operational_football_day": window.operational_day_key,
                "closeout_trigger_at": _iso(closeout_due_at),
                "formal_opportunity_count": len(opportunities),
                "complete_evaluation_count": states["EVALUATED_NO_EDGE"]
                + states["EVALUATED_CANDIDATE"],
                "blocked_by_gate_count": states["BLOCKED_BY_GATE"],
                "evaluation_error_count": states["EVALUATION_ERROR"],
                "missed_checkpoint_count": states["MISSED_CHECKPOINT"],
                "no_edge_count": states["EVALUATED_NO_EDGE"],
                "candidate_count": states["EVALUATED_CANDIDATE"],
                "invalid_count": invalid,
                "recommendations": recommendations,
                "zero_candidate_reason_by_market": reason_by_market,
                "zero_candidate_is_not_delivery_health": True,
                "dashboard_url": _dashboard_day_url(window.operational_day_key),
                "created_at": _iso(now),
            },
            created_at=now,
        ):
            inserted.append(event_id)
    return inserted


def enqueue_operational_summaries(
    *,
    now: datetime | None = None,
    engine: Engine | None = None,
) -> list[str]:
    resolved_now = now or datetime.now(UTC)
    with Session(engine or create_engine()) as session:
        inserted = enqueue_operational_summaries_in_session(session, now=resolved_now)
        session.commit()
    return inserted


def _zero_candidate_reasons(
    opportunities: list[DynamicPrematchOpportunityModel],
    attempts: list[DynamicPrematchEvaluationModel],
) -> dict[str, dict[str, Any]]:
    attempts_by_opportunity = {
        row.opportunity_identity_hash: row
        for row in attempts
        if row.opportunity_identity_hash
    }
    result: dict[str, dict[str, Any]] = {}
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        rows = [row for row in opportunities if row.market == market]
        candidates = sum(row.state == "EVALUATED_CANDIDATE" for row in rows)
        reason_counts: dict[str, int] = {}
        for row in rows:
            attempt = attempts_by_opportunity.get(row.opportunity_identity_hash)
            reason = (
                f"BLOCKED_BY_GATE:{attempt.first_failed_gate}"
                if row.state == "BLOCKED_BY_GATE" and attempt and attempt.first_failed_gate
                else row.state
            )
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        result[market] = {
            "candidate_count": candidates,
            "reason_counts": dict(sorted(reason_counts.items())),
            "summary": (
                "CANDIDATE_PRESENT"
                if candidates
                else max(reason_counts, key=lambda key: reason_counts[key])
                if reason_counts
                else "NO_OFFICIAL_OPPORTUNITY_RECORDED"
            ),
        }
    return result


def _summary_fixture(identity: MatchdayFixtureIdentityModel) -> dict[str, Any]:
    payload = identity.payload if isinstance(identity.payload, dict) else {}
    kickoff = _utc(identity.kickoff_utc)
    fixture_id = identity.provider_fixture_id
    return {
        "fixture_id": fixture_id,
        "home": payload.get("home_team_name")
        or payload.get("home_name")
        or identity.home_provider_team_id,
        "away": payload.get("away_team_name")
        or payload.get("away_name")
        or identity.away_provider_team_id,
        "kickoff_local": kickoff.astimezone(BEIJING).isoformat(),
        "kickoff_local_hm": kickoff.astimezone(BEIJING).strftime("%H:%M"),
        "dashboard_url": _dashboard_fixture_url(fixture_id, kickoff),
    }


def _fixture_closeout_time(
    identity: MatchdayFixtureIdentityModel,
    result: ResultModel | None,
) -> datetime | None:
    if result is not None:
        return _utc(result.confirmed_at)
    if normalize_match_status(identity.fixture_status) in {
        "FINISHED",
        "CANCELLED",
        "POSTPONED",
    }:
        return _utc(identity.captured_at)
    return None


def _closeout_recommendations(
    session: Session,
    *,
    fixture_aliases: set[str],
    results_by_fixture: Mapping[str, ResultModel],
) -> list[dict[str, Any]]:
    rows = list(
        session.scalars(
            select(CandidateNotificationOutboxModel)
            .where(
                CandidateNotificationOutboxModel.event_type.in_(
                    (
                        CANDIDATE_FORMED,
                        CANDIDATE_MATERIAL_CHANGE,
                        CANDIDATE_WITHDRAWN,
                        CANDIDATE_T30_CONFIRMED,
                    )
                )
            )
            .order_by(CandidateNotificationOutboxModel.created_at)
        )
    )
    aliases = {item.removeprefix("api_football:") for item in fixture_aliases}
    groups: dict[tuple[str, str], list[CandidateNotificationOutboxModel]] = {}
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        fixture_id = str(payload.get("fixture_id") or "").removeprefix("api_football:")
        market = str(payload.get("market") or "")
        if fixture_id in aliases and market:
            groups.setdefault((fixture_id, market), []).append(row)

    recommendations: list[dict[str, Any]] = []
    for (fixture_id, market), events in sorted(groups.items()):
        if not any(row.event_type == CANDIDATE_FORMED for row in events):
            continue
        signal_events = [row for row in events if row.event_type != CANDIDATE_WITHDRAWN]
        signal = signal_events[-1].payload
        last = events[-1]
        match = _as_mapping(signal.get("match"))
        result = results_by_fixture.get(fixture_id)
        settlement = "待结算"
        score = None
        if result is not None:
            score = f"{result.home_goals}-{result.away_goals}"
            try:
                settlement = _settle_candidate(
                    market=market,
                    selection=signal.get("direction"),
                    line=signal.get("line"),
                    home_goals=result.home_goals,
                    away_goals=result.away_goals,
                )
            except ValueError:
                settlement = "无法结算"
        recommendations.append(
            {
                "fixture_id": fixture_id,
                "home": match.get("home"),
                "away": match.get("away"),
                "market": market,
                "direction": signal.get("direction"),
                "line": signal.get("line"),
                "decimal_odds": signal.get("decimal_odds"),
                "slot": signal.get("slot"),
                "final_candidate_status": (
                    "WITHDRAWN"
                    if last.event_type == CANDIDATE_WITHDRAWN
                    else "T30_CONFIRMED"
                    if last.event_type == CANDIDATE_T30_CONFIRMED
                    else "CANDIDATE"
                ),
                "withdrawal_reason": (
                    _withdrawal_reason(last.payload)
                    if last.event_type == CANDIDATE_WITHDRAWN
                    else None
                ),
                "score": score,
                "settlement": settlement,
                "dashboard_url": signal.get("dashboard_url"),
            }
        )
    return recommendations


def _dashboard_fixture_url(fixture_id: str, kickoff: datetime) -> str:
    params = {
        "date": football_day_for_kickoff(kickoff).isoformat(),
        "fixture_id": fixture_id,
    }
    base = os.environ.get("W2_DASHBOARD_PUBLIC_BASE_URL", "").rstrip("/")
    path = f"/?{urlencode(params)}"
    return f"{base}{path}" if base else path


def _dashboard_day_url(day: str) -> str:
    base = os.environ.get("W2_DASHBOARD_PUBLIC_BASE_URL", "").rstrip("/")
    path = f"/?{urlencode({'date': day})}"
    return f"{base}{path}" if base else path


def _official(version: DynamicEvaluationVersion) -> bool:
    return (
        version.official_funnel_eligible is True
        and version.denominator_scope == CHECKPOINT_OPPORTUNITY_SCOPE
        and version.measurement_semantics == CHECKPOINT_OPPORTUNITY_SEMANTICS
    )


def _attempt_payload(
    session: Session,
    version: DynamicEvaluationVersion,
    *,
    event_type: str,
    comparison: Mapping[str, Any] | None,
    outbox_created_at: datetime,
) -> dict[str, Any]:
    recorded_at = version.recorded_at or outbox_created_at
    payload = _payload_from_mapping(
        session,
        version.as_dict(),
        event_type=event_type,
        created_at=outbox_created_at,
    )
    payload["source_kind"] = "IMMUTABLE_EVALUATION_ATTEMPT"
    payload["evaluation_recorded_at"] = _iso(recorded_at)
    payload["outbox_created_at"] = _iso(outbox_created_at)
    payload["outbox_enqueue_latency_seconds"] = round(
        max(_seconds(outbox_created_at - recorded_at), 0.0),
        6,
    )
    if comparison is not None:
        payload["change"] = _change_details(comparison, version.as_dict())
    return payload


def _payload_from_mapping(
    session: Session,
    value: Mapping[str, Any],
    *,
    event_type: str,
    created_at: datetime,
) -> dict[str, Any]:
    fixture_id = str(value.get("fixture_id") or "").removeprefix("api_football:")
    identity = _fixture_identity(session, fixture_id)
    identity_payload = identity.payload if identity and isinstance(identity.payload, dict) else {}
    kickoff = _utc(identity.kickoff_utc) if identity is not None else None
    capture_at = _parse_time(value.get("capture_at"))
    next_review = _next_review_at(
        session,
        fixture_id=fixture_id,
        policy_version=str(value.get("evaluation_policy_version") or ""),
        after=_parse_time(value.get("scheduled_checkpoint_at")) or created_at,
    )
    valid_until = capture_at + timedelta(seconds=QUOTE_MAX_AGE_SECONDS) if capture_at else None
    if valid_until is not None and next_review is not None:
        valid_until = min(valid_until, next_review)
    slot = str(value.get("evaluation_slot_id") or value.get("checkpoint") or "")
    bookmaker_id = str(value.get("bookmaker_id") or "") or None
    params = {
        "date": football_day_for_kickoff(kickoff).isoformat() if kickoff else "",
        "fixture_id": fixture_id,
    }
    base = os.environ.get("W2_DASHBOARD_PUBLIC_BASE_URL", "").rstrip("/")
    path = f"/?{urlencode(params)}"
    return {
        "schema_version": "w2.candidate_notification.v1",
        "event_type": event_type,
        "fixture_id": fixture_id,
        "match": {
            "home": identity_payload.get("home_team_name")
            or identity_payload.get("home_name")
            or (identity.home_provider_team_id if identity else None),
            "away": identity_payload.get("away_team_name")
            or identity_payload.get("away_name")
            or (identity.away_provider_team_id if identity else None),
        },
        "kickoff_local": kickoff.astimezone(BEIJING).isoformat() if kickoff else None,
        "market": value.get("market"),
        "direction": value.get("selection"),
        "line": value.get("exact_line"),
        "decimal_odds": value.get("decimal_odds"),
        "bookmaker": {
            "id": bookmaker_id,
            "name": _bookmaker_name(session, fixture_id, bookmaker_id),
        },
        "quote_captured_at": _iso(capture_at) if capture_at else None,
        "quote_age_seconds": (
            round(max(_seconds(created_at - capture_at), 0.0), 3) if capture_at else None
        ),
        "slot": slot,
        "candidate_status": value.get("opportunity_state"),
        "valid_until": _iso(valid_until) if valid_until else None,
        "next_review_at": _iso(next_review) if next_review else None,
        "dashboard_url": f"{base}{path}" if base else path,
        "dashboard_url_kind": "ABSOLUTE" if base else "RELATIVE_UNTIL_DEPLOY_CONFIGURED",
        "signal_semantics": (
            "T30_VALIDATED_SHADOW_CANDIDATE"
            if slot == T30_SLOT
            else "EARLY_SHADOW_CANDIDATE_UNCONFIRMED_MAY_BE_WITHDRAWN"
        ),
        "current_ev": value.get("current_ev"),
        "current_delta": value.get("current_delta"),
        "current_ev_minus_se": value.get("current_ev_minus_se"),
        "first_failed_gate": value.get("first_failed_gate"),
        "all_failed_gates": list(value.get("all_failed_gates") or []),
        "notification_thresholds": {
            "quote_max_age_seconds": QUOTE_MAX_AGE_SECONDS,
            "price_change_ratio": PRICE_CHANGE_THRESHOLD_RATIO,
            "absolute_ev_change": EV_CHANGE_THRESHOLD,
            "decision_gate_unchanged": True,
        },
    }


def render_bark_message(payload: Mapping[str, Any]) -> dict[str, str]:
    event_type = str(payload.get("event_type") or "")
    match = _as_mapping(payload.get("match"))
    home = str(match.get("home") or "主队")
    away = str(match.get("away") or "客队")
    teams = f"{home} vs {away}"
    market = _market_label(payload.get("market"))
    line = _format_line(payload.get("line"))
    direction = _direction_label(payload.get("direction"))
    odds = _format_odds(payload.get("decimal_odds"))
    kickoff = _parse_time(payload.get("kickoff_local"))
    kickoff_hm = kickoff.astimezone(BEIJING).strftime("%H:%M") if kickoff else "--:--"
    ev = _format_ev(payload.get("current_ev"))

    if event_type == CANDIDATE_FORMED:
        title = f"[阵容] {teams} {kickoff_hm} {market}{line} {direction} @{odds}"
    elif event_type == CANDIDATE_MATERIAL_CHANGE:
        if payload.get("reformed_after_state"):
            title = f"[恢复] {teams} {market}{line} {direction} @{odds}"
        else:
            change = _as_mapping(payload.get("change"))
            previous = _as_mapping(change.get("previous"))
            current = _as_mapping(change.get("current"))
            material_fields = set(change.get("material_fields") or [])
            old_line = _format_line(previous.get("exact_line"))
            new_line = _format_line(current.get("exact_line"))
            if "exact_line" in material_fields or old_line != new_line:
                detail = f"{market} {old_line} → {new_line}"
            elif "selection" in material_fields:
                detail = (
                    f"{market} {_direction_label(previous.get('selection'))} → "
                    f"{_direction_label(current.get('selection'))}"
                )
            elif "bookmaker_id" in material_fields:
                detail = (
                    f"{market} 机构 {previous.get('bookmaker_id') or '?'} → "
                    f"{current.get('bookmaker_id') or '?'}"
                )
            elif "current_ev" in material_fields:
                detail = (
                    f"{market} EV{_format_ev(previous.get('current_ev'))} → "
                    f"EV{_format_ev(current.get('current_ev'))}"
                )
            else:
                old_odds = _format_odds(previous.get("decimal_odds"))
                new_odds = _format_odds(current.get("decimal_odds"))
                detail = f"{market} @{old_odds} → @{new_odds}"
            title = f"[变盘] {teams} {detail}"
    elif event_type == CANDIDATE_WITHDRAWN:
        title = f"[撤回] {teams} {market} 原因：{_withdrawal_reason(payload)}"
    elif event_type == CANDIDATE_T30_CONFIRMED:
        title = f"[确认] {teams} T-30m 锁定 {market}{line} {direction} @{odds} EV{ev}"
    elif event_type == PLAN_SUMMARY:
        title = (
            f"[赛前计划] {payload.get('operational_football_day') or ''} "
            f"候选轨道 {len(list(payload.get('candidate_track_matches') or []))} 场"
        )
    elif event_type == DAY_CLOSEOUT_SUMMARY:
        title = (
            f"[当日收官] {payload.get('operational_football_day') or ''} "
            f"推荐 {len(list(payload.get('recommendations') or []))} 条"
        )
    elif event_type == TEST_MESSAGE:
        title = "[测试] W2 Bark 通道"
    else:
        title = "[W2] 候选通知"

    dashboard_url = str(payload.get("dashboard_url") or "")
    body = _message_body(payload)
    if dashboard_url:
        body = f"{body}\n{dashboard_url}" if body else dashboard_url
    result = {"title": title, "body": body}
    if dashboard_url.startswith(("https://", "http://")):
        result["url"] = dashboard_url
    return result


def _send_bark(payload: Mapping[str, Any]) -> None:
    configured, configuration_error = _bark_configuration()
    if not configured:
        raise RuntimeError(configuration_error or "CHANNEL_NOT_CONFIGURED")
    endpoint = os.environ["W2_BARK_ENDPOINT"].rstrip("/")
    message = render_bark_message(payload)
    request_payload = {
        "device_key": os.environ["W2_BARK_DEVICE_KEY"],
        "title": message["title"],
        "body": message["body"],
        "group": "W2候选",
        "level": "timeSensitive",
    }
    if message.get("url"):
        request_payload["url"] = message["url"]
    request = Request(  # noqa: S310 - endpoint is restricted to validated HTTPS
        f"{endpoint}/push",
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(  # noqa: S310 - request URL was restricted to validated HTTPS
            request, timeout=DELIVERY_TIMEOUT_SECONDS
        ) as response:
            status = int(getattr(response, "status", 0))
            response_payload = json.loads(response.read(4096))
    except HTTPError as exc:
        raise RuntimeError(f"BARK_HTTP_{exc.code}") from None
    except URLError:
        raise RuntimeError("BARK_NETWORK_ERROR") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("BARK_INVALID_RESPONSE") from None
    if not 200 <= status < 300 or response_payload.get("code") != 200:
        raise RuntimeError("BARK_REJECTED")


def _bark_configuration() -> tuple[bool, str | None]:
    endpoint = os.environ.get("W2_BARK_ENDPOINT", "").strip()
    device_key = os.environ.get("W2_BARK_DEVICE_KEY", "").strip()
    if not endpoint or not device_key:
        return False, None
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or "@" in parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        return False, "BARK_ENDPOINT_INVALID"
    return True, None


def _delivery_due(row: CandidateNotificationOutboxModel, now: datetime) -> bool:
    payload = row.payload if isinstance(row.payload, dict) else {}
    delivery = _as_mapping(payload.get("_delivery"))
    next_attempt_at = _parse_time(delivery.get("next_attempt_at"))
    return next_attempt_at is None or next_attempt_at <= now


def _consecutive_failure_count(rows: list[CandidateNotificationOutboxModel]) -> int:
    attempted: list[tuple[datetime, int]] = []
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        delivery = _as_mapping(payload.get("_delivery"))
        attempted_at = _parse_time(delivery.get("last_attempted_at"))
        if attempted_at is not None:
            attempted.append((attempted_at, int(delivery.get("consecutive_failure_count") or 0)))
    return max(attempted, default=(datetime.min.replace(tzinfo=UTC), 0))[1]


def _delivery_exception_name(exc: Exception) -> str:
    message = str(exc)
    if message.startswith("BARK_"):
        return message[:512]
    return f"{type(exc).__name__}:DELIVERY_FAILED"


def _safe_error(error: str | None) -> str:
    value = str(error or "DELIVERY_FAILED")
    return value[:512] if value.startswith("BARK_") else "DELIVERY_FAILED"


def _message_body(payload: Mapping[str, Any]) -> str:
    event_type = str(payload.get("event_type") or "")
    if event_type == PLAN_SUMMARY:
        matches = list(payload.get("candidate_track_matches") or [])
        lines = [
            "{time} {home} vs {away}".format(
                time=item.get("kickoff_local_hm", "--:--"),
                home=item.get("home", "主队"),
                away=item.get("away", "客队"),
            )
            for item in matches
            if isinstance(item, Mapping)
        ]
        return "\n".join(lines) or "当日无已就绪候选轨道比赛"
    if event_type == DAY_CLOSEOUT_SUMMARY:
        recommendations = list(payload.get("recommendations") or [])
        counts = (
            f"正式机会 {payload.get('formal_opportunity_count', 0)}；"
            f"完整评估 {payload.get('complete_evaluation_count', 0)}；"
            f"门禁阻断 {payload.get('blocked_by_gate_count', 0)}；"
            f"评估错误 {payload.get('evaluation_error_count', 0)}；"
            f"检查点错过 {payload.get('missed_checkpoint_count', 0)}；"
            f"NO_EDGE {payload.get('no_edge_count', 0)}；"
            f"候选 {payload.get('candidate_count', 0)}；"
            f"INVALID {payload.get('invalid_count', 0)}"
        )
        lines = [counts] + [
            f"{item.get('home', '主队')} vs {item.get('away', '客队')} "
            f"{_market_label(item.get('market'))}{_format_line(item.get('line'))} "
            f"{_direction_label(item.get('direction'))}："
            f"{item.get('score') or '待赛果'} {item.get('settlement', '待结算')}"
            for item in recommendations
            if isinstance(item, Mapping)
        ]
        if not recommendations:
            lines.append("当日无候选推荐")
        return "\n".join(lines)
    if event_type == TEST_MESSAGE:
        return "W2 Bark 外发通道测试消息"
    bookmaker = _as_mapping(payload.get("bookmaker"))
    quote_age = (
        payload.get("quote_age_seconds")
        if payload.get("quote_age_seconds") is not None
        else "未知"
    )
    fields = [
        f"机构：{bookmaker.get('name') or bookmaker.get('id') or '未知'}",
        f"报价时间：{payload.get('quote_captured_at') or '未知'}",
        f"报价年龄：{quote_age} 秒",
        f"档位：{payload.get('slot') or '未知'}",
        f"状态：{payload.get('candidate_status') or '未知'}",
        f"有效期：{payload.get('valid_until') or '未知'}",
        f"下次复核：{payload.get('next_review_at') or '无'}",
    ]
    return "\n".join(fields)


def _market_label(value: Any) -> str:
    return {"ASIAN_HANDICAP": "让球", "TOTALS": "大小球"}.get(str(value), str(value or "盘口"))


def _direction_label(value: Any) -> str:
    raw = str(value or "")
    if raw.startswith("HOME"):
        return "主"
    if raw.startswith("AWAY"):
        return "客"
    if raw.startswith("OVER"):
        return "大"
    if raw.startswith("UNDER"):
        return "小"
    return raw or "方向未知"


def _settlement_selection(market: str, value: Any) -> str:
    selection = str(value or "").upper()
    aliases = {
        "ASIAN_HANDICAP": {"HOME_AH": "HOME", "AWAY_AH": "AWAY"},
        "TOTALS": {"OVER_TOTALS": "OVER", "UNDER_TOTALS": "UNDER"},
    }
    return aliases.get(market, {}).get(selection, selection)


def _settle_candidate(
    *,
    market: str,
    selection: Any,
    line: Any,
    home_goals: int,
    away_goals: int,
) -> str:
    normalized = _settlement_selection(market, selection)
    if line is None:
        raise ValueError("candidate settlement requires line")
    if market == "ASIAN_HANDICAP":
        return settle_asian_handicap(
            home_goals,
            away_goals,
            normalized,
            Decimal(str(line)),
        ).value
    if market == "TOTALS":
        return settle_total_goals(
            home_goals + away_goals,
            normalized,
            Decimal(str(line)),
        ).value
    raise ValueError(f"unsupported candidate market {market}")


def _format_line(value: Any) -> str:
    number = _float(value)
    if number is None:
        return "?"
    return f"{number:g}"


def _format_odds(value: Any) -> str:
    number = _float(value)
    return f"{number:.2f}" if number is not None else "?"


def _format_ev(value: Any) -> str:
    number = _float(value)
    return f"{number * 100:+.1f}%" if number is not None else "?"


def _withdrawal_reason(payload: Mapping[str, Any]) -> str:
    reason = str(
        payload.get("withdrawal_reason")
        or payload.get("first_failed_gate")
        or next(iter(payload.get("all_failed_gates") or []), "")
        or payload.get("candidate_status")
        or "未知"
    )
    return {
        "QUOTE_FRESHNESS": "报价过期",
        "QUOTE_TOO_OLD": "报价过期",
        "BOOKMAKER_DEPTH": "机构深度不足",
        "CHECKPOINT_WINDOW_MISSED": "检查点错过",
        "MISSED_CHECKPOINT": "检查点错过",
        "EVALUATED_NO_EDGE": "价值优势消失",
        "NO_EDGE": "价值优势消失",
        "EVALUATION_ERROR": "评估错误",
    }.get(reason, reason)


def _materially_changed(previous: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    return bool(_change_details(previous, current)["material_fields"])


def _change_details(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    material: list[str] = []
    for field in ("exact_line", "selection", "bookmaker_id"):
        if previous.get(field) != current.get(field):
            material.append(field)
    old_odds = _float(previous.get("decimal_odds"))
    new_odds = _float(current.get("decimal_odds"))
    price_ratio = (
        abs(new_odds - old_odds) / old_odds
        if old_odds is not None and new_odds is not None and old_odds > 0
        else None
    )
    if price_ratio is not None and price_ratio >= PRICE_CHANGE_THRESHOLD_RATIO:
        material.append("decimal_odds")
    old_ev = _float(previous.get("current_ev"))
    new_ev = _float(current.get("current_ev"))
    ev_change = (
        abs(new_ev - old_ev) if old_ev is not None and new_ev is not None else None
    )
    if ev_change is not None and ev_change >= EV_CHANGE_THRESHOLD:
        material.append("current_ev")
    return {
        "material_fields": material,
        "previous": {
            key: previous.get(key)
            for key in ("selection", "exact_line", "bookmaker_id", "decimal_odds", "current_ev")
        },
        "current": {
            key: current.get(key)
            for key in ("selection", "exact_line", "bookmaker_id", "decimal_odds", "current_ev")
        },
        "price_change_ratio": round(price_ratio, 6) if price_ratio is not None else None,
        "absolute_ev_change": round(ev_change, 6) if ev_change is not None else None,
    }


def _insert(
    session: Session,
    *,
    event_id: str,
    opportunity_identity_hash: str | None,
    attempt_identity_hash: str | None,
    event_type: str,
    previous_state: str | None,
    current_state: str,
    payload: dict[str, Any],
    created_at: datetime,
) -> bool:
    if session.get(CandidateNotificationOutboxModel, event_id) is not None:
        return False
    session.add(
        CandidateNotificationOutboxModel(
            notification_event_id=event_id,
            opportunity_identity_hash=opportunity_identity_hash,
            attempt_identity_hash=attempt_identity_hash,
            event_type=event_type,
            previous_state=previous_state,
            current_state=current_state,
            payload=payload,
            created_at=created_at,
            delivered_at=None,
            delivery_status=PENDING,
            delivery_attempt_count=0,
            last_error=None,
        )
    )
    session.flush()
    return True


def _opportunity_state(row: DynamicPrematchEvaluationModel | None) -> str | None:
    if row is None:
        return None
    payload = row.payload if isinstance(row.payload, dict) else {}
    state = payload.get("opportunity_state")
    if state:
        return str(state)
    return (
        "EVALUATED_CANDIDATE"
        if row.original_state == DynamicEvaluationState.ANALYSIS_PICK_ACTIVE.value
        else "EVALUATED_NO_EDGE"
        if row.original_state == DynamicEvaluationState.NO_EDGE_CURRENT.value
        else "BLOCKED_BY_GATE"
    )


def _fixture_identity(
    session: Session, fixture_id: str
) -> MatchdayFixtureIdentityModel | None:
    return session.scalar(
        select(MatchdayFixtureIdentityModel)
        .where(
            MatchdayFixtureIdentityModel.fixture_id.in_(
                (fixture_id, f"api_football:{fixture_id}")
            )
        )
        .order_by(MatchdayFixtureIdentityModel.captured_at.desc())
        .limit(1)
    )


def _bookmaker_name(session: Session, fixture_id: str, bookmaker_id: str | None) -> str | None:
    if not bookmaker_id:
        return None
    return session.scalar(
        select(MatchdayMarketObservationModel.bookmaker_name)
        .where(
            MatchdayMarketObservationModel.fixture_id.in_(
                (fixture_id, f"api_football:{fixture_id}")
            ),
            MatchdayMarketObservationModel.bookmaker_id == bookmaker_id,
        )
        .order_by(MatchdayMarketObservationModel.captured_at.desc())
        .limit(1)
    ) or bookmaker_id


def _next_review_at(
    session: Session,
    *,
    fixture_id: str,
    policy_version: str,
    after: datetime,
) -> datetime | None:
    if not policy_version:
        return None
    registered = set(evaluation_slots(policy_version))
    rows = session.scalars(
        select(MatchdayCheckpointPlanModel)
        .where(
            MatchdayCheckpointPlanModel.fixture_id.in_(
                (fixture_id, f"api_football:{fixture_id}")
            ),
            MatchdayCheckpointPlanModel.policy_version == "w2.matchday_intake_policy.v2",
            MatchdayCheckpointPlanModel.scheduled_at > after,
        )
        .order_by(MatchdayCheckpointPlanModel.scheduled_at)
    )
    for row in rows:
        if row.checkpoint in registered and "odds" in list(row.endpoints or []):
            return _utc(row.scheduled_at)
    return None


def _event_id(subject: str, event_type: str) -> str:
    preimage = f"w2.candidate-notification.v1|{subject}|{event_type}"
    return hashlib.sha256(preimage.encode()).hexdigest()


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _seconds(value: timedelta) -> float:
    return value.total_seconds()
