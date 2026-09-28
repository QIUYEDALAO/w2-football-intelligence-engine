"""AH/OU v3 AS-OF contract columns (S1): separate first-capture / status-visibility
timestamps and a point-in-time provenance flag.

Revision ID: 0080_ah_ou_asof_contract_columns
Revises: 0079_append_only_ledger_triggers
Create Date: 2026-09-29 00:00:00.000000

The softmax decision path must prove each F9 snapshot and each F6 meeting was
observable *before* decision time. ``as_of_time`` is the match-time the rolling
window is "as of" -- it is NOT when the snapshot row first became available, so
it cannot prove observability. ``captured_at`` on a canonical meeting is when the
raw capture arrived -- it is NOT when the row's ``fixture_status`` first became
FT. This migration adds the two missing observability timestamps plus a
``pit_proven`` flag so backfilled (BACKTEST_LOOKBACK) rows are never mistaken for
point-in-time evidence.

Columns are nullable and default ``pit_proven = false``: existing rows are
legacy backfill, so they are correctly classified as not PIT-proven.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0080_ah_ou_asof_contract_columns"
down_revision: str | None = "0079_append_only_ledger_triggers"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "team_xg_rolling_snapshot",
        sa.Column("first_captured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "team_xg_rolling_snapshot",
        sa.Column("pit_proven", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "canonical_team_match_history",
        sa.Column("status_first_visible_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "canonical_team_match_history",
        sa.Column("pit_proven", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("canonical_team_match_history", "pit_proven")
    op.drop_column("canonical_team_match_history", "status_first_visible_at")
    op.drop_column("team_xg_rolling_snapshot", "pit_proven")
    op.drop_column("team_xg_rolling_snapshot", "first_captured_at")
