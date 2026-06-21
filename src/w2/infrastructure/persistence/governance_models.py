from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class OperationsCycleModel(Base):
    __tablename__ = "operations_cycle"
    __table_args__ = (UniqueConstraint("cycle_id", name="uq_operations_cycle_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    cycle_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    deterministic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class OperationsCheckResultModel(Base):
    __tablename__ = "operations_check_result"
    __table_args__ = (
        UniqueConstraint("cycle_id", "check_name", name="uq_operations_check_result"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    cycle_id: Mapped[str] = mapped_column(String(128), nullable=False)
    check_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ReleaseCandidateModel(Base):
    __tablename__ = "release_candidate"
    __table_args__ = (UniqueConstraint("release_id", name="uq_release_candidate_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    release_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ReleaseAuditModel(Base):
    __tablename__ = "release_audit"
    __table_args__ = (UniqueConstraint("release_id", "audit_hash", name="uq_release_audit"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    release_id: Mapped[str] = mapped_column(String(128), nullable=False)
    audit_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class RetentionAuditModel(Base):
    __tablename__ = "retention_audit"
    __table_args__ = (UniqueConstraint("audit_id", name="uq_retention_audit_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    audit_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DependencyRiskModel(Base):
    __tablename__ = "dependency_risk"
    __table_args__ = (UniqueConstraint("package", "source", name="uq_dependency_risk"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    package: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
