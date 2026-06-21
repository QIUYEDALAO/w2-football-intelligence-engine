"""create stage 3 domain model

Revision ID: 0002_create_stage3_domain_model
Revises: 0001_create_system_metadata
Create Date: 2026-06-22 01:00:00.000000
"""
from __future__ import annotations

from alembic import op

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0002_create_stage3_domain_model"
down_revision: str | None = "0001_create_system_metadata"
branch_labels: str | None = None
depends_on: str | None = None

STAGE3_TABLES = {
    "audit_events",
    "bookmakers",
    "competitions",
    "data_provenance",
    "feature_snapshots",
    "fixtures",
    "injuries",
    "lineups",
    "markets",
    "model_runs",
    "odds_observations",
    "players",
    "predictions",
    "provider_entity_mappings",
    "raw_payload_references",
    "recommendation_locks",
    "recommendations",
    "referees",
    "results",
    "seasons",
    "settlements",
    "squads",
    "stages",
    "suspensions",
    "team_ratings",
    "teams",
    "venues",
    "weather_observations",
}


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in STAGE3_TABLES:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in STAGE3_TABLES:
            table.drop(bind=bind, checkfirst=True)

