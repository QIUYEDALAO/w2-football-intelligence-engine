from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class MigrationSourceAssetModel(Base):
    __tablename__ = "migration_source_asset"
    __table_args__ = (
        UniqueConstraint("domain", "source_sha256", name="uq_migration_source_asset"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    domain: Mapped[str] = mapped_column(String(128), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    original_path: Mapped[str] = mapped_column(String(512), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_head: Mapped[str] = mapped_column(String(64), nullable=False)
    migration_eligibility: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MigrationDryRunModel(Base):
    __tablename__ = "migration_dry_run"
    __table_args__ = (UniqueConstraint("run_id", name="uq_migration_dry_run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MigrationValidationRecordModel(Base):
    __tablename__ = "migration_validation_record"
    __table_args__ = (
        UniqueConstraint("run_id", "domain", name="uq_migration_validation_domain"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MigrationQuarantineRecordModel(Base):
    __tablename__ = "migration_quarantine_record"
    __table_args__ = (
        UniqueConstraint("domain", "source_sha256", name="uq_migration_quarantine"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    domain: Mapped[str] = mapped_column(String(128), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ShadowRunModel(Base):
    __tablename__ = "shadow_run"
    __table_args__ = (UniqueConstraint("run_id", name="uq_shadow_run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ShadowComparisonRecordModel(Base):
    __tablename__ = "shadow_comparison_record"
    __table_args__ = (
        UniqueConstraint("run_id", "fixture_identity", name="uq_shadow_comparison_fixture"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fixture_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_comparison_status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
