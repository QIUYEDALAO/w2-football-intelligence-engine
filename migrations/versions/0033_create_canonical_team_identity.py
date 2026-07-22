"""create canonical team identity

Revision ID: 0033_create_canonical_team_identity
Revises: 0032_create_matchday_fixture_identities
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0033_create_canonical_team_identity"
down_revision: str | None = "0032_create_matchday_fixture_identities"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "canonical_teams",
        sa.Column("w2_team_id", sa.String(128), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(128), nullable=True),
        sa.Column("active_status", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("w2_team_id", name="uq_canonical_team_w2_team_id"),
        sa.UniqueConstraint("identity_hash", name="uq_canonical_team_identity_hash"),
    )
    op.create_index("ix_canonical_team_status", "canonical_teams", ["active_status"])

    op.create_table(
        "provider_team_identity_crosswalks",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_team_id", sa.String(64), nullable=False),
        sa.Column("w2_team_id", sa.String(128), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("season", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("identity_status", sa.String(64), nullable=False),
        sa.Column("evidence_hashes", sa.JSON(), nullable=False),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["w2_team_id"], ["canonical_teams.w2_team_id"]),
        sa.UniqueConstraint(
            "provider",
            "provider_team_id",
            "competition_id",
            "season",
            "valid_from",
            name="uq_provider_team_identity_crosswalk_natural",
        ),
        sa.UniqueConstraint(
            "identity_hash",
            name="uq_provider_team_identity_crosswalk_hash",
        ),
    )
    op.create_index(
        "ix_provider_team_identity_crosswalk_lookup",
        "provider_team_identity_crosswalks",
        ["provider", "provider_team_id", "competition_id", "season"],
    )
    op.create_index(
        "ix_provider_team_identity_crosswalk_w2_team",
        "provider_team_identity_crosswalks",
        ["w2_team_id"],
    )
    op.create_index(
        "ix_provider_team_identity_crosswalk_status",
        "provider_team_identity_crosswalks",
        ["identity_status"],
    )

    op.create_table(
        "canonical_team_match_history",
        sa.Column("history_id", sa.String(128), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_fixture_id", sa.String(64), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("season", sa.String(32), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fixture_status", sa.String(32), nullable=False),
        sa.Column("team_side", sa.String(16), nullable=False),
        sa.Column("team_provider_id", sa.String(64), nullable=False),
        sa.Column("opponent_provider_id", sa.String(64), nullable=False),
        sa.Column("team_w2_id", sa.String(128), nullable=False),
        sa.Column("opponent_w2_id", sa.String(128), nullable=False),
        sa.Column("goals_for", sa.Integer(), nullable=False),
        sa.Column("goals_against", sa.Integer(), nullable=False),
        sa.Column("result_identity_hash", sa.String(64), nullable=False),
        sa.Column("source_raw_hash", sa.String(64), nullable=False),
        sa.Column("endpoint_capture_id", sa.String(64), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("history_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["team_w2_id"], ["canonical_teams.w2_team_id"]),
        sa.ForeignKeyConstraint(["opponent_w2_id"], ["canonical_teams.w2_team_id"]),
        sa.ForeignKeyConstraint(["endpoint_capture_id"], ["matchday_endpoint_captures.capture_id"]),
        sa.UniqueConstraint(
            "provider",
            "provider_fixture_id",
            "team_w2_id",
            name="uq_canonical_team_match_history_fixture_team",
        ),
        sa.UniqueConstraint("history_hash", name="uq_canonical_team_match_history_hash"),
    )
    op.create_index(
        "ix_canonical_team_match_history_team_kickoff",
        "canonical_team_match_history",
        ["team_w2_id", "kickoff_utc"],
    )
    op.create_index(
        "ix_canonical_team_match_history_fixture",
        "canonical_team_match_history",
        ["fixture_id"],
    )
    op.create_index(
        "ix_canonical_team_match_history_capture",
        "canonical_team_match_history",
        ["endpoint_capture_id"],
    )

    op.create_table(
        "team_rating_snapshots",
        sa.Column("rating_id", sa.String(128), primary_key=True),
        sa.Column("w2_team_id", sa.String(128), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("elo", sa.Float(), nullable=False),
        sa.Column("attack_strength", sa.Float(), nullable=False),
        sa.Column("defence_strength", sa.Float(), nullable=False),
        sa.Column("form_index", sa.Float(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_history_hashes", sa.JSON(), nullable=False),
        sa.Column("rating_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["w2_team_id"], ["canonical_teams.w2_team_id"]),
        sa.UniqueConstraint(
            "w2_team_id",
            "observed_at",
            "model_version",
            name="uq_team_rating_snapshot_natural",
        ),
        sa.UniqueConstraint("rating_hash", name="uq_team_rating_snapshot_hash"),
    )
    op.create_index(
        "ix_team_rating_snapshot_lookup",
        "team_rating_snapshots",
        ["w2_team_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_team_rating_snapshot_lookup", table_name="team_rating_snapshots")
    op.drop_table("team_rating_snapshots")
    op.drop_index(
        "ix_canonical_team_match_history_capture",
        table_name="canonical_team_match_history",
    )
    op.drop_index(
        "ix_canonical_team_match_history_fixture",
        table_name="canonical_team_match_history",
    )
    op.drop_index(
        "ix_canonical_team_match_history_team_kickoff",
        table_name="canonical_team_match_history",
    )
    op.drop_table("canonical_team_match_history")
    op.drop_index(
        "ix_provider_team_identity_crosswalk_status",
        table_name="provider_team_identity_crosswalks",
    )
    op.drop_index(
        "ix_provider_team_identity_crosswalk_w2_team",
        table_name="provider_team_identity_crosswalks",
    )
    op.drop_index(
        "ix_provider_team_identity_crosswalk_lookup",
        table_name="provider_team_identity_crosswalks",
    )
    op.drop_table("provider_team_identity_crosswalks")
    op.drop_index("ix_canonical_team_status", table_name="canonical_teams")
    op.drop_table("canonical_teams")
