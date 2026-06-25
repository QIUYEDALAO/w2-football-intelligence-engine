from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class TeamValueSourceSnapshotModel(Base):
    __tablename__ = "team_value_source_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "raw_path",
            "sha256_checksum",
            name="uq_team_value_source_snapshot",
        ),
        Index("ix_team_value_source_snapshot_ingested", "ingested_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(512), nullable=False)
    source_revision: Mapped[str | None] = mapped_column(String(128))
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    license: Mapped[str] = mapped_column(String(64), nullable=False)
    terms_summary: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class TeamValueMappingModel(Base):
    __tablename__ = "team_value_mapping"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "transfermarkt_club_id",
            "w2_team_id",
            "valid_from",
            name="uq_team_value_mapping_identity",
        ),
        Index("ix_team_value_mapping_w2_team", "w2_team_id"),
        Index("ix_team_value_mapping_transfermarkt", "source_system", "transfermarkt_club_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    transfermarkt_club_id: Mapped[str] = mapped_column(String(64), nullable=False)
    transfermarkt_club_name: Mapped[str] = mapped_column(String(255), nullable=False)
    w2_team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    mapping_source: Mapped[str] = mapped_column(String(128), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(512))


class TeamValueObservationModel(Base):
    __tablename__ = "team_value_observation"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "transfermarkt_club_id",
            "valid_from",
            "source_row_sha256",
            name="uq_team_value_observation_idempotency",
        ),
        Index(
            "ix_team_value_observation_club_asof",
            "source_system",
            "transfermarkt_club_id",
            "valid_from",
        ),
        Index("ix_team_value_observation_ingested", "ingested_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("team_value_source_snapshot.id"),
        nullable=False,
    )
    transfermarkt_club_id: Mapped[str] = mapped_column(String(64), nullable=False)
    transfermarkt_club_name: Mapped[str] = mapped_column(String(255), nullable=False)
    season: Mapped[str | None] = mapped_column(String(32))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    value_eur: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    raw_path: Mapped[str] = mapped_column(String(512), nullable=False)
    source_row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
