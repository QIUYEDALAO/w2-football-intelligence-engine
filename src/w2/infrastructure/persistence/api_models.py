from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str


class ReadModelCheckpointModel(Base):
    __tablename__ = "read_model_checkpoint"
    __table_args__ = (UniqueConstraint("checkpoint_key", name="uq_read_model_checkpoint_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    checkpoint_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
