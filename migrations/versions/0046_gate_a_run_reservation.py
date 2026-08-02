"""create one-shot Gate A reservation and fencing authority

Revision ID: 0046_gate_a_run_reservation
Revises: 0045_eval_01a_results_outcome_ledger
"""

import sqlalchemy as sa
from alembic import op

revision = "0046_gate_a_run_reservation"
down_revision = "0045_eval_01a_results_outcome_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gate_a_run_reservations",
        sa.Column("lease_epoch", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("authorization_id", sa.String(length=128), nullable=False),
        sa.Column("task_key", sa.String(length=255), nullable=False),
        sa.Column("competition_id", sa.String(length=128), nullable=False),
        sa.Column("season", sa.String(length=32), nullable=False),
        sa.Column("exact_head", sa.String(length=64), nullable=False),
        sa.Column("exact_tree", sa.String(length=64), nullable=False),
        sa.Column("owner", sa.String(length=64), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_call_cap", sa.Integer(), nullable=False),
        sa.Column("provider_calls_used", sa.Integer(), nullable=False),
        sa.Column("last_endpoint", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("lease_epoch"),
        sa.UniqueConstraint("authorization_id", name="uq_gate_a_authorization_once"),
    )
    op.create_index(
        "uq_gate_a_active_task_key",
        "gate_a_run_reservations",
        ["task_key"],
        unique=True,
        postgresql_where=sa.text("status = 'RESERVED'"),
        sqlite_where=sa.text("status = 'RESERVED'"),
    )
    op.create_table(
        "gate_a_provider_calls",
        sa.Column("lease_epoch", sa.BigInteger(), nullable=False),
        sa.Column("call_ordinal", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["lease_epoch"],
            ["gate_a_run_reservations.lease_epoch"],
        ),
        sa.PrimaryKeyConstraint("lease_epoch", "call_ordinal"),
    )


def downgrade() -> None:
    op.drop_table("gate_a_provider_calls")
    op.drop_index("uq_gate_a_active_task_key", table_name="gate_a_run_reservations")
    op.drop_table("gate_a_run_reservations")
