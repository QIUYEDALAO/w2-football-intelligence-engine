"""reconcile historical lineup identity hash nullability

Revision ID: 0035_reconcile_lineup_identity_hash_nullability
Revises: 0034_create_dynamic_prematch_lifecycle
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0035_reconcile_lineup_identity_hash_nullability"
down_revision: str | None = "0034_create_dynamic_prematch_lifecycle"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Keep historical rows representable until they are re-materialized.

    Version 0034 already created this column nullable. Declaring the same fact
    here makes the persisted schema contract explicit for databases upgraded
    from older release chains.
    """
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "structured_lineup_snapshots",
            "lineup_identity_hash",
            existing_type=sa.String(length=64),
            nullable=True,
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "structured_lineup_snapshots",
            "lineup_identity_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )
