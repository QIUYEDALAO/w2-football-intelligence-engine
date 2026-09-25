"""Add immutable forward clock registration and review evidence.

Revision ID: 0076_forward_review_evidence
Revises: 0075_validation_samples_calibrated
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0076_forward_review_evidence"
down_revision: str | None = "0075_validation_samples_calibrated"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "forward_clock_registry",
        sa.Column("clock_id", sa.String(80), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code_revision", sa.String(40), nullable=False),
        sa.Column("model_identity", sa.String(80), nullable=False),
        sa.Column("preregistration_sha256", sa.String(64), nullable=False),
        sa.Column("input_version", sa.String(80), nullable=False),
    )
    op.create_table(
        "recommendation_review_ledger",
        sa.Column("review_event_id", sa.String(64), primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.String(80),
            sa.ForeignKey("dynamic_prematch_evaluations.evaluation_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pit_status", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("evaluation_id", "event_type", name="uq_review_evaluation_event"),
    )
    op.create_index("ix_review_evaluated_at", "recommendation_review_ledger", ["evaluated_at"])
    op.create_index("ix_review_pit_status", "recommendation_review_ledger", ["pit_status"])
    # Database guard: evidence and clock identities cannot be rewritten or removed.
    op.execute("""
        CREATE FUNCTION w2_forward_evidence_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'FORWARD_EVIDENCE_IMMUTABLE';
        END; $$ LANGUAGE plpgsql;
    """)
    for table in ("forward_clock_registry", "recommendation_review_ledger"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION w2_forward_evidence_immutable()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT count(*) FROM recommendation_review_ledger")).scalar_one()
    clock_count = bind.execute(sa.text("SELECT count(*) FROM forward_clock_registry")).scalar_one()
    if count or clock_count:
        raise RuntimeError("FORWARD_EVIDENCE_DOWNGRADE_REQUIRES_EMPTY_TABLES")
    for table in ("recommendation_review_ledger", "forward_clock_registry"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS w2_forward_evidence_immutable()")
    op.drop_index("ix_review_pit_status", table_name="recommendation_review_ledger")
    op.drop_index("ix_review_evaluated_at", table_name="recommendation_review_ledger")
    op.drop_table("recommendation_review_ledger")
    op.drop_table("forward_clock_registry")
