from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class IngestionRunModel(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint("provider", "endpoint", "run_key", name="uq_ingestion_run_key"),
        Index("ix_ingestion_runs_started_at", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False)
    live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderRequestLogModel(Base):
    __tablename__ = "provider_request_logs"
    __table_args__ = (
        UniqueConstraint("provider", "endpoint", "request_hash", name="uq_provider_request_log"),
        Index("ix_provider_request_logs_requested_at", "requested_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    ingestion_run_id: Mapped[str | None] = mapped_column(ForeignKey("ingestion_runs.id"))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(512))


class QuotaUsageModel(Base):
    __tablename__ = "quota_usage"
    __table_args__ = (
        UniqueConstraint("provider", "endpoint", "window_start", name="uq_quota_usage_window"),
        Index("ix_quota_usage_window_start", "window_start"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
