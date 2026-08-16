"""persist free-plan fixture scope observations

Revision ID: 0059_free_plan_fixture_scope_observation
Revises: 0058_quota_observation_history
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0059_free_plan_fixture_scope_observation"
down_revision: str | None = "0058_quota_observation_history"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "free_plan_fixture_scope_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("league_id", sa.String(length=64), nullable=False),
        sa.Column("season", sa.String(length=32), nullable=False),
        sa.Column("restricted", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider_error", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_free_plan_fixture_scope_observations_scope_time",
        "free_plan_fixture_scope_observations",
        ["provider", "league_id", "season", "observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_free_plan_fixture_scope_observations_scope_time",
        table_name="free_plan_fixture_scope_observations",
    )
    op.drop_table("free_plan_fixture_scope_observations")
