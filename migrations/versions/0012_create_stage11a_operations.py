"""create stage 11a operations tables

Revision ID: 0012_create_stage11a_operations
Revises: 0011_create_stage10a_read_api
Create Date: 2026-06-22 13:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0012_create_stage11a_operations"
down_revision: str | None = "0011_create_stage10a_read_api"
branch_labels: str | None = None
depends_on: str | None = None

STAGE11A_TABLES = {
    "operational_alert",
    "slo_evaluation",
    "backup_run",
    "restore_run",
    "security_audit_event",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE11A_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE11A_TABLES:
            table.drop(bind=bind, checkfirst=True)
