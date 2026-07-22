"""fix matchday checkpoint execution

Revision ID: 0030_fix_matchday_checkpoint_execution
Revises: 0029_consolidate_matchday_runtime_authority
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0030_fix_matchday_checkpoint_execution"
down_revision: str | None = "0029_consolidate_matchday_runtime_authority"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "matchday_endpoint_captures", sa.Column("competition_id", sa.String(128), nullable=True)
    )
    op.add_column(
        "matchday_endpoint_captures",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "matchday_checkpoint_plans",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "matchday_checkpoint_plans", sa.Column("claimed_by", sa.String(128), nullable=True)
    )
    op.add_column(
        "matchday_checkpoint_plans",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "matchday_checkpoint_plans",
        sa.Column("test_only", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "matchday_checkpoint_plans", sa.Column("namespace", sa.String(128), nullable=True)
    )
    op.create_index(
        "ix_matchday_checkpoint_plan_claim",
        "matchday_checkpoint_plans",
        ["status", "window_start", "window_end", "claimed_at"],
    )
    op.create_table(
        "football_data_team_crosswalks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("football_data_source_identity", sa.String(128), nullable=False),
        sa.Column("football_data_team_name", sa.String(255), nullable=False),
        sa.Column("league", sa.String(128), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("season_coverage", sa.JSON(), nullable=False),
        sa.Column("w2_team_id", sa.String(128), nullable=False),
        sa.Column("api_football_team_ids", sa.JSON(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("source_hashes", sa.JSON(), nullable=False),
        sa.Column("candidate_generation_method", sa.String(128), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("crosswalk_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("crosswalk_hash", name="uq_football_data_team_crosswalk_hash"),
        sa.UniqueConstraint(
            "football_data_source_identity",
            "competition_id",
            "valid_from",
            name="uq_football_data_team_crosswalk_natural",
        ),
    )
    op.create_index(
        "ix_football_data_team_crosswalk_lookup",
        "football_data_team_crosswalks",
        ["w2_team_id", "competition_id", "valid_from"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_football_data_team_crosswalk_lookup",
        table_name="football_data_team_crosswalks",
    )
    op.drop_table("football_data_team_crosswalks")
    op.drop_index("ix_matchday_checkpoint_plan_claim", table_name="matchday_checkpoint_plans")
    op.drop_column("matchday_checkpoint_plans", "namespace")
    op.drop_column("matchday_checkpoint_plans", "test_only")
    op.drop_column("matchday_checkpoint_plans", "attempt_count")
    op.drop_column("matchday_checkpoint_plans", "claimed_by")
    op.drop_column("matchday_checkpoint_plans", "claimed_at")
    op.drop_column("matchday_endpoint_captures", "attempt")
    op.drop_column("matchday_endpoint_captures", "competition_id")
