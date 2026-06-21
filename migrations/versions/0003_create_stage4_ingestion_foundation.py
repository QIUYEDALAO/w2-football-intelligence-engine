"""create stage 4 ingestion foundation

Revision ID: 0003_create_stage4_ingestion_foundation
Revises: 0002_create_stage3_domain_model
Create Date: 2026-06-22 02:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0003_create_stage4_ingestion_foundation"
down_revision: str | None = "0002_create_stage3_domain_model"
branch_labels: str | None = None
depends_on: str | None = None

STAGE4_TABLES = {
    "ingestion_runs",
    "provider_request_logs",
    "quota_usage",
    "sync_cursors",
    "freshness_alerts",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE4_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE4_TABLES:
            table.drop(bind=bind, checkfirst=True)

