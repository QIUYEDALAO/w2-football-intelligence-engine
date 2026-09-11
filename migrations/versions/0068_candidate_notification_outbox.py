"""add candidate notification outbox

Revision ID: 0068_candidate_notification_outbox
Revises: 0067_checkpoint_plan_reschedule_audit
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0068_candidate_notification_outbox"
down_revision: str | None = "0067_checkpoint_plan_reschedule_audit"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "candidate_notification_outbox"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("notification_event_id", sa.String(64), primary_key=True),
        sa.Column("opportunity_identity_hash", sa.String(64)),
        sa.Column("attempt_identity_hash", sa.String(64)),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("previous_state", sa.String(64)),
        sa.Column("current_state", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("delivery_status", sa.String(32), nullable=False),
        sa.Column("delivery_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(512)),
        sa.UniqueConstraint(
            "attempt_identity_hash",
            "event_type",
            name="uq_candidate_notification_attempt_event",
        ),
        sa.CheckConstraint(
            "delivery_status in ('PENDING', 'RETRY_PENDING', 'DELIVERED', 'FAILED')",
            name="ck_candidate_notification_delivery_status",
        ),
        sa.CheckConstraint(
            "delivery_attempt_count >= 0",
            name="ck_candidate_notification_attempt_count",
        ),
    )
    op.create_index(
        "ix_candidate_notification_delivery",
        TABLE,
        ["delivery_status", "created_at"],
    )
    op.create_index(
        "ix_candidate_notification_opportunity",
        TABLE,
        ["opportunity_identity_hash", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_notification_opportunity", table_name=TABLE)
    op.drop_index("ix_candidate_notification_delivery", table_name=TABLE)
    op.drop_table(TABLE)
