from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class ChallengerModelModel(Base):
    __tablename__ = "challenger_model"
    __table_args__ = (UniqueConstraint("model_key", name="uq_challenger_model_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    model_key: Mapped[str] = mapped_column(String(128), nullable=False)
    family: Mapped[str] = mapped_column(String(128), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ForwardHoldoutRunModel(Base):
    __tablename__ = "forward_holdout_run"
    __table_args__ = (UniqueConstraint("run_key", name="uq_forward_holdout_run_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    protocol: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ForwardPredictionLockModel(Base):
    __tablename__ = "forward_prediction_lock"
    __table_args__ = (
        UniqueConstraint("forward_holdout_run_id", "fixture_id", name="uq_forward_prediction_lock"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    forward_holdout_run_id: Mapped[str] = mapped_column(
        ForeignKey("forward_holdout_run.id"), nullable=False
    )
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prediction_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)


class ForwardEvaluationModel(Base):
    __tablename__ = "forward_evaluation"
    __table_args__ = (
        UniqueConstraint("forward_prediction_lock_id", name="uq_forward_evaluation_once"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    forward_prediction_lock_id: Mapped[str] = mapped_column(
        ForeignKey("forward_prediction_lock.id"), nullable=False
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
