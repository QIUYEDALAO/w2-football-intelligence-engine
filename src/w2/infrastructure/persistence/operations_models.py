from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class OperationalAlertModel(Base):
    __tablename__ = "operational_alert"
    __table_args__ = (UniqueConstraint("alert_key", name="uq_operational_alert_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    alert_key: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class SloEvaluationModel(Base):
    __tablename__ = "slo_evaluation"
    __table_args__ = (UniqueConstraint("evaluation_key", name="uq_slo_evaluation_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    evaluation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class BackupRunModel(Base):
    __tablename__ = "backup_run"
    __table_args__ = (UniqueConstraint("backup_id", name="uq_backup_run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    backup_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class RestoreRunModel(Base):
    __tablename__ = "restore_run"
    __table_args__ = (UniqueConstraint("restore_id", name="uq_restore_run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    restore_id: Mapped[str] = mapped_column(String(128), nullable=False)
    backup_id: Mapped[str] = mapped_column(String(128), nullable=False)
    restored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified: Mapped[bool] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class SecurityAuditEventModel(Base):
    __tablename__ = "security_audit_event"
    __table_args__ = (UniqueConstraint("event_key", name="uq_security_audit_event_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
