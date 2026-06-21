"""create stage 7b challenger

Revision ID: 0008_create_stage7b_challenger
Revises: 0007_create_stage8_replay
Create Date: 2026-06-22 09:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0008_create_stage7b_challenger"
down_revision: str | None = "0007_create_stage8_replay"
branch_labels: str | None = None
depends_on: str | None = None

STAGE7B_TABLES = {
    "challenger_model",
    "forward_holdout_run",
    "forward_prediction_lock",
    "forward_evaluation",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE7B_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE7B_TABLES:
            table.drop(bind=bind, checkfirst=True)
