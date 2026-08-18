"""persist pre-registered opportunities separately from evaluation attempts

Revision ID: 0066_dynamic_evaluation_opportunity_writer
Revises: 0065_opportunity_capture_identity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0066_dynamic_evaluation_opportunity_writer"
down_revision: str | None = "0065_opportunity_capture_identity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    table = "dynamic_prematch_evaluations"
    op.add_column(table, sa.Column("opportunity_identity_hash", sa.String(64)))
    op.add_column(table, sa.Column("attempt_identity_hash", sa.String(64)))
    op.add_column(table, sa.Column("scheduled_checkpoint_at", sa.DateTime(timezone=True)))
    op.add_column(table, sa.Column("checkpoint_plan_identity", sa.String(128)))
    op.add_column(table, sa.Column("source_event_identity", sa.String(128)))
    op.create_index(
        "ix_dynamic_prematch_evaluation_opportunity",
        table,
        ["opportunity_identity_hash"],
    )
    op.create_index(
        "uq_dynamic_prematch_evaluation_attempt",
        table,
        ["attempt_identity_hash"],
        unique=True,
    )

    op.create_table(
        "dynamic_prematch_opportunities",
        sa.Column("opportunity_identity_hash", sa.String(64), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("market", sa.String(64), nullable=False),
        sa.Column("model_forecast_capture_identity_hash", sa.String(64), nullable=False),
        sa.Column("evaluation_policy_version", sa.String(64), nullable=False),
        sa.Column("evaluation_slot_id", sa.String(64), nullable=False),
        sa.Column("scheduled_checkpoint_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checkpoint_plan_identity", sa.String(128), nullable=False),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("latest_attempt_identity_hash", sa.String(64)),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_dynamic_prematch_opportunity_fixture_slot",
        "dynamic_prematch_opportunities",
        ["fixture_id", "evaluation_slot_id", "market"],
    )


def downgrade() -> None:
    op.drop_table("dynamic_prematch_opportunities")
    table = "dynamic_prematch_evaluations"
    op.drop_index("uq_dynamic_prematch_evaluation_attempt", table_name=table)
    op.drop_index("ix_dynamic_prematch_evaluation_opportunity", table_name=table)
    op.drop_column(table, "source_event_identity")
    op.drop_column(table, "checkpoint_plan_identity")
    op.drop_column(table, "scheduled_checkpoint_at")
    op.drop_column(table, "attempt_identity_hash")
    op.drop_column(table, "opportunity_identity_hash")
