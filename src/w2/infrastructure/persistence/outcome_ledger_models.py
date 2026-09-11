from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, event
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class OutcomeLedgerModel(Base):
    __tablename__ = "outcome_ledger"
    __table_args__ = (
        Index("ix_outcome_ledger_fixture_type_time", "fixture_id", "record_type", "occurred_at"),
        Index("ix_outcome_ledger_capture_identity", "capture_identity_hash"),
        Index("ix_outcome_ledger_decision_hash", "decision_hash"),
    )

    business_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    record_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    recommendation_scope: Mapped[str | None] = mapped_column(String(32))
    capture_identity_hash: Mapped[str | None] = mapped_column(String(64))
    decision_hash: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_artifact: Mapped[str] = mapped_column(String(512), nullable=False)
    source_line_number: Mapped[int | None] = mapped_column(Integer)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutcomeLedgerRunStateModel(Base):
    """Mutable operational state; deliberately separate from the append-only ledger."""

    __tablename__ = "outcome_ledger_run_state"

    state_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    active_task_id: Mapped[str | None] = mapped_column(String(255))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    defer_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_deferrals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_defer_reason: Mapped[str | None] = mapped_column(String(128))
    pending_settlement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_cursor: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    last_error: Mapped[str | None] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _prevent_mutation(_mapper: Any, _connection: Any, _target: OutcomeLedgerModel) -> None:
    raise ValueError("OutcomeLedgerModel is append-only")


event.listen(OutcomeLedgerModel, "before_update", _prevent_mutation)
event.listen(OutcomeLedgerModel, "before_delete", _prevent_mutation)
