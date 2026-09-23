from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class CandidateNotificationOutboxModel(Base):
    __tablename__ = "candidate_notification_outbox"
    __table_args__ = (
        UniqueConstraint(
            "attempt_identity_hash",
            "event_type",
            name="uq_candidate_notification_attempt_event",
        ),
        Index(
            "ix_candidate_notification_delivery",
            "delivery_status",
            "created_at",
        ),
        Index(
            "ix_candidate_notification_opportunity",
            "opportunity_identity_hash",
            "created_at",
        ),
        CheckConstraint(
            "delivery_status in ('PENDING', 'RETRY_PENDING', 'DELIVERED', 'FAILED', "
            "'DIGEST_PENDING', 'DIGESTED', 'SUPPRESSED')",
            name="ck_candidate_notification_delivery_status",
        ),
    )

    notification_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_identity_hash: Mapped[str | None] = mapped_column(String(64))
    # MISSED/EVALUATION_ERROR closeouts and day summaries have no evaluation
    # attempt. Their deterministic notification_event_id is the idempotency key.
    attempt_identity_hash: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(64))
    current_state: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_status: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(512))


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


class ValidationSampleModel(Base):
    """Materialized post-match validation sample (official-funnel recommendation).

    One row per (fixture_id, market). Written by the forward_outcome_ledger
    rolling writer for the [now-3d, now+1d] kickoff window and by a one-off
    backfill; rows outside the writer window are frozen. The projection function
    that produced these rows stays as the reconciliation authority only.
    """

    __tablename__ = "validation_samples"
    __table_args__ = (
        CheckConstraint(
            "market in ('ASIAN_HANDICAP', 'TOTALS')",
            name="ck_validation_samples_market",
        ),
        Index("ix_validation_samples_kickoff", "kickoff_utc"),
        Index("ix_validation_samples_competition", "competition_id"),
        Index("ix_validation_samples_calibration", "calibration_identity"),
    )

    fixture_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    market: Mapped[str] = mapped_column(String(64), primary_key=True)
    competition_id: Mapped[str | None] = mapped_column(String(128))
    kickoff_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selection: Mapped[str] = mapped_column(String(64), nullable=False)
    exact_line: Mapped[str] = mapped_column(String(32), nullable=False)
    decimal_odds: Mapped[float] = mapped_column(Float, nullable=False)
    bookmaker_id: Mapped[str | None] = mapped_column(String(128))
    first_checkpoint: Mapped[str | None] = mapped_column(String(32))
    final_checkpoint: Mapped[str | None] = mapped_column(String(32))
    evaluation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    calibration_identity: Mapped[str | None] = mapped_column(String(64))
    settlement: Mapped[str] = mapped_column(String(32), nullable=False)
    profit_units: Mapped[float | None] = mapped_column(Float)
    score: Mapped[str | None] = mapped_column(String(16))
    projected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 展示字段：读取路径零 join 还原 projection 输出，避免请求期重算队名/生命周期。
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quote_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_ev: Mapped[float | None] = mapped_column(Float)
    home_team_label: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    away_team_label: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    later_unassessed_checkpoints: Mapped[list[str] | None] = mapped_column(JSON)
    lifecycle_note_zh: Mapped[str | None] = mapped_column(String(256))


class CalibratedValidationSampleModel(Base):
    """Independent, append-by-reconciliation projection for EV-ONLINE-01.

    This deliberately mirrors ``validation_samples`` instead of altering it.
    ``settlement_observed_at`` is nullable because missing provider terminal
    capture time is a fail-closed condition for the bias pool.
    """

    __tablename__ = "validation_samples_calibrated"
    __table_args__ = (
        CheckConstraint(
            "market in ('ASIAN_HANDICAP', 'TOTALS')",
            name="ck_validation_samples_calibrated_market",
        ),
        CheckConstraint(
            "filter_decision in ('KEPT', 'FILTERED')",
            name="ck_validation_samples_calibrated_filter_decision",
        ),
        Index("ix_validation_samples_calibrated_kickoff", "kickoff_utc"),
        Index("ix_validation_samples_calibrated_competition", "competition_id"),
        Index("ix_validation_samples_calibrated_decision", "filter_decision"),
    )

    fixture_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    market: Mapped[str] = mapped_column(String(64), primary_key=True)
    competition_id: Mapped[str | None] = mapped_column(String(128))
    kickoff_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selection: Mapped[str] = mapped_column(String(64), nullable=False)
    exact_line: Mapped[str] = mapped_column(String(32), nullable=False)
    decimal_odds: Mapped[float] = mapped_column(Float, nullable=False)
    bookmaker_id: Mapped[str | None] = mapped_column(String(128))
    first_checkpoint: Mapped[str | None] = mapped_column(String(32))
    final_checkpoint: Mapped[str | None] = mapped_column(String(32))
    evaluation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    calibration_identity: Mapped[str | None] = mapped_column(String(64))
    settlement: Mapped[str] = mapped_column(String(32), nullable=False)
    profit_units: Mapped[float | None] = mapped_column(Float)
    score: Mapped[str | None] = mapped_column(String(16))
    projected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quote_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_ev: Mapped[float | None] = mapped_column(Float)
    home_team_label: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    away_team_label: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    later_unassessed_checkpoints: Mapped[list[str] | None] = mapped_column(JSON)
    lifecycle_note_zh: Mapped[str | None] = mapped_column(String(256))
    settlement_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bias_at_decision: Mapped[float | None] = mapped_column(Float)
    ev_raw: Mapped[float | None] = mapped_column(Float)
    ev_corrected: Mapped[float | None] = mapped_column(Float)
    filter_decision: Mapped[str] = mapped_column(String(16), nullable=False)
    param_version: Mapped[str] = mapped_column(String(64), nullable=False)
    warmup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
