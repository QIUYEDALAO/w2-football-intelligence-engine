"""keep the window a checkpoint plan held before it was re-dated

plan_id excludes the kickoff, so a postponed fixture reuses its plan rows and
the re-date overwrites window, status, blockers and missed_at in place. No
other table records the previous plan: endpoint captures and the checkpoint
audit describe attempts, not the plan they were scheduled against.

Revision ID: 0067_checkpoint_plan_reschedule_audit
Revises: 0066_dynamic_evaluation_opportunity_writer
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0067_checkpoint_plan_reschedule_audit"
down_revision: str | None = "0066_dynamic_evaluation_opportunity_writer"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "matchday_checkpoint_plan_reschedules"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("reschedule_id", sa.String(64), primary_key=True),
        sa.Column(
            "plan_id",
            sa.String(128),
            sa.ForeignKey("matchday_checkpoint_plans.plan_id"),
            nullable=False,
        ),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("checkpoint", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_status", sa.String(32), nullable=False),
        sa.Column("previous_kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_attempt_count", sa.Integer(), nullable=False),
        sa.Column("previous_blockers", sa.JSON(), nullable=False),
        sa.Column("previous_missed_at", sa.DateTime(timezone=True)),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("new_kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "plan_id",
            "previous_kickoff_utc",
            "recorded_at",
            name="uq_matchday_checkpoint_plan_reschedule_identity",
        ),
    )
    op.create_index(
        "ix_matchday_checkpoint_plan_reschedule_plan",
        TABLE,
        ["plan_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_matchday_checkpoint_plan_reschedule_plan", table_name=TABLE)
    op.drop_table(TABLE)
