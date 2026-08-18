"""bind evaluation opportunities to the model forecast capture they belong to

Revision ID: 0065_opportunity_capture_identity
Revises: 0064_isolate_posthoc_denominator_snapshot

``capture_id`` on this table holds the odds snapshot's capture -- quote capture
id, falling back to the raw payload hash. It is not the frozen model track.

Keying opportunities on it merges every model track that happened to read the
same quote into one opportunity, and splits a single opportunity in two when a
retry reads a different snapshot. The frozen track is identified by
model_forecast_capture.capture_identity_hash, which already separates
family x version x policy x horizon, so opportunities must carry that instead.

Nullable and unbackfilled on purpose: no official opportunity row exists yet, so
there is nothing to migrate, and a NULL here must read as an invalid official
row rather than a silently accepted one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0065_opportunity_capture_identity"
down_revision: str | None = "0064_isolate_posthoc_denominator_snapshot"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "dynamic_prematch_evaluations"
COLUMN = "model_forecast_capture_identity_hash"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column(COLUMN, sa.String(64), nullable=True))
    op.create_index("ix_dynamic_prematch_evaluation_forecast_capture", TABLE, [COLUMN])


def downgrade() -> None:
    op.drop_index("ix_dynamic_prematch_evaluation_forecast_capture", table_name=TABLE)
    op.drop_column(TABLE, COLUMN)
