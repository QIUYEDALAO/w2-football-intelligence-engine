"""create lineup intelligence append-only tables

Revision ID: 0024_create_lineup_intelligence
Revises: 0023_create_checkpoint_refresh_schedule
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0024_create_lineup_intelligence"
down_revision: str | None = "0023_create_checkpoint_refresh_schedule"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "lineup_source_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_revision", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("object_uri", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source", "source_revision", "sha256", name="uq_lineup_source_snapshot"
        ),
    )
    op.create_table(
        "player_identity_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("api_football_player_id", sa.String(64), nullable=False),
        sa.Column("transfermarkt_player_id", sa.String(64)),
        sa.Column("team_external_id", sa.String(64), nullable=False),
        sa.Column("player_name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("provider_position", sa.String(64)),
        sa.Column("transfermarkt_position", sa.String(128)),
        sa.Column("mapping_status", sa.String(32), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.String(128)),
        sa.UniqueConstraint(
            "api_football_player_id",
            "team_external_id",
            "valid_from",
            name="uq_lineup_player_identity_validity",
        ),
    )
    op.create_index(
        "ix_lineup_identity_transfermarkt", "player_identity_mappings", ["transfermarkt_player_id"]
    )
    op.create_table(
        "player_valuation_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("transfermarkt_player_id", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_value_eur", sa.Numeric(16, 2), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "transfermarkt_player_id",
            "observed_at",
            "source_sha256",
            name="uq_player_valuation_observation",
        ),
    )
    op.create_index(
        "ix_player_valuation_asof",
        "player_valuation_observations",
        ["transfermarkt_player_id", "observed_at"],
    )
    op.create_table(
        "structured_lineup_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fixture_id", sa.String(64), nullable=False),
        sa.Column("team_external_id", sa.String(64), nullable=False),
        sa.Column("formation", sa.String(32)),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("authoritative_status", sa.String(32), nullable=False),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "fixture_id", "team_external_id", "captured_at", name="uq_lineup_snapshot"
        ),
    )
    op.create_index(
        "ix_lineup_snapshot_fixture", "structured_lineup_snapshots", ["fixture_id", "captured_at"]
    )
    op.create_table(
        "structured_lineup_players",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "lineup_snapshot_id",
            sa.String(36),
            sa.ForeignKey("structured_lineup_snapshots.id"),
            nullable=False,
        ),
        sa.Column("api_football_player_id", sa.String(64), nullable=False),
        sa.Column("player_name", sa.String(255), nullable=False),
        sa.Column("starter", sa.Boolean(), nullable=False),
        sa.Column("shirt_number", sa.Integer()),
        sa.Column("provider_position", sa.String(64)),
        sa.Column("grid", sa.String(32)),
        sa.Column("captain", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "identity_mapping_id", sa.String(36), sa.ForeignKey("player_identity_mappings.id")
        ),
        sa.Column("mapping_status", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "lineup_snapshot_id", "api_football_player_id", name="uq_lineup_snapshot_player"
        ),
    )
    op.create_index(
        "ix_lineup_player_snapshot", "structured_lineup_players", ["lineup_snapshot_id", "starter"]
    )
    op.create_table(
        "team_lineup_baselines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_external_id", sa.String(64), nullable=False),
        sa.Column("competition_external_id", sa.String(64), nullable=False),
        sa.Column("season", sa.String(32), nullable=False),
        sa.Column("as_of_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("input_manifest", sa.JSON(), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "team_external_id",
            "competition_external_id",
            "season",
            "as_of_time",
            name="uq_team_lineup_baseline_asof",
        ),
    )
    op.create_index(
        "ix_team_lineup_baseline_lookup",
        "team_lineup_baselines",
        ["team_external_id", "as_of_time"],
    )


def downgrade() -> None:
    for table, indexes in (
        ("team_lineup_baselines", ("ix_team_lineup_baseline_lookup",)),
        ("structured_lineup_players", ("ix_lineup_player_snapshot",)),
        ("structured_lineup_snapshots", ("ix_lineup_snapshot_fixture",)),
        ("player_valuation_observations", ("ix_player_valuation_asof",)),
        ("player_identity_mappings", ("ix_lineup_identity_transfermarkt",)),
        ("lineup_source_snapshots", ()),
    ):
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
