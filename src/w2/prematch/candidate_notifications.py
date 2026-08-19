from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.dashboard.date_window import football_day_for_kickoff
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

    events: list[tuple[str, DynamicPrematchEvaluationModel | None]] = []
    if current_state == OpportunityState.EVALUATED_CANDIDATE:
        if previous_candidate is None:
            events.append((CANDIDATE_FORMED, None))
        elif previous is None or _opportunity_state(previous) != "EVALUATED_CANDIDATE":
            events.append((CANDIDATE_MATERIAL_CHANGE, previous_candidate))
        elif _materially_changed(previous.payload, version.as_dict()):
            events.append((CANDIDATE_MATERIAL_CHANGE, previous))
        if version.evaluation_slot_id == T30_SLOT and previous_candidate is not None:
            events.append((CANDIDATE_T30_CONFIRMED, previous_candidate))
    elif previous is not None and _opportunity_state(previous) == "EVALUATED_CANDIDATE":
        events.append((CANDIDATE_WITHDRAWN, previous))

    inserted: list[str] = []
    for event_type, comparison in events:
        outbox_created_at = datetime.now(UTC)
        payload = _attempt_payload(
            session,
            version,
            event_type=event_type,
            comparison=(comparison.payload if comparison is not None else None),
            outbox_created_at=outbox_created_at,
        )
        event_id = _event_id(version.attempt_identity_hash, event_type)
        if _insert(
            session,
            event_id=event_id,
            opportunity_identity_hash=version.opportunity_identity_hash,
            attempt_identity_hash=version.attempt_identity_hash,
            event_type=event_type,
            previous_state=_opportunity_state(comparison) if comparison is not None else None,
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
    return {
        "status": "CHANNEL_NOT_CONFIGURED"
        if not os.environ.get("W2_CANDIDATE_NOTIFICATION_CHANNEL")
        else "DEGRADED"
        if failed or any(_seconds(now - row.created_at) > 30 for row in pending)
        else "READY",
        "channel": os.environ.get("W2_CANDIDATE_NOTIFICATION_CHANNEL") or None,
        "last_successful_delivery_at": _iso(last_success) if last_success else None,
        "failure_count": sum(
            max(row.delivery_attempt_count - int(row.delivery_status == DELIVERED), 0)
            for row in rows
        ),
        "retry_count": sum(max(row.delivery_attempt_count - 1, 0) for row in rows),
        "pending_backlog": len(pending),
        "oldest_pending_age_seconds": (
            round(_seconds(now - oldest_pending), 3) if oldest_pending else None
        ),
        "outbox_enqueue_slo_breach_count": sum(
            float((row.payload or {}).get("outbox_enqueue_latency_seconds") or 0) > 5
            for row in rows
        ),
        "delivery_target_breach_count": sum(
            _seconds(now - row.created_at) > 30 for row in pending
        ),
        "delivery_slo_breach_count": sum(
            _seconds(now - row.created_at) > 60 for row in pending
        ),
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
    if delivered:
        row.delivery_status = DELIVERED
        row.delivered_at = attempted_at
        row.last_error = None
    else:
        row.delivery_status = RETRY_PENDING if retryable else FAILED
        row.last_error = (error or "DELIVERY_FAILED")[:512]
    session.flush()


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

    inserted: list[str] = []
    t3_plans = [row for row in evaluation_plans if row.checkpoint == "T3_ODDS"]
    if t3_plans:
        first_t3 = min(_utc(row.scheduled_at) for row in t3_plans)
        plan_summary_due_at = first_t3 - timedelta(minutes=15)
        event_id = _event_id(window.operational_day_key, PLAN_SUMMARY)
        planned_opportunities = sum(
            2
            * track_count_by_fixture.get(
                row.fixture_id.removeprefix("api_football:"),
                0,
            )
            for row in evaluation_plans
        )
        if plan_summary_due_at <= now < first_t3 and _insert(
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
                "summary_timing": "BEFORE_FIRST_T3",
                "summary_due_at": _iso(plan_summary_due_at),
                "monitoring_fixture_count": len(identities),
                "model_track_ready_fixture_count": len(track_fixture_ids),
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
                "created_at": _iso(now),
            },
            created_at=now,
        ):
            inserted.append(event_id)

    t15_plans = [row for row in evaluation_plans if row.checkpoint == "T15_ODDS"]
    closeout_due_at = (
        max(_utc(row.window_end) for row in t15_plans)
        if t15_plans
        else max(_utc(row.kickoff_utc) for row in identities)
    )
    # Do not turn deployment into a historical summary backfill. The scheduler
    # checks every 30 seconds, so a five-minute forward-only window tolerates a
    # restart without rewriting an already closed football day.
    if closeout_due_at <= now <= closeout_due_at + timedelta(minutes=5):
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
                "zero_candidate_reason_by_market": reason_by_market,
                "zero_candidate_is_not_delivery_health": True,
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


def _seconds(value: timedelta) -> float:
    return value.total_seconds()
