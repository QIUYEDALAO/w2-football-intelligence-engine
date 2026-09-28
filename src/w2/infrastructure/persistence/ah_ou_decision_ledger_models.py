"""AH/OU v3 decision ledger persistence.

Append-only, identity-keyed. One row per ``(fixture_id, market, decision_at)``:
the identity hash is the canonical digest of the full decision input (quote,
F9 snapshots, F6 meetings, model/calibration versions), so retries are idempotent
and a change to any input becomes a *new* version instead of a silent edit.

This is the destination the v3 softmax path writes, replacing the old weighted
``factor_score`` / ``bookmaker_intent`` views. It carries everything S4 demands:
model version, calibration version, input hash, the full softmax distribution,
quote/source identity, timestamps and the skip reason.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base

AH_OU_DECISION_LEDGER_SCHEMA = "w2.ah_ou_decision_ledger.v3"


class AhOuDecisionLedgerModel(Base):
    __tablename__ = "ah_ou_decision_ledger"
    __table_args__ = (
        # One row per (fixture, market, decision_at). A re-evaluation that changes
        # any input produces a *different* identity hash, so this is the "single
        # effective version per slot" guard without needing a mutating unique key.
        Index(
            "uq_ah_ou_decision_ledger_slot",
            "fixture_id",
            "market",
            "decision_at",
            unique=True,
        ),
        Index("ix_ah_ou_decision_ledger_fixture", "fixture_id", "decision_at"),
        Index("ix_ah_ou_decision_ledger_capture", "capture_id"),
    )

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    calibration_version: Mapped[str] = mapped_column(String(128), nullable=False)

    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    full_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    quote_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_capture_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    capture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)

    home_team_id: Mapped[str] = mapped_column(String(128), nullable=False)
    away_team_id: Mapped[str] = mapped_column(String(128), nullable=False)

    selected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16))
    score: Mapped[str] = mapped_column(String(64), nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
