"""add the independent EV-ONLINE-01 validation projection

Revision ID: 0075_validation_samples_calibrated
Revises: 0074_progress_query_indexes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0075_validation_samples_calibrated"
down_revision: str | None = "0074_progress_query_indexes"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    table = "validation_samples_calibrated"
    op.create_table(
        table,
        sa.Column("fixture_id", sa.String(128), primary_key=True),
        sa.Column("market", sa.String(64), primary_key=True),
        sa.Column("competition_id", sa.String(128)),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True)),
        sa.Column("selection", sa.String(64), nullable=False),
        sa.Column("exact_line", sa.String(32), nullable=False),
        sa.Column("decimal_odds", sa.Float(), nullable=False),
        sa.Column("bookmaker_id", sa.String(128)),
        sa.Column("first_checkpoint", sa.String(32)),
        sa.Column("final_checkpoint", sa.String(32)),
        sa.Column("evaluation_id", sa.String(80), nullable=False),
        sa.Column("calibration_identity", sa.String(64)),
        sa.Column("settlement", sa.String(32), nullable=False),
        sa.Column("profit_units", sa.Float()),
        sa.Column("score", sa.String(16)),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("quote_captured_at", sa.DateTime(timezone=True)),
        sa.Column("current_ev", sa.Float()),
        sa.Column("home_team_label", sa.JSON()),
        sa.Column("away_team_label", sa.JSON()),
        sa.Column("later_unassessed_checkpoints", sa.JSON()),
        sa.Column("lifecycle_note_zh", sa.String(256)),
        sa.Column("settlement_observed_at", sa.DateTime(timezone=True)),
        sa.Column("bias_at_decision", sa.Float()),
        sa.Column("ev_raw", sa.Float()),
        sa.Column("ev_corrected", sa.Float()),
        sa.Column("filter_decision", sa.String(16), nullable=False),
        sa.Column("param_version", sa.String(64), nullable=False),
        sa.Column("warmup", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("market in ('ASIAN_HANDICAP', 'TOTALS')", name="ck_validation_samples_calibrated_market"),
        sa.CheckConstraint("filter_decision in ('KEPT', 'FILTERED')", name="ck_validation_samples_calibrated_filter_decision"),
    )
    op.create_index("ix_validation_samples_calibrated_kickoff", table, ["kickoff_utc"])
    op.create_index("ix_validation_samples_calibrated_competition", table, ["competition_id"])
    op.create_index("ix_validation_samples_calibrated_decision", table, ["filter_decision"])


def downgrade() -> None:
    table = "validation_samples_calibrated"
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(table):
        return
    op.drop_index("ix_validation_samples_calibrated_decision", table_name=table)
    op.drop_index("ix_validation_samples_calibrated_competition", table_name=table)
    op.drop_index("ix_validation_samples_calibrated_kickoff", table_name=table)
    op.drop_table(table)
