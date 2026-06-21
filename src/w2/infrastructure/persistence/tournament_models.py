from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class TournamentProfileModel(Base):
    __tablename__ = "tournament_profile"
    __table_args__ = (
        UniqueConstraint("competition_id", "version", name="uq_tournament_profile_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class TournamentOperationsPlanModel(Base):
    __tablename__ = "tournament_operations_plan"
    __table_args__ = (
        UniqueConstraint("competition_id", "plan_sha256", name="uq_tournament_plan_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class TournamentReadinessAuditModel(Base):
    __tablename__ = "tournament_readiness_audit"
    __table_args__ = (
        UniqueConstraint("competition_id", "readiness_sha256", name="uq_readiness_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    readiness_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
