from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class CanonicalTeamModel(Base):
    __tablename__ = "canonical_teams"
    __table_args__ = (
        UniqueConstraint("w2_team_id", name="uq_canonical_team_w2_team_id"),
        UniqueConstraint("identity_hash", name="uq_canonical_team_identity_hash"),
        Index("ix_canonical_team_status", "active_status"),
    )

    w2_team_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(128))
    active_status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ProviderTeamIdentityCrosswalkModel(Base):
    __tablename__ = "provider_team_identity_crosswalks"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_team_id",
            "competition_id",
            "season",
            "valid_from",
            name="uq_provider_team_identity_crosswalk_natural",
        ),
        UniqueConstraint("identity_hash", name="uq_provider_team_identity_crosswalk_hash"),
        Index(
            "ix_provider_team_identity_crosswalk_lookup",
            "provider",
            "provider_team_id",
            "competition_id",
            "season",
        ),
        Index("ix_provider_team_identity_crosswalk_w2_team", "w2_team_id"),
        Index("ix_provider_team_identity_crosswalk_status", "identity_status"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    w2_team_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_teams.w2_team_id"), nullable=False
    )
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identity_status: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_hashes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class CanonicalTeamMatchHistoryModel(Base):
    __tablename__ = "canonical_team_match_history"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_fixture_id",
            "team_w2_id",
            name="uq_canonical_team_match_history_fixture_team",
        ),
        UniqueConstraint("history_hash", name="uq_canonical_team_match_history_hash"),
        Index("ix_canonical_team_match_history_team_kickoff", "team_w2_id", "kickoff_utc"),
        Index("ix_canonical_team_match_history_fixture", "fixture_id"),
        Index("ix_canonical_team_match_history_capture", "endpoint_capture_id"),
    )

    history_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fixture_status: Mapped[str] = mapped_column(String(32), nullable=False)
    team_side: Mapped[str] = mapped_column(String(16), nullable=False)
    team_provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    opponent_provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team_w2_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_teams.w2_team_id"), nullable=False
    )
    opponent_w2_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_teams.w2_team_id"), nullable=False
    )
    goals_for: Mapped[int] = mapped_column(Integer, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, nullable=False)
    result_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_capture_id: Mapped[str | None] = mapped_column(
        ForeignKey("matchday_endpoint_captures.capture_id")
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    history_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class TeamRatingSnapshotModel(Base):
    __tablename__ = "team_rating_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "w2_team_id",
            "observed_at",
            "model_version",
            name="uq_team_rating_snapshot_natural",
        ),
        UniqueConstraint("rating_hash", name="uq_team_rating_snapshot_hash"),
        Index("ix_team_rating_snapshot_lookup", "w2_team_id", "observed_at"),
    )

    rating_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    w2_team_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_teams.w2_team_id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    elo: Mapped[float] = mapped_column(Float, nullable=False)
    attack_strength: Mapped[float] = mapped_column(Float, nullable=False)
    defence_strength: Mapped[float] = mapped_column(Float, nullable=False)
    form_index: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_history_hashes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    rating_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
