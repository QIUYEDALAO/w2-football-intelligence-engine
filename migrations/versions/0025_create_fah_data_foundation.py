"""create FAH data foundation tables

Revision ID: 0025_create_fah_data_foundation
Revises: 0024_create_lineup_intelligence
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0025_create_fah_data_foundation"
down_revision: str | None = "0024_create_lineup_intelligence"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "historical_market_source_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("object_uri", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("license_status", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("audit_payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("source_id", "sha256", name="uq_historical_market_source_snapshot"),
    )
    op.create_table(
        "canonical_historical_ah_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fact_id", sa.String(128), nullable=False),
        sa.Column("fact_hash", sa.String(64), nullable=False),
        sa.Column("source_snapshot_id", sa.String(128), nullable=False),
        sa.Column("provider_fixture_id", sa.String(128), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("season", sa.String(32), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_provider_id", sa.String(128), nullable=False),
        sa.Column("away_team_provider_id", sa.String(128), nullable=False),
        sa.Column("bookmaker_id", sa.String(128), nullable=False),
        sa.Column("quote_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quote_identity_hash", sa.String(64), nullable=False),
        sa.Column("result_identity_hash", sa.String(64), nullable=False),
        sa.Column("home_settlement", sa.String(32), nullable=False),
        sa.Column("away_settlement", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("fact_hash", name="uq_canonical_historical_ah_fact_hash"),
    )
    op.create_index(
        "ix_canonical_ah_competition_kickoff",
        "canonical_historical_ah_facts",
        ["competition_id", "kickoff_utc"],
    )
    op.create_index(
        "ix_canonical_ah_home_kickoff",
        "canonical_historical_ah_facts",
        ["home_team_provider_id", "kickoff_utc"],
    )
    op.create_index(
        "ix_canonical_ah_away_kickoff",
        "canonical_historical_ah_facts",
        ["away_team_provider_id", "kickoff_utc"],
    )
    op.create_index(
        "ix_canonical_ah_provider_fixture",
        "canonical_historical_ah_facts",
        ["provider_fixture_id"],
    )
    op.create_table(
        "team_identity_crosswalks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("api_football_team_id", sa.String(64), nullable=False),
        sa.Column("transfermarkt_club_id", sa.String(64), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("crosswalk_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("crosswalk_hash", name="uq_team_identity_crosswalk_hash"),
    )
    op.create_index(
        "ix_team_crosswalk_lookup",
        "team_identity_crosswalks",
        ["api_football_team_id", "competition_id", "valid_from"],
    )
    op.create_table(
        "player_club_membership_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("transfermarkt_player_id", sa.String(64), nullable=False),
        sa.Column("transfermarkt_club_id", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_player_club_membership_asof",
        "player_club_membership_observations",
        ["transfermarkt_club_id", "observed_at"],
    )
    op.create_table(
        "team_value_asof_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_external_id", sa.String(64), nullable=False),
        sa.Column("transfermarkt_club_id", sa.String(64), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("artifact_hash", name="uq_team_value_asof_artifact_hash"),
    )
    op.create_index(
        "ix_team_value_asof_lookup",
        "team_value_asof_artifacts",
        ["team_external_id", "competition_id", "as_of"],
    )


def downgrade() -> None:
    for table, indexes in (
        ("team_value_asof_artifacts", ("ix_team_value_asof_lookup",)),
        ("player_club_membership_observations", ("ix_player_club_membership_asof",)),
        ("team_identity_crosswalks", ("ix_team_crosswalk_lookup",)),
        (
            "canonical_historical_ah_facts",
            (
                "ix_canonical_ah_provider_fixture",
                "ix_canonical_ah_away_kickoff",
                "ix_canonical_ah_home_kickoff",
                "ix_canonical_ah_competition_kickoff",
            ),
        ),
        ("historical_market_source_snapshots", ()),
    ):
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
