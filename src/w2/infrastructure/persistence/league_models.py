from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class LeagueProfileModel(Base):
    __tablename__ = "league_profile"
    __table_args__ = (UniqueConstraint("competition_id", name="uq_league_profile_competition"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class LeagueSeasonModel(Base):
    __tablename__ = "league_season"
    __table_args__ = (
        UniqueConstraint("competition_id", "season", name="uq_league_season"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class LeagueReadinessAuditModel(Base):
    __tablename__ = "league_readiness_audit"
    __table_args__ = (
        UniqueConstraint("competition_id", "audit_sha256", name="uq_league_readiness_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    audit_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
