"""create validation_samples

Revision ID: 0073_validation_samples
Revises: 0072_runtime_ah_settlement_fact

Additive. A new table only: no existing table, column, index or constraint is
touched. `validation_samples` is the materialized post-match validation sample
set (the official-funnel recommendation rows), so the dashboard workspace and
the daily-settlement notification can read a pre-computed table instead of
re-projecting the full recommendation corpus on every request.

Populated by the forward_outcome_ledger writer (covering fixtures whose kickoff
falls in [now-3d, now+1d]) and by a one-off backfill. Rows outside the writer's
window are frozen and never touched by the rolling writer. The projection
function that produced these rows remains the single reconciliation authority
and is no longer on any request path.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0073_validation_samples"
down_revision: str | None = "0072_runtime_ah_settlement_fact"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "validation_samples"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("fixture_id", sa.String(128), primary_key=True),
        sa.Column("market", sa.String(64), primary_key=True),
        sa.Column("competition_id", sa.String(128), nullable=True),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("selection", sa.String(64), nullable=False),
        sa.Column("exact_line", sa.String(32), nullable=False),
        sa.Column("decimal_odds", sa.Float(), nullable=False),
        sa.Column("bookmaker_id", sa.String(128), nullable=True),
        sa.Column("first_checkpoint", sa.String(32), nullable=True),
        sa.Column("final_checkpoint", sa.String(32), nullable=True),
        sa.Column("evaluation_id", sa.String(80), nullable=False),
        sa.Column("calibration_identity", sa.String(64), nullable=True),
        sa.Column("settlement", sa.String(32), nullable=False),
        sa.Column("profit_units", sa.Float(), nullable=True),
        sa.Column("score", sa.String(16), nullable=True),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        # 展示字段（读取路径零 join 还原 projection 输出，避免请求期重算队名/生命周期）。
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quote_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_ev", sa.Float(), nullable=True),
        sa.Column("home_team_label", sa.JSON(), nullable=True),
        sa.Column("away_team_label", sa.JSON(), nullable=True),
        sa.Column("later_unassessed_checkpoints", sa.JSON(), nullable=True),
        sa.Column("lifecycle_note_zh", sa.String(256), nullable=True),
        sa.CheckConstraint(
            "market in ('ASIAN_HANDICAP', 'TOTALS')",
            name="ck_validation_samples_market",
        ),
    )
    op.create_index("ix_validation_samples_kickoff", _TABLE, ["kickoff_utc"])
    op.create_index("ix_validation_samples_competition", _TABLE, ["competition_id"])
    op.create_index(
        "ix_validation_samples_calibration", _TABLE, ["calibration_identity"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    op.drop_index("ix_validation_samples_calibration", table_name=_TABLE)
    op.drop_index("ix_validation_samples_competition", table_name=_TABLE)
    op.drop_index("ix_validation_samples_kickoff", table_name=_TABLE)
    op.drop_table(_TABLE)
