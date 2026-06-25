from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from w2.config import Settings
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.recommendation_lock_models import (
    Gate5RecommendationLockEventModel,
)


class LockLedgerError(RuntimeError):
    pass


class LockEventType(StrEnum):
    LOCK_CREATED = "LOCK_CREATED"
    VERSION_APPENDED = "VERSION_APPENDED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, kw_only=True)
class RecommendationLockPayload:
    fixture_id: str
    market: str
    selection: str
    line: str | None
    probability: Decimal
    source: str
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def canonical(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "probability": str(self.probability),
            "source": self.source,
            "candidate": False,
            "formal_recommendation": False,
        }


@dataclass(frozen=True, kw_only=True)
class RecommendationLockEvent:
    event_id: str
    lock_id: str
    fixture_id: str
    version: int
    event_type: LockEventType
    market: str
    selection: str
    line: str | None
    probability: Decimal
    actor: str
    reason: str
    event_time: datetime
    prior_event_id: str | None
    payload: dict[str, Any]
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "lock_id": self.lock_id,
            "fixture_id": self.fixture_id,
            "version": self.version,
            "event_type": self.event_type.value,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "probability": str(self.probability),
            "actor": self.actor,
            "reason": self.reason,
            "event_time": iso(self.event_time),
            "prior_event_id": self.prior_event_id,
            "payload": self.payload,
            "candidate": False,
            "formal_recommendation": False,
        }


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _db_datetime(engine: Engine, value: datetime) -> datetime:
    utc_value = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if engine.dialect.name == "sqlite":
        return utc_value.replace(tzinfo=None)
    return utc_value


def _db_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def lock_id_for(payload: RecommendationLockPayload) -> str:
    return _sha256(["gate5-lock", payload.fixture_id])


class RecommendationLockLedger:
    def __init__(self, *, engine: Engine | None = None, settings: Settings | None = None) -> None:
        self.engine = engine or create_engine(settings)

    def create_lock(
        self,
        payload: RecommendationLockPayload,
        *,
        actor: str,
        reason: str,
        event_time: datetime,
    ) -> RecommendationLockEvent:
        lock_id = lock_id_for(payload)
        current = self.active_event(lock_id)
        if current is not None:
            if current.event_type == LockEventType.REVOKED:
                raise LockLedgerError("LOCK_REVOKED_APPEND_VERSION_REQUIRED")
            if _same_direction_and_probability(current, payload):
                return current
            raise LockLedgerError("LOCK_IMMUTABLE_APPEND_VERSION_REQUIRED")
        return self._append(
            lock_id=lock_id,
            payload=payload,
            event_type=LockEventType.LOCK_CREATED,
            version=1,
            actor=actor,
            reason=reason,
            event_time=event_time,
            prior_event_id=None,
        )

    def append_version(
        self,
        lock_id: str,
        payload: RecommendationLockPayload,
        *,
        actor: str,
        reason: str,
        event_time: datetime,
    ) -> RecommendationLockEvent:
        current = self.active_event(lock_id)
        if current is None:
            raise LockLedgerError("LOCK_NOT_FOUND")
        return self._append(
            lock_id=lock_id,
            payload=payload,
            event_type=LockEventType.VERSION_APPENDED,
            version=current.version + 1,
            actor=actor,
            reason=reason,
            event_time=event_time,
            prior_event_id=current.event_id,
        )

    def revoke(
        self,
        lock_id: str,
        *,
        actor: str,
        reason: str,
        event_time: datetime,
    ) -> RecommendationLockEvent:
        current = self.active_event(lock_id)
        if current is None:
            raise LockLedgerError("LOCK_NOT_FOUND")
        payload = RecommendationLockPayload(
            fixture_id=current.fixture_id,
            market=current.market,
            selection=current.selection,
            line=current.line,
            probability=current.probability,
            source="revoke",
        )
        return self._append(
            lock_id=lock_id,
            payload=payload,
            event_type=LockEventType.REVOKED,
            version=current.version + 1,
            actor=actor,
            reason=reason,
            event_time=event_time,
            prior_event_id=current.event_id,
        )

    def events(self, lock_id: str) -> list[RecommendationLockEvent]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(Gate5RecommendationLockEventModel)
                    .where(Gate5RecommendationLockEventModel.lock_id == lock_id)
                    .order_by(Gate5RecommendationLockEventModel.version)
                )
            )
        return [self._event_from_row(row) for row in rows]

    def active_event(self, lock_id: str) -> RecommendationLockEvent | None:
        events = self.events(lock_id)
        return events[-1] if events else None

    def _append(
        self,
        *,
        lock_id: str,
        payload: RecommendationLockPayload,
        event_type: LockEventType,
        version: int,
        actor: str,
        reason: str,
        event_time: datetime,
        prior_event_id: str | None,
    ) -> RecommendationLockEvent:
        canonical = payload.canonical()
        event_id = _sha256([lock_id, version, event_type.value, canonical, actor, reason])
        with Session(self.engine) as session:
            row = Gate5RecommendationLockEventModel(
                id=_sha256(["row", event_id]),
                event_id=event_id,
                lock_id=lock_id,
                fixture_id=payload.fixture_id,
                version=version,
                event_type=event_type.value,
                market=payload.market,
                selection=payload.selection,
                line=payload.line,
                probability=str(payload.probability),
                actor=actor,
                reason=reason,
                event_time=_db_datetime(self.engine, event_time),
                prior_event_id=prior_event_id,
                payload=canonical,
                candidate=False,
                formal_recommendation=False,
            )
            session.add(row)
            session.commit()
            return self._event_from_row(row)

    def _event_from_row(
        self,
        row: Gate5RecommendationLockEventModel,
    ) -> RecommendationLockEvent:
        return RecommendationLockEvent(
            event_id=row.event_id,
            lock_id=row.lock_id,
            fixture_id=row.fixture_id,
            version=row.version,
            event_type=LockEventType(row.event_type),
            market=row.market,
            selection=row.selection,
            line=row.line,
            probability=Decimal(row.probability),
            actor=row.actor,
            reason=row.reason,
            event_time=_db_utc(row.event_time),
            prior_event_id=row.prior_event_id,
            payload=row.payload,
        )


def _same_direction_and_probability(
    event: RecommendationLockEvent,
    payload: RecommendationLockPayload,
) -> bool:
    return (
        event.market == payload.market
        and event.selection == payload.selection
        and event.line == payload.line
        and event.probability == payload.probability
    )
