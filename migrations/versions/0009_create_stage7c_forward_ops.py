"""create stage 7c forward operations

Revision ID: 0009_create_stage7c_forward_ops
Revises: 0008_create_stage7b_challenger
Create Date: 2026-06-22 10:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0009_create_stage7c_forward_ops"
down_revision: str | None = "0008_create_stage7b_challenger"
branch_labels: str | None = None
depends_on: str | None = None

STAGE7C_TABLES = {
    "forward_result_event",
    "forward_market_snapshot",
    "forward_gate_audit",
    "forward_cycle_run",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE7C_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE7C_TABLES:
            table.drop(bind=bind, checkfirst=True)
