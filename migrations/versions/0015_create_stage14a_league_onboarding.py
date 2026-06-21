"""create stage 14a league onboarding tables

Revision ID: 0015_create_stage14a_league_onboarding
Revises: 0014_create_stage13a_tournament_ops
Create Date: 2026-06-22 16:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0015_create_stage14a_league_onboarding"
down_revision: str | None = "0014_create_stage13a_tournament_ops"
branch_labels: str | None = None
depends_on: str | None = None

STAGE14A_TABLES = {
    "league_profile",
    "league_season",
    "league_team_membership",
    "promotion_relegation_mapping",
    "league_readiness_audit",
    "season_rollover_plan",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE14A_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE14A_TABLES:
            table.drop(bind=bind, checkfirst=True)
