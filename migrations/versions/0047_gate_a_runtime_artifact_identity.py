"""bind Gate A admission to a complete runtime artifact identity

Revision ID: 0047_gate_a_runtime_artifact_identity
Revises: 0046_gate_a_run_reservation
"""

import sqlalchemy as sa
from alembic import op

revision = "0047_gate_a_runtime_artifact_identity"
down_revision = "0046_gate_a_run_reservation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gate_a_run_reservations",
        sa.Column("execution_mode", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "gate_a_run_reservations",
        sa.Column("runtime_artifact_digest", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "gate_a_run_reservations",
        sa.Column("complete_checkout_manifest_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "gate_a_run_reservations",
        sa.Column("evidence_baseline", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gate_a_run_reservations", "evidence_baseline")
    op.drop_column("gate_a_run_reservations", "complete_checkout_manifest_sha256")
    op.drop_column("gate_a_run_reservations", "runtime_artifact_digest")
    op.drop_column("gate_a_run_reservations", "execution_mode")
