"""Append-only forward clock and evaluation evidence storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class ForwardClockModel(Base):
    __tablename__ = "forward_clock_registry"

    clock_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    code_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    model_identity: Mapped[str] = mapped_column(String(80), nullable=False)
    preregistration_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    input_version: Mapped[str] = mapped_column(String(80), nullable=False)


class RecommendationReviewLedgerModel(Base):
    __tablename__ = "recommendation_review_ledger"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "event_type", name="uq_review_evaluation_event"),
        Index("ix_review_evaluated_at", "evaluated_at"),
        Index("ix_review_pit_status", "pit_status"),
    )

    review_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("dynamic_prematch_evaluations.evaluation_id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pit_status: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
