"""seed the database competition runtime authority

Revision ID: 0037_seed_competition_runtime_authority
Revises: 0036_require_reviewed_player_identity
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import op

from w2.competitions.seed import seed_competition_runtime_authority

revision: str = "0037_seed_competition_runtime_authority"
down_revision: str | None = "0036_require_reviewed_player_identity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    report = seed_competition_runtime_authority(
        op.get_bind(),
        config_root=Path("config"),
        environment=os.environ.get("W2_ENVIRONMENT", "production"),
        updated_by="alembic-0037-first-install-seed",
    )
    if report.conflicts:
        raise RuntimeError(";".join(report.conflicts))


def downgrade() -> None:
    # Seeded rows may have received live operator changes; never erase runtime authority.
    pass
