"""append-only DB triggers for the quant ledger (task 7 gap #2)

Revision ID: 0079_append_only_ledger_triggers
Revises: 0078_quant_asof_role_isolation
Create Date: 2026-09-28 21:10:00.000000

The contract enforces append-only in the ORM (``before_update``/``before_delete``
raise), but that is an application boundary: a hand-written UPDATE/DELETE or a
second writer bypasses it. This adds a PostgreSQL BEFORE UPDATE OR DELETE trigger
that refuses mutation at the database, so the ledger is immutable even against a
direct SQL write.

SQLite is untouched: the trigger is PL/pgSQL and SQLite has no equivalent, and
the offline tests already cover the ORM boundary there.
"""
from __future__ import annotations

from alembic import op

revision: str = "0079_append_only_ledger_triggers"
down_revision: str | None = "0078_quant_asof_role_isolation"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "forward_ah_factor_observations"
_FUNCTION = "forward_ah_factor_observation_block_mutation"
_TRIGGER = "trg_forward_ah_factor_observation_append_only"


def _postgres_only() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _postgres_only():
        return
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION}() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'append_only_ledger: % is immutable', TG_TABLE_NAME
            USING ERRCODE = '55000';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        DO $$ BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_trigger WHERE tgname = '{_TRIGGER}' AND tgrelid = '{_TABLE}'::regclass
        ) THEN
          CREATE TRIGGER {_TRIGGER}
          BEFORE UPDATE OR DELETE ON {_TABLE}
          FOR EACH ROW EXECUTE FUNCTION {_FUNCTION}();
        END IF;
        END $$
        """  # noqa: S608 - all trigger identifiers are migration constants.
    )


def downgrade() -> None:
    if not _postgres_only():
        return
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON {_TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")
