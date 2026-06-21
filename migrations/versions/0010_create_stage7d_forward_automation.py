"""create stage 7d forward automation

Revision ID: 0010_create_stage7d_forward_automation
Revises: 0009_create_stage7c_forward_ops
Create Date: 2026-06-22 11:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0010_create_stage7d_forward_automation"
down_revision: str | None = "0009_create_stage7c_forward_ops"
branch_labels: str | None = None
depends_on: str | None = None

STAGE7D_TABLES = {
    "forward_cycle_checkpoint",
    "forward_scheduler_run",
    "forward_state_transition",
    "forward_operational_alert",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE7D_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE7D_TABLES:
            table.drop(bind=bind, checkfirst=True)
