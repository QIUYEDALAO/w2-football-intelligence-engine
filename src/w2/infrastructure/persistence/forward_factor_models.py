"""Persistence for forward AH factor observations (`w2.forward_ah_factor_observation.v1`).

Append-only. A row records what one factor contributed to one evaluation, what
sources it consumed and when those sources observed the facts. Nothing here is
written while `LIVE_CAPTURE_ENABLED` is false; the table exists so the wiring
has a destination that has been migrated, constrained and rolled back before
anything is captured into it.

Numbers are stored as canonical decimal text, not as floats or as a database
numeric type. `applied_weight` and `signed_score` are part of the observation
identity preimage, and a float round-trip through two dialects could change the
text a hash was computed over. Text preserves exactly what was hashed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base

FORWARD_AH_FACTOR_OBSERVATION_SCHEMA = "w2.forward_ah_factor_observation.v1"


class ForwardAhFactorObservationModel(Base):
    __tablename__ = "forward_ah_factor_observations"
    __table_args__ = (
        # One *original* observation per factor per evaluated attempt. This is
        # what stops a batch from silently carrying the same factor twice.
        #
        # It has to be partial. A correction is an append that supersedes an
        # earlier row rather than editing it, so the same factor legitimately
        # appears again on the same attempt with supersedes_observation_id set.
        # A plain unique constraint would forbid exactly the revision the
        # contract requires, so uniqueness applies only to the unsuperseding
        # rows.
        Index(
            "uq_forward_ah_factor_observation_original_per_attempt",
            "evaluation_id",
            "attempt_id",
            "fixture_id",
            "market",
            "factor_id",
            "evaluated_at_utc",
            unique=True,
            postgresql_where=text("supersedes_observation_id is null"),
            sqlite_where=text("supersedes_observation_id is null"),
        ),
        Index("ix_forward_ah_factor_observation_batch", "batch_key"),
        Index("ix_forward_ah_factor_observation_fixture", "fixture_id", "evaluated_at_utc"),
        Index("ix_forward_ah_factor_observation_supersedes", "supersedes_observation_id"),
    )

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    record_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    # (evaluation_id, attempt_id, fixture_id, evaluated_at_utc) as one value, so
    # the four-factor batch is addressable in a single index.
    batch_key: Mapped[str] = mapped_column(String(255), nullable=False)

    evaluation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    factor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    factor_version: Mapped[str] = mapped_column(String(128), nullable=False)
    factor_status: Mapped[str] = mapped_column(String(48), nullable=False)
    participated: Mapped[bool] = mapped_column(Boolean, nullable=False)

    applied_weight: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_score: Mapped[str | None] = mapped_column(String(64))
    factor_inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    evidence_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evaluated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source_capture_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_capture_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[str] = mapped_column(String(255), nullable=False)

    factor_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    factor_verdict_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("forward_ah_factor_observations.observation_id")
    )
    revision_reason: Mapped[str | None] = mapped_column(String(255))
