"""bind Gate A audit and raw insertion evidence to DB authorities

Revision ID: 0048_gate_a_evidence_authority
Revises: 0047_gate_a_runtime_artifact_identity
"""

import sqlalchemy as sa
from alembic import op

revision = "0048_gate_a_evidence_authority"
down_revision = "0047_gate_a_runtime_artifact_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("future_refresh_task_audit") as batch:
        batch.add_column(sa.Column("gate_a_authorization_id", sa.String(length=128)))
        batch.add_column(sa.Column("gate_a_lease_epoch", sa.BigInteger()))
        batch.create_foreign_key(
            "fk_future_refresh_task_audit_gate_a_lease",
            "gate_a_run_reservations",
            ["gate_a_lease_epoch"],
            ["lease_epoch"],
        )
        batch.create_unique_constraint(
            "uq_future_refresh_task_audit_gate_a_lease",
            ["gate_a_lease_epoch"],
        )
    op.add_column("raw_payload", sa.Column("inserted_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("raw_payload", "inserted_at")
    with op.batch_alter_table("future_refresh_task_audit") as batch:
        batch.drop_constraint("uq_future_refresh_task_audit_gate_a_lease", type_="unique")
        batch.drop_constraint("fk_future_refresh_task_audit_gate_a_lease", type_="foreignkey")
        batch.drop_column("gate_a_lease_epoch")
        batch.drop_column("gate_a_authorization_id")
