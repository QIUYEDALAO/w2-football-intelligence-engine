"""create checkpoint refresh schedule

Revision ID: 0023_create_checkpoint_refresh_schedule
Revises: 0022_extend_recommendation_lock_snapshot
Create Date: 2026-07-04 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0023_create_checkpoint_refresh_schedule"
down_revision: str | None = "0022_extend_recommendation_lock_snapshot"
branch_labels: str | None = None
depends_on: str | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "future_refresh_checkpoint_plan" not in tables:
        op.create_table(
            "future_refresh_checkpoint_plan",
            sa.Column("id", sa.String(length=160), nullable=False),
            sa.Column("fixture_id", sa.String(length=64), nullable=False),
            sa.Column("checkpoint", sa.String(length=64), nullable=False),
            sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("endpoints", sa.JSON(), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_audit_id", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("fixture_id", "checkpoint", name="uq_future_refresh_checkpoint"),
        )
        op.create_index(
            "ix_future_refresh_checkpoint_due",
            "future_refresh_checkpoint_plan",
            ["due_at", "status"],
        )
        op.create_index(
            "ix_future_refresh_checkpoint_fixture",
            "future_refresh_checkpoint_plan",
            ["fixture_id"],
        )
    if "future_refresh_checkpoint_audit" not in tables:
        op.create_table(
            "future_refresh_checkpoint_audit",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("fixture_id", sa.String(length=64), nullable=False),
            sa.Column("checkpoint", sa.String(length=64), nullable=False),
            sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
            sa.Column("calls_used", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_future_refresh_checkpoint_audit_fixture",
            "future_refresh_checkpoint_audit",
            ["fixture_id"],
        )
        op.create_index(
            "ix_future_refresh_checkpoint_audit_asof",
            "future_refresh_checkpoint_audit",
            ["as_of"],
        )


def downgrade() -> None:
    tables = _tables()
    if "future_refresh_checkpoint_audit" in tables:
        op.drop_index(
            "ix_future_refresh_checkpoint_audit_asof",
            table_name="future_refresh_checkpoint_audit",
        )
        op.drop_index(
            "ix_future_refresh_checkpoint_audit_fixture",
            table_name="future_refresh_checkpoint_audit",
        )
        op.drop_table("future_refresh_checkpoint_audit")
    if "future_refresh_checkpoint_plan" in tables:
        op.drop_index(
            "ix_future_refresh_checkpoint_fixture",
            table_name="future_refresh_checkpoint_plan",
        )
        op.drop_index(
            "ix_future_refresh_checkpoint_due",
            table_name="future_refresh_checkpoint_plan",
        )
        op.drop_table("future_refresh_checkpoint_plan")
