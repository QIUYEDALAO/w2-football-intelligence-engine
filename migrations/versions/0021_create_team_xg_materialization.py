"""create team xg materialization

Revision ID: 0021_create_team_xg_materialization
Revises: 0020_create_recommendation_lock
Create Date: 2026-06-26 03:40:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0021_create_team_xg_materialization"
down_revision: str | None = "0020_create_recommendation_lock"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "team_xg_match",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("team_id", sa.String(length=64), nullable=False),
        sa.Column("opponent_team_id", sa.String(length=64), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("xg_for", sa.Float(), nullable=False),
        sa.Column("xg_against", sa.Float(), nullable=False),
        sa.Column("goals_for", sa.Integer(), nullable=False),
        sa.Column("goals_against", sa.Integer(), nullable=False),
        sa.Column("raw_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("candidate", sa.Boolean(), nullable=False),
        sa.Column("formal_recommendation", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("fixture_id", "team_id", name="uq_team_xg_match_fixture_team"),
    )
    op.create_index("ix_team_xg_match_team_kickoff", "team_xg_match", ["team_id", "kickoff_at"])
    op.create_index("ix_team_xg_match_fixture", "team_xg_match", ["fixture_id"])

    op.create_table(
        "team_xg_rolling_snapshot",
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
        sa.UniqueConstraint("team_id", "as_of_fixture_id", name="uq_team_xg_snapshot_fixture_team"),
    )
    op.create_index(
        "ix_team_xg_rolling_snapshot_team_asof",
        "team_xg_rolling_snapshot",
        ["team_id", "as_of_time"],
    )


def downgrade() -> None:
    op.drop_table("team_xg_rolling_snapshot")
    op.drop_table("team_xg_match")
