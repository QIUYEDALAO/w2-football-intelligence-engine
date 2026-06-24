"""create future refresh persistence tables

Revision ID: 0017_create_future_refresh_persistence
Revises: 0016_create_stage15a_operational_governance
Create Date: 2026-06-25 07:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0017_create_future_refresh_persistence"
down_revision: str | None = "0016_create_stage15a_operational_governance"
branch_labels: str | None = None
depends_on: str | None = None

FUTURE_REFRESH_TABLES = {
    "future_market_observation",
    "future_refresh_task_audit",
    "future_refresh_run_audit",
    "raw_payload",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in FUTURE_REFRESH_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in FUTURE_REFRESH_TABLES:
            table.drop(bind=bind, checkfirst=True)
