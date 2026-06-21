"""create stage 12a migration and shadow tables

Revision ID: 0013_create_stage12a_migration_shadow
Revises: 0012_create_stage11a_operations
Create Date: 2026-06-22 14:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0013_create_stage12a_migration_shadow"
down_revision: str | None = "0012_create_stage11a_operations"
branch_labels: str | None = None
depends_on: str | None = None

STAGE12A_TABLES = {
    "migration_source_asset",
    "migration_dry_run",
    "migration_validation_record",
    "migration_quarantine_record",
    "shadow_run",
    "shadow_comparison_record",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE12A_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE12A_TABLES:
            table.drop(bind=bind, checkfirst=True)
