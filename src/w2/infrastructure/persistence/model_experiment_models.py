from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class ModelExperimentModel(Base):
    __tablename__ = "model_experiment"
    __table_args__ = (
        UniqueConstraint("experiment_key", name="uq_model_experiment_key"),
        Index("ix_model_experiment_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    experiment_key: Mapped[str] = mapped_column(String(128), nullable=False)
    track: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ModelArtifactModel(Base):
    __tablename__ = "model_artifact"
    __table_args__ = (
        UniqueConstraint("experiment_id", "artifact_key", name="uq_model_artifact_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("model_experiment.id"), nullable=False)
    artifact_key: Mapped[str] = mapped_column(String(128), nullable=False)
    uri: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class CalibrationArtifactModel(Base):
    __tablename__ = "calibration_artifact"
    __table_args__ = (
        UniqueConstraint("experiment_id", "method", "fitted_on", name="uq_calibration_artifact"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("model_experiment.id"), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    fitted_on: Mapped[str] = mapped_column(String(32), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class ModelEvaluationModel(Base):
    __tablename__ = "model_evaluation"
    __table_args__ = (
        UniqueConstraint("experiment_id", "model_name", "split", name="uq_model_evaluation"),
        Index("ix_model_evaluation_split", "split"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("model_experiment.id"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    split: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    slices: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ModelGateDecisionModel(Base):
    __tablename__ = "model_gate_decision"
    __table_args__ = (
        UniqueConstraint("gate_name", "decided_at", name="uq_model_gate_decision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    gate_name: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rationale: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
