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
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class FactorShadowForecastCaptureModel(Base):
    __tablename__ = "factor_shadow_forecast_capture"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "captured_at",
            "model_version",
            "feature_registry_version",
            "calibration_version",
            "source_mode",
            name="uq_factor_shadow_forecast_scope",
        ),
        Index("ix_factor_shadow_forecast_fixture", "fixture_id", "captured_at"),
        CheckConstraint(
            "source_mode in ('HISTORICAL_REPLAY','FORWARD_SHADOW')",
            name="ck_factor_shadow_forecast_source_mode",
        ),
        CheckConstraint(
            "probability_method = 'EXACT_MATRIX' and sampling_used = false",
            name="ck_factor_shadow_forecast_exact_matrix",
        ),
    )

    forecast_identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    production_capture_identity_hash: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("model_forecast_capture.capture_identity_hash", ondelete="RESTRICT"),
    )
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    model_family: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_registry_version: Mapped[str] = mapped_column(String(128), nullable=False)
    calibration_version: Mapped[str] = mapped_column(String(128), nullable=False)
    pit_input_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lambda_home: Mapped[float] = mapped_column(Float, nullable=False)
    lambda_away: Mapped[float] = mapped_column(Float, nullable=False)
    score_matrix_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    probability_method: Mapped[str] = mapped_column(String(32), nullable=False)
    sampling_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FactorShadowMarketOpportunityModel(Base):
    __tablename__ = "factor_shadow_market_opportunity"
    __table_args__ = (
        UniqueConstraint(
            "forecast_identity_hash",
            "market",
            "evaluation_policy_version",
            "evaluation_slot_id",
            name="uq_factor_shadow_market_opportunity_scope",
        ),
        Index("ix_factor_shadow_market_opportunity_fixture", "fixture_id", "scheduled_at"),
        CheckConstraint(
            "source_mode in ('HISTORICAL_REPLAY','FORWARD_SHADOW')",
            name="ck_factor_shadow_market_opportunity_source_mode",
        ),
    )

    opportunity_identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    forecast_identity_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("factor_shadow_forecast_capture.forecast_identity_hash", ondelete="RESTRICT"),
        nullable=False,
    )
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluation_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluation_slot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FactorShadowMarketAttemptModel(Base):
    __tablename__ = "factor_shadow_market_attempt"
    __table_args__ = (
        Index("ix_factor_shadow_market_attempt_opportunity", "opportunity_identity_hash"),
        Index("ix_factor_shadow_market_attempt_evaluated", "evaluated_at"),
    )

    attempt_identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_identity_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "factor_shadow_market_opportunity.opportunity_identity_hash",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    quote_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FactorShadowForecastOutcomeModel(Base):
    __tablename__ = "factor_shadow_forecast_outcome"
    __table_args__ = (
        UniqueConstraint("forecast_identity_hash", name="uq_factor_shadow_outcome_forecast"),
        Index("ix_factor_shadow_outcome_fixture", "fixture_id", "settled_at"),
    )

    outcome_identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    forecast_identity_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("factor_shadow_forecast_capture.forecast_identity_hash", ondelete="RESTRICT"),
        nullable=False,
    )
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    authoritative_result_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    brier: Mapped[float | None] = mapped_column(Float)
    log_loss: Mapped[float | None] = mapped_column(Float)
    rps: Mapped[float | None] = mapped_column(Float)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FactorShadowV2AdmissionModel(Base):
    __tablename__ = "factor_shadow_v2_admission"
    __table_args__ = (
        Index("ix_factor_shadow_v2_admission_time", "admitted_at"),
        CheckConstraint(
            "source_mode in ('HISTORICAL_REPLAY','FORWARD_SHADOW')",
            name="ck_factor_shadow_admission_source_mode",
        ),
    )

    admission_identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_registry_version: Mapped[str] = mapped_column(String(128), nullable=False)
    calibration_version: Mapped[str] = mapped_column(String(128), nullable=False)
    admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _prevent_mutation(_mapper: Any, _connection: Any, _target: Any) -> None:
    raise ValueError("factor shadow v2 ledgers are append-only")


for _model in (
    FactorShadowForecastCaptureModel,
    FactorShadowMarketOpportunityModel,
    FactorShadowMarketAttemptModel,
    FactorShadowForecastOutcomeModel,
    FactorShadowV2AdmissionModel,
):
    event.listen(_model, "before_update", _prevent_mutation)
    event.listen(_model, "before_delete", _prevent_mutation)
