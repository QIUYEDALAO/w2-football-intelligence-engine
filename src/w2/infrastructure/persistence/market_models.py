from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class MarketConsensusModel(Base):
    __tablename__ = "market_consensus"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "market",
            "selection",
            "line",
            "as_of_time",
            "method",
            name="uq_market_consensus_identity",
        ),
        Index("ix_market_consensus_as_of", "as_of_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    selection: Mapped[str] = mapped_column(String(64), nullable=False)
    line: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    fair_decimal_odds: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    effective_bookmakers: Mapped[int] = mapped_column(nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MarketBaselineRunModel(Base):
    __tablename__ = "market_baseline_run"
    __table_args__ = (
        UniqueConstraint("run_key", name="uq_market_baseline_run_key"),
        Index("ix_market_baseline_run_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    method_selection_policy: Mapped[str] = mapped_column(String(128), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MarketFitDiagnosticModel(Base):
    __tablename__ = "market_fit_diagnostic"
    __table_args__ = (
        Index("ix_market_fit_diagnostic_fixture", "fixture_id"),
        Index("ix_market_fit_diagnostic_run", "market_baseline_run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    market_baseline_run_id: Mapped[str] = mapped_column(
        ForeignKey("market_baseline_run.id"), nullable=False
    )
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    diagnostic_type: Mapped[str] = mapped_column(String(64), nullable=False)
    residual: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MarketQualityAssessmentModel(Base):
    __tablename__ = "market_quality_assessment"
    __table_args__ = (
        UniqueConstraint("fixture_id", "market", "as_of_time", name="uq_market_quality_identity"),
        Index("ix_market_quality_status", "quality_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    liquidity: Mapped[str] = mapped_column(String(32), nullable=False)
    bookmaker_coverage: Mapped[str] = mapped_column(String(32), nullable=False)
    freshness: Mapped[str] = mapped_column(String(32), nullable=False)
    dispersion: Mapped[str] = mapped_column(String(32), nullable=False)
    conflict: Mapped[str] = mapped_column(String(32), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
