"""Append-only descriptive monitoring; never a recommendation authority."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base


class AhOuV3MonitoringFactModel(Base):
    __tablename__ = "ah_ou_v3_monitoring_fact"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "market",
            "model_version",
            "calibration_version",
            name="uq_ahou_v3_monitoring_fixture_version",
        ),
    )

    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ah_ou_decision_ledger.decision_id"), primary_key=True
    )
    fixture_id: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calibration_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AhOuV3MonitoringReportModel(Base):
    __tablename__ = "ah_ou_v3_monitoring_report"
    __table_args__ = (
        UniqueConstraint(
            "market",
            "model_version",
            "calibration_version",
            "eligible_settled_count",
            name="uq_ahou_v3_monitoring_report_milestone",
        ),
    )

    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calibration_version: Mapped[str] = mapped_column(String(64), nullable=False)
    eligible_settled_count: Mapped[int] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _immutable(_mapper: Any, _connection: Any, target: Any) -> None:
    raise ValueError(f"{type(target).__name__} is append-only")


for _model in (AhOuV3MonitoringFactModel, AhOuV3MonitoringReportModel):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
