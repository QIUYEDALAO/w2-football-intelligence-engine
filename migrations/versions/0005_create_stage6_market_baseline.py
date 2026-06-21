"""create stage 6 market baseline

Revision ID: 0005_create_stage6_market_baseline
Revises: 0004_create_stage5_asof_foundation
Create Date: 2026-06-22 06:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0005_create_stage6_market_baseline"
down_revision: str | None = "0004_create_stage5_asof_foundation"
branch_labels: str | None = None
depends_on: str | None = None

STAGE6_TABLES = {
    "market_consensus",
    "market_baseline_run",
    "market_fit_diagnostic",
    "market_quality_assessment",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE6_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE6_TABLES:
            table.drop(bind=bind, checkfirst=True)
