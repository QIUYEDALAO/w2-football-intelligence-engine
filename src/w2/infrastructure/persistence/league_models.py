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


class LeagueTeamMembershipModel(Base):
    __tablename__ = "league_team_membership"
    __table_args__ = (
        UniqueConstraint(
            "competition_id",
            "season",
            "provider_team_id",
            name="uq_league_team_membership",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_team_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class PromotionRelegationMappingModel(Base):
    __tablename__ = "promotion_relegation_mapping"
    __table_args__ = (
        UniqueConstraint("competition_id", "from_season", "to_season", name="uq_promo_rel"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    from_season: Mapped[str] = mapped_column(String(32), nullable=False)
    to_season: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
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


class SeasonRolloverPlanModel(Base):
    __tablename__ = "season_rollover_plan"
    __table_args__ = (
        UniqueConstraint("competition_id", "next_season", name="uq_season_rollover"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    next_season: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
