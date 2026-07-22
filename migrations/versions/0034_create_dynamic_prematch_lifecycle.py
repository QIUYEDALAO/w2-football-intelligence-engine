"""create dynamic pre-match lifecycle

Revision ID: 0034_create_dynamic_prematch_lifecycle
Revises: 0033_create_canonical_team_identity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0034_create_dynamic_prematch_lifecycle"
down_revision: str | None = "0033_create_canonical_team_identity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "player_identity_mappings",
        sa.Column("canonical_player_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "player_valuation_observations",
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
    )
    op.add_column(
        "player_valuation_observations",
        sa.Column(
            "mapping_review_status",
            sa.String(32),
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "structured_lineup_snapshots",
        sa.Column("lineup_identity_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "structured_lineup_snapshots",
        sa.Column("team_w2_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "structured_lineup_snapshots",
        sa.Column("source_capture_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "structured_lineup_players",
        sa.Column("canonical_player_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "structured_lineup_players",
        sa.Column("valuation_source_player_id", sa.String(64), nullable=True),
    )

    op.create_table(
        "dynamic_prematch_evaluations",
        sa.Column("evaluation_id", sa.String(80), primary_key=True),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("market", sa.String(64), nullable=False),
        sa.Column("selection", sa.String(64), nullable=False),
        sa.Column("checkpoint", sa.String(64), nullable=False),
        sa.Column("capture_id", sa.String(128), nullable=True),
        sa.Column("quote_identity_hash", sa.String(64), nullable=True),
        sa.Column("model_input_hash", sa.String(64), nullable=True),
        sa.Column("lineup_input_hash", sa.String(64), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capture_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_state", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "identity_hash", name="uq_dynamic_prematch_evaluation_identity"
        ),
    )
    op.create_index(
        "ix_dynamic_prematch_evaluation_current",
        "dynamic_prematch_evaluations",
        ["fixture_id", "market", "evaluated_at"],
    )
    op.create_table(
        "dynamic_prematch_supersessions",
        sa.Column(
            "superseded_evaluation_id",
            sa.String(80),
            sa.ForeignKey("dynamic_prematch_evaluations.evaluation_id"),
            primary_key=True,
        ),
        sa.Column(
            "superseded_by_evaluation_id",
            sa.String(80),
            sa.ForeignKey("dynamic_prematch_evaluations.evaluation_id"),
            nullable=False,
        ),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("market", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "superseded_evaluation_id",
            name="uq_dynamic_prematch_superseded_once",
        ),
    )
    op.create_index(
        "ix_dynamic_prematch_supersession_fixture",
        "dynamic_prematch_supersessions",
        ["fixture_id", "created_at"],
    )
    op.create_table(
        "lineup_confirmed_events",
        sa.Column("event_id", sa.String(80), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("lineup_input_hash", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checkpoint", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "lineup_input_hash",
            name="uq_lineup_confirmed_event_identity",
        ),
    )
    op.create_index(
        "ix_lineup_confirmed_event_fixture",
        "lineup_confirmed_events",
        ["fixture_id", "captured_at"],
    )
    op.create_table(
        "t30_validation_snapshots",
        sa.Column("validation_id", sa.String(80), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("capture_id", sa.String(128), nullable=False),
        sa.Column("capture_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checkpoint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("fixture_id", name="uq_t30_validation_snapshot_fixture"),
        sa.UniqueConstraint("capture_id", name="uq_t30_validation_snapshot_capture"),
    )


def downgrade() -> None:
    op.drop_table("t30_validation_snapshots")
    op.drop_index(
        "ix_lineup_confirmed_event_fixture", table_name="lineup_confirmed_events"
    )
    op.drop_table("lineup_confirmed_events")
    op.drop_index(
        "ix_dynamic_prematch_supersession_fixture",
        table_name="dynamic_prematch_supersessions",
    )
    op.drop_table("dynamic_prematch_supersessions")
    op.drop_index(
        "ix_dynamic_prematch_evaluation_current",
        table_name="dynamic_prematch_evaluations",
    )
    op.drop_table("dynamic_prematch_evaluations")
    op.drop_column("structured_lineup_players", "valuation_source_player_id")
    op.drop_column("structured_lineup_players", "canonical_player_id")
    op.drop_column("structured_lineup_snapshots", "source_capture_id")
    op.drop_column("structured_lineup_snapshots", "team_w2_id")
    op.drop_column("structured_lineup_snapshots", "lineup_identity_hash")
    op.drop_column("player_valuation_observations", "mapping_review_status")
    op.drop_column("player_valuation_observations", "confidence")
    op.drop_column("player_identity_mappings", "canonical_player_id")
