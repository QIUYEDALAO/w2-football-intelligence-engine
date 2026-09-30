"""AH/OU v3 decision ledger (S3/S4): append-only identity-keyed decision storage.

Revision ID: 0081_ah_ou_decision_ledger
Revises: 0080_ah_ou_asof_contract_columns
Create Date: 2026-09-29 00:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0081_ah_ou_decision_ledger"
down_revision: str | None = "0080_ah_ou_asof_contract_columns"
branch_labels: str | None = None
depends_on: str | None = None


def _columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("decision_id", sa.String(64), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("calibration_version", sa.String(128), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("full_distribution", sa.JSON(), nullable=False),
        sa.Column("quote_identity_hash", sa.String(64), nullable=False),
        sa.Column("source_capture_sha256", sa.String(64), nullable=False),
        sa.Column("capture_id", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("home_team_id", sa.String(128), nullable=False),
        sa.Column("away_team_id", sa.String(128), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("direction", sa.String(16), nullable=True),
        sa.Column("score", sa.String(64), nullable=False),
        sa.Column("skip_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def _verify_existing_ledger(columns: tuple[sa.Column, ...]) -> None:
    """Adopt only the exact pre-0086 ORM shape observed at stale 0076.

    Never stamp a revision or overwrite rows. Unknown columns, defaults,
    constraints or triggers refuse the whole transactional upgrade.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    actual = {row["name"]: row for row in inspector.get_columns("ah_ou_decision_ledger")}
    if set(actual) != {column.name for column in columns}:
        raise RuntimeError("PREEXISTING_AH_OU_LEDGER_COLUMN_SET_CONFLICT")
    for column in columns:
        row = actual[column.name]
        if (
            str(row["type"].compile(dialect=bind.dialect))
            != str(column.type.compile(dialect=bind.dialect))
            or row["nullable"] != column.nullable
            or row["default"] is not None
        ):
            raise RuntimeError(f"PREEXISTING_AH_OU_LEDGER_COLUMN_CONFLICT:{column.name}")
    if inspector.get_pk_constraint("ah_ou_decision_ledger")["constrained_columns"] != [
        "decision_id"
    ]:
        raise RuntimeError("PREEXISTING_AH_OU_LEDGER_PRIMARY_KEY_CONFLICT")
    if inspector.get_foreign_keys("ah_ou_decision_ledger") or inspector.get_check_constraints(
        "ah_ou_decision_ledger"
    ):
        raise RuntimeError("PREEXISTING_AH_OU_LEDGER_CONSTRAINT_CONFLICT")
    if bind.dialect.name == "postgresql" and bind.scalar(
        sa.text(
            "SELECT count(*) FROM pg_trigger "
            "WHERE tgrelid='ah_ou_decision_ledger'::regclass AND NOT tgisinternal"
        )
    ):
        raise RuntimeError("PREEXISTING_AH_OU_LEDGER_TRIGGER_CONFLICT")
    unique = inspector.get_unique_constraints("ah_ou_decision_ledger")
    slot = ["fixture_id", "market", "decision_at"]
    name = "uq_ah_ou_decision_ledger_slot"
    if any(row["name"] != name or row["column_names"] != slot for row in unique):
        raise RuntimeError("PREEXISTING_AH_OU_LEDGER_UNIQUE_CONFLICT")
    indexes = {row["name"]: row for row in inspector.get_indexes("ah_ou_decision_ledger")}
    expected = {
        "ix_ah_ou_decision_ledger_fixture": (["fixture_id", "decision_at"], False),
        "ix_ah_ou_decision_ledger_capture": (["capture_id"], False),
        name: (slot, True),
    }
    for index_name, row in indexes.items():
        if (
            index_name not in expected
            or (row["column_names"], bool(row["unique"])) != expected[index_name]
            or row.get("dialect_options", {}).get("postgresql_where") is not None
            or any(row.get("column_sorting", {}).values())
        ):
            raise RuntimeError(f"PREEXISTING_AH_OU_LEDGER_INDEX_CONFLICT:{index_name}")
    if set(indexes) != set(expected):
        raise RuntimeError("PREEXISTING_AH_OU_LEDGER_INDEX_SET_CONFLICT")
    if not unique:
        if bind.dialect.name != "postgresql":
            raise RuntimeError("PREEXISTING_AH_OU_LEDGER_DIALECT_UNSUPPORTED")
        # The known ORM version made this a unique index. Promote that same
        # index to the migration's constraint without touching business rows.
        op.execute(
            sa.text(
                "ALTER TABLE ah_ou_decision_ledger "
                "ADD CONSTRAINT uq_ah_ou_decision_ledger_slot "
                "UNIQUE USING INDEX uq_ah_ou_decision_ledger_slot"
            )
        )


def upgrade() -> None:
    columns = _columns()
    if sa.inspect(op.get_bind()).has_table("ah_ou_decision_ledger"):
        _verify_existing_ledger(columns)
        return
    op.create_table(
        "ah_ou_decision_ledger",
        *columns,
        sa.UniqueConstraint(
            "fixture_id", "market", "decision_at", name="uq_ah_ou_decision_ledger_slot"
        ),
    )
    op.create_index(
        "ix_ah_ou_decision_ledger_fixture", "ah_ou_decision_ledger", ["fixture_id", "decision_at"]
    )
    op.create_index("ix_ah_ou_decision_ledger_capture", "ah_ou_decision_ledger", ["capture_id"])


def downgrade() -> None:
    op.drop_index("ix_ah_ou_decision_ledger_capture", table_name="ah_ou_decision_ledger")
    op.drop_index("ix_ah_ou_decision_ledger_fixture", table_name="ah_ou_decision_ledger")
    op.drop_table("ah_ou_decision_ledger")
