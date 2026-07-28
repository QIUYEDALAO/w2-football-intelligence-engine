"""drop the retired shadow-strategy persistence

Revision ID: 0044_drop_retired_shadow_strategy
Revises: 0043_drop_legacy_identity_crosswalks
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0044_drop_retired_shadow_strategy"
down_revision: str | None = "0043_drop_legacy_identity_crosswalks"
branch_labels: str | None = None
depends_on: str | None = None

_TABLES = ("shadow_strategy_run", "shadow_strategy_lock", "shadow_strategy_evaluation")


def _dependencies(bind: sa.Connection, inspector: sa.Inspector) -> list[str]:
    dependencies: list[str] = []
    for table in inspector.get_table_names():
        for foreign_key in inspector.get_foreign_keys(table):
            if table in _TABLES or foreign_key.get("referred_table") in _TABLES:
                dependencies.append(
                    f"foreign_key:{table}:{foreign_key.get('name')}:"
                    f"{foreign_key.get('referred_table')}"
                )
    for view in inspector.get_view_names():
        definition = (inspector.get_view_definition(view) or "").lower()
        if any(table in definition for table in _TABLES):
            dependencies.append(f"view:{view}")
    if bind.dialect.name == "sqlite":
        objects = bind.execute(
            sa.text(
                "select type, name, sql from sqlite_master "
                "where type in ('trigger', 'view') and sql is not null"
            )
        ).mappings()
        for item in objects:
            if any(table in str(item["sql"]).lower() for table in _TABLES):
                dependencies.append(f"{item['type']}:{item['name']}")
    elif bind.dialect.name == "postgresql":
        for kind, query in (
            ("materialized_view", "select matviewname as name, definition from pg_matviews"),
            (
                "trigger",
                "select c.relname || '.' || t.tgname as name, "
                "pg_get_triggerdef(t.oid) as definition from pg_trigger t "
                "join pg_class c on c.oid=t.tgrelid where not t.tgisinternal",
            ),
        ):
            for item in bind.execute(sa.text(query)).mappings():
                if any(table in str(item["definition"]).lower() for table in _TABLES):
                    dependencies.append(f"{kind}:{item['name']}")
    return sorted(set(dependencies))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    missing = set(_TABLES) - tables
    if missing:
        raise RuntimeError(f"SHADOW_STRATEGY_DROP_REQUIRED_TABLES_MISSING:{sorted(missing)}")
    counts = {
        table: bind.execute(sa.text(f"select count(*) from {table}")).scalar_one()  # noqa: S608
        for table in _TABLES
    }
    if any(counts.values()):
        raise RuntimeError(f"SHADOW_STRATEGY_DROP_NONEMPTY:{counts}")
    dependencies = _dependencies(bind, inspector)
    if dependencies:
        raise RuntimeError(f"SHADOW_STRATEGY_DROP_DEPENDENCIES:{dependencies}")
    for table in reversed(_TABLES):
        op.drop_table(table)


def downgrade() -> None:
    op.create_table(
        "shadow_strategy_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("strategy_version", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("run_id", name="uq_shadow_strategy_run_id"),
    )
    op.create_index(
        "ix_shadow_strategy_run_started_at", "shadow_strategy_run", ["started_at"]
    )
    op.create_table(
        "shadow_strategy_lock",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fixture_id", sa.String(64), nullable=False),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("strategy_version", sa.String(64), nullable=False),
        sa.Column("decision_hash", sa.String(64), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "phase",
            "strategy_version",
            name="uq_shadow_strategy_lock_fixture_phase_version",
        ),
    )
    op.create_index(
        "ix_shadow_strategy_lock_locked_at", "shadow_strategy_lock", ["locked_at"]
    )
    op.create_table(
        "shadow_strategy_evaluation",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fixture_id", sa.String(64), nullable=False),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("strategy_version", sa.String(64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "phase",
            "strategy_version",
            name="uq_shadow_strategy_evaluation_fixture_phase_version",
        ),
    )
