"""create stage 15a operational governance tables

Revision ID: 0016_create_stage15a_operational_governance
Revises: 0015_create_stage14a_league_onboarding
Create Date: 2026-06-22 17:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0016_create_stage15a_operational_governance"
down_revision: str | None = "0015_create_stage14a_league_onboarding"
branch_labels: str | None = None
depends_on: str | None = None

STAGE15A_TABLES = {
    "operations_cycle",
    "operations_check_result",
    "release_candidate",
    "release_audit",
    "retention_audit",
    "dependency_risk",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE15A_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE15A_TABLES:
            table.drop(bind=bind, checkfirst=True)
