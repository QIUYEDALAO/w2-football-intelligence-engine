"""create stage 8 replay

Revision ID: 0007_create_stage8_replay
Revises: 0006_create_stage7_independent_models
Create Date: 2026-06-22 08:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0007_create_stage8_replay"
down_revision: str | None = "0006_create_stage7_independent_models"
branch_labels: str | None = None
depends_on: str | None = None

STAGE8_TABLES = {
    "replay_run",
    "replay_event",
    "replay_checkpoint",
    "prediction_snapshot",
    "evaluation_record",
    "ablation_run",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE8_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE8_TABLES:
            table.drop(bind=bind, checkfirst=True)
