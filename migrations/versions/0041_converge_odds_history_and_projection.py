"""converge odds tables onto one history table and one current projection

`matchday_market_observations` becomes the only append-only odds history and
`current_market_projection` becomes the only current-market projection.

`future_market_observation` is dropped. Its rows are not unique data: on the
acceptance database all 3840 rows were the same 1920 quotes stored twice, once
under a bare fixture id and once under an ``api_football:`` prefixed one, and
every one of them matched a canonical row on the full quote identity. The
upgrade re-proves that before dropping anything: it counts legacy rows that are
not covered by the canonical history and refuses to continue if any exist, so
replaying this revision against a database holding unique legacy quotes fails
loudly instead of deleting them.

Revision ID: 0041_converge_odds_history_and_projection
Revises: 0040_drop_empty_fk_components
Create Date: 2026-07-23 19:40:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from w2.infrastructure.persistence.market_projection_view import (
    CREATE_PROJECTION_VIEW,
    DROP_PROJECTION_VIEW,
)

revision: str = "0041_converge_odds_history_and_projection"
down_revision: str | None = "0040_drop_empty_fk_components"
branch_labels: str | None = None
depends_on: str | None = None

LEGACY_TABLE = "future_market_observation"
CANONICAL_TABLE = "matchday_market_observations"

# Coverage is proven on every business field the two tables share, not just on
# the price identity. Two quotes can carry the same fixture, bookmaker, market,
# selection, line, odds, capture time and raw payload hash and still differ in
# `provider_bet_id` or `raw_market_label`; comparing only the price identity
# would call such a row covered and delete it.
#
# Deliberately excluded, per the canonical observation identity contract:
#   - `ingested_at`   local write time, not part of the quote
#   - `source_revision` code revision that performed the write
# Legacy-only bookkeeping columns are not compared but are asserted to be unset
# below, so no candidate or formal-recommendation row is ever dropped silently.
UNCOVERED_LEGACY_ROWS = """
select count(*)
from future_market_observation f
where not exists (
    select 1
    from matchday_market_observations m
    where m.provider_fixture_id = replace(f.fixture_id, 'api_football:', '')
      and m.provider = f.provider
      and m.bookmaker_id = f.bookmaker_id
      and m.bookmaker_name = f.bookmaker_name
      and m.provider_bet_id = f.provider_bet_id
      and m.raw_market_label = f.raw_market_label
      and m.canonical_market = f.canonical_market
      and m.canonical_selection = f.selection
      and coalesce(m.line, '') = coalesce(f.line, '')
      and m.decimal_odds = f.decimal_odds
      and m.suspended = f.suspended
      and m.live = f.live
      and m.provider_updated_at = f.provider_last_update
      and m.captured_at = f.captured_at
      and m.raw_payload_sha256 = f.raw_payload_sha256
)
"""

# A candidate or formal-recommendation row carries decision meaning that the
# canonical table does not model, so it can never be treated as a duplicate.
FLAGGED_LEGACY_ROWS = """
select count(*)
from future_market_observation
where candidate or formal_recommendation
"""

COMPARED_SEMANTIC_FIELDS = (
    "provider",
    "fixture_id",
    "bookmaker_id",
    "bookmaker_name",
    "provider_bet_id",
    "raw_market_label",
    "canonical_market",
    "selection",
    "line",
    "decimal_odds",
    "suspended",
    "live",
    "provider_last_update",
    "captured_at",
    "raw_payload_sha256",
)
EXCLUDED_SEMANTIC_FIELDS = ("ingested_at", "source_revision")

LEGACY_COLUMNS: tuple[tuple[str, sa.types.TypeEngine[object], bool, bool], ...] = (
    ("observation_id", sa.String(length=64), False, True),
    ("fixture_id", sa.String(length=64), False, False),
    ("provider", sa.String(length=64), False, False),
    ("bookmaker_id", sa.String(length=64), False, False),
    ("bookmaker_name", sa.String(length=255), False, False),
    ("provider_bet_id", sa.String(length=64), False, False),
    ("raw_market_label", sa.String(length=255), False, False),
    ("canonical_market", sa.String(length=64), False, False),
    ("selection", sa.String(length=128), False, False),
    ("line", sa.String(length=64), True, False),
    ("decimal_odds", sa.String(length=32), False, False),
    ("suspended", sa.Boolean(), False, False),
    ("live", sa.Boolean(), False, False),
    ("provider_last_update", sa.String(length=64), False, False),
    ("captured_at", sa.DateTime(timezone=True), False, False),
    ("ingested_at", sa.DateTime(timezone=True), False, False),
    ("raw_payload_sha256", sa.String(length=64), False, False),
    ("source_revision", sa.String(length=128), False, False),
    ("candidate", sa.Boolean(), False, False),
    ("formal_recommendation", sa.Boolean(), False, False),
)

LEGACY_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ix_future_market_observation_fixture", ("fixture_id",)),
    ("ix_future_market_observation_captured_at", ("captured_at",)),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(LEGACY_TABLE):
        if not inspector.has_table(CANONICAL_TABLE):
            raise RuntimeError(
                "ODDS_CONVERGENCE_CANONICAL_TABLE_MISSING:"
                f"{CANONICAL_TABLE} must exist before {LEGACY_TABLE} can be dropped"
            )
        flagged = bind.execute(sa.text(FLAGGED_LEGACY_ROWS)).scalar_one()
        if flagged:
            raise RuntimeError(
                "ODDS_CONVERGENCE_FLAGGED_LEGACY_ROWS:"
                f"{flagged} row(s) in {LEGACY_TABLE} are marked candidate or "
                "formal_recommendation and carry decision meaning the canonical "
                "table does not model; resolve them before dropping the table"
            )
        uncovered = bind.execute(sa.text(UNCOVERED_LEGACY_ROWS)).scalar_one()
        if uncovered:
            raise RuntimeError(
                "ODDS_CONVERGENCE_UNCOVERED_LEGACY_ROWS:"
                f"{uncovered} row(s) in {LEGACY_TABLE} have no matching quote in "
                f"{CANONICAL_TABLE} across "
                f"{len(COMPARED_SEMANTIC_FIELDS)} shared business fields; "
                "migrate them before dropping the table"
            )
        op.drop_table(LEGACY_TABLE)

    op.execute(sa.text(DROP_PROJECTION_VIEW))
    op.execute(sa.text(CREATE_PROJECTION_VIEW))


def downgrade() -> None:
    op.execute(sa.text(DROP_PROJECTION_VIEW))

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(LEGACY_TABLE):
        return
    op.create_table(
        LEGACY_TABLE,
        *(
            sa.Column(name, column_type, nullable=nullable, primary_key=primary_key)
            for name, column_type, nullable, primary_key in LEGACY_COLUMNS
        ),
    )
    for index_name, columns in LEGACY_INDEXES:
        op.create_index(index_name, LEGACY_TABLE, list(columns))
