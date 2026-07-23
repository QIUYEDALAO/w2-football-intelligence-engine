from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class DatasetVersionModel(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    dataset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    artifacts: Mapped[list[DatasetArtifactModel]] = relationship(back_populates="dataset_version")


class DatasetArtifactModel(Base):
    __tablename__ = "dataset_artifacts"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "artifact_id", name="uq_dataset_artifact"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id"), nullable=False
    )
    artifact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)

    dataset_version: Mapped[DatasetVersionModel] = relationship(back_populates="artifacts")


class AsOfSampleModel(Base):
    __tablename__ = "asof_samples"
    __table_args__ = (
        UniqueConstraint("fixture_id", "prediction_phase", "as_of_time", name="uq_asof_sample"),
        Index("ix_asof_samples_kickoff", "kickoff_utc"),
        Index("ix_asof_samples_as_of_time", "as_of_time"),
        Index("ix_asof_samples_fixture", "fixture_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id"), nullable=False
    )
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    competition: Mapped[str] = mapped_column(String(128), nullable=False)
    season: Mapped[str] = mapped_column(String(64), nullable=False)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prediction_phase: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    label_reference_id: Mapped[str] = mapped_column(
        ForeignKey("label_references.id"), nullable=False
    )


class LabelReferenceModel(Base):
    __tablename__ = "label_references"
    __table_args__ = (UniqueConstraint("fixture_id", "confirmed_at", name="uq_label_reference"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    result_status: Mapped[str] = mapped_column(String(64), nullable=False)
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
