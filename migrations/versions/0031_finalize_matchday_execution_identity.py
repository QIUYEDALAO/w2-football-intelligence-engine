"""finalize matchday execution identity

Revision ID: 0031_finalize_matchday_execution_identity
Revises: 0030_fix_matchday_checkpoint_execution
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0031_finalize_matchday_execution_identity"
down_revision: str | None = "0030_fix_matchday_checkpoint_execution"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "matchday_checkpoint_plans", sa.Column("claim_token", sa.String(64), nullable=True)
    )
    op.add_column(
        "matchday_checkpoint_plans",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "matchday_endpoint_capture_plans",
        sa.Column("link_hash", sa.String(64), primary_key=True),
        sa.Column("capture_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(128), nullable=False),
        sa.Column("endpoint", sa.String(64), nullable=False),
        sa.Column("link_status", sa.String(32), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["matchday_endpoint_captures.capture_id"],
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["matchday_checkpoint_plans.plan_id"],
        ),
        sa.UniqueConstraint(
            "capture_id",
            "plan_id",
            "endpoint",
            name="uq_matchday_endpoint_capture_plan_identity",
        ),
    )
    op.create_index(
        "ix_matchday_endpoint_capture_plan_capture",
        "matchday_endpoint_capture_plans",
        ["capture_id"],
    )
    op.create_index(
        "ix_matchday_endpoint_capture_plan_plan",
        "matchday_endpoint_capture_plans",
        ["plan_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_matchday_endpoint_capture_plan_plan",
        table_name="matchday_endpoint_capture_plans",
    )
    op.drop_index(
        "ix_matchday_endpoint_capture_plan_capture",
        table_name="matchday_endpoint_capture_plans",
    )
    op.drop_table("matchday_endpoint_capture_plans")
    op.drop_column("matchday_checkpoint_plans", "claim_expires_at")
    op.drop_column("matchday_checkpoint_plans", "claim_token")
