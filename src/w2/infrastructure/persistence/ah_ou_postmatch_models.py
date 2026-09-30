"""Append-only v3 settlement and versioned validation projection."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, event
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class AhOuV3SettlementModel(Base):
    __tablename__ = "ah_ou_v3_settlement"
    __table_args__ = (Index("ix_ahou_v3_settlement_fixture", "fixture_id", "market"),)

    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ah_ou_decision_ledger.decision_id"), primary_key=True
    )
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    terms_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_id: Mapped[str] = mapped_column(String(36), ForeignKey("results.id"), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_raw_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result_capture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    home_goals: Mapped[int] = mapped_column(nullable=False)
    away_goals: Mapped[int] = mapped_column(nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    net_units: Mapped[str] = mapped_column(String(32), nullable=False)
    settlement_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AhOuV3ValidationSampleModel(Base):
    __tablename__ = "ah_ou_v3_validation_sample"
    __table_args__ = (Index("ix_ahou_v3_sample_fixture", "fixture_id", "market"),)

    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ah_ou_decision_ledger.decision_id"), primary_key=True
    )
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    selection: Mapped[str] = mapped_column(String(16), nullable=False)
    exact_line: Mapped[str] = mapped_column(String(32), nullable=False)
    decimal_odds: Mapped[str] = mapped_column(String(32), nullable=False)
    terms_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    settlement_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    settlement: Mapped[str] = mapped_column(String(16), nullable=False)
    net_units: Mapped[str] = mapped_column(String(32), nullable=False)
    projected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _immutable(_mapper: Any, _connection: Any, target: Any) -> None:
    raise ValueError(f"{type(target).__name__} is append-only")


for _model in (AhOuV3SettlementModel, AhOuV3ValidationSampleModel):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
