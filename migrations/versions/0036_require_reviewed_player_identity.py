"""require reviewed player identities for lineup value evidence

Revision ID: 0036_require_reviewed_player_identity
Revises: 0035_reconcile_lineup_identity_hash_nullability
"""

from __future__ import annotations

from alembic import op

revision: str = "0036_require_reviewed_player_identity"
down_revision: str | None = "0035_reconcile_lineup_identity_hash_nullability"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Retain only explicitly reviewed legacy matches as model-facing rows."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            UPDATE player_identity_mappings
            SET mapping_status = 'REVIEWED'
            WHERE mapping_status = 'MATCHED'
              AND reviewed_at IS NOT NULL
              AND COALESCE(evidence->>'review_status', '') = 'APPROVED'
            """
        )
    else:
        op.execute(
            "UPDATE player_identity_mappings SET mapping_status = 'REVIEWED' "
            "WHERE mapping_status = 'MATCHED' AND reviewed_at IS NOT NULL"
        )
    op.execute(
        "UPDATE player_identity_mappings SET mapping_status = 'CANDIDATE' "
        "WHERE mapping_status IN ('MATCHED', 'REVIEW_REQUIRED')"
    )
    op.execute(
        "UPDATE structured_lineup_players SET mapping_status = 'CANDIDATE' "
        "WHERE mapping_status IN ('MATCHED', 'REVIEW_REQUIRED')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE player_identity_mappings SET mapping_status = 'MATCHED' "
        "WHERE mapping_status = 'REVIEWED'"
    )
    op.execute(
        "UPDATE player_identity_mappings SET mapping_status = 'REVIEW_REQUIRED' "
        "WHERE mapping_status = 'CANDIDATE'"
    )
    op.execute(
        "UPDATE structured_lineup_players SET mapping_status = 'MATCHED' "
        "WHERE mapping_status = 'REVIEWED'"
    )
    op.execute(
        "UPDATE structured_lineup_players SET mapping_status = 'REVIEW_REQUIRED' "
        "WHERE mapping_status = 'CANDIDATE'"
    )
