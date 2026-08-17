from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    case,
    event,
    literal,
)
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base

API_FOOTBALL_FIXTURE_PREFIX = "api_football:"


def model_forecast_fixture_aliases(value: str) -> tuple[str, ...]:
    fixture_id = str(value or "").strip()
    if not fixture_id:
        return ()
    bare = fixture_id.removeprefix(API_FOOTBALL_FIXTURE_PREFIX)
    return (bare, f"{API_FOOTBALL_FIXTURE_PREFIX}{bare}")


def canonical_model_forecast_fixture_id(value: str) -> str:
    aliases = model_forecast_fixture_aliases(value)
    return aliases[-1] if aliases else ""


def canonical_model_forecast_fixture_id_sql(column: Any) -> Any:
    """Normalize stored fixture IDs before any cross-table comparison."""

    return case(
        (column.like(f"{API_FOOTBALL_FIXTURE_PREFIX}%"), column),
        else_=literal(API_FOOTBALL_FIXTURE_PREFIX) + column,
    )


class ModelForecastCaptureModel(Base):
    __tablename__ = "model_forecast_capture"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "model_family",
            "model_version",
            name="uq_model_forecast_capture_fixture_model",
        ),
        Index("ix_model_forecast_capture_fixture_kickoff", "fixture_id", "kickoff_utc"),
    )

    capture_identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    competition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lead_time_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lead_time_bucket: Mapped[str] = mapped_column(String(32), nullable=False)
    model_family: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_input_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    four_field_xg_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    score_matrix_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelForecastCaptureDataVersionModel(Base):
    __tablename__ = "model_forecast_capture_data_version"

    capture_identity_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("model_forecast_capture.capture_identity_hash", ondelete="RESTRICT"),
        primary_key=True,
    )
    data_version: Mapped[str] = mapped_column(String(128), nullable=False)
    team_xg_match_count: Mapped[int | None] = mapped_column(BigInteger)
    evidence_source: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelForecastOutcomeModel(Base):
    __tablename__ = "model_forecast_outcome"
    __table_args__ = (
        UniqueConstraint("capture_identity_hash", name="uq_model_forecast_outcome_capture"),
        Index("ix_model_forecast_outcome_fixture_settled", "fixture_id", "settled_at"),
    )

    outcome_identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_identity_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("model_forecast_capture.capture_identity_hash", ondelete="RESTRICT"),
        nullable=False,
    )
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    authoritative_result_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    brier: Mapped[float] = mapped_column(Float, nullable=False)
    log_loss: Mapped[float] = mapped_column(Float, nullable=False)
    rps: Mapped[float] = mapped_column(Float, nullable=False)
    lead_time_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lead_time_bucket: Mapped[str] = mapped_column(String(32), nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _prevent_mutation(_mapper: Any, _connection: Any, _target: Any) -> None:
    raise ValueError("model forecast ledgers are append-only")


for _model in (
    ModelForecastCaptureModel,
    ModelForecastCaptureDataVersionModel,
    ModelForecastOutcomeModel,
):
    event.listen(_model, "before_update", _prevent_mutation)
    event.listen(_model, "before_delete", _prevent_mutation)
