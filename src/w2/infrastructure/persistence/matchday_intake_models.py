from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class MatchdayEndpointCaptureModel(Base):
    __tablename__ = "matchday_endpoint_captures"
    __table_args__ = (
        UniqueConstraint(
            "endpoint",
            "params_hash",
            "checkpoint",
            "provider_captured_at",
            "raw_payload_sha256",
            name="uq_matchday_endpoint_capture_identity",
        ),
        Index("ix_matchday_endpoint_capture_endpoint", "endpoint", "provider_captured_at"),
        Index("ix_matchday_endpoint_capture_raw_payload", "raw_payload_sha256"),
    )

    capture_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fixture_id: Mapped[str | None] = mapped_column(String(128))
    competition_id: Mapped[str | None] = mapped_column(String(128))
    checkpoint: Mapped[str | None] = mapped_column(String(64))
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    sanitized_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_task_key: Mapped[str] = mapped_column(String(255), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    response_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quota_values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    raw_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_event_time: Mapped[str | None] = mapped_column(String(64))
    capture_status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))


class MatchdayMarketObservationModel(Base):
    __tablename__ = "matchday_market_observations"
    __table_args__ = (
        UniqueConstraint("observation_id", name="uq_matchday_market_observation_identity"),
        Index("ix_matchday_market_observation_fixture", "fixture_id", "captured_at"),
        Index("ix_matchday_market_observation_capture", "capture_id"),
    )

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    bookmaker_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bookmaker_name: Mapped[str] = mapped_column(String(255), nullable=False)
    capture_id: Mapped[str] = mapped_column(
        ForeignKey("matchday_endpoint_captures.capture_id"), nullable=False
    )
    provider_bet_id: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_market_label: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_market: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_selection: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_selection: Mapped[str] = mapped_column(String(128), nullable=False)
    line: Mapped[str | None] = mapped_column(String(64))
    decimal_odds: Mapped[str] = mapped_column(String(32), nullable=False)
    suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_updated_at: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(128), nullable=False)


class MatchdayCheckpointPlanModel(Base):
    __tablename__ = "matchday_checkpoint_plans"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "competition_id",
            "season",
            "checkpoint",
            "policy_version",
            name="uq_matchday_checkpoint_plan_identity",
        ),
        Index("ix_matchday_checkpoint_plan_status", "status", "scheduled_at"),
        Index("ix_matchday_checkpoint_plan_fixture", "fixture_id"),
    )

    plan_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    endpoints: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(128))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    test_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    namespace: Mapped[str | None] = mapped_column(String(128))
    missed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capture_id: Mapped[str | None] = mapped_column(String(64))
    current_unscheduled_capture_id: Mapped[str | None] = mapped_column(String(64))
    blockers: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class MatchdayEvidenceManifestModel(Base):
    __tablename__ = "matchday_evidence_manifests"
    __table_args__ = (
        UniqueConstraint("fixture_id", "as_of", "manifest_hash", name="uq_matchday_manifest_hash"),
        Index("ix_matchday_evidence_manifest_fixture", "fixture_id", "as_of"),
    )

    manifest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_hash: Mapped[str | None] = mapped_column(String(64))
    manifest_integrity_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="PASS"
    )
    natural_key_hash: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
