from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import (
    GateAProviderCallModel,
    GateARunReservationModel,
)

GATE_A_AUTHORIZATION_SCHEMA = "w2.gate-a-one-shot-authorization.v1"
GATE_A_ACTION = "ONE_SHOT_FOREGROUND_CANARY"


class GateAError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class GateARuntimeAuthorization:
    authorization_id: str
    competition_id: str
    season: str
    persistence: str
    exact_head: str
    allowed_endpoints: frozenset[str]
    provider_call_cap: int
    issued_at: datetime
    expires_at: datetime
    author: str
    reviewer: str

    @classmethod
    def load(cls, path: Path) -> GateARuntimeAuthorization:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GateAError("GATE_A_AUTHORIZATION_UNREADABLE") from exc
        if not isinstance(payload, dict):
            raise GateAError("GATE_A_AUTHORIZATION_INVALID")
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> GateARuntimeAuthorization:
        required = {
            "authorization_id",
            "competition_id",
            "season",
            "exact_head",
            "allowed_endpoints",
            "provider_call_cap",
            "issued_at",
            "expires_at",
            "author",
            "reviewer",
        }
        if (
            payload.get("schema_version") != GATE_A_AUTHORIZATION_SCHEMA
            or payload.get("action") != GATE_A_ACTION
            or payload.get("review_status") != "APPROVED"
            or payload.get("one_shot") is not True
            or payload.get("persistence") != "db"
            or not required.issubset(payload)
        ):
            raise GateAError("GATE_A_AUTHORIZATION_INVALID")
        author = str(payload["author"]).strip()
        reviewer = str(payload["reviewer"]).strip()
        if not author or not reviewer or author == reviewer:
            raise GateAError("GATE_A_INDEPENDENT_REVIEW_REQUIRED")
        authorization_id = str(payload["authorization_id"]).strip()
        exact_head = str(payload["exact_head"]).strip()
        raw_endpoints = payload["allowed_endpoints"]
        if (
            not authorization_id
            or len(authorization_id) > 128
            or re.fullmatch(r"[0-9a-f]{40}", exact_head) is None
            or not isinstance(raw_endpoints, list)
        ):
            raise GateAError("GATE_A_AUTHORIZATION_INVALID")
        endpoints = frozenset(str(value) for value in raw_endpoints)
        if not endpoints or not endpoints <= {"status", "fixtures", "odds", "lineups"}:
            raise GateAError("GATE_A_ENDPOINT_SCOPE_INVALID")
        try:
            cap = int(payload["provider_call_cap"])
        except (TypeError, ValueError) as exc:
            raise GateAError("GATE_A_PROVIDER_CALL_CAP_INVALID") from exc
        if not 1 <= cap <= 10:
            raise GateAError("GATE_A_PROVIDER_CALL_CAP_INVALID")
        issued_at = _aware_utc(payload["issued_at"])
        expires_at = _aware_utc(payload["expires_at"])
        if expires_at <= issued_at or expires_at - issued_at > timedelta(hours=1):
            raise GateAError("GATE_A_AUTHORIZATION_WINDOW_INVALID")
        return cls(
            authorization_id=authorization_id,
            competition_id=str(payload["competition_id"]),
            season=str(payload["season"]),
            persistence="db",
            exact_head=exact_head,
            allowed_endpoints=endpoints,
            provider_call_cap=cap,
            issued_at=issued_at,
            expires_at=expires_at,
            author=author,
            reviewer=reviewer,
        )

    def validate_scope(
        self,
        *,
        competition_id: str,
        season: str,
        persistence: str,
        exact_head: str,
        now: datetime,
    ) -> None:
        current = _aware_utc(now)
        if current < self.issued_at or current > self.expires_at:
            raise GateAError("GATE_A_AUTHORIZATION_EXPIRED")
        if competition_id != self.competition_id:
            raise GateAError("GATE_A_COMPETITION_SCOPE_MISMATCH")
        if season != self.season:
            raise GateAError("GATE_A_SEASON_SCOPE_MISMATCH")
        if persistence != "db":
            raise GateAError("GATE_A_DB_PERSISTENCE_REQUIRED")
        if exact_head != self.exact_head:
            raise GateAError("GATE_A_EXACT_HEAD_MISMATCH")


@dataclass(frozen=True, kw_only=True)
class GateARunReservation:
    authorization_id: str
    owner: str
    lease_epoch: int
    provider_call_cap: int

    def reserve_provider_call(self, endpoint: str) -> int:
        engine = create_engine()
        with Session(engine) as session:
            result = session.execute(
                update(GateARunReservationModel)
                .where(
                    GateARunReservationModel.lease_epoch == self.lease_epoch,
                    GateARunReservationModel.authorization_id == self.authorization_id,
                    GateARunReservationModel.owner == self.owner,
                    GateARunReservationModel.status == "RESERVED",
                    GateARunReservationModel.provider_calls_used
                    < GateARunReservationModel.provider_call_cap,
                )
                .values(
                    provider_calls_used=GateARunReservationModel.provider_calls_used + 1,
                    last_endpoint=endpoint,
                )
            )
            if getattr(result, "rowcount", 0) != 1:
                session.rollback()
                raise GateAError("GATE_A_PROVIDER_CALL_RESERVATION_REJECTED")
            row = session.get(GateARunReservationModel, self.lease_epoch)
            assert row is not None
            ordinal = row.provider_calls_used
            session.add(
                GateAProviderCallModel(
                    lease_epoch=self.lease_epoch,
                    call_ordinal=ordinal,
                    endpoint=endpoint,
                    state="RESERVED_BEFORE_DISPATCH",
                    reserved_at=datetime.now(UTC),
                )
            )
            session.commit()
        return ordinal

    def record_provider_outcome(
        self,
        ordinal: int,
        *,
        state: str,
        error_code: str | None = None,
    ) -> None:
        if state not in {"RESPONSE_RECEIVED", "DELIVERY_UNCERTAIN"}:
            raise GateAError("GATE_A_PROVIDER_OUTCOME_INVALID")
        engine = create_engine()
        with Session(engine) as session:
            result = session.execute(
                update(GateAProviderCallModel)
                .where(
                    GateAProviderCallModel.lease_epoch == self.lease_epoch,
                    GateAProviderCallModel.call_ordinal == ordinal,
                    GateAProviderCallModel.state == "RESERVED_BEFORE_DISPATCH",
                )
                .values(
                    state=state,
                    finished_at=datetime.now(UTC),
                    error_code=error_code,
                )
            )
            if getattr(result, "rowcount", 0) != 1:
                session.rollback()
                raise GateAError("GATE_A_PROVIDER_OUTCOME_WRITE_FAILED")
            session.commit()

    def finalize(self, status: str) -> None:
        engine = create_engine()
        with Session(engine) as session:
            result = session.execute(
                update(GateARunReservationModel)
                .where(
                    GateARunReservationModel.lease_epoch == self.lease_epoch,
                    GateARunReservationModel.authorization_id == self.authorization_id,
                    GateARunReservationModel.owner == self.owner,
                    GateARunReservationModel.status == "RESERVED",
                )
                .values(status=status, finished_at=datetime.now(UTC))
            )
            if getattr(result, "rowcount", 0) != 1:
                session.rollback()
                raise GateAError("GATE_A_LEASE_EPOCH_REJECTED")
            session.commit()


def reserve_gate_a_run(
    authorization: GateARuntimeAuthorization,
    *,
    owner: str,
    now: datetime,
) -> GateARunReservation:
    engine = create_engine()
    with Session(engine) as session:
        row = GateARunReservationModel(
            authorization_id=authorization.authorization_id,
            competition_id=authorization.competition_id,
            season=authorization.season,
            exact_head=authorization.exact_head,
            owner=owner,
            reserved_at=_aware_utc(now),
            status="RESERVED",
            provider_call_cap=authorization.provider_call_cap,
            provider_calls_used=0,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(
                select(GateARunReservationModel.lease_epoch).where(
                    GateARunReservationModel.authorization_id
                    == authorization.authorization_id
                )
            )
            code = (
                "GATE_A_AUTHORIZATION_ALREADY_CONSUMED"
                if existing is not None
                else "GATE_A_RESERVATION_WRITE_FAILED"
            )
            raise GateAError(code) from None
        session.refresh(row)
        lease_epoch = row.lease_epoch
    return GateARunReservation(
        authorization_id=authorization.authorization_id,
        owner=owner,
        lease_epoch=lease_epoch,
        provider_call_cap=authorization.provider_call_cap,
    )


def _aware_utc(value: Any) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except (TypeError, ValueError) as exc:
        raise GateAError("GATE_A_AUTHORIZATION_TIME_INVALID") from exc
    if parsed.tzinfo is None:
        raise GateAError("GATE_A_AUTHORIZATION_TIME_INVALID")
    return parsed.astimezone(UTC)
