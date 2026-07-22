"""create matchday fixture identities

Revision ID: 0032_create_matchday_fixture_identities
Revises: 0031_finalize_matchday_execution_identity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0032_create_matchday_fixture_identities"
down_revision: str | None = "0031_finalize_matchday_execution_identity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "matchday_fixture_identities",
        sa.Column("fixture_id", sa.String(128), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_fixture_id", sa.String(64), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("provider_league_id", sa.String(64), nullable=False),
        sa.Column("season", sa.String(32), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fixture_status", sa.String(32), nullable=False),
        sa.Column("home_provider_team_id", sa.String(64), nullable=False),
        sa.Column("away_provider_team_id", sa.String(64), nullable=False),
        sa.Column("home_w2_team_id", sa.String(128), nullable=True),
        sa.Column("away_w2_team_id", sa.String(128), nullable=True),
        sa.Column("team_identity_status", sa.String(64), nullable=False),
        sa.Column("raw_payload_sha256", sa.String(64), nullable=False),
        sa.Column("endpoint_capture_id", sa.String(64), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["endpoint_capture_id"],
            ["matchday_endpoint_captures.capture_id"],
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_fixture_id",
            name="uq_matchday_fixture_identity_provider_fixture",
        ),
    )
    op.create_index(
        "ix_matchday_fixture_identity_competition",
        "matchday_fixture_identities",
        ["competition_id", "kickoff_utc"],
    )
    op.create_index(
        "ix_matchday_fixture_identity_status",
        "matchday_fixture_identities",
        ["team_identity_status"],
    )
    op.create_index(
        "ix_matchday_fixture_identity_raw_payload",
        "matchday_fixture_identities",
        ["raw_payload_sha256"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_matchday_fixture_identity_raw_payload",
        table_name="matchday_fixture_identities",
    )
    op.drop_index(
        "ix_matchday_fixture_identity_status",
        table_name="matchday_fixture_identities",
    )
    op.drop_index(
        "ix_matchday_fixture_identity_competition",
        table_name="matchday_fixture_identities",
    )
    op.drop_table("matchday_fixture_identities")
