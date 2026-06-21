"""create stage 7 independent models

Revision ID: 0006_create_stage7_independent_models
Revises: 0005_create_stage6_market_baseline
Create Date: 2026-06-22 07:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0006_create_stage7_independent_models"
down_revision: str | None = "0005_create_stage6_market_baseline"
branch_labels: str | None = None
depends_on: str | None = None

STAGE7_TABLES = {
    "model_experiment",
    "model_artifact",
    "calibration_artifact",
    "model_evaluation",
    "model_gate_decision",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE7_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE7_TABLES:
            table.drop(bind=bind, checkfirst=True)
