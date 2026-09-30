"""Preserve the observed unproven minimal source tables at stale revision 0076.

Only exact known shapes with no dependent foreign keys can be archived. Missing
capture/result proof is never invented. Healthy tables follow the normal path.
"""

import sqlalchemy as sa
from alembic import op


def _capture_columns():
    return (
        sa.Column("capture_id", sa.String(64), primary_key=True),
        sa.Column("fixture_id", sa.String(128)),
        sa.Column("competition_id", sa.String(128)),
        sa.Column("checkpoint", sa.String(64)),
        sa.Column("endpoint", sa.String(64), nullable=False),
        sa.Column("sanitized_params", sa.JSON(), nullable=False),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("request_task_key", sa.String(255), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("response_count", sa.Integer(), nullable=False),
        sa.Column("quota_values", sa.JSON(), nullable=False),
        sa.Column("raw_payload_sha256", sa.String(64), nullable=False),
        sa.Column("provider_event_time", sa.String(64)),
        sa.Column("capture_status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(128)),
    )


def _result_columns():
    return (
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("home_goals", sa.Integer(), nullable=False),
        sa.Column("away_goals", sa.Integer(), nullable=False),
        sa.Column("result_status", sa.String(8), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_payload_sha256", sa.String(64), nullable=False),
        sa.Column("source_capture_id", sa.String(64)),
        sa.Column("result_hash", sa.String(64), nullable=False),
    )


def recover_known_minimal_sources():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    specs = {
        "matchday_endpoint_captures": (
            _capture_columns(),
            {"capture_id": ("VARCHAR(64)", False), "raw_payload_sha256": ("VARCHAR(64)", False)},
            ["capture_id"],
        ),
        "results": (
            _result_columns(),
            {
                "fixture_id": ("VARCHAR(128)", False),
                "home_goals": ("INTEGER", True),
                "away_goals": ("INTEGER", True),
            },
            ["fixture_id"],
        ),
    }
    pending = []
    for table, (columns, minimal, pk) in specs.items():
        actual = {r["name"]: r for r in inspector.get_columns(table)}
        if set(actual) == {c.name for c in columns}:
            for c in columns:
                row = actual[c.name]
                if (
                    str(row["type"].compile(dialect=bind.dialect))
                    != str(c.type.compile(dialect=bind.dialect))
                    or row["nullable"] != c.nullable
                ):
                    raise RuntimeError(f"LEGACY_0076_SOURCE_COLUMN_CONFLICT:{table}:{c.name}")
            continue
        if bind.dialect.name != "postgresql" or set(actual) != set(minimal):
            raise RuntimeError(f"LEGACY_0076_SOURCE_SCHEMA_CONFLICT:{table}")
        for name, (kind, nullable) in minimal.items():
            if (
                str(actual[name]["type"].compile(dialect=bind.dialect)) != kind
                or actual[name]["nullable"] != nullable
                or actual[name]["default"] is not None
            ):
                raise RuntimeError(f"LEGACY_0076_SOURCE_COLUMN_CONFLICT:{table}:{name}")
        if (
            inspector.get_pk_constraint(table)["constrained_columns"] != pk
            or inspector.get_indexes(table)
            or inspector.get_unique_constraints(table)
            or inspector.get_check_constraints(table)
            or inspector.get_foreign_keys(table)
        ):
            raise RuntimeError(f"LEGACY_0076_SOURCE_CONSTRAINT_CONFLICT:{table}")
        dependents = bind.scalar(
            sa.text(
                "SELECT count(*) FROM pg_constraint WHERE contype='f' "
                "AND confrelid=CAST(:name AS regclass)"
            ),
            {"name": table},
        )
        triggers = bind.scalar(
            sa.text(
                "SELECT count(*) FROM pg_trigger WHERE tgrelid=CAST(:name AS regclass) "
                "AND NOT tgisinternal"
            ),
            {"name": table},
        )
        if dependents or triggers:
            raise RuntimeError(f"LEGACY_0076_SOURCE_DEPENDENCY_CONFLICT:{table}")
        archive = "w2_legacy_unproven_" + table + "_0076"
        if inspector.has_table(archive):
            raise RuntimeError(f"LEGACY_0076_SOURCE_ARCHIVE_EXISTS:{table}")
        pending.append((table, archive, columns, inspector.get_pk_constraint(table)["name"]))
    for table, archive, columns, pk_name in pending:
        op.rename_table(table, archive)
        op.execute(
            sa.text(f'ALTER TABLE "{archive}" RENAME CONSTRAINT "{pk_name}" TO "{archive}_pkey"')
        )
        op.execute(
            sa.text(f"""
            CREATE FUNCTION {archive}_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'LEGACY_UNPROVEN_SOURCE_IMMUTABLE'; END $$;
            CREATE TRIGGER {archive}_immutable BEFORE INSERT OR UPDATE OR DELETE ON {archive}
              FOR EACH ROW EXECUTE FUNCTION {archive}_immutable();
            CREATE TRIGGER {archive}_no_truncate BEFORE TRUNCATE ON {archive}
              FOR EACH STATEMENT EXECUTE FUNCTION {archive}_immutable();
        """)
        )
        if table == "results":
            op.create_table(
                table,
                *columns,
                sa.UniqueConstraint("fixture_id", name="uq_result_fixture"),
                sa.UniqueConstraint("result_hash", name="uq_result_hash"),
            )
            op.create_index("ix_results_confirmed_at", table, ["confirmed_at"])
        else:
            op.create_table(
                table,
                *columns,
                sa.UniqueConstraint(
                    "endpoint",
                    "params_hash",
                    "checkpoint",
                    "provider_captured_at",
                    "raw_payload_sha256",
                    name="uq_matchday_endpoint_capture_identity",
                ),
            )
            op.create_index(
                "ix_matchday_endpoint_capture_endpoint", table, ["endpoint", "provider_captured_at"]
            )
            op.create_index(
                "ix_matchday_endpoint_capture_raw_payload", table, ["raw_payload_sha256"]
            )
        print(f"LEGACY_0076_SOURCE_ARCHIVED:{table}:{archive}:NO_PROOF_UPGRADE")
