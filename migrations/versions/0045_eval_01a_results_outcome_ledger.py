"""databaseize results and the outcome event ledger

Revision ID: 0045_eval_01a_results_outcome_ledger
Revises: 0044_drop_retired_shadow_strategy
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0045_eval_01a_results_outcome_ledger"
down_revision: str | None = "0044_drop_retired_shadow_strategy"
branch_labels: str | None = None
depends_on: str | None = None

_NAMING = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}
_RESULT_COLUMNS = {
    "result_status",
    "source_payload_sha256",
    "source_capture_id",
    "result_hash",
}


def _count(bind: sa.Connection, table: str) -> int:
    return int(bind.execute(sa.text(f"select count(*) from {table}")).scalar_one())  # noqa: S608


def _result_fk(inspector: sa.Inspector) -> dict[str, object] | None:
    matches = [
        item
        for item in inspector.get_foreign_keys("results")
        if item.get("referred_table") == "fixtures"
        and item.get("constrained_columns") == ["fixture_id"]
    ]
    if len(matches) > 1:
        raise RuntimeError(f"RESULTS_FIXTURE_IDENTITY_FK_AMBIGUOUS:{matches}")
    return matches[0] if matches else None


def _upgrade_results(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("results")}
    fixture_fk = _result_fk(inspector)
    if _RESULT_COLUMNS <= columns and fixture_fk is None:
        return
    if _count(bind, "results") or _count(bind, "settlements"):
        raise RuntimeError("RESULTS_LEGACY_ROWS_REQUIRE_EXPLICIT_MIGRATION")

    with op.batch_alter_table(
        "results",
        recreate="always" if bind.dialect.name == "sqlite" else "auto",
        naming_convention=_NAMING,
    ) as batch:
        if fixture_fk is not None:
            name = fixture_fk.get("name") or "fk_results_fixture_id_fixtures"
            batch.drop_constraint(str(name), type_="foreignkey")
        batch.alter_column(
            "fixture_id",
            existing_type=sa.String(36),
            type_=sa.String(128),
            existing_nullable=False,
        )
        if "result_status" not in columns:
            batch.add_column(sa.Column("result_status", sa.String(8), nullable=False))
        if "source_payload_sha256" not in columns:
            batch.add_column(sa.Column("source_payload_sha256", sa.String(64), nullable=False))
        if "source_capture_id" not in columns:
            batch.add_column(sa.Column("source_capture_id", sa.String(64)))
        if "result_hash" not in columns:
            batch.add_column(sa.Column("result_hash", sa.String(64), nullable=False))
            batch.create_unique_constraint("uq_result_hash", ["result_hash"])
            batch.create_index("ix_results_confirmed_at", ["confirmed_at"])


def upgrade() -> None:
    bind = op.get_bind()
    _upgrade_results(bind)
    inspector = sa.inspect(bind)
    if "outcome_ledger" in inspector.get_table_names():
        raise RuntimeError("OUTCOME_LEDGER_ALREADY_EXISTS")
    op.create_table(
        "outcome_ledger",
        sa.Column("business_key", sa.String(64), primary_key=True),
        sa.Column("record_type", sa.String(32), nullable=False),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True)),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("recommendation_scope", sa.String(32)),
        sa.Column("capture_identity_hash", sa.String(64)),
        sa.Column("decision_hash", sa.String(64)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("source_artifact", sa.String(512), nullable=False),
        sa.Column("source_line_number", sa.Integer()),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_outcome_ledger_fixture_type_time",
        "outcome_ledger",
        ["fixture_id", "record_type", "occurred_at"],
    )
    op.create_index(
        "ix_outcome_ledger_capture_identity",
        "outcome_ledger",
        ["capture_identity_hash"],
    )
    op.create_index(
        "ix_outcome_ledger_decision_hash",
        "outcome_ledger",
        ["decision_hash"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _count(bind, "outcome_ledger"):
        raise RuntimeError("OUTCOME_LEDGER_DOWNGRADE_NONEMPTY")
    if _count(bind, "results") or _count(bind, "settlements"):
        raise RuntimeError("RESULTS_DOWNGRADE_NONEMPTY")
    op.drop_index("ix_outcome_ledger_decision_hash", table_name="outcome_ledger")
    op.drop_index("ix_outcome_ledger_capture_identity", table_name="outcome_ledger")
    op.drop_index("ix_outcome_ledger_fixture_type_time", table_name="outcome_ledger")
    op.drop_table("outcome_ledger")
    with op.batch_alter_table(
        "results",
        recreate="always" if bind.dialect.name == "sqlite" else "auto",
        naming_convention=_NAMING,
    ) as batch:
        batch.drop_index("ix_results_confirmed_at")
        batch.drop_constraint("uq_result_hash", type_="unique")
        batch.drop_column("result_hash")
        batch.drop_column("source_capture_id")
        batch.drop_column("source_payload_sha256")
        batch.drop_column("result_status")
        batch.alter_column(
            "fixture_id",
            existing_type=sa.String(128),
            type_=sa.String(36),
            existing_nullable=False,
        )
        batch.create_foreign_key(
            "fk_results_fixture_id_fixtures",
            "fixtures",
            ["fixture_id"],
            ["id"],
        )
