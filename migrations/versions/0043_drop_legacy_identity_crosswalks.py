"""drop the three legacy identity crosswalk tables

Revision ID: 0043_drop_legacy_identity_crosswalks
Revises: 0042_team_identity_provider_review_provenance
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

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


def _assert_upgrade_safe() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    missing = (set(_TARGETS) | set(_AUTHORITIES)) - tables
    if missing:
        raise RuntimeError(f"LEGACY_IDENTITY_M4_REQUIRED_TABLES_MISSING:{sorted(missing)}")

    dependencies: list[str] = []
    for table in tables:
        for foreign_key in inspector.get_foreign_keys(table):
            referred = foreign_key.get("referred_table")
            if table in _TARGETS or referred in _TARGETS:
                dependencies.append(f"{table}:{foreign_key.get('name')}:{referred}")
    for view in inspector.get_view_names():
        definition = (inspector.get_view_definition(view) or "").lower()
        if any(target in definition for target in _TARGETS):
            dependencies.append(f"view:{view}")
    if dependencies:
        raise RuntimeError(f"LEGACY_IDENTITY_M4_DEPENDENCIES:{sorted(dependencies)}")

    empty_required = {
        table: bind.execute(sa.text(f"select count(*) from {table}")).scalar_one()  # noqa: S608
        for table in ("football_data_team_crosswalks", "player_identity_crosswalks")
    }
    if any(empty_required.values()):
        raise RuntimeError(f"LEGACY_IDENTITY_M4_UNMIGRATED_ROWS:{empty_required}")

    unreconciled_teams = bind.execute(
        sa.text(
            """
            select count(*)
            from team_identity_crosswalks legacy
            where legacy.review_status <> 'APPROVED'
               or not exists (
                    select 1
                    from provider_team_identity_crosswalks api
                    join provider_team_identity_crosswalks tm
                      on tm.w2_team_id = api.w2_team_id
                     and tm.competition_id = api.competition_id
                     and tm.provider = 'transfermarkt'
                     and tm.provider_team_id = legacy.transfermarkt_club_id
                     and tm.identity_status = 'PROVIDER_PRIMARY_READY'
                     and tm.review_status = 'APPROVED'
                    where api.provider = 'api_football'
                      and api.provider_team_id = legacy.api_football_team_id
                      and api.competition_id = legacy.competition_id
                      and api.identity_status = 'PROVIDER_PRIMARY_READY'
                      and api.review_status = 'APPROVED'
                      and api.valid_from <= legacy.valid_from
                      and (api.valid_to is null or api.valid_to > legacy.valid_from)
               )
            """
        )
    ).scalar_one()
    if unreconciled_teams:
        raise RuntimeError(f"LEGACY_IDENTITY_M4_TEAM_AUTHORITY_UNRECONCILED:{unreconciled_teams}")


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
