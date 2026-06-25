from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.config import Settings
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.stage7i_lifecycle_models import (
    Stage7ILifecycleEventModel,
    Stage7ILifecycleHeartbeatModel,
    Stage7ILifecycleRunModel,
)

TERMINAL_STATUSES = {"COMPLETED", "FAILED", "NON_QUALIFYING"}


class Stage7ISupervisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Stage7IFinalAudit:
    status: str
    blockers: list[str]
    run_id: str
    fixture_id: str
    candidate: bool = False
    formal_recommendation: bool = False


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        raise Stage7ISupervisionError("INVALID_UTC")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise Stage7ISupervisionError("UTC_REQUIRED")
    return parsed.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=lambda value: iso(value) if isinstance(value, datetime) else str(value),
    ).encode()


def stable_id(*parts: Any) -> str:
    return hashlib.sha256(canonical_json(parts)).hexdigest()


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            safe[key] = iso(value)
        else:
            safe[key] = value
    return safe


class Stage7ILifecycleRepository:
    def __init__(self, *, engine: Engine | None = None, settings: Settings | None = None) -> None:
        self.engine = engine or create_engine(settings)

    def _db_datetime(self, value: datetime) -> datetime:
        utc_value = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        if self.engine.dialect.name == "sqlite":
            return utc_value.astimezone().replace(tzinfo=None)
        return utc_value

    def start_run(
        self,
        *,
        run_id: str,
        fixture_id: str,
        scheduled_kickoff_utc: datetime,
        started_at: datetime,
        observer_pid: int | None,
        collector_pid: int | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with Session(self.engine) as session:
            try:
                session.add(
                    Stage7ILifecycleRunModel(
                        id=stable_id("run", run_id),
                        run_id=run_id,
                        fixture_id=fixture_id,
                        scheduled_kickoff_utc=self._db_datetime(scheduled_kickoff_utc),
                        observer_pid=observer_pid,
                        collector_pid=collector_pid,
                        status="IN_PROGRESS",
                        started_at=self._db_datetime(started_at),
                        updated_at=self._db_datetime(started_at),
                        candidate=False,
                        formal_recommendation=False,
                        payload={
                            **(payload or {}),
                            "candidate": False,
                            "formal_recommendation": False,
                        },
                    )
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(Stage7ILifecycleRunModel).where(
                        Stage7ILifecycleRunModel.run_id == run_id
                    )
                )
                if existing is None:
                    raise
            except Exception:
                session.rollback()
                raise

    def heartbeat(
        self,
        *,
        run_id: str,
        component: str,
        observed_at: datetime,
        pid: int | None,
        status: str = "ACTIVE",
        payload: dict[str, Any] | None = None,
    ) -> None:
        with Session(self.engine) as session:
            row = session.scalar(
                select(Stage7ILifecycleHeartbeatModel).where(
                    Stage7ILifecycleHeartbeatModel.run_id == run_id,
                    Stage7ILifecycleHeartbeatModel.component == component,
                )
            )
            if row is None:
                row = Stage7ILifecycleHeartbeatModel(
                    id=stable_id("heartbeat", run_id, component),
                    run_id=run_id,
                    component=component,
                    pid=pid,
                    status=status,
                    last_seen_at=self._db_datetime(observed_at),
                    payload=_json_safe(payload or {}),
                )
                session.add(row)
            else:
                row.pid = pid
                row.status = status
                row.last_seen_at = self._db_datetime(observed_at)
                row.payload = _json_safe(payload or {})
            run = self._run_row(session, run_id)
            run.updated_at = self._db_datetime(observed_at)
            session.commit()

    def append_event(
        self,
        *,
        run_id: str,
        fixture_id: str,
        event_type: str,
        event_time: datetime,
        evidence_category: str,
        payload: dict[str, Any],
        event_id: str | None = None,
    ) -> bool:
        resolved_id = event_id or stable_id("stage7i-event", run_id, event_type, payload)
        with Session(self.engine) as session:
            try:
                session.add(
                    Stage7ILifecycleEventModel(
                        id=stable_id("event-row", resolved_id),
                        event_id=resolved_id,
                        run_id=run_id,
                        fixture_id=fixture_id,
                        event_type=event_type,
                        event_time=self._db_datetime(event_time),
                        evidence_category=evidence_category,
                        payload={
                            **_json_safe(payload),
                            "candidate": False,
                            "formal_recommendation": False,
                        },
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
                self._run_row(session, run_id).updated_at = self._db_datetime(event_time)
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False
            except Exception:
                session.rollback()
                raise

    def mark_failed(
        self,
        *,
        run_id: str,
        reason: str,
        observed_at: datetime,
        status: str = "FAILED",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if status not in {"FAILED", "NON_QUALIFYING"}:
            raise Stage7ISupervisionError("INVALID_FAILURE_STATUS")
        with Session(self.engine) as session:
            run = self._run_row(session, run_id)
            run.status = status
            run.failure_reason = reason
            run.updated_at = self._db_datetime(observed_at)
            run.completed_at = self._db_datetime(observed_at)
            run.payload = {**run.payload, **_json_safe(payload or {}), "failure_reason": reason}
            session.commit()
        self.append_event(
            run_id=run_id,
            fixture_id=self.run(run_id)["fixture_id"],
            event_type="WATCHDOG_FAILURE",
            event_time=observed_at,
            evidence_category="AUDIT",
            payload={"reason": reason, **_json_safe(payload or {})},
            event_id=stable_id("watchdog", run_id, reason, iso(observed_at)),
        )

    def record_actual_kickoff(
        self,
        *,
        run_id: str,
        actual_kickoff_utc: datetime,
        source: str,
        observed_at: datetime,
    ) -> None:
        self._update_run_fields(
            run_id,
            observed_at=observed_at,
            actual_kickoff_utc=actual_kickoff_utc,
            actual_kickoff_source=source,
        )
        run_payload = self.run(run_id)
        self.append_event(
            run_id=run_id,
            fixture_id=run_payload["fixture_id"],
            event_type="ACTUAL_KICKOFF",
            event_time=observed_at,
            evidence_category="RETROSPECTIVE",
            payload={"actual_kickoff_utc": actual_kickoff_utc, "source": source},
        )

    def record_closing_observation(self, *, run_id: str, captured_at: datetime) -> None:
        self._update_run_fields(
            run_id,
            observed_at=captured_at,
            closing_observation_utc=captured_at,
        )
        run_payload = self.run(run_id)
        self.append_event(
            run_id=run_id,
            fixture_id=run_payload["fixture_id"],
            event_type="CLOSING_OBSERVATION",
            event_time=captured_at,
            evidence_category="FORWARD",
            payload={"closing_observation_utc": captured_at},
        )

    def record_result(self, *, run_id: str, status: str, observed_at: datetime) -> None:
        self._update_run_fields(run_id, observed_at=observed_at, result_status=status)
        run_payload = self.run(run_id)
        self.append_event(
            run_id=run_id,
            fixture_id=run_payload["fixture_id"],
            event_type="RESULT",
            event_time=observed_at,
            evidence_category="RETROSPECTIVE",
            payload={"result_status": status},
        )

    def record_settlement_evaluation(
        self,
        *,
        run_id: str,
        settlement_status: str,
        evaluation_status: str,
        observed_at: datetime,
    ) -> None:
        self._update_run_fields(
            run_id,
            observed_at=observed_at,
            settlement_status=settlement_status,
            evaluation_status=evaluation_status,
        )
        run = self.run(run_id)
        self.append_event(
            run_id=run_id,
            fixture_id=run["fixture_id"],
            event_type="SETTLEMENT_EVALUATION",
            event_time=observed_at,
            evidence_category="RETROSPECTIVE",
            payload={
                "settlement_status": settlement_status,
                "evaluation_status": evaluation_status,
            },
        )

    def write_final_audit(
        self,
        *,
        run_id: str,
        status: str,
        observed_at: datetime,
        blockers: list[str],
    ) -> Stage7IFinalAudit:
        final_status = "PASS" if status == "COMPLETED" and not blockers else "FAIL"
        terminal_status = "COMPLETED" if final_status == "PASS" else "NON_QUALIFYING"
        with Session(self.engine) as session:
            run = self._run_row(session, run_id)
            if terminal_status == "COMPLETED":
                collector = self._heartbeat_row(session, run_id, "collector")
                if collector.status != "ACTIVE":
                    blockers = [*blockers, "COLLECTOR_NOT_ACTIVE"]
                    final_status = "FAIL"
                    terminal_status = "NON_QUALIFYING"
            run.status = terminal_status
            run.final_audit_status = final_status
            run.failure_reason = ",".join(blockers) if blockers else None
            run.updated_at = self._db_datetime(observed_at)
            run.completed_at = self._db_datetime(observed_at)
            run.payload = {
                **run.payload,
                "final_audit_status": final_status,
                "blockers": blockers,
                "candidate": False,
                "formal_recommendation": False,
            }
            session.commit()
        run_payload = self.run(run_id)
        self.append_event(
            run_id=run_id,
            fixture_id=str(run_payload["fixture_id"]),
            event_type="FINAL_AUDIT",
            event_time=observed_at,
            evidence_category="AUDIT",
            payload={"status": final_status, "blockers": blockers},
        )
        return Stage7IFinalAudit(
            status="COMPLETED" if final_status == "PASS" else "FAIL",
            blockers=blockers,
            run_id=run_id,
            fixture_id=str(run_payload["fixture_id"]),
        )

    def run(self, run_id: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            row = self._run_row(session, run_id)
            return self._run_dict(row)

    def heartbeats(self, run_id: str) -> dict[str, dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(Stage7ILifecycleHeartbeatModel).where(
                        Stage7ILifecycleHeartbeatModel.run_id == run_id
                    )
                )
            )
            return {row.component: self._heartbeat_dict(row) for row in rows}

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(Stage7ILifecycleEventModel)
                    .where(Stage7ILifecycleEventModel.run_id == run_id)
                    .order_by(Stage7ILifecycleEventModel.event_time)
                )
            )
            return [self._event_dict(row) for row in rows]

    def latest_terminal_task_status(self, run_id: str) -> str | None:
        with Session(self.engine) as session:
            row = session.scalar(
                select(Stage7ILifecycleEventModel)
                .where(
                    Stage7ILifecycleEventModel.run_id == run_id,
                    Stage7ILifecycleEventModel.event_type == "FINAL_AUDIT",
                )
                .order_by(desc(Stage7ILifecycleEventModel.event_time))
            )
            return None if row is None else str(row.payload.get("status"))

    def _update_run_fields(self, run_id: str, *, observed_at: datetime, **fields: Any) -> None:
        with Session(self.engine) as session:
            run = self._run_row(session, run_id)
            for key, value in fields.items():
                resolved = self._db_datetime(value) if isinstance(value, datetime) else value
                setattr(run, key, resolved)
            run.updated_at = self._db_datetime(observed_at)
            session.commit()

    def _run_row(self, session: Session, run_id: str) -> Stage7ILifecycleRunModel:
        row = session.scalar(
            select(Stage7ILifecycleRunModel).where(Stage7ILifecycleRunModel.run_id == run_id)
        )
        if row is None:
            raise Stage7ISupervisionError(f"RUN_NOT_FOUND:{run_id}")
        return row

    def _heartbeat_row(
        self, session: Session, run_id: str, component: str
    ) -> Stage7ILifecycleHeartbeatModel:
        row = session.scalar(
            select(Stage7ILifecycleHeartbeatModel).where(
                Stage7ILifecycleHeartbeatModel.run_id == run_id,
                Stage7ILifecycleHeartbeatModel.component == component,
            )
        )
        if row is None:
            raise Stage7ISupervisionError(f"HEARTBEAT_NOT_FOUND:{component}")
        return row

    def _run_dict(self, row: Stage7ILifecycleRunModel) -> dict[str, Any]:
        return {
            "run_id": row.run_id,
            "fixture_id": row.fixture_id,
            "scheduled_kickoff_utc": iso(row.scheduled_kickoff_utc),
            "observer_pid": row.observer_pid,
            "collector_pid": row.collector_pid,
            "status": row.status,
            "started_at": iso(row.started_at),
            "updated_at": iso(row.updated_at),
            "completed_at": iso(row.completed_at) if row.completed_at else None,
            "failure_reason": row.failure_reason,
            "actual_kickoff_utc": iso(row.actual_kickoff_utc) if row.actual_kickoff_utc else None,
            "actual_kickoff_source": row.actual_kickoff_source,
            "closing_observation_utc": (
                iso(row.closing_observation_utc) if row.closing_observation_utc else None
            ),
            "result_status": row.result_status,
            "settlement_status": row.settlement_status,
            "evaluation_status": row.evaluation_status,
            "final_audit_status": row.final_audit_status,
            "candidate": row.candidate,
            "formal_recommendation": row.formal_recommendation,
            "payload": dict(row.payload),
        }

    def _heartbeat_dict(self, row: Stage7ILifecycleHeartbeatModel) -> dict[str, Any]:
        return {
            "run_id": row.run_id,
            "component": row.component,
            "pid": row.pid,
            "status": row.status,
            "last_seen_at": iso(row.last_seen_at),
            "payload": dict(row.payload),
        }

    def _event_dict(self, row: Stage7ILifecycleEventModel) -> dict[str, Any]:
        return {
            "event_id": row.event_id,
            "run_id": row.run_id,
            "fixture_id": row.fixture_id,
            "event_type": row.event_type,
            "event_time": iso(row.event_time),
            "evidence_category": row.evidence_category,
            "payload": dict(row.payload),
            "candidate": row.candidate,
            "formal_recommendation": row.formal_recommendation,
        }


class Stage7ILifecycleSupervisor:
    def __init__(
        self,
        *,
        repository: Stage7ILifecycleRepository | None = None,
        heartbeat_timeout_seconds: int = 900,
    ) -> None:
        self.repository = repository or Stage7ILifecycleRepository()
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds

    def start_run(
        self,
        *,
        run_id: str,
        fixture_id: str,
        scheduled_kickoff_utc: datetime,
        started_at: datetime | None = None,
        observer_pid: int | None = None,
        collector_pid: int | None = None,
    ) -> None:
        now = started_at or utc_now()
        self.repository.start_run(
            run_id=run_id,
            fixture_id=fixture_id,
            scheduled_kickoff_utc=scheduled_kickoff_utc,
            started_at=now,
            observer_pid=observer_pid,
            collector_pid=collector_pid,
            payload={"supervisor": "single_process_db_state_machine"},
        )
        self.heartbeat(run_id=run_id, component="observer", observed_at=now, pid=observer_pid)
        self.heartbeat(run_id=run_id, component="collector", observed_at=now, pid=collector_pid)

    def heartbeat(
        self,
        *,
        run_id: str,
        component: str,
        observed_at: datetime | None = None,
        pid: int | None = None,
        status: str = "ACTIVE",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.repository.heartbeat(
            run_id=run_id,
            component=component,
            observed_at=observed_at or utc_now(),
            pid=pid,
            status=status,
            payload=payload or {},
        )

    def watchdog_check(self, *, run_id: str, observed_at: datetime | None = None) -> bool:
        now = observed_at or utc_now()
        heartbeats = self.repository.heartbeats(run_id)
        collector = heartbeats.get("collector")
        if collector is None:
            self.repository.mark_failed(
                run_id=run_id,
                reason="COLLECTOR_HEARTBEAT_MISSING",
                observed_at=now,
                status="FAILED",
            )
            return False
        last_seen = parse_utc(collector["last_seen_at"])
        stale = now - last_seen > timedelta(seconds=self.heartbeat_timeout_seconds)
        inactive = collector["status"] not in {"ACTIVE", "RUNNING"}
        if stale or inactive:
            reason = "COLLECTOR_HEARTBEAT_TIMEOUT" if stale else "COLLECTOR_INACTIVE"
            self.repository.mark_failed(
                run_id=run_id,
                reason=reason,
                observed_at=now,
                status="FAILED",
                payload={"collector_heartbeat": collector},
            )
            return False
        return True

    def record_actual_kickoff(
        self, *, run_id: str, actual_kickoff_utc: datetime, source: str, observed_at: datetime
    ) -> None:
        self.repository.record_actual_kickoff(
            run_id=run_id,
            actual_kickoff_utc=actual_kickoff_utc,
            source=source,
            observed_at=observed_at,
        )

    def record_closing_observation(self, *, run_id: str, captured_at: datetime) -> None:
        self.repository.record_closing_observation(run_id=run_id, captured_at=captured_at)

    def record_result(self, *, run_id: str, status: str, observed_at: datetime) -> None:
        self.repository.record_result(run_id=run_id, status=status, observed_at=observed_at)

    def record_settlement_evaluation(
        self,
        *,
        run_id: str,
        settlement_status: str,
        evaluation_status: str,
        observed_at: datetime,
    ) -> None:
        self.repository.record_settlement_evaluation(
            run_id=run_id,
            settlement_status=settlement_status,
            evaluation_status=evaluation_status,
            observed_at=observed_at,
        )

    def final_audit(self, *, run_id: str, observed_at: datetime | None = None) -> Stage7IFinalAudit:
        now = observed_at or utc_now()
        run = self.repository.run(run_id)
        heartbeats = self.repository.heartbeats(run_id)
        events = self.repository.events(run_id)
        blockers: list[str] = []
        if run["status"] in {"FAILED", "NON_QUALIFYING"}:
            blockers.append(str(run.get("failure_reason") or run["status"]))
        collector = heartbeats.get("collector")
        if collector is None or collector["status"] not in {"ACTIVE", "RUNNING"}:
            blockers.append("COLLECTOR_NOT_ACTIVE")
        elif now - parse_utc(collector["last_seen_at"]) > timedelta(
            seconds=self.heartbeat_timeout_seconds
        ):
            blockers.append("COLLECTOR_HEARTBEAT_TIMEOUT")
        if not run.get("actual_kickoff_utc"):
            blockers.append("ACTUAL_KICKOFF_SOURCE_UNAVAILABLE")
        if not run.get("closing_observation_utc"):
            blockers.append("CLOSING_OBSERVATION_MISSING")
        else:
            actual = parse_utc(run["actual_kickoff_utc"]) if run.get("actual_kickoff_utc") else None
            closing = parse_utc(run["closing_observation_utc"])
            if actual is not None and closing >= actual:
                blockers.append("CLOSING_NOT_BEFORE_ACTUAL_KICKOFF")
        if run.get("result_status") not in {"FT", "AET", "PEN", "FINAL"}:
            blockers.append("RESULT_MISSING")
        if run.get("settlement_status") != "COMPLETED":
            blockers.append("SETTLEMENT_MISSING")
        if run.get("evaluation_status") != "COMPLETED":
            blockers.append("EVALUATION_MISSING")
        if any(event["candidate"] or event["formal_recommendation"] for event in events):
            blockers.append("ILLEGAL_CANDIDATE_OR_FORMAL_FLAG")
        if any(
            event["event_type"] in {"SETTLEMENT_EVALUATION", "RESULT", "FINAL_AUDIT"}
            and event["evidence_category"] == "FORWARD"
            for event in events
        ):
            blockers.append("RETROSPECTIVE_EVIDENCE_MISCLASSIFIED_AS_FORWARD")
        status = "COMPLETED" if not blockers else "FAIL"
        return self.repository.write_final_audit(
            run_id=run_id,
            status=status,
            observed_at=now,
            blockers=blockers,
        )
