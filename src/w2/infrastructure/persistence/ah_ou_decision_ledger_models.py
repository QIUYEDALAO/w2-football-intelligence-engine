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
AH_OU_FROZEN_TERMS_SCHEMA = "w2.ah_ou_frozen_terms.v1"
AH_OU_COHORT_SCHEMA = "w2.ah_ou_forward_cohort.v3"


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
    # NULL is a historical v3 record. New v3.1 selected rows must freeze terms
    # before publication; no post-result backfill is permitted.
    decision_contract: Mapped[str | None] = mapped_column(String(64))
    frozen_terms: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    terms_hash: Mapped[str | None] = mapped_column(String(64))

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


class AhOuCohortModel(Base):
    """AH/OU v3 forward cohort preregistration (S4/R3 persisted).

    One row per ``(fixture_id, decision_at)``. The scheduler preregisters it at
    ``decision_at = kickoff - 2h`` with the real home/away ids, both markets'
    capture/source, the model/calibration versions and the frozen input identity.
    Re-running with the same identity is a one-row no-op. Results are added only
    later, by a separate POST_EVENT_ENRICHMENT step, never by the pre-match role.
    """

    __tablename__ = "ah_ou_forward_cohort"
    __table_args__ = (
        Index(
            "uq_ah_ou_forward_cohort_slot",
            "fixture_id",
            "decision_at",
            unique=True,
        ),
        Index("ix_ah_ou_forward_cohort_fixture", "fixture_id", "decision_at"),
    )

    cohort_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    home_team_id: Mapped[str] = mapped_column(String(128), nullable=False)
    away_team_id: Mapped[str] = mapped_column(String(128), nullable=False)

    ah_capture_id: Mapped[str | None] = mapped_column(String(64))
    ah_source_capture_sha256: Mapped[str | None] = mapped_column(String(64))
    ou_capture_id: Mapped[str | None] = mapped_column(String(64))
    ou_source_capture_sha256: Mapped[str | None] = mapped_column(String(64))

    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    calibration_version: Mapped[str] = mapped_column(String(128), nullable=False)
    frozen_identity: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
