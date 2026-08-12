"""apply the seven-day market collection policy

Revision ID: 0051_apply_seven_day_collection_policy
Revises: 0050_gate_a_runtime_selection
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from alembic import op

from w2.competitions.seed import apply_collection_policy_update

revision: str = "0051_apply_seven_day_collection_policy"
down_revision: str | None = "0050_gate_a_runtime_selection"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    updated = apply_collection_policy_update(
        op.get_bind(),
        config_root=Path("config"),
        updated_by="alembic-0051-owner-authorized-seven-day-collection",
        now=datetime.now(UTC),
    )
    if len(updated) != 14:
        raise RuntimeError(f"COLLECTION_POLICY_UPDATE_COUNT_INVALID:{len(updated)}")


def downgrade() -> None:
    # Runtime collection evidence may already exist; never revive the retired World Cup job.
    pass
