"""Freeze v3 entry terms and append-only postmatch lineage.

Revision ID: 0086_ahou_v3_postmatch
Revises: 0085_ahou_visibility_owned
"""

import sqlalchemy as sa
from alembic import op

revision = "0086_ahou_v3_postmatch"
down_revision = "0085_ahou_visibility_owned"
branch_labels = depends_on = None


def upgrade():
    op.add_column("ah_ou_decision_ledger", sa.Column("decision_contract", sa.String(64)))
    op.add_column("ah_ou_decision_ledger", sa.Column("frozen_terms", sa.JSON()))
    op.add_column("ah_ou_decision_ledger", sa.Column("terms_hash", sa.String(64)))
    op.create_table(
        "ah_ou_v3_settlement",
        sa.Column(
            "decision_id",
            sa.String(64),
            sa.ForeignKey("ah_ou_decision_ledger.decision_id"),
            primary_key=True,
        ),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("terms_hash", sa.String(64), nullable=False),
        sa.Column("result_id", sa.String(36), sa.ForeignKey("results.id"), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("result_raw_sha256", sa.String(64), nullable=False),
        sa.Column("result_capture_id", sa.String(64), nullable=False),
        sa.Column("home_goals", sa.Integer(), nullable=False),
        sa.Column("away_goals", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("net_units", sa.String(32), nullable=False),
        sa.Column("settlement_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ahou_v3_settlement_fixture", "ah_ou_v3_settlement", ["fixture_id", "market"]
    )
    op.create_table(
        "ah_ou_v3_validation_sample",
        sa.Column(
            "decision_id",
            sa.String(64),
            sa.ForeignKey("ah_ou_decision_ledger.decision_id"),
            primary_key=True,
        ),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("selection", sa.String(16), nullable=False),
        sa.Column("exact_line", sa.String(32), nullable=False),
        sa.Column("decimal_odds", sa.String(32), nullable=False),
        sa.Column("terms_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("settlement_hash", sa.String(64), nullable=False),
        sa.Column("settlement", sa.String(16), nullable=False),
        sa.Column("net_units", sa.String(32), nullable=False),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ahou_v3_sample_fixture", "ah_ou_v3_validation_sample", ["fixture_id", "market"]
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
        CREATE FUNCTION w2_ahou_postmatch_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'AH_OU_POSTMATCH_FROZEN_CONTENT_CONFLICT'; END $$;
        CREATE TRIGGER w2_ahou_terms_immutable BEFORE UPDATE OR DELETE ON ah_ou_decision_ledger
          FOR EACH ROW EXECUTE FUNCTION w2_ahou_postmatch_immutable();
        CREATE TRIGGER w2_ahou_terms_no_truncate BEFORE TRUNCATE ON ah_ou_decision_ledger
          FOR EACH STATEMENT EXECUTE FUNCTION w2_ahou_postmatch_immutable();
        CREATE TRIGGER w2_ahou_settlement_immutable BEFORE UPDATE OR DELETE ON ah_ou_v3_settlement
          FOR EACH ROW EXECUTE FUNCTION w2_ahou_postmatch_immutable();
        CREATE TRIGGER w2_ahou_settlement_no_truncate BEFORE TRUNCATE ON ah_ou_v3_settlement
          FOR EACH STATEMENT EXECUTE FUNCTION w2_ahou_postmatch_immutable();
        CREATE TRIGGER w2_ahou_sample_immutable BEFORE UPDATE OR DELETE
          ON ah_ou_v3_validation_sample
          FOR EACH ROW EXECUTE FUNCTION w2_ahou_postmatch_immutable();
        CREATE TRIGGER w2_ahou_sample_no_truncate BEFORE TRUNCATE ON ah_ou_v3_validation_sample
          FOR EACH STATEMENT EXECUTE FUNCTION w2_ahou_postmatch_immutable();
        """)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table, trigger in (
            ("ah_ou_decision_ledger", "w2_ahou_terms_immutable"),
            ("ah_ou_decision_ledger", "w2_ahou_terms_no_truncate"),
            ("ah_ou_v3_settlement", "w2_ahou_settlement_immutable"),
            ("ah_ou_v3_settlement", "w2_ahou_settlement_no_truncate"),
            ("ah_ou_v3_validation_sample", "w2_ahou_sample_immutable"),
            ("ah_ou_v3_validation_sample", "w2_ahou_sample_no_truncate"),
        ):
            op.execute(f"DROP TRIGGER {trigger} ON {table}")
        op.execute("DROP FUNCTION w2_ahou_postmatch_immutable()")
    op.drop_index("ix_ahou_v3_sample_fixture", table_name="ah_ou_v3_validation_sample")
    op.drop_table("ah_ou_v3_validation_sample")
    op.drop_index("ix_ahou_v3_settlement_fixture", table_name="ah_ou_v3_settlement")
    op.drop_table("ah_ou_v3_settlement")
    for field in ("terms_hash", "frozen_terms", "decision_contract"):
        op.drop_column("ah_ou_decision_ledger", field)
