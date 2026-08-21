from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, and_, func, literal, or_, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerRunStateModel
from w2.prematch.read_model_projection import ANALYSIS_CARD_SHADOW_PREFIX

STATE_KEY = "forward_outcome_ledger"
NEAR_CHECKPOINTS = (
    "T60_ODDS_LINEUPS",
    "T45_ODDS",
    "T45_LINEUPS_RETRY",
    "T-30m_VALIDATION_LOCK",
    "T30_LINEUPS_RETRY",
    "T15_ODDS",
)
ACTIVE_STATUSES = frozenset({"QUEUED", "RUNNING"})


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    normalized = _utc(value)
    return normalized.isoformat().replace("+00:00", "Z") if normalized else None


def _env_seconds(name: str, default: int) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), 1)
    except ValueError:
        return default


def _env_nonnegative_int(name: str, default: int) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), 0)
    except ValueError:
        return default


@dataclass(frozen=True)
class DispatchDecision:
    status: str
    task_id: str | None
    reason: str | None
    consecutive_deferrals: int
    pending_settlement_count: int
    forced: bool = False


@dataclass(frozen=True)
class IncrementalWork:
    analysis_fixture_ids: tuple[str, ...]
    result_fixture_ids: tuple[str, ...]
    source_cursor: dict[str, Any]


class OutcomeLedgerRuntimeRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine()

    def prepare_dispatch(
        self,
        *,
        now: datetime,
        task_id: str,
        pending_settlement_count: int | None = None,
    ) -> DispatchDecision:
        reference = _utc(now)
        if reference is None:
            raise ValueError("now is required")
        with Session(self.engine) as session:
            state = self._locked_state(session, reference)
            updated_at = _utc(state.updated_at) or reference
            active_stale_after = _env_seconds("W2_OUTCOME_LEDGER_ACTIVE_STALE_SECONDS", 1800)
            if (
                state.status in ACTIVE_STATUSES
                and (reference - updated_at).total_seconds() < active_stale_after
            ):
                return DispatchDecision(
                    status="ACTIVE_OR_RESERVED",
                    task_id=state.active_task_id,
                    reason=state.status,
                    consecutive_deferrals=state.consecutive_deferrals,
                    pending_settlement_count=state.pending_settlement_count,
                )

            defer_reason = self._prematch_defer_reason(session, reference)
            defer_started = _utc(state.defer_started_at)
            max_delay = _env_seconds("W2_OUTCOME_LEDGER_MAX_DEFER_SECONDS", 1800)
            max_count = _env_seconds("W2_OUTCOME_LEDGER_MAX_CONSECUTIVE_DEFERRALS", 3)
            elapsed = (reference - defer_started).total_seconds() if defer_started else 0
            forced = bool(
                defer_reason
                and (
                    state.consecutive_deferrals >= max_count
                    or (defer_started is not None and elapsed >= max_delay)
                )
            )
            if defer_reason and not forced:
                state.status = "DEFERRED_FOR_PREMATCH_CHECKPOINT"
                state.active_task_id = None
                state.defer_started_at = defer_started or reference
                state.consecutive_deferrals += 1
                state.last_defer_reason = defer_reason
                if pending_settlement_count is not None:
                    state.pending_settlement_count = pending_settlement_count
                state.updated_at = reference
                session.commit()
                return DispatchDecision(
                    status=state.status,
                    task_id=None,
                    reason=defer_reason,
                    consecutive_deferrals=state.consecutive_deferrals,
                    pending_settlement_count=state.pending_settlement_count,
                )

            state.status = "QUEUED"
            state.active_task_id = task_id
            state.queued_at = reference
            state.started_at = None
            state.completed_at = None
            if pending_settlement_count is not None:
                state.pending_settlement_count = pending_settlement_count
            state.last_error = None
            state.updated_at = reference
            session.commit()
            return DispatchDecision(
                status="QUEUED",
                task_id=task_id,
                reason=defer_reason if forced else None,
                consecutive_deferrals=state.consecutive_deferrals,
                pending_settlement_count=state.pending_settlement_count,
                forced=forced,
            )

    def mark_running(self, *, task_id: str, now: datetime) -> bool:
        reference = _utc(now)
        if reference is None:
            raise ValueError("now is required")
        with Session(self.engine) as session:
            state = self._locked_state(session, reference)
            if state.status != "QUEUED" or state.active_task_id != task_id:
                return False
            state.status = "RUNNING"
            state.started_at = reference
            state.updated_at = reference
            session.commit()
            return True

    def mark_failed(self, *, task_id: str, error: str, now: datetime) -> None:
        self._finish(task_id=task_id, now=now, status="FAILED", error=error)

    def mark_succeeded(
        self,
        *,
        task_id: str,
        now: datetime,
        source_cursor: dict[str, Any],
        pending_settlement_count: int,
    ) -> None:
        self._finish(
            task_id=task_id,
            now=now,
            status="SUCCEEDED",
            source_cursor=source_cursor,
            pending_settlement_count=pending_settlement_count,
        )

    def mark_queue_failed(self, *, task_id: str, error: str, now: datetime) -> None:
        self._finish(task_id=task_id, now=now, status="FAILED", error=error)

    def incremental_work(
        self,
        *,
        now: datetime | None = None,
        horizon: timedelta = timedelta(days=7),
    ) -> IncrementalWork:
        reference = _utc(now or datetime.now(UTC))
        if reference is None:
            raise ValueError("now is required")
        with Session(self.engine) as session:
            state = session.get(OutcomeLedgerRunStateModel, STATE_KEY)
            cursor = dict(state.source_cursor) if state is not None else {}
            analysis_fixture_ids, analysis_cursor = self._changed_analysis_fixture_ids(
                session,
                cursor,
                start=reference,
                end=reference + horizon,
            )
            fixture_ids, capture_cursor = self._changed_fixture_captures(session, cursor)
            result_ids, result_cursor = self._changed_results(session, cursor)
            pending_ids = cursor.get("pending_result_fixture_ids")
            pending_fixture_ids = (
                [str(item) for item in pending_ids if str(item)]
                if isinstance(pending_ids, list)
                else []
            )
        return IncrementalWork(
            analysis_fixture_ids=tuple(analysis_fixture_ids),
            result_fixture_ids=tuple(
                sorted(set(fixture_ids) | set(result_ids) | set(pending_fixture_ids))
            ),
            source_cursor={**cursor, **analysis_cursor, **capture_cursor, **result_cursor},
        )

    def health(self, *, now: datetime | None = None) -> dict[str, Any]:
        reference = _utc(now or datetime.now(UTC))
        if reference is None:
            raise ValueError("now is required")
        with Session(self.engine) as session:
            state = session.get(OutcomeLedgerRunStateModel, STATE_KEY)
        if state is None:
            return {
                "status": "DEGRADED",
                "reason_codes": ["OUTCOME_LEDGER_NEVER_SCHEDULED"],
                "run_status": "UNKNOWN",
                "consecutive_deferrals": 0,
                "seconds_since_last_success": None,
                "pending_settlement_count": 0,
            }
        last_success = _utc(state.last_success_at)
        success_age = int((reference - last_success).total_seconds()) if last_success else None
        max_age = _env_seconds("W2_OUTCOME_LEDGER_SUCCESS_MAX_AGE_SECONDS", 1800)
        pending_limit = _env_nonnegative_int("W2_OUTCOME_LEDGER_PENDING_DEGRADED_COUNT", 0)
        max_deferrals = _env_seconds("W2_OUTCOME_LEDGER_MAX_CONSECUTIVE_DEFERRALS", 3)
        reasons = []
        if success_age is None:
            reasons.append("OUTCOME_LEDGER_NEVER_SUCCEEDED")
        elif success_age > max_age:
            reasons.append("OUTCOME_LEDGER_SUCCESS_STALE")
        if state.consecutive_deferrals >= max_deferrals:
            reasons.append("OUTCOME_LEDGER_DEFERRAL_LIMIT_REACHED")
        if state.pending_settlement_count > pending_limit:
            reasons.append("OUTCOME_LEDGER_SETTLEMENT_BACKLOG")
        if state.status == "FAILED":
            reasons.append("OUTCOME_LEDGER_LAST_RUN_FAILED")
        return {
            "status": "DEGRADED" if reasons else "READY",
            "reason_codes": reasons,
            "run_status": state.status,
            "active_task_id": state.active_task_id,
            "consecutive_deferrals": state.consecutive_deferrals,
            "defer_started_at": _iso(state.defer_started_at),
            "last_defer_reason": state.last_defer_reason,
            "last_successful_run_at": _iso(last_success),
            "seconds_since_last_success": success_age,
            "pending_settlement_count": state.pending_settlement_count,
            "last_error": state.last_error,
            "thresholds": {
                "max_consecutive_deferrals": max_deferrals,
                "max_seconds_since_success": max_age,
                "pending_settlement_count": pending_limit,
            },
        }

    def _finish(
        self,
        *,
        task_id: str,
        now: datetime,
        status: str,
        error: str | None = None,
        source_cursor: dict[str, Any] | None = None,
        pending_settlement_count: int | None = None,
    ) -> None:
        reference = _utc(now)
        if reference is None:
            raise ValueError("now is required")
        with Session(self.engine) as session:
            state = self._locked_state(session, reference)
            if state.active_task_id != task_id:
                return
            state.status = status
            state.active_task_id = None
            state.completed_at = reference
            state.last_error = error
            state.updated_at = reference
            if source_cursor is not None:
                state.source_cursor = source_cursor
            if pending_settlement_count is not None:
                state.pending_settlement_count = pending_settlement_count
            if status == "SUCCEEDED":
                state.last_success_at = reference
                state.defer_started_at = None
                state.consecutive_deferrals = 0
                state.last_defer_reason = None
            session.commit()

    def _locked_state(
        self,
        session: Session,
        now: datetime,
    ) -> OutcomeLedgerRunStateModel:
        state = session.scalar(
            select(OutcomeLedgerRunStateModel)
            .where(OutcomeLedgerRunStateModel.state_key == STATE_KEY)
            .with_for_update()
        )
        if state is None:
            state = OutcomeLedgerRunStateModel(
                state_key=STATE_KEY,
                status="IDLE",
                consecutive_deferrals=0,
                pending_settlement_count=0,
                source_cursor={},
                updated_at=now,
            )
            session.add(state)
            session.flush()
        return state

    @staticmethod
    def _prematch_defer_reason(session: Session, now: datetime) -> str | None:
        due_count = int(
            session.scalar(
                select(func.count())
                .select_from(MatchdayCheckpointPlanModel)
                .where(
                    MatchdayCheckpointPlanModel.status == "DUE",
                    MatchdayCheckpointPlanModel.checkpoint != "POSTMATCH_RESULT",
                    MatchdayCheckpointPlanModel.test_only.is_(False),
                )
            )
            or 0
        )
        if due_count:
            return "UNFINISHED_PREMATCH_DUE"
        next_window = session.scalar(
            select(func.min(MatchdayCheckpointPlanModel.window_start)).where(
                MatchdayCheckpointPlanModel.status.in_(("PLANNED", "DUE")),
                MatchdayCheckpointPlanModel.checkpoint.in_(NEAR_CHECKPOINTS),
                MatchdayCheckpointPlanModel.window_start >= now,
                MatchdayCheckpointPlanModel.window_start < now + timedelta(minutes=5),
                MatchdayCheckpointPlanModel.test_only.is_(False),
            )
        )
        return "PREMATCH_WINDOW_WITHIN_5_MINUTES" if next_window is not None else None

    @staticmethod
    def _changed_analysis_fixture_ids(
        session: Session,
        cursor: dict[str, Any],
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[list[str], dict[str, Any]]:
        previous = cursor.get("analysis_sources")
        previous_sources = dict(previous) if isinstance(previous, dict) else {}
        checkpoint_identity = (
            literal(ANALYSIS_CARD_SHADOW_PREFIX)
            + MatchdayFixtureIdentityModel.provider_fixture_id
        )
        rows = list(
            session.execute(
                select(ReadModelCheckpointModel)
                .join(
                    MatchdayFixtureIdentityModel,
                    ReadModelCheckpointModel.checkpoint_key == checkpoint_identity,
                )
                .where(
                    MatchdayFixtureIdentityModel.kickoff_utc >= start,
                    MatchdayFixtureIdentityModel.kickoff_utc < end,
                )
                .order_by(ReadModelCheckpointModel.checkpoint_key)
            )
        )
        fixture_ids = []
        current_sources: dict[str, str] = {}
        for (row,) in rows:
            current_sources[row.checkpoint_key] = row.source_hash
            if previous_sources.get(row.checkpoint_key) == row.source_hash:
                continue
            fixture_id = row.checkpoint_key.removeprefix(ANALYSIS_CARD_SHADOW_PREFIX)
            fixture_ids.append(fixture_id)
        return fixture_ids, {"analysis_sources": current_sources}

    @staticmethod
    def _changed_fixture_captures(
        session: Session,
        cursor: dict[str, Any],
    ) -> tuple[list[str], dict[str, str]]:
        since = _parse_cursor_time(cursor.get("fixture_capture_at"))
        since_id = str(cursor.get("fixture_capture_id") or "")
        statement = select(MatchdayEndpointCaptureModel).where(
            MatchdayEndpointCaptureModel.endpoint == "fixtures",
            MatchdayEndpointCaptureModel.fixture_id.is_not(None),
        )
        if since is not None:
            statement = statement.where(
                or_(
                    MatchdayEndpointCaptureModel.provider_captured_at > since,
                    and_(
                        MatchdayEndpointCaptureModel.provider_captured_at == since,
                        MatchdayEndpointCaptureModel.capture_id > since_id,
                    ),
                )
            )
        rows = list(
            session.scalars(
                statement.order_by(
                    MatchdayEndpointCaptureModel.provider_captured_at,
                    MatchdayEndpointCaptureModel.capture_id,
                )
            )
        )
        if not rows:
            return [], {}
        last = rows[-1]
        return [str(row.fixture_id) for row in rows if row.fixture_id], {
            "fixture_capture_at": _iso(last.provider_captured_at) or "",
            "fixture_capture_id": last.capture_id,
        }

    @staticmethod
    def _changed_results(
        session: Session,
        cursor: dict[str, Any],
    ) -> tuple[list[str], dict[str, str]]:
        since = _parse_cursor_time(cursor.get("result_confirmed_at"))
        since_id = str(cursor.get("result_fixture_id") or "")
        statement = select(ResultModel)
        if since is not None:
            statement = statement.where(
                or_(
                    ResultModel.confirmed_at > since,
                    and_(
                        ResultModel.confirmed_at == since,
                        ResultModel.fixture_id > since_id,
                    ),
                )
            )
        rows = list(
            session.scalars(
                statement.order_by(ResultModel.confirmed_at, ResultModel.fixture_id)
            )
        )
        if not rows:
            return [], {}
        last = rows[-1]
        return [row.fixture_id for row in rows], {
            "result_confirmed_at": _iso(last.confirmed_at) or "",
            "result_fixture_id": last.fixture_id,
        }


def _parse_cursor_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def outcome_ledger_runtime_health() -> dict[str, Any]:
    return OutcomeLedgerRuntimeRepository().health()
