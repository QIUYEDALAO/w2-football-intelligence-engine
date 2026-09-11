"""drop the retired future-refresh checkpoint plan authority

Revision ID: 0052_drop_retired_future_refresh_checkpoint_plan
Revises: 0051_apply_seven_day_collection_policy
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0052_drop_retired_future_refresh_checkpoint_plan"
down_revision: str | None = "0051_apply_seven_day_collection_policy"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "future_refresh_checkpoint_plan"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError("RETIRED_CHECKPOINT_PLAN_TABLE_MISSING")
    row_count = bind.execute(
        sa.text("select count(*) from future_refresh_checkpoint_plan")
    ).scalar_one()
    if row_count:
        raise RuntimeError(f"RETIRED_CHECKPOINT_PLAN_TABLE_NONEMPTY:{row_count}")
    dependencies = [
        f"{table}:{foreign_key.get('name')}"
        for table in inspector.get_table_names()
        for foreign_key in inspector.get_foreign_keys(table)
        if foreign_key.get("referred_table") == _TABLE
    ]
    if dependencies:
        raise RuntimeError(f"RETIRED_CHECKPOINT_PLAN_DEPENDENCIES:{sorted(dependencies)}")
    op.drop_table(_TABLE)


def downgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("checkpoint", sa.String(length=64), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("endpoints", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("last_audit_id", sa.Integer()),
        sa.UniqueConstraint("fixture_id", "checkpoint", name="uq_future_refresh_checkpoint"),
    )
    op.create_index(
        "ix_future_refresh_checkpoint_due",
        _TABLE,
        ["due_at", "status"],
    )
    op.create_index(
        "ix_future_refresh_checkpoint_fixture",
        _TABLE,
        ["fixture_id"],
    )
