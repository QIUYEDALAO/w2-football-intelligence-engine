"""finalize FAH authority constraints

Revision ID: 0027_finalize_fah_authority_constraints
Revises: 0026_harden_fah_authority_integrity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0027_finalize_fah_authority_constraints"
down_revision: str | None = "0026_harden_fah_authority_integrity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("historical_market_source_snapshots") as batch:
        batch.add_column(sa.Column("snapshot_hash", sa.String(64), nullable=True))
    op.execute(
        "UPDATE historical_market_source_snapshots "
        "SET snapshot_hash = sha256 "
        "WHERE snapshot_hash IS NULL OR snapshot_hash = ''"
    )
    with op.batch_alter_table("historical_market_source_snapshots") as batch:
        batch.alter_column("snapshot_hash", existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint(
            "uq_historical_market_source_snapshot_hash",
            ["snapshot_hash"],
        )

    with op.batch_alter_table("canonical_historical_ah_facts") as batch:
        batch.add_column(sa.Column("source_snapshot_db_id", sa.String(36), nullable=True))
    op.execute(
        "UPDATE canonical_historical_ah_facts "
        "SET source_snapshot_db_id = ("
        "  SELECT id FROM historical_market_source_snapshots s "
        "  WHERE s.source_id = canonical_historical_ah_facts.source_snapshot_id "
        "  LIMIT 1"
        ") "
        "WHERE source_snapshot_db_id IS NULL"
    )
    with op.batch_alter_table("canonical_historical_ah_facts") as batch:
        batch.alter_column("canonical_key", existing_type=sa.String(64), nullable=False)
        batch.create_foreign_key(
            "fk_canonical_ah_source_snapshot_db_id",
            "historical_market_source_snapshots",
            ["source_snapshot_db_id"],
            ["id"],
        )

    with op.batch_alter_table("team_identity_crosswalks") as batch:
        batch.create_unique_constraint(
            "uq_team_identity_crosswalk_natural",
            [
                "api_football_team_id",
                "transfermarkt_club_id",
                "competition_id",
                "valid_from",
            ],
        )

    with op.batch_alter_table("player_club_membership_observations") as batch:
        batch.alter_column("membership_hash", existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint(
            "uq_player_club_membership_hash",
            ["membership_hash"],
        )

    with op.batch_alter_table("registered_roster_snapshots") as batch:
        batch.add_column(sa.Column("roster_snapshot_id", sa.String(128), nullable=True))
    op.execute(
        "UPDATE registered_roster_snapshots "
        "SET roster_snapshot_id = "
        "  transfermarkt_club_id || ':' || snapshot_date "
        "WHERE roster_snapshot_id IS NULL OR roster_snapshot_id = ''"
    )
    with op.batch_alter_table("registered_roster_snapshots") as batch:
        batch.alter_column("roster_snapshot_id", existing_type=sa.String(128), nullable=False)
        batch.create_unique_constraint(
            "uq_registered_roster_snapshot_player",
            ["roster_snapshot_id", "transfermarkt_player_id"],
        )

    with op.batch_alter_table("team_value_asof_artifacts") as batch:
        batch.alter_column("natural_identity", existing_type=sa.String(64), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("team_value_asof_artifacts") as batch:
        batch.alter_column("natural_identity", existing_type=sa.String(64), nullable=True)

    with op.batch_alter_table("registered_roster_snapshots") as batch:
        batch.drop_constraint("uq_registered_roster_snapshot_player", type_="unique")
        batch.drop_column("roster_snapshot_id")

    with op.batch_alter_table("player_club_membership_observations") as batch:
        batch.drop_constraint("uq_player_club_membership_hash", type_="unique")
        batch.alter_column("membership_hash", existing_type=sa.String(64), nullable=True)

    with op.batch_alter_table("team_identity_crosswalks") as batch:
        batch.drop_constraint("uq_team_identity_crosswalk_natural", type_="unique")

    with op.batch_alter_table("canonical_historical_ah_facts") as batch:
        batch.drop_constraint("fk_canonical_ah_source_snapshot_db_id", type_="foreignkey")
        batch.alter_column("canonical_key", existing_type=sa.String(64), nullable=True)
        batch.drop_column("source_snapshot_db_id")

    with op.batch_alter_table("historical_market_source_snapshots") as batch:
        batch.drop_constraint("uq_historical_market_source_snapshot_hash", type_="unique")
        batch.drop_column("snapshot_hash")
