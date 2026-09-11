"""persist immutable provider quota observations

Revision ID: 0058_quota_observation_history
Revises: 0057_provider_quota_observation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0058_quota_observation_history"
down_revision: str | None = "0057_provider_quota_observation"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "provider_quota_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("daily_remaining", sa.Integer(), nullable=True),
        sa.Column("burst_limit", sa.Integer(), nullable=True),
        sa.Column("burst_remaining", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "endpoint",
            "request_hash",
            name="uq_provider_quota_observation_request",
        ),
    )
    op.create_index(
        "ix_provider_quota_observations_observed_at",
        "provider_quota_observations",
        ["observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_quota_observations_observed_at",
        table_name="provider_quota_observations",
    )
    op.drop_table("provider_quota_observations")
