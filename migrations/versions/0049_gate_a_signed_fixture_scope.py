"""bind the one-shot Gate A reservation to the signed fixture

Revision ID: 0049_gate_a_signed_fixture_scope
Revises: 0048_gate_a_evidence_authority
"""

import sqlalchemy as sa
from alembic import op

revision = "0049_gate_a_signed_fixture_scope"
down_revision = "0048_gate_a_evidence_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gate_a_run_reservations",
        sa.Column("fixture_id", sa.String(length=128)),
    )
    op.execute(
        sa.text(
            "UPDATE gate_a_run_reservations "
            "SET fixture_id = 'LEGACY_UNSCOPED_REJECTED' WHERE fixture_id IS NULL"
        )
    )
    with op.batch_alter_table("gate_a_run_reservations") as batch:
        batch.alter_column("fixture_id", existing_type=sa.String(length=128), nullable=False)


def downgrade() -> None:
    op.drop_column("gate_a_run_reservations", "fixture_id")
