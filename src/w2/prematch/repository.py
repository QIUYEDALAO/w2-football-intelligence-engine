from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchSupersessionModel,
    LineupConfirmedEventModel,
    T30ValidationSnapshotModel,
)
from w2.prematch.lifecycle import (
    DynamicEvaluationState,
    DynamicEvaluationVersion,
    LineupConfirmedEvent,
    LockSnapshotResult,
)


class DynamicPrematchRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine()

    def append_evaluation(
        self,
        version: DynamicEvaluationVersion,
        *,
        supersession_reason: str = "NEW_CAPTURE_OR_MODEL_INPUT",
    ) -> tuple[DynamicEvaluationVersion, bool]:
        with Session(self.engine) as session:
            try:
                result = self.append_evaluation_in_session(
                    session,
                    version,
                    supersession_reason=supersession_reason,
                )
                session.commit()
                return result
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(DynamicPrematchEvaluationModel).where(
                        DynamicPrematchEvaluationModel.identity_hash == version.identity_hash
                    )
                )
                if existing is None:
                    raise
                return _version_from_payload(existing.payload), False

    def append_evaluation_in_session(
        self,
        session: Session,
        version: DynamicEvaluationVersion,
        *,
        supersession_reason: str = "NEW_CAPTURE_OR_MODEL_INPUT",
    ) -> tuple[DynamicEvaluationVersion, bool]:
        """Append evaluation and supersession without owning the transaction."""
        payload = version.as_dict()
        existing = session.scalar(
            select(DynamicPrematchEvaluationModel).where(
                DynamicPrematchEvaluationModel.identity_hash == version.identity_hash
            )
        )
        if existing is not None:
            return _version_from_payload(existing.payload), False
        previous = session.scalar(
            select(DynamicPrematchEvaluationModel)
            .where(
                DynamicPrematchEvaluationModel.fixture_id == version.fixture_id,
                DynamicPrematchEvaluationModel.market == version.market,
                ~DynamicPrematchEvaluationModel.evaluation_id.in_(
                    select(DynamicPrematchSupersessionModel.superseded_evaluation_id)
                ),
            )
            .order_by(DynamicPrematchEvaluationModel.evaluated_at.desc())
            .limit(1)
        )
        session.add(
            DynamicPrematchEvaluationModel(
                evaluation_id=version.evaluation_id,
                identity_hash=version.identity_hash,
                fixture_id=version.fixture_id,
                market=version.market,
                selection=version.selection,
                checkpoint=version.checkpoint,
                capture_id=version.capture_id,
                quote_identity_hash=version.quote_identity_hash,
                model_input_hash=version.model_input_hash,
                lineup_input_hash=version.lineup_input_hash,
                evaluated_at=version.evaluated_at,
                capture_at=version.capture_at,
                original_state=version.state.value,
                payload=payload,
            )
        )
        session.flush()
        if previous is not None:
            session.add(
                DynamicPrematchSupersessionModel(
                    superseded_evaluation_id=previous.evaluation_id,
                    superseded_by_evaluation_id=version.evaluation_id,
                    fixture_id=version.fixture_id,
                    market=version.market,
                    reason=supersession_reason,
                    created_at=version.evaluated_at,
                )
            )
            session.flush()
        return version, True

    def append_lineup_event(
        self,
        event: LineupConfirmedEvent,
    ) -> tuple[LineupConfirmedEvent, bool]:
        with Session(self.engine) as session:
            try:
                result = self.append_lineup_event_in_session(session, event)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise

    def append_lineup_event_in_session(
        self,
        session: Session,
        event: LineupConfirmedEvent,
    ) -> tuple[LineupConfirmedEvent, bool]:
        existing = list(
            session.scalars(
                select(LineupConfirmedEventModel)
                .where(LineupConfirmedEventModel.fixture_id == event.fixture_id)
                .order_by(LineupConfirmedEventModel.captured_at, LineupConfirmedEventModel.event_id)
                .limit(2)
            )
        )
        if len(existing) > 1:
            raise ValueError("LINEUP_CONFIRMATION_CONFLICT")
        if existing:
            row = existing[0]
            if row.lineup_input_hash != event.lineup_input_hash:
                raise ValueError("LINEUP_CONFIRMATION_CONFLICT")
            original = _lineup_event_from_payload(row.payload)
            if _lineup_event_business_fields(original) != _lineup_event_business_fields(event):
                raise ValueError("LINEUP_EVENT_PAYLOAD_CONFLICT")
            return original, False

        session.add(
            LineupConfirmedEventModel(
                event_id=f"lineup:{event.lineup_input_hash}",
                fixture_id=event.fixture_id,
                lineup_input_hash=event.lineup_input_hash,
                captured_at=event.captured_at,
                checkpoint=event.checkpoint,
                payload=event.as_dict(),
            )
        )
        session.flush()
        return event, True

    def freeze_t30_snapshot(self, fixture_id: str, result: LockSnapshotResult) -> bool:
        if result.status != "READY" or result.snapshot is None:
            return False
        capture_id = str(result.snapshot.get("capture_id") or "")
        capture_at = _parse_utc(
            result.snapshot.get("capture_at") or result.snapshot.get("captured_at")
        )
        if not capture_id or capture_at is None:
            raise ValueError("LOCK_SNAPSHOT_IDENTITY_INCOMPLETE")
        validation_id = f"t30-{fixture_id}-{capture_id}"
        with Session(self.engine) as session:
            session.add(
                T30ValidationSnapshotModel(
                    validation_id=validation_id,
                    fixture_id=fixture_id,
                    capture_id=capture_id,
                    capture_at=capture_at,
                    checkpoint=result.checkpoint,
                    status=result.status,
                    payload=json.loads(
                        json.dumps(
                            result.snapshot,
                            default=lambda value: (
                                value.astimezone(UTC).isoformat()
                                if isinstance(value, datetime)
                                else str(value)
                            ),
                        )
                    ),
                )
            )
            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(T30ValidationSnapshotModel).where(
                        T30ValidationSnapshotModel.fixture_id == fixture_id
                    )
                )
                if existing is not None and existing.capture_id == capture_id:
                    return False
                raise ValueError("T30_VALIDATION_SNAPSHOT_ALREADY_FROZEN") from None

    def lifecycle(self, fixture_id: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            return self.lifecycle_in_session(session, fixture_id)

    @staticmethod
    def lifecycle_in_session(
        session: Session,
        fixture_id: str,
    ) -> dict[str, Any]:
        """Read the lifecycle visible to an existing projection unit-of-work."""
        rows = list(
            session.scalars(
                select(DynamicPrematchEvaluationModel)
                .where(DynamicPrematchEvaluationModel.fixture_id == fixture_id)
                .order_by(DynamicPrematchEvaluationModel.evaluated_at)
            )
        )
        supersessions = {
            row.superseded_evaluation_id: row
            for row in session.scalars(
                select(DynamicPrematchSupersessionModel).where(
                    DynamicPrematchSupersessionModel.fixture_id == fixture_id
                )
            )
        }
        versions: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.payload)
            supersession = supersessions.get(row.evaluation_id)
            if supersession is not None:
                payload["state"] = DynamicEvaluationState.SUPERSEDED.value
                payload["superseded_by_evaluation_id"] = supersession.superseded_by_evaluation_id
                payload["supersession_reason"] = supersession.reason
            versions.append(payload)
        return {
            "schema_version": "w2.dynamic_quote_ev_lifecycle.v1",
            "fixture_id": fixture_id,
            "versions": versions,
            "current": [row for row in versions if row.get("state") != "SUPERSEDED"],
        }


def _version_from_payload(payload: dict[str, Any]) -> DynamicEvaluationVersion:
    return DynamicEvaluationVersion(
        evaluation_id=str(payload["evaluation_id"]),
        identity_hash=str(payload["identity_hash"]),
        fixture_id=str(payload["fixture_id"]),
        market=str(payload["market"]),
        selection=str(payload["selection"]),
        exact_line=float(payload["exact_line"]) if payload.get("exact_line") is not None else None,
        bookmaker_id=str(payload["bookmaker_id"]) if payload.get("bookmaker_id") else None,
        capture_id=str(payload["capture_id"]) if payload.get("capture_id") else None,
        quote_identity_hash=str(payload["quote_identity_hash"])
        if payload.get("quote_identity_hash")
        else None,
        model_input_hash=str(payload["model_input_hash"])
        if payload.get("model_input_hash")
        else None,
        lineup_input_hash=str(payload["lineup_input_hash"])
        if payload.get("lineup_input_hash")
        else None,
        checkpoint=str(payload["checkpoint"]),
        evaluated_at=_parse_utc(payload["evaluated_at"]) or datetime.now(UTC),
        capture_at=_parse_utc(payload.get("capture_at")),
        state=DynamicEvaluationState(str(payload["state"])),
        current_ev=float(payload["current_ev"]) if payload.get("current_ev") is not None else None,
        current_delta=float(payload["current_delta"])
        if payload.get("current_delta") is not None
        else None,
        current_ev_minus_se=float(payload["current_ev_minus_se"])
        if payload.get("current_ev_minus_se") is not None
        else None,
        required_ev=float(payload["required_ev"]),
        required_delta=float(payload["required_delta"]),
        required_ev_minus_se=float(payload["required_ev_minus_se"]),
        shortfall={str(key): float(value) for key, value in payload["shortfall"].items()},
        blockers=tuple(str(item) for item in payload.get("blockers", [])),
        user_message=str(payload["user_message"]) if payload.get("user_message") else None,
        next_action=str(payload["next_action"]) if payload.get("next_action") else None,
        supersedes_evaluation_id=str(payload["supersedes_evaluation_id"])
        if payload.get("supersedes_evaluation_id")
        else None,
        supersession_reason=str(payload["supersession_reason"])
        if payload.get("supersession_reason")
        else None,
    )


def _lineup_event_from_payload(payload: dict[str, Any]) -> LineupConfirmedEvent:
    if payload.get("schema_version") != "w2.lineup_confirmed_event.v2":
        raise ValueError("LINEUP_EVENT_PAYLOAD_CONFLICT")
    captured_at = _parse_utc(payload.get("captured_at"))
    if captured_at is None:
        raise ValueError("LINEUP_EVENT_PAYLOAD_CONFLICT")
    try:
        return LineupConfirmedEvent(
            fixture_id=str(payload["fixture_id"]),
            competition_id=str(payload["competition_id"]),
            season=str(payload["season"]),
            captured_at=captured_at,
            checkpoint=str(payload["checkpoint"]),
            lineup_input_hash=str(payload["lineup_input_hash"]),
            home_lineup_identity_hash=str(payload["home_lineup_identity_hash"]),
            away_lineup_identity_hash=str(payload["away_lineup_identity_hash"]),
            home_starters=int(payload["home_starters"]),
            away_starters=int(payload["away_starters"]),
            source_capture_id=str(payload["source_capture_id"]),
            raw_sha256=str(payload["raw_sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("LINEUP_EVENT_PAYLOAD_CONFLICT") from exc


def _lineup_event_business_fields(event: LineupConfirmedEvent) -> tuple[object, ...]:
    return (
        event.fixture_id,
        event.competition_id,
        event.season,
        event.lineup_input_hash,
        event.home_lineup_identity_hash,
        event.away_lineup_identity_hash,
        event.home_starters,
        event.away_starters,
        event.checkpoint,
    )


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
