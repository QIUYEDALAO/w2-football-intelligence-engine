"""drop the three legacy identity crosswalk tables

Revision ID: 0043_drop_legacy_identity_crosswalks
Revises: 0042_team_identity_provider_review_provenance
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

from w2.matchday.intake_v2 import stable_hash

revision: str = "0043_drop_legacy_identity_crosswalks"
down_revision: str | None = "0042_team_identity_provider_review_provenance"
branch_labels: str | None = None
depends_on: str | None = None

_TARGETS = (
    "team_identity_crosswalks",
    "football_data_team_crosswalks",
    "player_identity_crosswalks",
)
_AUTHORITIES = (
    "canonical_teams",
    "provider_team_identity_crosswalks",
    "player_identity_mappings",
)
_PROVIDER_PRIMARY_READY = "PROVIDER_PRIMARY_READY"
_MIGRATION_OWNER = "0042_team_identity_provider_review_provenance"


def _coerce_dt(value: Any) -> Any:
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _coerce_json(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list)):
        return value
    return json.loads(str(value))


def _valid_at(valid_from: Any, valid_to: Any, as_of: Any) -> bool:
    return (valid_from is None or valid_from <= as_of) and (valid_to is None or valid_to > as_of)


def _owned_payload(source_payload: Any) -> dict[str, Any]:
    return {"migrated_by": _MIGRATION_OWNER, "source_payload": source_payload}


def _transfermarkt_identity_hash(
    *, provider_team_id: str, w2_team_id: str, competition_id: str, season: str
) -> str:
    return stable_hash(
        {
            "schema_version": "ProviderTeamIdentityCrosswalkV1",
            "provider": "transfermarkt",
            "provider_team_id": provider_team_id,
            "w2_team_id": w2_team_id,
            "competition_id": competition_id,
            "season": season,
            "identity_status": _PROVIDER_PRIMARY_READY,
            "scope_note": (
                "Transfermarkt provider identity migrated from team_identity_crosswalks."
            ),
        }
    )


def _database_dependencies(bind: sa.Connection, inspector: sa.Inspector) -> list[str]:
    tables = set(inspector.get_table_names())
    dependencies: list[str] = []
    for table in tables:
        for foreign_key in inspector.get_foreign_keys(table):
            referred = foreign_key.get("referred_table")
            if table in _TARGETS or referred in _TARGETS:
                dependencies.append(f"foreign_key:{table}:{foreign_key.get('name')}:{referred}")
    for view in inspector.get_view_names():
        definition = (inspector.get_view_definition(view) or "").lower()
        if any(target in definition for target in _TARGETS):
            dependencies.append(f"view:{view}")

    dialect = bind.dialect.name
    if dialect == "sqlite":
        objects = bind.execute(
            sa.text(
                "select type, name, sql from sqlite_master "
                "where type in ('trigger', 'view') and sql is not null"
            )
        ).mappings()
        for item in objects:
            definition = str(item["sql"]).lower()
            if any(target in definition for target in _TARGETS):
                marker = f"{item['type']}:{item['name']}"
                if marker not in dependencies:
                    dependencies.append(marker)
    elif dialect == "postgresql":
        catalog_queries = (
            (
                "materialized_view",
                "select schemaname || '.' || matviewname as name, definition from pg_matviews",
            ),
            (
                "function",
                "select n.nspname || '.' || p.proname as name, "
                "pg_get_functiondef(p.oid) as definition "
                "from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
                "where p.prokind in ('f','p') "
                "and n.nspname not in ('pg_catalog','information_schema')",
            ),
            (
                "trigger",
                "select n.nspname || '.' || c.relname || '.' || t.tgname as name, "
                "pg_get_triggerdef(t.oid) as definition "
                "from pg_trigger t join pg_class c on c.oid=t.tgrelid "
                "join pg_namespace n on n.oid=c.relnamespace "
                "where not t.tgisinternal",
            ),
        )
        for kind, query in catalog_queries:
            for item in bind.execute(sa.text(query)).mappings():
                definition = str(item["definition"]).lower()
                if any(target in definition for target in _TARGETS):
                    dependencies.append(f"{kind}:{item['name']}")
    return sorted(set(dependencies))


def _compare_fields(
    actual: Mapping[str, Any],
    expected_fields: tuple[tuple[str, object, str], ...],
) -> list[str]:
    divergences: list[str] = []
    for field, expected, kind in expected_fields:
        value = actual[field]
        if kind == "dt":
            value = _coerce_dt(value)
        elif kind == "json":
            value = _coerce_json(value)
        if value != expected:
            divergences.append(field)
    return divergences


def _team_reconciliation_blockers(bind: sa.Connection) -> list[str]:
    legacy_rows = bind.execute(
        sa.text(
            "select id, api_football_team_id, transfermarkt_club_id, competition_id, "
            "valid_from, valid_to, review_status, reviewed_by, reviewed_at, "
            "source_sha256, payload from team_identity_crosswalks"
        )
    ).mappings()
    blockers: list[str] = []
    for legacy in legacy_rows:
        legacy_id = str(legacy["id"])
        if str(legacy["review_status"] or "").upper() != "APPROVED":
            blockers.append(f"{legacy_id}:LEGACY_NOT_APPROVED")
            continue
        as_of = _coerce_dt(legacy["valid_from"])
        api_rows = (
            bind.execute(
                sa.text(
                    "select id, w2_team_id, season, valid_from, valid_to, identity_hash, "
                    "review_status, reviewed_by, reviewed_at, source_hashes, payload "
                    "from provider_team_identity_crosswalks "
                    "where provider='api_football' and provider_team_id=:provider_team_id "
                    "and competition_id=:competition_id and identity_status=:status"
                ),
                {
                    "provider_team_id": str(legacy["api_football_team_id"]),
                    "competition_id": str(legacy["competition_id"]),
                    "status": _PROVIDER_PRIMARY_READY,
                },
            )
            .mappings()
            .all()
        )
        valid_api = [
            row
            for row in api_rows
            if _valid_at(_coerce_dt(row["valid_from"]), _coerce_dt(row["valid_to"]), as_of)
        ]
        if len(valid_api) != 1:
            blockers.append(f"{legacy_id}:API_AUTHORITY_ROWS={len(valid_api)}")
            continue
        api = valid_api[0]
        source_hashes = [legacy["source_sha256"]] if legacy["source_sha256"] else []
        api_divergences = _compare_fields(
            api,
            (
                ("review_status", legacy["review_status"], "raw"),
                ("reviewed_by", legacy["reviewed_by"], "raw"),
                ("reviewed_at", _coerce_dt(legacy["reviewed_at"]), "dt"),
                ("source_hashes", source_hashes, "json"),
                ("payload", _coerce_json(legacy["payload"]), "json"),
            ),
        )
        if not str(api["identity_hash"] or ""):
            api_divergences.append("identity_hash")
        if api_divergences:
            blockers.append(f"{legacy_id}:API_AUTHORITY_DIVERGENT:{','.join(api_divergences)}")
            continue

        w2_team_id = str(api["w2_team_id"])
        season = str(api["season"])
        tm_rows = (
            bind.execute(
                sa.text(
                    "select id, provider, provider_team_id, w2_team_id, competition_id, season, "
                    "valid_from, valid_to, identity_status, evidence_hashes, identity_hash, "
                    "review_status, reviewed_by, reviewed_at, source_hashes, payload "
                    "from provider_team_identity_crosswalks "
                    "where provider='transfermarkt' and provider_team_id=:provider_team_id "
                    "and w2_team_id=:w2_team_id and competition_id=:competition_id "
                    "and season=:season and identity_status=:status"
                ),
                {
                    "provider_team_id": str(legacy["transfermarkt_club_id"]),
                    "w2_team_id": w2_team_id,
                    "competition_id": str(legacy["competition_id"]),
                    "season": season,
                    "status": _PROVIDER_PRIMARY_READY,
                },
            )
            .mappings()
            .all()
        )
        valid_tm = [
            row
            for row in tm_rows
            if _valid_at(_coerce_dt(row["valid_from"]), _coerce_dt(row["valid_to"]), as_of)
        ]
        if len(valid_tm) != 1:
            blockers.append(f"{legacy_id}:TRANSFERMARKT_AUTHORITY_ROWS={len(valid_tm)}")
            continue
        tm = valid_tm[0]
        tm_id = str(legacy["transfermarkt_club_id"])
        competition_id = str(legacy["competition_id"])
        tm_divergences = _compare_fields(
            tm,
            (
                ("id", f"transfermarkt:{tm_id}:{competition_id}:{season}", "raw"),
                ("provider", "transfermarkt", "raw"),
                ("provider_team_id", tm_id, "raw"),
                ("w2_team_id", w2_team_id, "raw"),
                ("competition_id", competition_id, "raw"),
                ("season", season, "raw"),
                ("identity_status", _PROVIDER_PRIMARY_READY, "raw"),
                (
                    "identity_hash",
                    _transfermarkt_identity_hash(
                        provider_team_id=tm_id,
                        w2_team_id=w2_team_id,
                        competition_id=competition_id,
                        season=season,
                    ),
                    "raw",
                ),
                ("valid_from", as_of, "dt"),
                ("valid_to", _coerce_dt(legacy["valid_to"]), "dt"),
                ("evidence_hashes", source_hashes, "json"),
                ("source_hashes", source_hashes, "json"),
                ("review_status", legacy["review_status"], "raw"),
                ("reviewed_by", legacy["reviewed_by"], "raw"),
                ("reviewed_at", _coerce_dt(legacy["reviewed_at"]), "dt"),
                ("payload", _owned_payload(_coerce_json(legacy["payload"])), "json"),
            ),
        )
        if tm_divergences:
            blockers.append(
                f"{legacy_id}:TRANSFERMARKT_AUTHORITY_DIVERGENT:{','.join(tm_divergences)}"
            )
    return blockers


def _assert_upgrade_safe() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    missing = (set(_TARGETS) | set(_AUTHORITIES)) - tables
    if missing:
        raise RuntimeError(f"LEGACY_IDENTITY_M4_REQUIRED_TABLES_MISSING:{sorted(missing)}")

    dependencies = _database_dependencies(bind, inspector)
    if dependencies:
        raise RuntimeError(f"LEGACY_IDENTITY_M4_DEPENDENCIES:{sorted(dependencies)}")

    empty_required = {
        table: bind.execute(sa.text(f"select count(*) from {table}")).scalar_one()  # noqa: S608
        for table in ("football_data_team_crosswalks", "player_identity_crosswalks")
    }
    if any(empty_required.values()):
        raise RuntimeError(f"LEGACY_IDENTITY_M4_UNMIGRATED_ROWS:{empty_required}")

    blockers = _team_reconciliation_blockers(bind)
    if blockers:
        raise RuntimeError(
            "LEGACY_IDENTITY_M4_TEAM_AUTHORITY_UNRECONCILED:" + ";".join(sorted(blockers))
        )


def upgrade() -> None:
    _assert_upgrade_safe()
    for table in _TARGETS:
        op.drop_table(table)


def downgrade() -> None:
    op.create_table(
        "team_identity_crosswalks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("api_football_team_id", sa.String(64), nullable=False),
        sa.Column("transfermarkt_club_id", sa.String(64), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("crosswalk_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source_sha256", sa.String(64)),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("crosswalk_hash", name="uq_team_identity_crosswalk_hash"),
        sa.UniqueConstraint(
            "api_football_team_id",
            "transfermarkt_club_id",
            "competition_id",
            "valid_from",
            name="uq_team_identity_crosswalk_natural",
        ),
    )
    op.create_index(
        "ix_team_crosswalk_lookup",
        "team_identity_crosswalks",
        ["api_football_team_id", "competition_id", "valid_from"],
    )

    op.create_table(
        "football_data_team_crosswalks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("football_data_source_identity", sa.String(128), nullable=False),
        sa.Column("football_data_team_name", sa.String(255), nullable=False),
        sa.Column("league", sa.String(128), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("season_coverage", sa.JSON(), nullable=False),
        sa.Column("w2_team_id", sa.String(128), nullable=False),
        sa.Column("api_football_team_ids", sa.JSON(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("source_hashes", sa.JSON(), nullable=False),
        sa.Column("candidate_generation_method", sa.String(128), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("crosswalk_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("crosswalk_hash", name="uq_football_data_team_crosswalk_hash"),
        sa.UniqueConstraint(
            "football_data_source_identity",
            "competition_id",
            "valid_from",
            name="uq_football_data_team_crosswalk_natural",
        ),
    )
    op.create_index(
        "ix_football_data_team_crosswalk_lookup",
        "football_data_team_crosswalks",
        ["w2_team_id", "competition_id", "valid_from"],
    )

    op.create_table(
        "player_identity_crosswalks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("api_football_player_id", sa.String(64), nullable=False),
        sa.Column("transfermarkt_player_id", sa.String(64), nullable=False),
        sa.Column("api_football_team_id", sa.String(64), nullable=False),
        sa.Column("transfermarkt_club_id", sa.String(64), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("crosswalk_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("crosswalk_hash", name="uq_player_identity_crosswalk_hash"),
        sa.UniqueConstraint(
            "api_football_player_id",
            "competition_id",
            "valid_from",
            name="uq_player_identity_crosswalk_natural",
        ),
    )
    op.create_index(
        "ix_player_crosswalk_lookup",
        "player_identity_crosswalks",
        ["api_football_team_id", "competition_id", "valid_from"],
    )
