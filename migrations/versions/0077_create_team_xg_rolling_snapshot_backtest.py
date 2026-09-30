"""create team xg rolling snapshot backtest

Revision ID: 0077_create_team_xg_rolling_snapshot_backtest
Revises: 0076_forward_review_evidence
Create Date: 2026-09-28 20:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0077_create_team_xg_rolling_snapshot_backtest"
down_revision: str | None = "0076_forward_review_evidence"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    from migrations.legacy_0076_source_recovery import recover_known_minimal_sources

    recover_known_minimal_sources()
    op.create_table(
        "team_xg_rolling_snapshot_backtest",
        sa.Column("snapshot_id", sa.String(length=96), primary_key=True),
        sa.Column("team_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_fixture_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False),
        sa.Column("rolling_xg_for", sa.Float(), nullable=False),
        sa.Column("rolling_xg_against", sa.Float(), nullable=False),
        sa.Column("rolling_goals_for", sa.Float(), nullable=False),
        sa.Column("rolling_goals_against", sa.Float(), nullable=False),
        sa.Column("regression_index", sa.Float(), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("candidate", sa.Boolean(), nullable=False),
        sa.Column("formal_recommendation", sa.Boolean(), nullable=False),
        sa.UniqueConstraint(
            "team_id",
            "as_of_fixture_id",
            name="uq_team_xg_snapshot_bt_fixture_team",
        ),
    )
    op.create_index(
        "ix_team_xg_rolling_snapshot_bt_team_asof",
        "team_xg_rolling_snapshot_backtest",
        ["team_id", "as_of_time"],
    )


def downgrade() -> None:
    op.drop_table("team_xg_rolling_snapshot_backtest")
