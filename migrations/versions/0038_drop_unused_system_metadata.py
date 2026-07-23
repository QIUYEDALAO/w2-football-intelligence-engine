"""drop the unused system metadata table

Revision ID: 0038_drop_unused_system_metadata
Revises: 0037_seed_competition_runtime_authority
Create Date: 2026-07-23 12:30:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0038_drop_unused_system_metadata"
down_revision: str | None = "0037_seed_competition_runtime_authority"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_table("system_metadata")


def downgrade() -> None:
    op.create_table(
        "system_metadata",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
