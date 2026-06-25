"""create stage 7i lifecycle supervision tables

Revision ID: 0019_create_stage7i_lifecycle_supervision
Revises: 0018_create_future_refresh_persistence
Create Date: 2026-06-25 10:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0019_create_stage7i_lifecycle_supervision"
down_revision: str | None = "0018_create_future_refresh_persistence"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "stage7i_lifecycle_run",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("scheduled_kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observer_pid", sa.Integer(), nullable=True),
        sa.Column("collector_pid", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("actual_kickoff_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_kickoff_source", sa.String(length=128), nullable=True),
        sa.Column("closing_observation_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_status", sa.String(length=32), nullable=True),
        sa.Column("settlement_status", sa.String(length=32), nullable=True),
        sa.Column("evaluation_status", sa.String(length=32), nullable=True),
        sa.Column("final_audit_status", sa.String(length=32), nullable=True),
        sa.Column("candidate", sa.Boolean(), nullable=False),
        sa.Column("formal_recommendation", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("run_id", name="uq_stage7i_lifecycle_run_id"),
    )
    op.create_index("ix_stage7i_lifecycle_run_fixture", "stage7i_lifecycle_run", ["fixture_id"])
    op.create_index("ix_stage7i_lifecycle_run_status", "stage7i_lifecycle_run", ["status"])
    op.create_table(
        "stage7i_lifecycle_heartbeat",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("component", sa.String(length=32), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("run_id", "component", name="uq_stage7i_lifecycle_heartbeat"),
    )
    op.create_index(
        "ix_stage7i_lifecycle_heartbeat_last_seen",
        "stage7i_lifecycle_heartbeat",
        ["last_seen_at"],
    )
    op.create_table(
        "stage7i_lifecycle_event",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_category", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("candidate", sa.Boolean(), nullable=False),
        sa.Column("formal_recommendation", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_stage7i_lifecycle_event_id"),
    )
    op.create_index("ix_stage7i_lifecycle_event_run", "stage7i_lifecycle_event", ["run_id"])
    op.create_index("ix_stage7i_lifecycle_event_time", "stage7i_lifecycle_event", ["event_time"])
    op.create_index("ix_stage7i_lifecycle_event_type", "stage7i_lifecycle_event", ["event_type"])


def downgrade() -> None:
    op.drop_table("stage7i_lifecycle_event")
    op.drop_table("stage7i_lifecycle_heartbeat")
    op.drop_table("stage7i_lifecycle_run")
