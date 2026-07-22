"""harden FAH authority integrity

Revision ID: 0026_harden_fah_authority_integrity
Revises: 0025_create_fah_data_foundation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0026_harden_fah_authority_integrity"
down_revision: str | None = "0025_create_fah_data_foundation"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("historical_market_source_snapshots") as batch:
        batch.add_column(sa.Column("registry_schema_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("snapshot_semantics", sa.String(32), nullable=True))
        batch.add_column(sa.Column("canonical_bookmaker_policy", sa.String(64), nullable=True))
        batch.create_unique_constraint("uq_historical_market_source_sha256", ["sha256"])

    with op.batch_alter_table("canonical_historical_ah_facts") as batch:
        batch.add_column(sa.Column("canonical_key", sa.String(64), nullable=True))
        batch.add_column(sa.Column("source_registry_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("source_schema_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("bookmaker_policy", sa.String(64), nullable=True))
        batch.create_unique_constraint(
            "uq_canonical_historical_ah_canonical_key",
            ["canonical_key"],
        )
        batch.create_unique_constraint("uq_canonical_historical_ah_fact_id", ["fact_id"])
        batch.create_unique_constraint(
            "uq_canonical_historical_ah_source_snapshot_key",
            ["source_snapshot_id", "canonical_key"],
        )

    with op.batch_alter_table("team_identity_crosswalks") as batch:
        batch.add_column(sa.Column("source_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("reviewed_by", sa.String(128), nullable=True))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "player_identity_crosswalks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("api_football_player_id", sa.String(64), nullable=False),
        sa.Column("transfermarkt_player_id", sa.String(64), nullable=False),
        sa.Column("api_football_team_id", sa.String(64), nullable=False),
        sa.Column("transfermarkt_club_id", sa.String(64), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("crosswalk_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("crosswalk_hash", name="uq_player_identity_crosswalk_hash"),
        sa.UniqueConstraint(
            "api_football_player_id",
            "competition_id",
            "valid_from",
            name="uq_player_identity_crosswalk_natural",
        ),
    )
    op.create_index(
        "ix_player_crosswalk_lookup",
        "player_identity_crosswalks",
        ["api_football_team_id", "competition_id", "valid_from"],
    )

    op.create_table(
        "registered_roster_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("transfermarkt_club_id", sa.String(64), nullable=False),
        sa.Column("transfermarkt_player_id", sa.String(64), nullable=False),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot_status", sa.String(32), nullable=False),
        sa.Column("membership_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("membership_hash", name="uq_registered_roster_membership_hash"),
        sa.UniqueConstraint(
            "transfermarkt_club_id",
            "transfermarkt_player_id",
            "snapshot_date",
            name="uq_registered_roster_membership_natural",
        ),
    )
    op.create_index(
        "ix_registered_roster_snapshot_lookup",
        "registered_roster_snapshots",
        ["transfermarkt_club_id", "snapshot_date"],
    )

    with op.batch_alter_table("player_club_membership_observations") as batch:
        batch.add_column(sa.Column("membership_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("team_value_asof_artifacts") as batch:
        batch.add_column(sa.Column("natural_identity", sa.String(64), nullable=True))
        batch.create_unique_constraint("uq_team_value_asof_natural_identity", ["natural_identity"])


def downgrade() -> None:
    with op.batch_alter_table("team_value_asof_artifacts") as batch:
        batch.drop_constraint("uq_team_value_asof_natural_identity", type_="unique")
        batch.drop_column("natural_identity")

    with op.batch_alter_table("player_club_membership_observations") as batch:
        batch.drop_column("valid_to")
        batch.drop_column("valid_from")
        batch.drop_column("membership_hash")

    op.drop_index("ix_registered_roster_snapshot_lookup", table_name="registered_roster_snapshots")
    op.drop_table("registered_roster_snapshots")

    op.drop_index("ix_player_crosswalk_lookup", table_name="player_identity_crosswalks")
    op.drop_table("player_identity_crosswalks")

    with op.batch_alter_table("team_identity_crosswalks") as batch:
        batch.drop_column("reviewed_at")
        batch.drop_column("reviewed_by")
        batch.drop_column("source_sha256")

    with op.batch_alter_table("canonical_historical_ah_facts") as batch:
        batch.drop_constraint(
            "uq_canonical_historical_ah_source_snapshot_key",
            type_="unique",
        )
        batch.drop_constraint("uq_canonical_historical_ah_fact_id", type_="unique")
        batch.drop_constraint("uq_canonical_historical_ah_canonical_key", type_="unique")
        batch.drop_column("bookmaker_policy")
        batch.drop_column("source_schema_version")
        batch.drop_column("source_registry_version")
        batch.drop_column("canonical_key")

    with op.batch_alter_table("historical_market_source_snapshots") as batch:
        batch.drop_constraint("uq_historical_market_source_sha256", type_="unique")
        batch.drop_column("canonical_bookmaker_policy")
        batch.drop_column("snapshot_semantics")
        batch.drop_column("registry_schema_version")
