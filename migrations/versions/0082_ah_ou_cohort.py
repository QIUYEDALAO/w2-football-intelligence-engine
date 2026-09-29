"""AH/OU v3 forward cohort preregistration (S4/R3 persisted).

Revision ID: 0082_ah_ou_cohort
Revises: 0081_ah_ou_decision_ledger
Create Date: 2026-09-29 00:30:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0082_ah_ou_cohort"
down_revision: str | None = "0081_ah_ou_decision_ledger"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "ah_ou_forward_cohort",
        sa.Column("cohort_id", sa.String(64), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_id", sa.String(128), nullable=False),
        sa.Column("away_team_id", sa.String(128), nullable=False),
        sa.Column("ah_capture_id", sa.String(64), nullable=True),
        sa.Column("ah_source_capture_sha256", sa.String(64), nullable=True),
        sa.Column("ou_capture_id", sa.String(64), nullable=True),
        sa.Column("ou_source_capture_sha256", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("calibration_version", sa.String(128), nullable=False),
        sa.Column("frozen_identity", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "fixture_id", "decision_at", name="uq_ah_ou_forward_cohort_slot"
        ),
    )
    op.create_index(
        "ix_ah_ou_forward_cohort_fixture", "ah_ou_forward_cohort", ["fixture_id", "decision_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ah_ou_forward_cohort_fixture", table_name="ah_ou_forward_cohort")
    op.drop_table("ah_ou_forward_cohort")
