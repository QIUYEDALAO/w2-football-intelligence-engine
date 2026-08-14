from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class FutureRefreshTaskAuditModel(Base):
    __tablename__ = "future_refresh_task_audit"
    __table_args__ = (
        Index("ix_future_refresh_task_audit_key", "key"),
        UniqueConstraint("gate_a_lease_epoch", name="uq_future_refresh_task_audit_gate_a_lease"),
    )

    task_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    gate_a_authorization_id: Mapped[str | None] = mapped_column(String(128))
    gate_a_lease_epoch: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("gate_a_run_reservations.lease_epoch"),
    )


class GateARunReservationModel(Base):
    __tablename__ = "gate_a_run_reservations"
    __table_args__ = (
        Index(
            "uq_gate_a_active_task_key",
            "task_key",
            unique=True,
            postgresql_where=text("status = 'RESERVED'"),
            sqlite_where=text("status = 'RESERVED'"),
        ),
    )

    lease_epoch: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    authorization_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    task_key: Mapped[str] = mapped_column(String(255), nullable=False)
    fixture_id: Mapped[str | None] = mapped_column(String(128))
    provider_league_id: Mapped[str | None] = mapped_column(String(64))
    fixture_scope_mode: Mapped[str | None] = mapped_column(String(32))
    kickoff_window_start_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kickoff_window_end_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selection_policy_version: Mapped[str | None] = mapped_column(String(64))
    policy_config_hash: Mapped[str | None] = mapped_column(String(64))
    selected_fixture_id: Mapped[str | None] = mapped_column(String(128))
    fixture_candidate_set_sha256: Mapped[str | None] = mapped_column(String(64))
    fixture_discovery_capture_id: Mapped[str | None] = mapped_column(String(64))
    eligible_candidate_count: Mapped[int | None] = mapped_column(Integer)
    fixture_selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    exact_head: Mapped[str] = mapped_column(String(64), nullable=False)
    exact_tree: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_mode: Mapped[str | None] = mapped_column(String(32))
    runtime_artifact_digest: Mapped[str | None] = mapped_column(String(80))
    complete_checkout_manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    evidence_baseline: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_call_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_endpoint: Mapped[str | None] = mapped_column(String(64))


class GateAProviderCallModel(Base):
    __tablename__ = "gate_a_provider_calls"

    lease_epoch: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("gate_a_run_reservations.lease_epoch"),
        primary_key=True,
    )
    call_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))


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
    __table_args__ = (Index("ix_raw_payload_endpoint_captured", "endpoint", "captured_at"),)

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    inserted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class RawStatisticsRetentionModel(Base):
    __tablename__ = "raw_statistics_retention"

    raw_payload_sha256: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("raw_payload.sha256", ondelete="RESTRICT"),
        primary_key=True,
    )
    retained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _prevent_statistics_raw_mutation(
    _mapper: Any,
    _connection: Any,
    target: RawPayloadModel,
) -> None:
    if target.endpoint == "statistics":
        raise ValueError("raw Statistics payloads are permanently retained")


def _prevent_retention_manifest_mutation(_mapper: Any, _connection: Any, _target: Any) -> None:
    raise ValueError("raw Statistics retention manifest is append-only")


event.listen(RawPayloadModel, "before_update", _prevent_statistics_raw_mutation)
event.listen(RawPayloadModel, "before_delete", _prevent_statistics_raw_mutation)
event.listen(RawStatisticsRetentionModel, "before_update", _prevent_retention_manifest_mutation)
event.listen(RawStatisticsRetentionModel, "before_delete", _prevent_retention_manifest_mutation)


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
