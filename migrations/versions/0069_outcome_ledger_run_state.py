"""add outcome ledger operational run state

Revision ID: 0069_outcome_ledger_run_state
Revises: 0068_candidate_notification_outbox
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0069_outcome_ledger_run_state"
down_revision: str | None = "0068_candidate_notification_outbox"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "outcome_ledger_run_state",
        sa.Column("state_key", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("active_task_id", sa.String(255)),
        sa.Column("queued_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("defer_started_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_deferrals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_defer_reason", sa.String(128)),
        sa.Column("pending_settlement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_cursor", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_error", sa.String(512)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "consecutive_deferrals >= 0",
            name="ck_outcome_ledger_run_state_deferrals",
        ),
        sa.CheckConstraint(
            "pending_settlement_count >= 0",
            name="ck_outcome_ledger_run_state_pending",
        ),
    )


def downgrade() -> None:
    op.drop_table("outcome_ledger_run_state")
