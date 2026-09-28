"""AH/OU v3 decision ledger (S3/S4): append-only identity-keyed decision storage.

Revision ID: 0081_ah_ou_decision_ledger
Revises: 0080_ah_ou_asof_contract_columns
Create Date: 2026-09-29 00:10:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0081_ah_ou_decision_ledger"
down_revision: str | None = "0080_ah_ou_asof_contract_columns"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "ah_ou_decision_ledger",
        sa.Column("decision_id", sa.String(64), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("calibration_version", sa.String(128), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("full_distribution", sa.JSON(), nullable=False),
        sa.Column("quote_identity_hash", sa.String(64), nullable=False),
        sa.Column("source_capture_sha256", sa.String(64), nullable=False),
        sa.Column("capture_id", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("home_team_id", sa.String(128), nullable=False),
        sa.Column("away_team_id", sa.String(128), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("direction", sa.String(16), nullable=True),
        sa.Column("score", sa.String(64), nullable=False),
        sa.Column("skip_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "fixture_id", "market", "decision_at", name="uq_ah_ou_decision_ledger_slot"
        ),
    )
    op.create_index(
        "ix_ah_ou_decision_ledger_fixture", "ah_ou_decision_ledger", ["fixture_id", "decision_at"]
    )
    op.create_index(
        "ix_ah_ou_decision_ledger_capture", "ah_ou_decision_ledger", ["capture_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ah_ou_decision_ledger_capture", table_name="ah_ou_decision_ledger")
    op.drop_index("ix_ah_ou_decision_ledger_fixture", table_name="ah_ou_decision_ledger")
    op.drop_table("ah_ou_decision_ledger")
