"""Immutable per-market, per-version descriptive monitoring reports.

Revision ID: 0089_ahou_v3_monitoring
Revises: 0088_ahou_v3_outbox
"""

import sqlalchemy as sa
from alembic import op

revision = "0089_ahou_v3_monitoring"
down_revision = "0088_ahou_v3_outbox"
branch_labels = depends_on = None


def _create_or_verify(name: str, *items: object) -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(name):
        op.create_table(name, *items)
        return
    columns = {row["name"]: row for row in inspector.get_columns(name)}
    expected = [item for item in items if isinstance(item, sa.Column)]
    if set(columns) != {column.name for column in expected}:
        raise RuntimeError("V3_MONITORING_SCHEMA_CONFLICT:" + name)
    for column in expected:
        actual = columns[column.name]
        dialect = op.get_bind().dialect
        if (
            actual["type"].compile(dialect=dialect) != column.type.compile(dialect=dialect)
            or actual["nullable"] != column.nullable
        ):
            raise RuntimeError("V3_MONITORING_SCHEMA_CONFLICT:" + name + ":" + column.name)
    primary = inspector.get_pk_constraint(name)["constrained_columns"]
    if primary != [column.name for column in expected if column.primary_key]:
        raise RuntimeError("V3_MONITORING_PRIMARY_KEY_CONFLICT:" + name)
    actual_unique = {tuple(row["column_names"]) for row in inspector.get_unique_constraints(name)}
    # Detached string-column constraints are resolved by a temporary Table.
    schema = sa.Table(name, sa.MetaData(), *items)
    required_unique = {
        tuple(constraint.columns.keys())
        for constraint in schema.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    if not required_unique <= actual_unique:
        raise RuntimeError("V3_MONITORING_UNIQUE_CONFLICT:" + name)
    actual_foreign = {
        (source, row["referred_table"], target)
        for row in inspector.get_foreign_keys(name)
        for source, target in zip(row["constrained_columns"], row["referred_columns"], strict=True)
    }
    required_foreign = {
        (column.name, *foreign.target_fullname.split("."))
        for column in expected
        for foreign in column.foreign_keys
    }
    if not required_foreign <= actual_foreign:
        raise RuntimeError("V3_MONITORING_FOREIGN_KEY_CONFLICT:" + name)


def upgrade() -> None:
    _create_or_verify(
        "ah_ou_v3_monitoring_fact",
        sa.Column(
            "decision_id",
            sa.String(64),
            sa.ForeignKey("ah_ou_decision_ledger.decision_id"),
            primary_key=True,
        ),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("calibration_version", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "market",
            "model_version",
            "calibration_version",
            name="uq_ahou_v3_monitoring_fixture_version",
        ),
    )
    _create_or_verify(
        "ah_ou_v3_monitoring_report",
        sa.Column("report_id", sa.String(64), primary_key=True),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("calibration_version", sa.String(64), nullable=False),
        sa.Column("eligible_settled_count", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "market",
            "model_version",
            "calibration_version",
            "eligible_settled_count",
            name="uq_ahou_v3_monitoring_report_milestone",
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
        CREATE OR REPLACE FUNCTION w2_ahou_v3_monitoring_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'V3_MONITORING_IMMUTABLE'; END $$;
        DROP TRIGGER IF EXISTS w2_ahou_v3_monitoring_fact_immutable ON ah_ou_v3_monitoring_fact;
        CREATE TRIGGER w2_ahou_v3_monitoring_fact_immutable BEFORE UPDATE OR DELETE
          ON ah_ou_v3_monitoring_fact FOR EACH ROW
          EXECUTE FUNCTION w2_ahou_v3_monitoring_immutable();
        DROP TRIGGER IF EXISTS w2_ahou_v3_monitoring_report_immutable ON ah_ou_v3_monitoring_report;
        CREATE TRIGGER w2_ahou_v3_monitoring_report_immutable BEFORE UPDATE OR DELETE
          ON ah_ou_v3_monitoring_report FOR EACH ROW
          EXECUTE FUNCTION w2_ahou_v3_monitoring_immutable();
        """)


def downgrade() -> None:
    # A code rollback keeps nonempty monitoring evidence. Never destroy it as
    # a side effect of a schema downgrade. Empty isolated schemas can migrate
    # back through the older ledger's DROP without leaving an orphan FK.
    inspector = sa.inspect(op.get_bind())
    tables = ("ah_ou_v3_monitoring_report", "ah_ou_v3_monitoring_fact")
    for name in tables:
        if inspector.has_table(name):
            count = op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(name)))
            if count:
                raise RuntimeError("V3_MONITORING_EVIDENCE_PREVENTS_SCHEMA_DOWNGRADE")
    for name in tables:
        if inspector.has_table(name):
            op.drop_table(name)
