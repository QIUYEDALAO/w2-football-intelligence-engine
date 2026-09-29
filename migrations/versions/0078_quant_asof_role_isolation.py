"""quant AS-OF / POST_EVENT role isolation (task 7 gap #1)

Revision ID: 0078_quant_asof_role_isolation
Revises: 0077_create_team_xg_rolling_snapshot_backtest
Create Date: 2026-09-28 21:00:00.000000

Creates the three NOLOGIN roles the quant append-only ledgers are written and
read under, and grants the AS-OF reader access only to the as-of ledger while
explicitly revoking the result/settlement tables. The AS-OF reader must never
see a score or a closing price, so the default PostgreSQL posture (no privileges
unless granted) plus an explicit REVOKE on ``results`` enforces that.

Rollback drops the roles only after revoking their grants; a role that has been
granted privileges it no longer needs is dropped, never left half-configured.
"""
from __future__ import annotations

from alembic import op

revision: str = "0078_quant_asof_role_isolation"
down_revision: str | None = "0077_create_team_xg_rolling_snapshot_backtest"
branch_labels: str | None = None
depends_on: str | None = None

_ASOF_ROLE = "quant_asof_reader_role"
_INGEST_ROLE = "quant_ingest_role"
_POSTEVENT_ROLE = "quant_postevent_role"
_LEDGER = "forward_ah_factor_observations"
_RESULT_TABLES = ("results",)
# AS-OF 读角色可读的 as-of 事实表：账本 + 软最大值 F9/F6 来源 + crosswalk。
_ASOF_READ_TABLES = (
    _LEDGER,
    "team_xg_rolling_snapshot",
    "canonical_team_match_history",
    "provider_team_identity_crosswalks",
)


def _postgres_only() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _postgres_only():
        return
    for role in (_ASOF_ROLE, _INGEST_ROLE, _POSTEVENT_ROLE):
        op.execute(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
            f"CREATE ROLE {role} NOLOGIN; "
            f"END IF; END $$;"
        )
    # AS-OF reader may read the as-of ledger + the F9/F6 source tables it reads.
    for table in _ASOF_READ_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {_ASOF_ROLE}")
    for table in _RESULT_TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM {_ASOF_ROLE}")
    # Ingest writes the as-of ledger; post-event role is reserved for settlement
    # enrichment and gets nothing yet (it must be granted per table later).
    op.execute(f"GRANT SELECT, INSERT ON {_LEDGER} TO {_INGEST_ROLE}")


def downgrade() -> None:
    if not _postgres_only():
        return
    for table in _ASOF_READ_TABLES:
        op.execute(f"REVOKE SELECT ON {table} FROM {_ASOF_ROLE}")
    op.execute(f"REVOKE SELECT, INSERT ON {_LEDGER} FROM {_INGEST_ROLE}")
    for role in (_ASOF_ROLE, _INGEST_ROLE, _POSTEVENT_ROLE):
        op.execute(
            f"DO $$ BEGIN "
            f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "
            f"AND NOT EXISTS (SELECT 1 FROM pg_shdepend d JOIN pg_roles r ON r.oid=d.refobjid "
            f"WHERE r.rolname='{role}' AND d.refclassid='pg_authid'::regclass) THEN "
            f"DROP ROLE {role}; "
            f"END IF; END $$;"
        )
