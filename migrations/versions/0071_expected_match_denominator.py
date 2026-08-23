"""materialize PIT expected-match fixture observations

Revision ID: 0071_expected_match_denominator
Revises: 0070_notification_delivery_routing
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0071_expected_match_denominator"
down_revision: str | None = "0070_notification_delivery_routing"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "expected_match_fixture_materialization",
        sa.Column("raw_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_inserted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("rejection_count", sa.Integer(), nullable=False),
        sa.Column("rejection_samples", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "status in ('COMPLETE', 'COMPLETE_WITH_REJECTIONS', 'REJECTED')",
            name="ck_expected_match_fixture_materialization_status",
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_sha256"],
            ["raw_payload.sha256"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("raw_payload_sha256"),
    )
    op.create_table(
        "expected_match_fixture_observation",
        sa.Column("observation_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_fixture_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_fixture_id", sa.String(length=128), nullable=False),
        sa.Column("provider_league_id", sa.String(length=64), nullable=False),
        sa.Column("season", sa.String(length=32), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_provider_team_id", sa.String(length=64), nullable=False),
        sa.Column("away_provider_team_id", sa.String(length=64), nullable=False),
        sa.Column("fixture_status", sa.String(length=16), nullable=False),
        sa.Column("home_goals", sa.Integer(), nullable=True),
        sa.Column("away_goals", sa.Integer(), nullable=True),
        sa.Column("raw_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_inserted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["raw_payload_sha256"],
            ["raw_payload.sha256"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("observation_hash"),
        sa.UniqueConstraint(
            "raw_payload_sha256",
            "provider",
            "provider_fixture_id",
            name="uq_expected_match_fixture_raw_identity",
        ),
    )
    op.create_index(
        "ix_expected_match_fixture_scope_pit",
        "expected_match_fixture_observation",
        [
            "provider",
            "provider_league_id",
            "captured_at",
            "source_inserted_at",
        ],
    )
    op.create_index(
        "ix_expected_match_fixture_home_kickoff",
        "expected_match_fixture_observation",
        ["home_provider_team_id", "kickoff_at"],
    )
    op.create_index(
        "ix_expected_match_fixture_away_kickoff",
        "expected_match_fixture_observation",
        ["away_provider_team_id", "kickoff_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_expected_match_fixture_away_kickoff",
        table_name="expected_match_fixture_observation",
    )
    op.drop_index(
        "ix_expected_match_fixture_home_kickoff",
        table_name="expected_match_fixture_observation",
    )
    op.drop_index(
        "ix_expected_match_fixture_scope_pit",
        table_name="expected_match_fixture_observation",
    )
    op.drop_table("expected_match_fixture_observation")
    op.drop_table("expected_match_fixture_materialization")
