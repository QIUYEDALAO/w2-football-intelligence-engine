"""Provider 不确定副作用栅栏模型（V7 包5/E）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base

STATE_ATTEMPTING = "ATTEMPTING"
STATE_DONE = "DONE"
STATE_SIDE_EFFECT_UNCERTAIN = "SIDE_EFFECT_UNCERTAIN"
STATE_BLOCKED = "BLOCKED"


class ProviderSideEffectFenceModel(Base):
    __tablename__ = "provider_side_effect_fence"

    task_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    stage: Mapped[str] = mapped_column(String(32), primary_key=True)
    attempt: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default=STATE_ATTEMPTING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    owner_token: Mapped[str | None] = mapped_column(String(64))
    stored_result: Mapped[dict[str, object] | None] = mapped_column(JSON)
