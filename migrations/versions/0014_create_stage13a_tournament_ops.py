"""create stage 13a tournament operations tables

Revision ID: 0014_create_stage13a_tournament_ops
Revises: 0013_create_stage12a_migration_shadow
Create Date: 2026-06-22 15:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0014_create_stage13a_tournament_ops"
down_revision: str | None = "0013_create_stage12a_migration_shadow"
branch_labels: str | None = None
depends_on: str | None = None

STAGE13A_TABLES = {
    "tournament_profile",
    "tournament_operations_plan",
    "tournament_readiness_audit",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE13A_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE13A_TABLES:
            table.drop(bind=bind, checkfirst=True)
