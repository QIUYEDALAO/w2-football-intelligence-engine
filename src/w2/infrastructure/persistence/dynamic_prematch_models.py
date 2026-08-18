from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class DynamicPrematchEvaluationModel(Base):
    __tablename__ = "dynamic_prematch_evaluations"
    __table_args__ = (
        UniqueConstraint("identity_hash", name="uq_dynamic_prematch_evaluation_identity"),
        Index(
            "ix_dynamic_prematch_evaluation_current",
            "fixture_id",
            "market",
            "evaluated_at",
        ),
        Index(
            "uq_dynamic_prematch_evaluation_attempt",
            "attempt_identity_hash",
            unique=True,
        ),
    )

    evaluation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    selection: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    capture_id: Mapped[str | None] = mapped_column(String(128))
    quote_identity_hash: Mapped[str | None] = mapped_column(String(64))
    model_input_hash: Mapped[str | None] = mapped_column(String(64))
    lineup_input_hash: Mapped[str | None] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capture_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_state: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    denominator_scope: Mapped[str | None] = mapped_column(String(64))
    # Rows written by the one-off sweep describe scan-time state, not checkpoint
    # state.  They stay in the table but must never reach a pass-rate.
    measurement_semantics: Mapped[str | None] = mapped_column(String(64))
    official_funnel_eligible: Mapped[bool | None] = mapped_column(Boolean)
    exclusion_reason: Mapped[str | None] = mapped_column(String(128))
    evaluation_policy_version: Mapped[str | None] = mapped_column(String(64))
    evaluation_slot_id: Mapped[str | None] = mapped_column(String(64))
    # The frozen model track this opportunity belongs to.  Distinct from
    # capture_id above, which is the odds snapshot's capture and cannot tell two
    # model tracks apart when they read the same quote.
    model_forecast_capture_identity_hash: Mapped[str | None] = mapped_column(String(64))
    opportunity_identity_hash: Mapped[str | None] = mapped_column(String(64))
    attempt_identity_hash: Mapped[str | None] = mapped_column(String(64))
    scheduled_checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checkpoint_plan_identity: Mapped[str | None] = mapped_column(String(128))
    source_event_identity: Mapped[str | None] = mapped_column(String(128))
    bookmaker_count: Mapped[int | None] = mapped_column(Integer)
    first_failed_gate: Mapped[str | None] = mapped_column(String(64))
    all_failed_gates: Mapped[list[str] | None] = mapped_column(JSON)
    gate_results: Mapped[dict[str, bool] | None] = mapped_column(JSON)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DynamicPrematchOpportunityModel(Base):
    __tablename__ = "dynamic_prematch_opportunities"
    __table_args__ = (
        Index(
            "ix_dynamic_prematch_opportunity_fixture_slot",
            "fixture_id",
            "evaluation_slot_id",
            "market",
        ),
    )

    opportunity_identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    model_forecast_capture_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_slot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_checkpoint_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    checkpoint_plan_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_attempt_identity_hash: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DynamicPrematchSupersessionModel(Base):
    __tablename__ = "dynamic_prematch_supersessions"
    __table_args__ = (
        UniqueConstraint(
            "superseded_evaluation_id",
            name="uq_dynamic_prematch_superseded_once",
        ),
        Index("ix_dynamic_prematch_supersession_fixture", "fixture_id", "created_at"),
    )

    superseded_evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("dynamic_prematch_evaluations.evaluation_id"), primary_key=True
    )
    superseded_by_evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("dynamic_prematch_evaluations.evaluation_id"), nullable=False
    )
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LineupConfirmedEventModel(Base):
    __tablename__ = "lineup_confirmed_events"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "lineup_input_hash",
            name="uq_lineup_confirmed_event_identity",
        ),
        Index("ix_lineup_confirmed_event_fixture", "fixture_id", "captured_at"),
    )

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lineup_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checkpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class T30ValidationSnapshotModel(Base):
    __tablename__ = "t30_validation_snapshots"
    __table_args__ = (
        UniqueConstraint("fixture_id", name="uq_t30_validation_snapshot_fixture"),
        UniqueConstraint("capture_id", name="uq_t30_validation_snapshot_capture"),
    )

    validation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capture_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checkpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
