from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class FutureMarketObservationModel(Base):
    __tablename__ = "future_market_observation"
    __table_args__ = (
        Index("ix_future_market_observation_fixture", "fixture_id"),
        Index("ix_future_market_observation_captured_at", "captured_at"),
    )

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    bookmaker_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bookmaker_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_bet_id: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_market_label: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_market: Mapped[str] = mapped_column(String(64), nullable=False)
    selection: Mapped[str] = mapped_column(String(128), nullable=False)
    line: Mapped[str | None] = mapped_column(String(64))
    decimal_odds: Mapped[str] = mapped_column(String(32), nullable=False)
    suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_last_update: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    formal_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FutureRefreshTaskAuditModel(Base):
    __tablename__ = "future_refresh_task_audit"
    __table_args__ = (Index("ix_future_refresh_task_audit_key", "key"),)

    task_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class FutureRefreshRunAuditModel(Base):
    __tablename__ = "future_refresh_run_audit"
    __table_args__ = (
        Index("ix_future_refresh_run_audit_generated_at", "generated_at"),
        Index("ix_future_refresh_run_audit_competition", "competition_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_quota: Mapped[int | None] = mapped_column(Integer)
    fixture_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_count: Mapped[int] = mapped_column(Integer, nullable=False)
    market_snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ledger_appended_count: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_market_fixture_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    requests: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    formal_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FutureRefreshCheckpointPlanModel(Base):
    __tablename__ = "future_refresh_checkpoint_plan"
    __table_args__ = (
        UniqueConstraint("fixture_id", "checkpoint", name="uq_future_refresh_checkpoint"),
        Index("ix_future_refresh_checkpoint_due", "due_at", "status"),
        Index("ix_future_refresh_checkpoint_fixture", "fixture_id"),
    )

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    endpoints: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_audit_id: Mapped[int | None] = mapped_column(Integer)


class FutureRefreshCheckpointAuditModel(Base):
    __tablename__ = "future_refresh_checkpoint_audit"
    __table_args__ = (
        Index("ix_future_refresh_checkpoint_audit_fixture", "fixture_id"),
        Index("ix_future_refresh_checkpoint_audit_asof", "as_of"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calls_used: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class RawPayloadModel(Base):
    __tablename__ = "raw_payload"
    __table_args__ = (
        Index("ix_raw_payload_endpoint_captured", "endpoint", "captured_at"),
    )

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class TeamXgMatchModel(Base):
    __tablename__ = "team_xg_match"
    __table_args__ = (
        UniqueConstraint("fixture_id", "team_id", name="uq_team_xg_match_fixture_team"),
        Index("ix_team_xg_match_team_kickoff", "team_id", "kickoff_at"),
        Index("ix_team_xg_match_fixture", "fixture_id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    opponent_team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    xg_for: Mapped[float] = mapped_column(Float, nullable=False)
    xg_against: Mapped[float] = mapped_column(Float, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    formal_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TeamXgRollingSnapshotModel(Base):
    __tablename__ = "team_xg_rolling_snapshot"
    __table_args__ = (
        UniqueConstraint("team_id", "as_of_fixture_id", name="uq_team_xg_snapshot_fixture_team"),
        Index("ix_team_xg_rolling_snapshot_team_asof", "team_id", "as_of_time"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    match_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rolling_xg_for: Mapped[float] = mapped_column(Float, nullable=False)
    rolling_xg_against: Mapped[float] = mapped_column(Float, nullable=False)
    rolling_goals_for: Mapped[float] = mapped_column(Float, nullable=False)
    rolling_goals_against: Mapped[float] = mapped_column(Float, nullable=False)
    regression_index: Mapped[float] = mapped_column(Float, nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    formal_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
