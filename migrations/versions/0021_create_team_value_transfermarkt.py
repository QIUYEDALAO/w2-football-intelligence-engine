"""create transfermarkt team value timeline

Revision ID: 0021_create_team_value_transfermarkt
Revises: 0020_create_recommendation_lock
Create Date: 2026-06-25 22:10:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0021_create_team_value_transfermarkt"
down_revision: str | None = "0020_create_recommendation_lock"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "team_value_source_snapshot",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=False),
        sa.Column("source_revision", sa.String(length=128), nullable=True),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("raw_path", sa.String(length=512), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("license", sa.String(length=64), nullable=False),
        sa.Column("terms_summary", sa.String(length=512), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "source_system",
            "raw_path",
            "sha256_checksum",
            name="uq_team_value_source_snapshot",
        ),
    )
    op.create_index(
        "ix_team_value_source_snapshot_ingested",
        "team_value_source_snapshot",
        ["ingested_at"],
    )

    op.create_table(
        "team_value_mapping",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("transfermarkt_club_id", sa.String(length=64), nullable=False),
        sa.Column("transfermarkt_club_name", sa.String(length=255), nullable=False),
        sa.Column("w2_team_id", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("mapping_source", sa.String(length=128), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(length=512), nullable=True),
        sa.UniqueConstraint(
            "source_system",
            "transfermarkt_club_id",
            "w2_team_id",
            "valid_from",
            name="uq_team_value_mapping_identity",
        ),
    )
    op.create_index("ix_team_value_mapping_w2_team", "team_value_mapping", ["w2_team_id"])
    op.create_index(
        "ix_team_value_mapping_transfermarkt",
        "team_value_mapping",
        ["source_system", "transfermarkt_club_id"],
    )

    op.create_table(
        "team_value_observation",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("transfermarkt_club_id", sa.String(length=64), nullable=False),
        sa.Column("transfermarkt_club_name", sa.String(length=255), nullable=False),
        sa.Column("season", sa.String(length=32), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("value_eur", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("raw_path", sa.String(length=512), nullable=False),
        sa.Column("source_row_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["team_value_source_snapshot.id"]),
        sa.UniqueConstraint(
            "source_system",
            "transfermarkt_club_id",
            "valid_from",
            "source_row_sha256",
            name="uq_team_value_observation_idempotency",
        ),
    )
    op.create_index(
        "ix_team_value_observation_club_asof",
        "team_value_observation",
        ["source_system", "transfermarkt_club_id", "valid_from"],
    )
    op.create_index(
        "ix_team_value_observation_ingested",
        "team_value_observation",
        ["ingested_at"],
    )


def downgrade() -> None:
    op.drop_table("team_value_observation")
    op.drop_table("team_value_mapping")
    op.drop_table("team_value_source_snapshot")
