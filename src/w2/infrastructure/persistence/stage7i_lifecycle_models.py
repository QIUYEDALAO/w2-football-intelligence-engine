from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class Stage7ILifecycleRunModel(Base):
    __tablename__ = "stage7i_lifecycle_run"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_stage7i_lifecycle_run_id"),
        Index("ix_stage7i_lifecycle_run_fixture", "fixture_id"),
        Index("ix_stage7i_lifecycle_run_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observer_pid: Mapped[int | None] = mapped_column(Integer)
    collector_pid: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    actual_kickoff_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_kickoff_source: Mapped[str | None] = mapped_column(String(128))
    closing_observation_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_status: Mapped[str | None] = mapped_column(String(32))
    settlement_status: Mapped[str | None] = mapped_column(String(32))
    evaluation_status: Mapped[str | None] = mapped_column(String(32))
    final_audit_status: Mapped[str | None] = mapped_column(String(32))
    candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    formal_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class Stage7ILifecycleHeartbeatModel(Base):
    __tablename__ = "stage7i_lifecycle_heartbeat"
    __table_args__ = (
        UniqueConstraint("run_id", "component", name="uq_stage7i_lifecycle_heartbeat"),
        Index("ix_stage7i_lifecycle_heartbeat_last_seen", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    component: Mapped[str] = mapped_column(String(32), nullable=False)
    pid: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class Stage7ILifecycleEventModel(Base):
    __tablename__ = "stage7i_lifecycle_event"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_stage7i_lifecycle_event_id"),
        Index("ix_stage7i_lifecycle_event_run", "run_id"),
        Index("ix_stage7i_lifecycle_event_time", "event_time"),
        Index("ix_stage7i_lifecycle_event_type", "event_type"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_category: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    formal_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
