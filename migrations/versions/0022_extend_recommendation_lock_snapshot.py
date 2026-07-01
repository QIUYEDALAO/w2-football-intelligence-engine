"""extend recommendation lock snapshot

Revision ID: 0022_extend_recommendation_lock_snapshot
Revises: 0021_create_team_xg_materialization
Create Date: 2026-07-02 01:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0022_extend_recommendation_lock_snapshot"
down_revision: str | None = "0021_create_team_xg_materialization"
branch_labels: str | None = None
depends_on: str | None = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _foreign_keys(table_name: str) -> set[str]:
    return {
        foreign_key["name"]
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
        if foreign_key["name"]
    }


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _drop_column_if_present(table_name: str, column_name: str) -> None:
    if column_name in _columns(table_name):
        op.drop_column(table_name, column_name)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    if index_name not in _indexes(table_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_present(table_name: str, index_name: str) -> None:
    if index_name in _indexes(table_name):
        op.drop_index(index_name, table_name=table_name)


def _create_fk_if_missing(
    constraint_name: str,
    source_table: str,
    referent_table: str,
    local_cols: list[str],
    remote_cols: list[str],
) -> None:
    if constraint_name not in _foreign_keys(source_table):
        op.create_foreign_key(
            constraint_name,
            source_table,
            referent_table,
            local_cols,
            remote_cols,
        )


def _drop_fk_if_present(table_name: str, constraint_name: str) -> None:
    if constraint_name in _foreign_keys(table_name):
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("fixture_id", sa.String(length=36), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("tier", sa.String(length=32), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("pick_side", sa.String(length=32), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("pick_line", sa.Numeric(8, 4), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("our_fair_ah", sa.Numeric(8, 4), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("market_ah", sa.Numeric(8, 4), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("home_price", sa.Numeric(8, 4), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("away_price", sa.Numeric(8, 4), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("expected_value", sa.Numeric(10, 6), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("devig_method", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("snapshot_payload_json", sa.JSON(), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("snapshot_payload_hash", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("release_sha", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("market_timeline_json", sa.JSON(), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("ah_settlement_distribution_json", sa.JSON(), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("team_score_home", sa.Numeric(8, 4), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("team_score_away", sa.Numeric(8, 4), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("factors_json", sa.JSON(), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("independent_signal_count", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("signal_groups", sa.JSON(), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("missing_sources", sa.JSON(), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("scoreline_top3_json", sa.JSON(), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("lineups_status", sa.String(length=32), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("xg_status", sa.String(length=32), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("model_version", sa.String(length=128), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("calibration_version", sa.String(length=128), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("coherent", sa.Boolean(), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("reverse_value", sa.Boolean(), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("data_profile", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("reproducible", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("legacy_marker_only", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    _add_column_if_missing(
        "recommendation_locks",
        sa.Column("snapshot_schema_version", sa.String(length=64), nullable=True),
    )
    _create_index_if_missing(
        "recommendation_locks",
        "ix_recommendation_locks_fixture",
        ["fixture_id"],
    )
    _create_index_if_missing("recommendation_locks", "ix_recommendation_locks_as_of", ["as_of"])
    if dialect != "sqlite":
        _create_fk_if_missing(
            "fk_recommendation_locks_fixture_id",
            "recommendation_locks",
            "fixtures",
            ["fixture_id"],
            ["id"],
        )

    _add_column_if_missing("settlements", sa.Column("lock_id", sa.String(length=36), nullable=True))
    _add_column_if_missing(
        "settlements",
        sa.Column("matched_recommendation", sa.Boolean(), nullable=True),
    )
    _add_column_if_missing("settlements", sa.Column("tier", sa.String(length=32), nullable=True))
    _add_column_if_missing(
        "settlements",
        sa.Column("movement_pattern", sa.String(length=64), nullable=True),
    )
    _create_index_if_missing("settlements", "ix_settlements_lock", ["lock_id"])
    if dialect != "sqlite":
        _create_fk_if_missing(
            "fk_settlements_lock_id",
            "settlements",
            "recommendation_locks",
            ["lock_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        # Fresh SQLite test databases create these columns from current metadata in
        # 0002, including inline FK metadata. The full downgrade path drops the
        # table in 0002, so avoid SQLite's limited DROP COLUMN support here.
        return
    _drop_fk_if_present("settlements", "fk_settlements_lock_id")
    _drop_index_if_present("settlements", "ix_settlements_lock")
    for column in ("movement_pattern", "tier", "matched_recommendation", "lock_id"):
        _drop_column_if_present("settlements", column)

    _drop_fk_if_present("recommendation_locks", "fk_recommendation_locks_fixture_id")
    _drop_index_if_present("recommendation_locks", "ix_recommendation_locks_as_of")
    _drop_index_if_present("recommendation_locks", "ix_recommendation_locks_fixture")
    for column in (
        "snapshot_schema_version",
        "legacy_marker_only",
        "reproducible",
        "data_profile",
        "reverse_value",
        "coherent",
        "calibration_version",
        "model_version",
        "xg_status",
        "lineups_status",
        "scoreline_top3_json",
        "missing_sources",
        "signal_groups",
        "independent_signal_count",
        "factors_json",
        "team_score_away",
        "team_score_home",
        "ah_settlement_distribution_json",
        "market_timeline_json",
        "release_sha",
        "snapshot_payload_hash",
        "snapshot_payload_json",
        "devig_method",
        "expected_value",
        "away_price",
        "home_price",
        "market_ah",
        "our_fair_ah",
        "pick_line",
        "pick_side",
        "tier",
        "kickoff_utc",
        "as_of",
        "fixture_id",
    ):
        _drop_column_if_present("recommendation_locks", column)
