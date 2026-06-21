from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class ForwardCycleRunModel(Base):
    __tablename__ = "forward_cycle_run"
    __table_args__ = (UniqueConstraint("cycle_key", name="uq_forward_cycle_run_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    cycle_key: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    request_budget: Mapped[int] = mapped_column(nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ForwardResultEventModel(Base):
    __tablename__ = "forward_result_event"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "provider",
            "raw_payload_hash",
            name="uq_forward_result_event",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ForwardMarketSnapshotModel(Base):
    __tablename__ = "forward_market_snapshot"
    __table_args__ = (
        UniqueConstraint("fixture_id", "phase", "captured_at", name="uq_forward_market_snapshot"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    market_comparable: Mapped[bool] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ForwardGateAuditModel(Base):
    __tablename__ = "forward_gate_audit"
    __table_args__ = (
        UniqueConstraint("cycle_run_id", "gate_name", name="uq_forward_gate_audit"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    cycle_run_id: Mapped[str] = mapped_column(ForeignKey("forward_cycle_run.id"), nullable=False)
    gate_name: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ForwardCycleCheckpointModel(Base):
    __tablename__ = "forward_cycle_checkpoint"
    __table_args__ = (
        UniqueConstraint("cycle_id", "step", "payload_hash", name="uq_forward_cycle_checkpoint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    cycle_id: Mapped[str] = mapped_column(String(128), nullable=False)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ForwardSchedulerRunModel(Base):
    __tablename__ = "forward_scheduler_run"
    __table_args__ = (
        UniqueConstraint("scheduler_key", "scheduled_for", name="uq_forward_scheduler_run"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    scheduler_key: Mapped[str] = mapped_column(String(128), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    audit_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ForwardStateTransitionModel(Base):
    __tablename__ = "forward_state_transition"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "from_state",
            "to_state",
            "event_time",
            name="uq_forward_state_transition",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    from_state: Mapped[str] = mapped_column(String(64), nullable=False)
    to_state: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False)


class ForwardOperationalAlertModel(Base):
    __tablename__ = "forward_operational_alert"
    __table_args__ = (
        UniqueConstraint("alert_key", name="uq_forward_operational_alert_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    alert_key: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
