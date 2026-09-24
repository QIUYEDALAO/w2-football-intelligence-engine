from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.dashboard.date_window import (
    football_day_for_kickoff,
    football_day_window,
)
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.domain.profit import profit_units_with_rebate
from w2.domain.recommendation_decision_v4 import (
    RecommendationOutcomeV4,
    validate_decision_v4_identity,
)
from w2.identity.public_competition_labels import public_competition_labels
from w2.identity.public_team_labels import reviewed_public_team_labels
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CandidateNotificationOutboxModel,
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
    ValidationSampleModel,
)
from w2.infrastructure.persistence.league_models import LeagueSeasonModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.infrastructure.persistence.models import ResultModel
from w2.prematch.evaluation_slots import evaluation_slots
from w2.prematch.lifecycle import (
    CHECKPOINT_OPPORTUNITY_SCOPE,
    CHECKPOINT_OPPORTUNITY_SEMANTICS,
    DynamicEvaluationState,
    DynamicEvaluationVersion,
    OpportunityState,
)
from w2.prematch.official_funnel import (
    official_funnel_recommendations,
    public_team_labels_for_fixtures,
)

TEST_MESSAGE = "TEST_MESSAGE"
# NOTIF-04: the three business push types plus the test message.
DAILY_CANDIDATE_LIST = "DAILY_CANDIDATE_LIST"
VALIDATION_SAMPLE_CONFIRMED = "VALIDATION_SAMPLE_CONFIRMED"
DAILY_SETTLEMENT = "DAILY_SETTLEMENT"

PENDING = "PENDING"
RETRY_PENDING = "RETRY_PENDING"
DELIVERED = "DELIVERED"
FAILED = "FAILED"
# Recorded in the outbox for audit but deliberately not pushed.
SUPPRESSED = "SUPPRESSED"

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

# NOTIF-04 timing anchors (all Beijing time).
DAILY_CANDIDATE_LIST_DEFAULT_HOUR = 14
DAILY_CANDIDATE_LIST_DEFAULT_MINUTE = 0
DAILY_CANDIDATE_LIST_ADVANCE_THRESHOLD = time(14, 30)
DAILY_CANDIDATE_LIST_ADVANCE_MINUTES = 30
DAILY_SETTLEMENT_HOUR = 11
DAILY_SETTLEMENT_MINUTE = 30
VALIDATION_SAMPLE_FALLBACK_MINUTES_BEFORE_KICKOFF = 5
# ② fallback 只补推当天（北京 12:00~次日 12:00）且开球未过 30 分钟的比赛。
VALIDATION_SAMPLE_MAX_AFTER_KICKOFF_MINUTES = 30
T15_SLOT = "T15_ODDS"

def enqueue_attempt_notification_in_session(
    session: Session,
    version: DynamicEvaluationVersion,
    *,
    recommendation_decision_v4: Mapping[str, Any] | None = None,
) -> list[str]:
    """Enqueue only the T15 final validation recommendation confirmation."""
    if (
        not _official(version)
        or version.attempt_identity_hash is None
    ):
        return []
    # Keep the existing attempt/V4 identity guard on every official evaluation.
    _v4_candidate_for_attempt(version, recommendation_decision_v4)
    if version.evaluation_slot_id != T15_SLOT:
        return []
    confirmation = enqueue_validation_sample_confirmed_in_session(
        session, fixture_id=version.fixture_id, market=version.market, now=datetime.now(UTC)
    )
    return [confirmation] if confirmation else []


def notification_health_in_session(session: Session, *, now: datetime) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(CandidateNotificationOutboxModel).where(
                CandidateNotificationOutboxModel.event_type.in_(_ALWAYS_PUSH)
            )
        )
    )
    delivered = [row for row in rows if row.delivery_status == DELIVERED]
    pending = [row for row in rows if row.delivery_status in {PENDING, RETRY_PENDING}]
    failed = [row for row in rows if row.delivery_status == FAILED]
    last_success = max((row.delivered_at for row in delivered if row.delivered_at), default=None)
    oldest_pending = min((row.created_at for row in pending), default=None)
    device_keys, configuration_error = _bark_configuration()
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
    pending_over_target = [row for row in pending if _seconds(now - _utc(row.created_at)) > 30]
    status = (
        "CHANNEL_NOT_CONFIGURED"
        if not device_keys and configuration_error is None
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
        list(
            session.scalars(
                select(CandidateNotificationOutboxModel).where(
                    CandidateNotificationOutboxModel.event_type.in_(_ALWAYS_PUSH)
                )
            )
        )
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
                + timedelta(seconds=RETRY_BACKOFF_SECONDS[row.delivery_attempt_count - 1])
            )
        else:
            delivery.pop("next_attempt_at", None)
    payload["_delivery"] = delivery
    row.payload = payload
    session.flush()


def _aware(moment: datetime) -> datetime:
    """SQLite hands back naive datetimes; production Postgres does not."""

    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


_ALWAYS_PUSH = frozenset(
    {DAILY_CANDIDATE_LIST, VALIDATION_SAMPLE_CONFIRMED, DAILY_SETTLEMENT, TEST_MESSAGE}
)


def delivery_route(row: CandidateNotificationOutboxModel) -> tuple[str, str]:
    """Only the four approved event types reach the phone."""
    if str(row.event_type) in _ALWAYS_PUSH:
        return "SEND", "ACTIONABLE"
    return "SUPPRESS", "EVENT_TYPE_RETIRED"


def deliver_pending_notifications(
    *,
    now: datetime | None = None,
    engine: Engine | None = None,
    sender: Callable[[Mapping[str, Any]], None] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Deliver due outbox rows; an absent Bark setting performs no writes."""

    resolved_now = now or datetime.now(UTC)
    device_keys, configuration_error = _bark_configuration()
    if not device_keys:
        return {
            "status": "CHANNEL_NOT_CONFIGURED" if configuration_error is None else "DEGRADED",
            "channel": BARK_CHANNEL,
            "delivered": 0,
            "failed_attempts": 0,
        }
    send = sender or _send_bark
    delivered_count = 0
    failed_count = 0
    suppressed_count = 0
    with Session(engine or create_engine()) as session:
        rows = list(
            session.scalars(
                select(CandidateNotificationOutboxModel)
                .where(
                    CandidateNotificationOutboxModel.delivery_status.in_((PENDING, RETRY_PENDING))
                )
                .order_by(CandidateNotificationOutboxModel.created_at)
            )
        )
        due_rows = [row for row in rows if _delivery_due(row, resolved_now)][: max(limit, 1)]
        for row in due_rows:
            route, reason = delivery_route(row)
            if route != "SEND":
                row.delivery_status = SUPPRESSED
                row.last_error = reason[:512]
                suppressed_count += 1
                session.commit()
                continue
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
        else "ROUTED"
        if suppressed_count
        else "IDLE",
        "channel": BARK_CHANNEL,
        "delivered": delivered_count,
        "failed_attempts": failed_count,
        "suppressed": suppressed_count,
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


def _team_name(identity: MatchdayFixtureIdentityModel, side: str) -> str:
    w2_team_id = str(getattr(identity, f"{side}_w2_team_id") or "")
    reviewed = reviewed_public_team_labels().get(w2_team_id)
    if reviewed:
        return reviewed
    payload = identity.payload if isinstance(identity.payload, dict) else {}
    teams = payload.get("teams")
    team = teams.get(side) if isinstance(teams, dict) else None
    raw_name = (
        str(team.get("name") or "").strip()
        if isinstance(team, dict)
        else str(payload.get(f"{side}_team_name") or payload.get(f"{side}_name") or "").strip()
    )
    if raw_name:
        return raw_name
    provider_id = str(getattr(identity, f"{side}_provider_team_id") or "").strip()
    return f"球队ID {provider_id}（身份未解析）" if provider_id else "球队身份未解析"


# === NOTIF-04: ① 每日候选名单 / ② 验证样本最终确认 / ③ 每日结算 ===


def _active_competitions(session: Session) -> frozenset[str]:
    return frozenset(
        str(row.competition_id)
        for row in session.scalars(select(LeagueSeasonModel))
        if isinstance(row.payload, dict) and row.payload.get("enabled") is True
    )


def _official_recommendations(
    session: Session,
    *,
    active_competitions: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """The single validation-sample authority shared by ② and ③.

    Loads the same inputs the Dashboard recommendation table reads and projects
    them through ``official_funnel_recommendations``, so the notification rows
    and the Dashboard rows can never disagree.  Withdrawn competitions are
    filtered exactly as the Dashboard filters them.
    """

    if active_competitions is None:
        active_competitions = _active_competitions(session)
    evaluations = list(
        session.scalars(
            select(DynamicPrematchEvaluationModel).where(
                DynamicPrematchEvaluationModel.official_funnel_eligible.is_(True),
                DynamicPrematchEvaluationModel.measurement_semantics
                == CHECKPOINT_OPPORTUNITY_SEMANTICS,
            )
        )
    )
    opportunities = list(session.scalars(select(DynamicPrematchOpportunityModel)))
    candidate_fixture_ids = {
        str(row.fixture_id).removeprefix("api_football:")
        for row in evaluations
        if isinstance(row.payload, dict)
        and row.payload.get("state") == "ANALYSIS_PICK_ACTIVE"
    }
    fixtures = {
        row.provider_fixture_id: row
        for row in session.scalars(
            select(MatchdayFixtureIdentityModel).where(
                MatchdayFixtureIdentityModel.provider == "api_football",
                MatchdayFixtureIdentityModel.provider_fixture_id.in_(candidate_fixture_ids),
            )
        )
    }
    canonical_ids = {str(row.fixture_id) for row in fixtures.values()}
    results = {
        str(row.fixture_id): row
        for row in session.scalars(
            select(ResultModel).where(ResultModel.fixture_id.in_(canonical_ids))
        )
    }
    team_labels = public_team_labels_for_fixtures(session, list(fixtures.values()))
    return official_funnel_recommendations(
        evaluations,
        opportunities,
        fixtures,
        results,
        team_labels,
        active_competitions=active_competitions,
    )


def _parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _official_recommendations_dashboard_scope(
    session: Session,
    *,
    active_competitions: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """工作台口径的验证样本投影（不过滤 measurement_semantics）。

    与 ``dashboard_model_forecast_validation_progress`` 上线前对
    ``official_recommendations`` 的构造一致：只过滤 official_funnel_eligible，
    队名用 ``public_team_labels_for_fixtures`` 解析。物化表与对账都用这一口径，
    确保「推荐表条数、单位合计、排序与上线前完全一致」。
    """

    if active_competitions is None:
        active_competitions = _active_competitions(session)
    evaluations = list(
        session.scalars(
            select(DynamicPrematchEvaluationModel).where(
                DynamicPrematchEvaluationModel.official_funnel_eligible.is_(True)
            )
        )
    )
    opportunities = list(session.scalars(select(DynamicPrematchOpportunityModel)))
    candidate_fixture_ids = {
        str(row.fixture_id).removeprefix("api_football:")
        for row in evaluations
        if isinstance(row.payload, dict)
        and row.payload.get("state") == "ANALYSIS_PICK_ACTIVE"
    }
    candidate_fixtures = list(
        session.scalars(
            select(MatchdayFixtureIdentityModel).where(
                MatchdayFixtureIdentityModel.provider == "api_football",
                MatchdayFixtureIdentityModel.provider_fixture_id.in_(
                    candidate_fixture_ids
                ),
            )
        )
    )
    fixtures = {row.provider_fixture_id: row for row in candidate_fixtures}
    canonical_ids = {str(row.fixture_id) for row in candidate_fixtures}
    results = {
        str(row.fixture_id): row
        for row in session.scalars(
            select(ResultModel).where(ResultModel.fixture_id.in_(canonical_ids))
        )
    }
    team_labels = public_team_labels_for_fixtures(session, candidate_fixtures)
    return official_funnel_recommendations(
        evaluations,
        opportunities,
        fixtures,
        results,
        team_labels,
        active_competitions=active_competitions,
    )


def materialize_validation_samples(
    session: Session,
    *,
    now: datetime,
    window_before_days: int = 3,
    window_after_days: int = 1,
) -> dict[str, int]:
    """Materialize the post-match validation sample set into ``validation_samples``.

    Covers fixtures whose kickoff falls in [now - window_before_days, now +
    window_after_days]. Uses the same projection 口径 as
    ``_official_funnel_recommendations``, then upserts the in-window rows and
    deletes in-window rows that are no longer samples. Rows outside the window
    are frozen and never touched.
    """

    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)
    window_start = now - timedelta(days=window_before_days)
    window_end = now + timedelta(days=window_after_days)

    # 窗口内的 api_football fixture（provider_fixture_id 为纯数字，与投影结果一致）。
    window_provider_ids = {
        str(row.provider_fixture_id)
        for row in session.scalars(
            select(MatchdayFixtureIdentityModel).where(
                MatchdayFixtureIdentityModel.provider == "api_football",
                MatchdayFixtureIdentityModel.kickoff_utc >= window_start,
                MatchdayFixtureIdentityModel.kickoff_utc < window_end,
            )
        )
    }

    # 同一口径全量投影，再按窗口过滤（口径不变；性能由每 10 分钟一次的写入承担）。
    active_competitions = _active_competitions(session)
    recommendations = _official_recommendations_dashboard_scope(
        session, active_competitions=active_competitions
    )
    window_rows = [
        row for row in recommendations if row["fixture_id"] in window_provider_ids
    ]

    # 现有窗口内的样本行（用于 upsert 与删除不再属于样本的行）。
    existing = {
        (row.fixture_id, row.market): row
        for row in session.scalars(
            select(ValidationSampleModel).where(
                ValidationSampleModel.kickoff_utc >= window_start,
                ValidationSampleModel.kickoff_utc < window_end,
            )
        )
    }

    projected_now = now
    new_keys: set[tuple[str, str]] = set()
    for row in window_rows:
        key = (row["fixture_id"], row["market"])
        new_keys.add(key)
        sample = existing.get(key)
        if sample is None:
            sample = ValidationSampleModel(
                fixture_id=row["fixture_id"],
                market=row["market"],
                selection=row["selection"],
                exact_line=row["exact_line"],
                decimal_odds=row["decimal_odds"],
                evaluation_id=row["evaluation_id"],
                settlement=row["settlement"],
                projected_at=projected_now,
            )
            session.add(sample)
        sample.competition_id = row.get("competition_id")
        sample.kickoff_utc = _parse_iso_utc(row.get("kickoff_utc"))
        sample.selection = row["selection"]
        sample.exact_line = row["exact_line"]
        sample.decimal_odds = row["decimal_odds"]
        sample.bookmaker_id = row.get("bookmaker_id")
        sample.first_checkpoint = row.get("first_checkpoint")
        sample.final_checkpoint = row.get("final_checkpoint")
        sample.evaluation_id = row["evaluation_id"]
        sample.calibration_identity = row.get("calibration_identity")
        sample.settlement = row["settlement"]
        sample.profit_units = row.get("profit_units")
        sample.score = row.get("score")
        sample.projected_at = projected_now
        sample.settled_at = _parse_iso_utc(row.get("settled_at"))
        sample.evaluated_at = _parse_iso_utc(row.get("evaluated_at"))
        sample.quote_captured_at = _parse_iso_utc(row.get("quote_captured_at"))
        sample.current_ev = row.get("current_ev")
        sample.home_team_label = row.get("home_team_label")
        sample.away_team_label = row.get("away_team_label")
        sample.later_unassessed_checkpoints = row.get("later_unassessed_checkpoints")
        sample.lifecycle_note_zh = row.get("lifecycle_note_zh")

    deleted = 0
    for key, sample in list(existing.items()):
        if key not in new_keys:
            session.delete(sample)
            deleted += 1

    session.flush()
    return {
        "window_fixtures": len(window_provider_ids),
        "window_rows": len(window_rows),
        "deleted": deleted,
    }


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sample_row_to_projection(row: ValidationSampleModel) -> dict[str, Any]:
    return {
        "evaluation_id": row.evaluation_id,
        "fixture_id": row.fixture_id,
        "evaluated_at": _iso_or_none(row.evaluated_at),
        "kickoff_utc": _iso_or_none(row.kickoff_utc),
        "market": row.market,
        "selection": row.selection,
        "exact_line": row.exact_line,
        "decimal_odds": row.decimal_odds,
        "bookmaker_id": row.bookmaker_id,
        "quote_captured_at": _iso_or_none(row.quote_captured_at),
        "current_ev": row.current_ev,
        "home_team_label": row.home_team_label or {},
        "away_team_label": row.away_team_label or {},
        "score": row.score,
        "settlement": row.settlement,
        "profit_units": row.profit_units,
        "confirmed_checkpoint": row.final_checkpoint,
        "later_unassessed_checkpoints": row.later_unassessed_checkpoints or [],
        "lifecycle_note_zh": row.lifecycle_note_zh,
        "competition_id": row.competition_id,
        "first_checkpoint": row.first_checkpoint,
        "final_checkpoint": row.final_checkpoint,
        "calibration_identity": row.calibration_identity,
        "settled_at": _iso_or_none(row.settled_at),
    }


def validation_samples_snapshot(
    session: Session,
    *,
    active_competitions: frozenset[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """从 validation_samples 物化表读取验证样本（开球时间倒序，同场让球在前）。

    取代请求路径上的全量重算。返回结构与 ``official_funnel_recommendations``
    输出一致（队名/生命周期等展示字段全部来自物化列，零 join）。
    """

    stmt = select(ValidationSampleModel)
    if active_competitions is not None:
        stmt = stmt.where(ValidationSampleModel.competition_id.in_(active_competitions))
    stmt = stmt.order_by(
        ValidationSampleModel.kickoff_utc.desc().nullslast(),
        ValidationSampleModel.fixture_id.desc(),
        case(
            (ValidationSampleModel.market == "ASIAN_HANDICAP", 0),
            (ValidationSampleModel.market == "TOTALS", 1),
            else_=99,
        ),
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    if offset:
        stmt = stmt.offset(offset)
    rows = list(session.scalars(stmt))
    return [_sample_row_to_projection(row) for row in rows]


def validation_sample_totals(
    session: Session,
    *,
    active_competitions: frozenset[str] | None = None,
) -> dict[str, Any]:
    """累计注数/单位与按 calibration_identity 拆分的汇总（由表聚合）。"""

    def _where(stmt: Any) -> Any:
        if active_competitions is not None:
            return stmt.where(ValidationSampleModel.competition_id.in_(active_competitions))
        return stmt

    totals = session.execute(
        _where(
            select(
                func.count().label("total_count"),
                func.count(ValidationSampleModel.profit_units).label("settled_count"),
                func.coalesce(func.sum(ValidationSampleModel.profit_units), 0.0).label(
                    "total_profit_units"
                ),
            )
        )
    ).one()
    by_calibration = session.execute(
        _where(
            select(
                ValidationSampleModel.calibration_identity,
                func.count().label("count"),
                func.coalesce(func.sum(ValidationSampleModel.profit_units), 0.0).label(
                    "profit_units"
                ),
            ).group_by(ValidationSampleModel.calibration_identity)
        )
    ).all()
    return {
        "total_count": totals.total_count,
        "settled_count": totals.settled_count,
        "total_profit_units": float(totals.total_profit_units),
        "by_calibration_identity": [
            {
                "calibration_identity": row.calibration_identity,
                "count": row.count,
                "profit_units": float(row.profit_units),
            }
            for row in by_calibration
        ],
    }


def _candidate_track_fixture_ids(
    session: Session,
    window: tuple[datetime, datetime],
) -> tuple[set[str], list[MatchdayFixtureIdentityModel]]:
    """Candidate-track fixtures for a football-day window.

    A fixture is on the candidate track when it has both a model-forecast
    capture and at least one registered odds evaluation plan.
    """

    identities = list(
        session.scalars(
            select(MatchdayFixtureIdentityModel)
            .where(
                MatchdayFixtureIdentityModel.kickoff_utc >= window[0],
                MatchdayFixtureIdentityModel.kickoff_utc < window[1],
            )
            .order_by(MatchdayFixtureIdentityModel.kickoff_utc)
        )
    )
    if not identities:
        return set(), []
    canonical_ids = {row.fixture_id for row in identities}
    bare_ids = {row.provider_fixture_id for row in identities}
    aliases = canonical_ids | bare_ids
    plans = list(
        session.scalars(
            select(MatchdayCheckpointPlanModel).where(
                MatchdayCheckpointPlanModel.fixture_id.in_(aliases)
            )
        )
    )
    registered = set(evaluation_slots())
    plan_fixture_ids = {
        row.fixture_id.removeprefix("api_football:")
        for row in plans
        if row.checkpoint in registered and "odds" in list(row.endpoints or [])
    }
    tracks = list(
        session.scalars(
            select(ModelForecastCaptureModel).where(
                ModelForecastCaptureModel.fixture_id.in_(aliases)
            )
        )
    )
    track_fixture_ids = {row.fixture_id.removeprefix("api_football:") for row in tracks}
    return track_fixture_ids & plan_fixture_ids, identities


def _competition_zh_name(competition_id: str | None) -> str:
    return public_competition_labels().get(
        str(competition_id or ""), str(competition_id or "未知联赛")
    )


def _daily_candidate_list_due_at(
    session: Session,
    *,
    day: date,
    candidate_fixture_ids: set[str],
) -> datetime:
    """Beijing 14:00, advanced to 30min before the earliest T3_ODDS plan if that
    plan lands before 14:30."""

    default_due = datetime.combine(
        day,
        time(DAILY_CANDIDATE_LIST_DEFAULT_HOUR, DAILY_CANDIDATE_LIST_DEFAULT_MINUTE),
        tzinfo=BEIJING,
    ).astimezone(UTC)
    if not candidate_fixture_ids:
        return default_due
    aliases = candidate_fixture_ids | {f"api_football:{item}" for item in candidate_fixture_ids}
    earliest_t3 = min(
        (
            _utc(row.scheduled_at)
            for row in session.scalars(
                select(MatchdayCheckpointPlanModel).where(
                    MatchdayCheckpointPlanModel.fixture_id.in_(aliases),
                    MatchdayCheckpointPlanModel.checkpoint == "T3_ODDS",
                )
            )
        ),
        default=None,
    )
    if earliest_t3 is None:
        return default_due
    threshold = datetime.combine(day, DAILY_CANDIDATE_LIST_ADVANCE_THRESHOLD, tzinfo=BEIJING)
    if earliest_t3.astimezone(BEIJING) < threshold:
        return earliest_t3 - timedelta(minutes=DAILY_CANDIDATE_LIST_ADVANCE_MINUTES)
    return default_due


def enqueue_daily_candidate_list_in_session(session: Session, *, now: datetime) -> str | None:
    """① 每日候选名单.  Once per football day, idempotent, N=0 still emits."""

    day = football_day_for_kickoff(now)
    window = football_day_window(day)
    candidate_ids, identities = _candidate_track_fixture_ids(session, window)
    due_at = _daily_candidate_list_due_at(
        session, day=day, candidate_fixture_ids=candidate_ids
    )
    if now < due_at:
        return None
    event_id = _event_id(day.isoformat(), DAILY_CANDIDATE_LIST)
    if session.get(CandidateNotificationOutboxModel, event_id) is not None:
        return None
    matches = [
        {
            "fixture_id": str(identity.provider_fixture_id),
            "kickoff_local_hm": _utc(identity.kickoff_utc)
            .astimezone(BEIJING)
            .strftime("%m-%d %H:%M"),
            "competition": _competition_zh_name(identity.competition_id),
            "home": _team_name(identity, "home"),
            "away": _team_name(identity, "away"),
        }
        for identity in identities
        if str(identity.provider_fixture_id) in candidate_ids
    ]
    payload = {
        "schema_version": "w2.candidate_notification.v1",
        "event_type": DAILY_CANDIDATE_LIST,
        "football_day": day.isoformat(),
        "match_count": len(matches),
        "matches": matches,
        "dashboard_url": _dashboard_day_url(day.isoformat()),
        "created_at": _iso(now),
    }
    if _insert(
        session,
        event_id=event_id,
        opportunity_identity_hash=None,
        attempt_identity_hash=None,
        event_type=DAILY_CANDIDATE_LIST,
        previous_state=None,
        current_state="PLANNED",
        payload=payload,
        created_at=now,
    ):
        return event_id
    return None


def enqueue_daily_candidate_list(
    *, now: datetime | None = None, engine: Engine | None = None
) -> list[str]:
    resolved_now = now or datetime.now(UTC)
    with Session(engine or create_engine()) as session:
        inserted = enqueue_daily_candidate_list_in_session(session, now=resolved_now)
        session.commit()
    return [inserted] if inserted else []


def _team_display_name(label: Mapping[str, Any], fallback: str) -> str:
    name = str(label.get("display_name") or label.get("raw_provider_name") or "").strip()
    return name or fallback


def enqueue_validation_sample_confirmed_in_session(
    session: Session,
    *,
    fixture_id: str,
    market: str,
    now: datetime,
) -> str | None:
    """② 验证样本最终确认.  Idempotent per fixture x market."""

    bare_fixture = str(fixture_id).removeprefix("api_football:")
    event_id = _event_id(f"{bare_fixture}|{market}", VALIDATION_SAMPLE_CONFIRMED)
    if session.get(CandidateNotificationOutboxModel, event_id) is not None:
        return None
    recommendations = _official_recommendations(session)
    row = next(
        (
            item
            for item in recommendations
            if item["fixture_id"] == bare_fixture and item["market"] == market
        ),
        None,
    )
    if row is None:
        return None
    identity = _fixture_identity(session, bare_fixture)
    kickoff = _utc(identity.kickoff_utc) if identity is not None else None
    bookmaker_id = row.get("bookmaker_id")
    payload = {
        "schema_version": "w2.candidate_notification.v1",
        "event_type": VALIDATION_SAMPLE_CONFIRMED,
        "fixture_id": bare_fixture,
        "match": {
            "home": _team_display_name(row["home_team_label"], "主队"),
            "away": _team_display_name(row["away_team_label"], "客队"),
        },
        "kickoff_local": kickoff.astimezone(BEIJING).isoformat() if kickoff else None,
        "kickoff_local_hm": (
            kickoff.astimezone(BEIJING).strftime("%m-%d %H:%M") if kickoff else "--:--"
        ),
        "market": market,
        "direction": row["selection"],
        "line": row["exact_line"],
        "decimal_odds": row["decimal_odds"],
        "bookmaker": {
            "id": bookmaker_id,
            "name": _bookmaker_name(session, bare_fixture, bookmaker_id),
        },
        "quote_captured_at": row.get("quote_captured_at"),
        "current_ev": row.get("current_ev"),
        "dashboard_url": (
            _dashboard_fixture_url(bare_fixture, kickoff) if kickoff is not None else None
        ),
        "created_at": _iso(now),
    }
    if _insert(
        session,
        event_id=event_id,
        opportunity_identity_hash=None,
        attempt_identity_hash=None,
        event_type=VALIDATION_SAMPLE_CONFIRMED,
        previous_state=None,
        current_state="CONFIRMED",
        payload=payload,
        created_at=now,
    ):
        return event_id
    return None


def enqueue_validation_sample_fallbacks_in_session(
    session: Session, *, now: datetime
) -> list[str]:
    """② fallback: at kickoff-5min, confirm any validation sample whose T15
    never produced a real evaluation."""

    recommendations = _official_recommendations(session)
    # ② fallback 只推当天比赛：开球在北京 [当日 12:00, 次日 12:00) 且开球已过
    # 不超过 30 分钟，避免调度延迟把历史样本一次性全推出去。
    day = football_day_for_kickoff(now)
    window_start, window_end = football_day_window(day)
    inserted: list[str] = []
    for row in recommendations:
        kickoff = _parse_time(row.get("kickoff_utc"))
        if kickoff is None:
            continue
        if not (window_start <= kickoff < window_end):
            continue
        if now - kickoff > timedelta(minutes=VALIDATION_SAMPLE_MAX_AFTER_KICKOFF_MINUTES):
            continue
        fallback_at = kickoff - timedelta(minutes=VALIDATION_SAMPLE_FALLBACK_MINUTES_BEFORE_KICKOFF)
        if now < fallback_at:
            continue
        event_id = enqueue_validation_sample_confirmed_in_session(
            session,
            fixture_id=row["fixture_id"],
            market=row["market"],
            now=now,
        )
        if event_id:
            inserted.append(event_id)
    return inserted


def _settlement_bucket(settlement: str) -> str:
    if settlement in {"WIN", "HALF_WIN"}:
        return "win"
    if settlement == "PUSH":
        return "push"
    return "loss"


def enqueue_daily_settlement_in_session(session: Session, *, now: datetime) -> str | None:
    """③ 每日结算.  At Beijing 11:30 for the just-closed football day."""

    now_bj = now.astimezone(BEIJING)
    if (now_bj.hour, now_bj.minute) < (DAILY_SETTLEMENT_HOUR, DAILY_SETTLEMENT_MINUTE):
        return None
    today = now_bj.date()
    settled_day = today - timedelta(days=1)
    event_id = _event_id(settled_day.isoformat(), DAILY_SETTLEMENT)
    if session.get(CandidateNotificationOutboxModel, event_id) is not None:
        return None
    active = _active_competitions(session)
    recommendations = validation_samples_snapshot(session, active_competitions=active)
    window_start, window_end = football_day_window(settled_day)

    def in_window(row: Mapping[str, Any]) -> bool:
        kickoff = _parse_time(row.get("kickoff_utc"))
        return kickoff is not None and window_start <= kickoff < window_end

    today_samples = [row for row in recommendations if in_window(row)]
    today_samples.sort(key=lambda row: str(row.get("kickoff_utc") or ""))

    # 补结算: items pending in the previous settlement that have now settled.
    prev_day = settled_day - timedelta(days=1)
    prev_event = session.scalar(
        select(CandidateNotificationOutboxModel).where(
            CandidateNotificationOutboxModel.event_type == DAILY_SETTLEMENT,
            CandidateNotificationOutboxModel.notification_event_id
            == _event_id(prev_day.isoformat(), DAILY_SETTLEMENT),
        )
    )
    settled_by_key = {
        (str(row["fixture_id"]), str(row["market"])): row
        for row in recommendations
        if row["profit_units"] is not None
    }
    supplementary: list[dict[str, Any]] = []
    if prev_event is not None:
        for pending in list((prev_event.payload or {}).get("pending") or []):
            key = (str(pending.get("fixture_id")), str(pending.get("market")))
            settled = settled_by_key.get(key)
            if settled is not None:
                supplementary.append(settled)
    supplementary.sort(key=lambda row: str(row.get("kickoff_utc") or ""))

    # 累计 = 推荐表全部已结算样本（不限日期窗口）的注数与单位合计。
    cumulative_settled = [row for row in recommendations if row["profit_units"] is not None]

    win = push = loss = 0
    total = Decimal("0")
    items: list[dict[str, Any]] = []

    def add_item(row: Mapping[str, Any], *, supplementary_flag: bool) -> None:
        nonlocal win, push, loss, total
        base = {
            "fixture_id": row["fixture_id"],
            "competition_id": row.get("competition_id"),
            "competition": _competition_zh_name(row.get("competition_id")),
            "home": _team_display_name(row["home_team_label"], "主队"),
            "away": _team_display_name(row["away_team_label"], "客队"),
            "market": row["market"],
            "direction": row["selection"],
            "line": row["exact_line"],
            "decimal_odds": row["decimal_odds"],
            "score": row["score"],
            "settlement": row["settlement"],
            "profit_units": row["profit_units"],
            "supplementary": supplementary_flag,
        }
        items.append(base)
        if row["profit_units"] is not None:
            bucket = _settlement_bucket(row["settlement"])
            if bucket == "win":
                win += 1
            elif bucket == "push":
                push += 1
            else:
                loss += 1
            total += Decimal(str(row["profit_units"]))

    # 补结算列在当天场次前。
    for row in supplementary:
        add_item(row, supplementary_flag=True)
    for row in today_samples:
        add_item(row, supplementary_flag=False)

    pending = [
        {"fixture_id": row["fixture_id"], "market": row["market"]}
        for row in today_samples
        if row["profit_units"] is None
    ]
    payload = {
        "schema_version": "w2.candidate_notification.v1",
        "event_type": DAILY_SETTLEMENT,
        "football_day": settled_day.isoformat(),
        "item_count": len(items),
        "win_count": win,
        "push_count": push,
        "loss_count": loss,
        "total_profit_units": float(total),
        "total_profit_units_with_rebate": float(profit_units_with_rebate(total, win + push + loss)),
        "cumulative_settled_count": len(cumulative_settled),
        "cumulative_profit_units": float(
            sum(Decimal(str(row["profit_units"])) for row in cumulative_settled)
        ),
        "cumulative_profit_units_with_rebate": float(
            profit_units_with_rebate(
                sum(Decimal(str(row["profit_units"])) for row in cumulative_settled),
                len(cumulative_settled),
            )
        ),
        "items": items,
        "pending": pending,
        "dashboard_url": _dashboard_day_url(settled_day.isoformat()),
        "created_at": _iso(now),
    }
    if _insert(
        session,
        event_id=event_id,
        opportunity_identity_hash=None,
        attempt_identity_hash=None,
        event_type=DAILY_SETTLEMENT,
        previous_state=None,
        current_state="SETTLED",
        payload=payload,
        created_at=now,
    ):
        return event_id
    return None


def enqueue_daily_settlement(
    *, now: datetime | None = None, engine: Engine | None = None
) -> list[str]:
    resolved_now = now or datetime.now(UTC)
    with Session(engine or create_engine()) as session:
        inserted = enqueue_daily_settlement_in_session(session, now=resolved_now)
        session.commit()
    return [inserted] if inserted else []


def enqueue_scheduled_notifications_in_session(session: Session, *, now: datetime) -> list[str]:
    """① ②(fallback) ③ scheduled enqueues, for the scheduler tick."""

    inserted: list[str] = []
    candidate = enqueue_daily_candidate_list_in_session(session, now=now)
    if candidate:
        inserted.append(candidate)
    fallbacks = enqueue_validation_sample_fallbacks_in_session(session, now=now)
    inserted.extend(fallbacks)
    settlement = enqueue_daily_settlement_in_session(session, now=now)
    if settlement:
        inserted.append(settlement)
    return inserted


def enqueue_scheduled_notifications(
    *, now: datetime | None = None, engine: Engine | None = None
) -> list[str]:
    resolved_now = now or datetime.now(UTC)
    with Session(engine or create_engine()) as session:
        inserted = enqueue_scheduled_notifications_in_session(session, now=resolved_now)
        session.commit()
    return inserted


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
    selected_candidate: Mapping[str, Any] | None,
    decision_hash: str | None,
    event_type: str,
    comparison: Mapping[str, Any] | None,
    outbox_created_at: datetime,
) -> dict[str, Any]:
    recorded_at = version.recorded_at or outbox_created_at
    value = version.as_dict()
    if selected_candidate is not None:
        value.update(
            {
                "market": selected_candidate.get("market"),
                "selection": selected_candidate.get("selection"),
                "exact_line": selected_candidate.get("exact_line"),
                "decimal_odds": selected_candidate.get("decimal_odds"),
                "bookmaker_id": selected_candidate.get("bookmaker_id"),
                "capture_id": selected_candidate.get("capture_id"),
                "capture_at": selected_candidate.get("captured_at"),
                "current_ev": selected_candidate.get("expected_value"),
            }
        )
    payload = _payload_from_mapping(
        session,
        value,
        event_type=event_type,
        created_at=outbox_created_at,
    )
    payload["source_kind"] = "IMMUTABLE_EVALUATION_ATTEMPT"
    # The attempt is the authority for the market, line and price it recommends.
    # The card-level V4 hash is retained when present as evidence, not as the
    # source of the selection.
    payload["recommendation_authority"] = "IMMUTABLE_EVALUATION_ATTEMPT"
    payload["recommendation_decision_v4_hash"] = decision_hash
    payload["evaluation_recorded_at"] = _iso(recorded_at)
    payload["outbox_created_at"] = _iso(outbox_created_at)
    payload["outbox_enqueue_latency_seconds"] = round(
        max(_seconds(outbox_created_at - recorded_at), 0.0),
        6,
    )
    if comparison is not None:
        payload["change"] = _change_details(comparison, version.as_dict())
    return payload


def _attempt_selection(version: DynamicEvaluationVersion) -> dict[str, Any] | None:
    """The recommendation as the frozen attempt recorded it.

    This is the same evidence the card-level V4 was only ever cross-checking
    against, so it is available exactly when the attempt is.
    """

    if not version.market or not version.selection or version.decimal_odds is None:
        return None
    return {
        "market": version.market,
        "selection": version.selection,
        "exact_line": version.exact_line,
        "decimal_odds": version.decimal_odds,
        "bookmaker_id": version.bookmaker_id,
        "capture_id": version.capture_id,
        "captured_at": _iso(version.capture_at) if version.capture_at is not None else None,
        "expected_value": version.current_ev,
    }


def _v4_candidate_for_attempt(
    version: DynamicEvaluationVersion,
    decision: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if decision is None:
        return None
    try:
        validate_decision_v4_identity(decision)
    except ValueError as exc:
        raise ValueError("CANDIDATE_NOTIFICATION_V4_INVALID") from exc
    if version.opportunity_state != OpportunityState.EVALUATED_CANDIDATE:
        return None
    if decision.get("outcome") not in {
        RecommendationOutcomeV4.ANALYSIS_PICK.value,
        RecommendationOutcomeV4.FORMAL_RECOMMEND.value,
    }:
        return None
    selected = decision.get("selected_candidate")
    authoritative = decision.get("authoritative_input")
    if not isinstance(selected, Mapping) or not isinstance(authoritative, Mapping):
        raise ValueError("CANDIDATE_NOTIFICATION_V4_CANDIDATE_MISSING")
    mainline = authoritative.get("canonical_mainline_identity")
    mainline = mainline if isinstance(mainline, Mapping) else {}
    fixture_id = str(version.fixture_id).removeprefix("api_football:")
    decision_fixture_id = str(decision.get("fixture_id") or "").removeprefix(
        "api_football:"
    )
    if fixture_id != decision_fixture_id:
        raise ValueError(
            "CANDIDATE_NOTIFICATION_V4_ATTEMPT_IDENTITY_MISMATCH:fixture_id"
        )
    if version.market != selected.get("market"):
        return None
    mismatches = [
        field
        for field, current, frozen in (
            (
                "selection",
                str(version.selection).removesuffix("_AH"),
                selected.get("selection"),
            ),
            ("exact_line", _float(version.exact_line), _float(selected.get("exact_line"))),
            ("decimal_odds", _float(version.decimal_odds), _float(selected.get("decimal_odds"))),
            ("bookmaker_id", version.bookmaker_id, selected.get("bookmaker_id")),
            ("capture_id", version.capture_id, selected.get("capture_id")),
            (
                "quote_identity_hash",
                version.quote_identity_hash,
                mainline.get("quote_identity_hash"),
            ),
        )
        if current != frozen
    ]
    if mismatches:
        raise ValueError(
            "CANDIDATE_NOTIFICATION_V4_ATTEMPT_IDENTITY_MISMATCH:"
            + ",".join(mismatches)
        )
    return selected


def _payload_from_mapping(
    session: Session,
    value: Mapping[str, Any],
    *,
    event_type: str,
    created_at: datetime,
) -> dict[str, Any]:
    fixture_id = str(value.get("fixture_id") or "").removeprefix("api_football:")
    identity = _fixture_identity(session, fixture_id)
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
        "competition_id": identity.competition_id if identity else None,
        "competition": _competition_zh_name(identity.competition_id) if identity else "未知联赛",
        "match": {
            "home": _team_name(identity, "home") if identity else "主队（身份未解析）",
            "away": _team_name(identity, "away") if identity else "客队（身份未解析）",
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
    line = _format_line(payload.get("line"))
    direction = _direction_label(payload.get("direction"))
    odds = _format_odds(payload.get("decimal_odds"))
    kickoff = _parse_time(payload.get("kickoff_local"))

    if event_type == DAILY_CANDIDATE_LIST:
        day_str = str(payload.get("football_day") or "")
        count = int(payload.get("match_count") or 0)
        try:
            day = date.fromisoformat(day_str)
            day_label = f"{day.month}月{day.day}日"
        except ValueError:
            day_label = day_str or "未知日期"
        title = f"[今日候选] {day_label} 共 {count} 场待评估"
    elif event_type == VALIDATION_SAMPLE_CONFIRMED:
        competition = str(payload.get("competition") or payload.get("league") or "未知联赛")
        kickoff_time = kickoff.astimezone(BEIJING).strftime("%H:%M") if kickoff else "--:--"
        title = f"[推荐] {competition} {home}vs{away} {kickoff_time} {direction}{line} @{odds}"
    elif event_type == DAILY_SETTLEMENT:
        day_str = str(payload.get("football_day") or "")
        try:
            settled_day = date.fromisoformat(day_str)
            day_label = f"{settled_day.month}月{settled_day.day}日"
        except ValueError:
            day_label = day_str or "未知日期"
        if int(payload.get("item_count", 0) or 0) == 0:
            title = f"[结算] {day_label} 当天无推荐"
        else:
            title = (
                f"[结算] {day_label} {int(payload.get('item_count') or 0)}场 "
                f"{int(payload.get('win_count') or 0)}赢 "
                f"{int(payload.get('loss_count') or 0)}输"
            )
    elif event_type == TEST_MESSAGE:
        title = "[测试] W2 Bark 通道"
    else:
        raise ValueError("NOTIFICATION_EVENT_TYPE_RETIRED")

    body = _message_body(payload)
    result = {"title": title, "body": body}
    dashboard_url = str(payload.get("dashboard_url") or "")
    if dashboard_url.startswith(("https://", "http://")):
        result["url"] = dashboard_url
    elif dashboard_url:
        result["body"] = f"{body}\n{dashboard_url}" if body else dashboard_url
    return result


def _send_bark(payload: Mapping[str, Any]) -> None:
    device_keys, configuration_error = _bark_configuration()
    if not device_keys:
        raise RuntimeError(configuration_error or "CHANNEL_NOT_CONFIGURED")
    endpoint = os.environ["W2_BARK_ENDPOINT"].rstrip("/")
    message = render_bark_message(payload)
    request_payload: dict[str, Any] = {
        "title": message["title"],
        "body": message["body"],
        "group": "W2候选",
        "level": "timeSensitive",
    }
    if message.get("url"):
        request_payload["url"] = message["url"]
    if len(device_keys) == 1:
        _post_bark_device(endpoint, {**request_payload, "device_key": device_keys[0]})
        return
    delivery = dict(_as_mapping(payload.get("_delivery")))
    successful_key_hashes = set(delivery.get("successful_device_key_hashes") or [])
    failures: list[str] = []
    for device_key in device_keys:
        key_hash = hashlib.sha256(device_key.encode("utf-8")).hexdigest()
        if key_hash in successful_key_hashes:
            continue
        try:
            _post_bark_device(endpoint, {**request_payload, "device_key": device_key})
        except Exception as exc:  # attempt every device before failing the outbox delivery
            failures.append(_delivery_exception_name(exc))
        else:
            successful_key_hashes.add(key_hash)
    if isinstance(payload, dict):
        payload["_delivery"] = {
            **delivery,
            "successful_device_key_hashes": sorted(successful_key_hashes),
        }
    if failures:
        raise RuntimeError(
            f"BARK_DEVICE_DELIVERY_FAILED:{len(failures)}/{len(device_keys)}:{failures[0]}"
        )


def _post_bark_device(endpoint: str, request_payload: Mapping[str, Any]) -> None:
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


def _bark_configuration() -> tuple[list[str], str | None]:
    endpoint = os.environ.get("W2_BARK_ENDPOINT", "").strip()
    device_keys_raw = os.environ.get("W2_BARK_DEVICE_KEY", "")
    if not endpoint or not device_keys_raw.strip():
        return [], None
    device_keys = [key.strip() for key in device_keys_raw.split(",")]
    if any(not key for key in device_keys):
        return [], "BARK_DEVICE_KEY_INVALID"
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or "@" in parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        return [], "BARK_ENDPOINT_INVALID"
    return device_keys, None


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
    if event_type == DAILY_CANDIDATE_LIST:
        lines = [
            "以下比赛将在开球前 3 小时起评估，开球前 15 分钟确定的推荐会逐条推送"
        ]
        for item in payload.get("matches") or []:
            if not isinstance(item, Mapping):
                continue
            lines.append(
                f"{item.get('kickoff_local_hm', '--:--')} {item.get('competition', '')} "
                f"{item.get('home', '主队')} vs {item.get('away', '客队')}"
            )
        return "\n".join(lines)
    if event_type == VALIDATION_SAMPLE_CONFIRMED:
        bookmaker = _as_mapping(payload.get("bookmaker"))
        return "\n".join(
            (
                f"推荐 {_market_label(payload.get('market'))} "
                f"{_format_line(payload.get('line'))} · "
                f"{_direction_label(payload.get('direction'))} / "
                f"赔率 {_format_odds(payload.get('decimal_odds'))} · "
                f"EV {_format_ev(payload.get('current_ev'))}",
                f"机构：{bookmaker.get('name') or bookmaker.get('id') or '未知'}",
                f"报价时间：{payload.get('quote_captured_at') or '未知'}",
            )
        )
    if event_type == DAILY_SETTLEMENT:
        cumulative_pure = payload.get("cumulative_profit_units") or 0
        cumulative_with_rebate = payload.get("cumulative_profit_units_with_rebate")
        if cumulative_with_rebate is None:
            cumulative_with_rebate = profit_units_with_rebate(
                cumulative_pure, int(payload.get("cumulative_settled_count") or 0)
            )
        total_pure = payload.get("total_profit_units") or 0
        total_with_rebate = payload.get("total_profit_units_with_rebate")
        if total_with_rebate is None:
            total_with_rebate = profit_units_with_rebate(
                total_pure,
                sum(
                    int(payload.get(key) or 0)
                    for key in ("win_count", "push_count", "loss_count")
                ),
            )
        lines = [
            f"累计：{payload.get('cumulative_settled_count', 0)} 注 "
            f"{_format_settlement_units(cumulative_pure)} 单位"
        ]
        lines.append(
            f"纯盈亏 {_format_settlement_units(cumulative_pure)} · 含返水 "
            f"{_format_settlement_units(cumulative_with_rebate)} 单位"
        )
        for item in payload.get("items") or []:
            if not isinstance(item, Mapping):
                continue
            direction = _settlement_direction(item.get("market"), item.get("direction"))
            line = _format_line(item.get("line"))
            odds = _format_odds(item.get("decimal_odds"))
            score = str(item.get("score") or "--")
            prefix = "补结算 " if item.get("supplementary") else ""
            if item.get("profit_units") is None:
                result = "待结算"
            else:
                result = (
                    f"{_settlement_short_label(item.get('settlement'))} "
                    f"{_format_settlement_units(item.get('profit_units'))}"
                )
            lines.append(
                f"{prefix}{item.get('competition', '未知联赛')} "
                f"{item.get('home', '主队')} vs {item.get('away', '客队')}　"
                f"推荐 {direction} {line} @{odds}　比分 {score}　{result}"
            )
        lines.append(
            f"当天：{payload.get('item_count', 0)} 注　"
            f"赢 {payload.get('win_count', 0)} / 走水 {payload.get('push_count', 0)} / "
            f"输 {payload.get('loss_count', 0)}　"
            f"纯盈亏 {_format_settlement_units(total_pure)} · "
            f"含返水 {_format_settlement_units(total_with_rebate)} 单位"
        )
        return "\n".join(lines)
    if event_type == TEST_MESSAGE:
        return "W2 Bark 外发通道测试消息"
    raise ValueError("NOTIFICATION_EVENT_TYPE_RETIRED")

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


def _opportunity_state_label(value: Any) -> str:
    raw = str(value or "")
    return {
        OpportunityState.EVALUATED_CANDIDATE.value: "已形成候选",
        OpportunityState.EVALUATED_NO_EDGE.value: "已评估无优势",
        OpportunityState.BLOCKED_BY_GATE.value: "门禁阻断",
        OpportunityState.MISSED_CHECKPOINT.value: "检查点错过",
        OpportunityState.EVALUATION_ERROR.value: "评估错误",
    }.get(raw, raw or "未知")


def _settlement_label(value: Any) -> str:
    return {
        "WIN": "赢",
        "HALF_WIN": "赢一半",
        "PUSH": "走盘",
        "HALF_LOSS": "输一半",
        "LOSS": "输",
        "VOID": "作废",
        "RESULT_NOT_COLLECTED": "赛果未采集",
        "SETTLEMENT_ERROR": "无法结算",
    }.get(str(value or ""), str(value or "未知"))


def _settlement_short_label(value: Any) -> str:
    """NOTIF-04 ③ wording: 赢/赢半/走水/输半/输."""

    return {
        "WIN": "赢",
        "HALF_WIN": "赢半",
        "PUSH": "走水",
        "HALF_LOSS": "输半",
        "LOSS": "输",
        "VOID": "作废",
        "RESULT_NOT_COLLECTED": "待结算",
        "SETTLEMENT_ERROR": "无法结算",
        "PENDING": "待结算",
    }.get(str(value or ""), str(value or "未知"))


def _settlement_direction(market: Any, value: Any) -> str:
    """③ 结算行方向：让球「主队/客队」、大小球「大/小」."""

    raw = str(value or "")
    if str(market) == "TOTALS":
        if raw.startswith("OVER"):
            return "大"
        if raw.startswith("UNDER"):
            return "小"
    if raw.startswith("HOME"):
        return "主队"
    if raw.startswith("AWAY"):
        return "客队"
    return raw or "方向未知"


def _mm_dd(day: str) -> str:
    return day[5:] if len(day) >= 10 else day


def _closeout_recommendation_line(item: Mapping[str, Any]) -> str:
    selection = _direction_label(item.get("direction"))
    recommendation = (
        f"{item.get('competition', '未知联赛')} "
        f"{item.get('home', '主队')} vs {item.get('away', '客队')} "
        f"{_market_label(item.get('market'))}{_format_line(item.get('line'))} "
        f"{selection} @{_format_odds(item.get('decimal_odds'))}"
    )
    if item.get("settlement") == "RESULT_NOT_COLLECTED":
        return f"{recommendation}：赛果未采集"
    return (
        f"{recommendation}：{item.get('score') or '无比分'} · "
        f"{_settlement_label(item.get('settlement'))} · "
        f"{_format_units(item.get('profit_units'))} 单位"
    )


def _format_duration(value: Any) -> str:
    seconds = _float(value)
    if seconds is None:
        return "未知"
    total = max(int(seconds), 0)
    if total < 60:
        return f"{total} 秒"
    minutes, remainder = divmod(total, 60)
    if minutes < 10:
        return f"{minutes} 分 {remainder} 秒"
    if minutes < 60:
        return f"{minutes} 分钟"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 小时 {minutes} 分钟"


def _format_units(value: Any) -> str:
    number = _float(value)
    if number is None:
        return "未知"
    return f"{number:+.3f}" if number else "0.000"


def _format_settlement_units(value: Any) -> str:
    """③ 结算单位：两位小数（如 +1.05 / -1.00）。"""

    number = _float(value)
    if number is None:
        return "未知"
    return f"{number:+.2f}"


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
    ev_change = abs(new_ev - old_ev) if old_ev is not None and new_ev is not None else None
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


def _fixture_identity(session: Session, fixture_id: str) -> MatchdayFixtureIdentityModel | None:
    return session.scalar(
        select(MatchdayFixtureIdentityModel)
        .where(
            MatchdayFixtureIdentityModel.fixture_id.in_((fixture_id, f"api_football:{fixture_id}"))
        )
        .order_by(MatchdayFixtureIdentityModel.captured_at.desc())
        .limit(1)
    )


def _bookmaker_name(session: Session, fixture_id: str, bookmaker_id: str | None) -> str | None:
    if not bookmaker_id:
        return None
    return (
        session.scalar(
            select(MatchdayMarketObservationModel.bookmaker_name)
            .where(
                MatchdayMarketObservationModel.fixture_id.in_(
                    (fixture_id, f"api_football:{fixture_id}")
                ),
                MatchdayMarketObservationModel.bookmaker_id == bookmaker_id,
            )
            .order_by(MatchdayMarketObservationModel.captured_at.desc())
            .limit(1)
        )
        or bookmaker_id
    )


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
            MatchdayCheckpointPlanModel.fixture_id.in_((fixture_id, f"api_football:{fixture_id}")),
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
