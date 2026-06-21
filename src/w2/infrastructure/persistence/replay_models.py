from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class ReplayRunModel(Base):
    __tablename__ = "replay_run"
    __table_args__ = (
        UniqueConstraint("run_key", name="uq_replay_run_key"),
        Index("ix_replay_run_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class ReplayEventModel(Base):
    __tablename__ = "replay_event"
    __table_args__ = (
        UniqueConstraint("replay_run_id", "event_id", name="uq_replay_event_once"),
        Index("ix_replay_event_time", "event_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    replay_run_id: Mapped[str] = mapped_column(ForeignKey("replay_run.id"), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ReplayCheckpointModel(Base):
    __tablename__ = "replay_checkpoint"
    __table_args__ = (
        UniqueConstraint("replay_run_id", "checkpoint_key", name="uq_replay_checkpoint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    replay_run_id: Mapped[str] = mapped_column(ForeignKey("replay_run.id"), nullable=False)
    checkpoint_key: Mapped[str] = mapped_column(String(128), nullable=False)
    last_event_id: Mapped[str | None] = mapped_column(String(128))
    ledger_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_events: Mapped[int] = mapped_column(nullable=False)


class PredictionSnapshotModel(Base):
    __tablename__ = "prediction_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "replay_run_id",
            "fixture_id",
            "model_name",
            name="uq_prediction_snapshot",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    replay_run_id: Mapped[str] = mapped_column(ForeignKey("replay_run.id"), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prediction_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    probabilities: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)


class EvaluationRecordModel(Base):
    __tablename__ = "evaluation_record"
    __table_args__ = (
        UniqueConstraint("replay_run_id", "fixture_id", "model_name", name="uq_evaluation_record"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    replay_run_id: Mapped[str] = mapped_column(ForeignKey("replay_run.id"), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class AblationRunModel(Base):
    __tablename__ = "ablation_run"
    __table_args__ = (
        UniqueConstraint("replay_run_id", "ablation_key", name="uq_ablation_run"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    replay_run_id: Mapped[str] = mapped_column(ForeignKey("replay_run.id"), nullable=False)
    ablation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
