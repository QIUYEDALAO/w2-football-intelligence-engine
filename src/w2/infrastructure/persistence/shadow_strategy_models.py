from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class ShadowStrategyRunModel(Base):
    __tablename__ = "shadow_strategy_run"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_shadow_strategy_run_id"),
        Index("ix_shadow_strategy_run_started_at", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ShadowStrategyCandidateModel(Base):
    __tablename__ = "shadow_strategy_candidate"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "phase",
            "strategy_version",
            "rank",
            name="uq_shadow_strategy_candidate_rank",
        ),
        Index("ix_shadow_strategy_candidate_fixture", "fixture_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rank: Mapped[int] = mapped_column(nullable=False)
    shadow_action: Mapped[str] = mapped_column(String(32), nullable=False)
    public_decision: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ShadowStrategyLockModel(Base):
    __tablename__ = "shadow_strategy_lock"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "phase",
            "strategy_version",
            name="uq_shadow_strategy_lock_fixture_phase_version",
        ),
        Index("ix_shadow_strategy_lock_locked_at", "locked_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ShadowStrategyEventModel(Base):
    __tablename__ = "shadow_strategy_event"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_shadow_strategy_event_id"),
        Index("ix_shadow_strategy_event_fixture", "fixture_id"),
        Index("ix_shadow_strategy_event_time", "event_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ShadowStrategySettlementModel(Base):
    __tablename__ = "shadow_strategy_settlement"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "phase",
            "strategy_version",
            name="uq_shadow_strategy_settlement_fixture_phase_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ShadowStrategyEvaluationModel(Base):
    __tablename__ = "shadow_strategy_evaluation"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "phase",
            "strategy_version",
            name="uq_shadow_strategy_evaluation_fixture_phase_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
