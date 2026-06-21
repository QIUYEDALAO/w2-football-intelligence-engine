"""create stage 5 as-of dataset foundation

Revision ID: 0004_create_stage5_asof_foundation
Revises: 0003_create_stage4_ingestion_foundation
Create Date: 2026-06-22 05:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0004_create_stage5_asof_foundation"
down_revision: str | None = "0003_create_stage4_ingestion_foundation"
branch_labels: str | None = None
depends_on: str | None = None

STAGE5_TABLES = {
    "dataset_sources",
    "dataset_versions",
    "dataset_artifacts",
    "label_references",
    "asof_samples",
    "data_quality_runs",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE5_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE5_TABLES:
            table.drop(bind=bind, checkfirst=True)
