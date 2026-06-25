"""create recommendation lock ledger

Revision ID: 0020_create_recommendation_lock
Revises: 0019_create_stage7i_lifecycle_supervision
Create Date: 2026-06-25 16:45:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0020_create_recommendation_lock"
down_revision: str | None = "0019_create_stage7i_lifecycle_supervision"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "gate5_recommendation_lock_event",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("lock_id", sa.String(length=128), nullable=False),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("selection", sa.String(length=64), nullable=False),
        sa.Column("line", sa.String(length=64), nullable=True),
        sa.Column("probability", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prior_event_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("candidate", sa.Boolean(), nullable=False),
        sa.Column("formal_recommendation", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_gate5_recommendation_lock_event_id"),
        sa.UniqueConstraint("lock_id", "version", name="uq_gate5_recommendation_lock_version"),
    )
    op.create_index(
        "ix_gate5_recommendation_lock_event_lock",
        "gate5_recommendation_lock_event",
        ["lock_id"],
    )
    op.create_index(
        "ix_gate5_recommendation_lock_event_fixture",
        "gate5_recommendation_lock_event",
        ["fixture_id"],
    )
    op.create_index(
        "ix_gate5_recommendation_lock_event_time",
        "gate5_recommendation_lock_event",
        ["event_time"],
    )


def downgrade() -> None:
    op.drop_table("gate5_recommendation_lock_event")
