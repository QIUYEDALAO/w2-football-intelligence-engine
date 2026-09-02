"""persist immutable lineup first-seen evidence

Revision ID: 0071_lineup_first_seen_event
Revises: 0070_notification_delivery_routing
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0071_lineup_first_seen_event"
down_revision: str | None = "0070_notification_delivery_routing"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "lineup_first_seen_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("fixture_id", sa.String(length=128), nullable=False),
        sa.Column("competition_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_fixture_id", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("minutes_to_kickoff", sa.Integer(), nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), nullable=False),
        sa.Column("starting_xi", sa.JSON(), nullable=False),
        sa.Column("bench", sa.JSON(), nullable=False),
        sa.Column("formation", sa.JSON(), nullable=False),
        sa.Column("coach", sa.JSON(), nullable=False),
        sa.Column("coverage_status", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "provider",
            "provider_fixture_id",
            name="uq_lineup_first_seen_provider_fixture",
        ),
    )
    op.create_index(
        "ix_lineup_first_seen_at",
        "lineup_first_seen_events",
        ["first_seen_at"],
    )
    op.create_index(
        "ix_lineup_first_seen_competition",
        "lineup_first_seen_events",
        ["competition_id", "kickoff_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_lineup_first_seen_competition", table_name="lineup_first_seen_events")
    op.drop_index("ix_lineup_first_seen_at", table_name="lineup_first_seen_events")
    op.drop_table("lineup_first_seen_events")
