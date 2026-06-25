from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class Gate5RecommendationLockEventModel(Base):
    __tablename__ = "gate5_recommendation_lock_event"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_gate5_recommendation_lock_event_id"),
        UniqueConstraint("lock_id", "version", name="uq_gate5_recommendation_lock_version"),
        Index("ix_gate5_recommendation_lock_event_lock", "lock_id"),
        Index("ix_gate5_recommendation_lock_event_fixture", "fixture_id"),
        Index("ix_gate5_recommendation_lock_event_time", "event_time"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    lock_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    selection: Mapped[str] = mapped_column(String(64), nullable=False)
    line: Mapped[str | None] = mapped_column(String(64))
    probability: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prior_event_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    formal_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
