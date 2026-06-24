"""create future refresh persistence tables

Revision ID: 0018_create_future_refresh_persistence
Revises: 0017_create_stage9a_shadow_strategy
Create Date: 2026-06-25 07:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0018_create_future_refresh_persistence"
down_revision: str | None = "0017_create_stage9a_shadow_strategy"
branch_labels: str | None = None
depends_on: str | None = None

FUTURE_REFRESH_TABLES = {
    "future_market_observation",
    "future_refresh_task_audit",
    "future_refresh_run_audit",
    "raw_payload",
}


def upgrade() -> None:
    op.create_table(
        "future_market_observation",
        sa.Column("observation_id", sa.String(length=64), primary_key=True),
        sa.Column("fixture_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("bookmaker_id", sa.String(length=64), nullable=False),
        sa.Column("bookmaker_name", sa.String(length=255), nullable=False),
        sa.Column("provider_bet_id", sa.String(length=64), nullable=False),
        sa.Column("raw_market_label", sa.String(length=255), nullable=False),
        sa.Column("canonical_market", sa.String(length=64), nullable=False),
        sa.Column("selection", sa.String(length=128), nullable=False),
        sa.Column("line", sa.String(length=64), nullable=True),
        sa.Column("decimal_odds", sa.String(length=32), nullable=False),
        sa.Column("suspended", sa.Boolean(), nullable=False),
        sa.Column("live", sa.Boolean(), nullable=False),
        sa.Column("provider_last_update", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_revision", sa.String(length=128), nullable=False),
        sa.Column("candidate", sa.Boolean(), nullable=False),
        sa.Column("formal_recommendation", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_future_market_observation_fixture",
        "future_market_observation",
        ["fixture_id"],
    )
    op.create_index(
        "ix_future_market_observation_captured_at",
        "future_market_observation",
        ["captured_at"],
    )
    op.create_table(
        "future_refresh_task_audit",
        sa.Column("task_id", sa.String(length=255), primary_key=True),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=64), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
    )
    op.create_index("ix_future_refresh_task_audit_key", "future_refresh_task_audit", ["key"])
    op.create_table(
        "future_refresh_run_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("competition_id", sa.String(length=128), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("remaining_quota", sa.Integer(), nullable=True),
        sa.Column("fixture_count", sa.Integer(), nullable=False),
        sa.Column("mapping_count", sa.Integer(), nullable=False),
        sa.Column("market_snapshot_count", sa.Integer(), nullable=False),
        sa.Column("ledger_appended_count", sa.Integer(), nullable=False),
        sa.Column("selected_market_fixture_ids", sa.JSON(), nullable=False),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("requests", sa.JSON(), nullable=False),
        sa.Column("candidate", sa.Boolean(), nullable=False),
        sa.Column("formal_recommendation", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_future_refresh_run_audit_generated_at",
        "future_refresh_run_audit",
        ["generated_at"],
    )
    op.create_index(
        "ix_future_refresh_run_audit_competition",
        "future_refresh_run_audit",
        ["competition_id"],
    )
    op.create_table(
        "raw_payload",
        sa.Column("sha256", sa.String(length=64), primary_key=True),
        sa.Column("endpoint", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("storage_uri", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_raw_payload_endpoint_captured", "raw_payload", ["endpoint", "captured_at"])


def downgrade() -> None:
    for table in reversed(sorted(FUTURE_REFRESH_TABLES)):
        op.drop_table(table)
