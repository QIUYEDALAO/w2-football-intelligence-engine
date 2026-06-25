"""create stage 9a shadow strategy tables

Revision ID: 0017_create_stage9a_shadow_strategy
Revises: 0016_create_stage15a_operational_governance
Create Date: 2026-06-23 01:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0017_create_stage9a_shadow_strategy"
down_revision: str | None = "0016_create_stage15a_operational_governance"
branch_labels: str | None = None
depends_on: str | None = None

STAGE9A_TABLES = {
    "shadow_strategy_run",
    "shadow_strategy_candidate",
    "shadow_strategy_lock",
    "shadow_strategy_event",
    "shadow_strategy_settlement",
    "shadow_strategy_evaluation",
}


def upgrade() -> None:
    op.create_table(
        "shadow_strategy_run",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("run_id", name="uq_shadow_strategy_run_id"),
    )
    op.create_index(
        "ix_shadow_strategy_run_started_at",
        "shadow_strategy_run",
        ["started_at"],
    )
    op.create_table(
        "shadow_strategy_candidate",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("shadow_action", sa.String(length=32), nullable=False),
        sa.Column("public_decision", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "phase",
            "strategy_version",
            "rank",
            name="uq_shadow_strategy_candidate_rank",
        ),
    )
    op.create_index(
        "ix_shadow_strategy_candidate_fixture",
        "shadow_strategy_candidate",
        ["fixture_id"],
    )
    op.create_table(
        "shadow_strategy_lock",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("decision_hash", sa.String(length=64), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "phase",
            "strategy_version",
            name="uq_shadow_strategy_lock_fixture_phase_version",
        ),
    )
    op.create_index("ix_shadow_strategy_lock_locked_at", "shadow_strategy_lock", ["locked_at"])
    op.create_table(
        "shadow_strategy_event",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_shadow_strategy_event_id"),
    )
    op.create_index("ix_shadow_strategy_event_fixture", "shadow_strategy_event", ["fixture_id"])
    op.create_index("ix_shadow_strategy_event_time", "shadow_strategy_event", ["event_time"])
    op.create_table(
        "shadow_strategy_settlement",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "phase",
            "strategy_version",
            name="uq_shadow_strategy_settlement_fixture_phase_version",
        ),
    )
    op.create_table(
        "shadow_strategy_evaluation",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "phase",
            "strategy_version",
            name="uq_shadow_strategy_evaluation_fixture_phase_version",
        ),
    )


def downgrade() -> None:
    for table in reversed(sorted(STAGE9A_TABLES)):
        op.drop_table(table)
