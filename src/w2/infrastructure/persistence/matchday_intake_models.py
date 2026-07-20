from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class MatchdayEndpointCaptureModel(Base):
    __tablename__ = "matchday_endpoint_captures"
    __table_args__ = (
        UniqueConstraint(
            "endpoint",
            "params_hash",
            "provider_captured_at",
            "raw_payload_sha256",
            name="uq_matchday_endpoint_capture_identity",
        ),
        Index("ix_matchday_endpoint_capture_endpoint", "endpoint", "provider_captured_at"),
        Index("ix_matchday_endpoint_capture_raw_payload", "raw_payload_sha256"),
    )

    capture_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    sanitized_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_task_key: Mapped[str] = mapped_column(String(255), nullable=False)
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
    status: Mapped[str] = mapped_column(String(32), nullable=False)
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
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
