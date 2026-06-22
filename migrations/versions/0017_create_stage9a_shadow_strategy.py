"""create stage 9a shadow strategy tables

Revision ID: 0017_create_stage9a_shadow_strategy
Revises: 0016_create_stage15a_operational_governance
Create Date: 2026-06-23 01:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0017_create_stage9a_shadow_strategy"
down_revision: str | None = "0016_create_stage15a_operational_governance"
branch_labels: str | None = None
depends_on: str | None = None

STAGE9A_TABLES = {
    "shadow_strategy_run",
    "shadow_strategy_candidate",
    "shadow_strategy_lock",
    "shadow_strategy_event",
    "shadow_strategy_settlement",
    "shadow_strategy_evaluation",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE9A_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE9A_TABLES:
            table.drop(bind=bind, checkfirst=True)
