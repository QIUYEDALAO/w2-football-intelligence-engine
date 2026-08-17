"""persist complete ModelForecast market-evaluation denominator

Revision ID: 0062_dynamic_evaluation_denominator
Revises: 0061_model_forecast_data_version
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0062_dynamic_evaluation_denominator"
down_revision: str | None = "0061_model_forecast_data_version"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "dynamic_prematch_evaluations",
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dynamic_prematch_evaluations",
        sa.Column("denominator_scope", sa.String(64), nullable=True),
    )
    op.add_column(
        "dynamic_prematch_evaluations",
        sa.Column("bookmaker_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "dynamic_prematch_evaluations",
        sa.Column("first_failed_gate", sa.String(64), nullable=True),
    )
    op.add_column(
        "dynamic_prematch_evaluations",
        sa.Column("all_failed_gates", sa.JSON(), nullable=True),
    )
    op.add_column(
        "dynamic_prematch_evaluations",
        sa.Column("gate_results", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_dynamic_prematch_evaluation_denominator",
        "dynamic_prematch_evaluations",
        ["denominator_scope", "fixture_id", "market", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dynamic_prematch_evaluation_denominator",
        table_name="dynamic_prematch_evaluations",
    )
    op.drop_column("dynamic_prematch_evaluations", "gate_results")
    op.drop_column("dynamic_prematch_evaluations", "all_failed_gates")
    op.drop_column("dynamic_prematch_evaluations", "first_failed_gate")
    op.drop_column("dynamic_prematch_evaluations", "bookmaker_count")
    op.drop_column("dynamic_prematch_evaluations", "denominator_scope")
    op.drop_column("dynamic_prematch_evaluations", "recorded_at")
