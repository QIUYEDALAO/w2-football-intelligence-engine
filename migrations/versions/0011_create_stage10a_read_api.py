"""create stage 10a read api tables

Revision ID: 0011_create_stage10a_read_api
Revises: 0010_create_stage7d_forward_automation
Create Date: 2026-06-22 12:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0011_create_stage10a_read_api"
down_revision: str | None = "0010_create_stage7d_forward_automation"
branch_labels: str | None = None
depends_on: str | None = None

STAGE10A_TABLES = {
    "api_request_audit",
    "read_model_checkpoint",
    "operational_metric_snapshot",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE10A_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE10A_TABLES:
            table.drop(bind=bind, checkfirst=True)
