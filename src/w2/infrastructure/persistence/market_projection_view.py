"""Single current-market projection derived from the canonical odds history.

`matchday_market_observations` is the only append-only odds history. This module
defines the only current-market projection on top of it: a database view that
keeps, per fixture/market/bookmaker/selection/line, the latest non-suspended and
non-live quote.

The projection is a view, never a second fact table, so it cannot drift from the
history it is derived from. It is created by the Alembic migration on real
databases and by a metadata event for the `create_all` schema used in tests, so
production and tests read the same object.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from w2.infrastructure.database import Base

PROJECTION_VIEW_NAME = "current_market_projection"
CANONICAL_HISTORY_TABLE = "matchday_market_observations"

# The projection fixture id mirrors what the read path has always exposed:
# the provider fixture id, falling back to the canonical id without its prefix.
_PROJECTION_FIXTURE_ID = (
    "coalesce(nullif(o.provider_fixture_id, ''), "
    "replace(o.fixture_id, 'api_football:', ''))"
)

# Written out literally rather than interpolated so no value can ever be
# injected into the statement.
PROJECTION_SELECT = """
select
    ranked.observation_id,
    ranked.fixture_id,
    ranked.provider_fixture_id,
    ranked.projection_fixture_id,
    ranked.competition_id,
    ranked.provider,
    ranked.bookmaker_id,
    ranked.bookmaker_name,
    ranked.capture_id,
    ranked.provider_bet_id,
    ranked.raw_market_label,
    ranked.canonical_market,
    ranked.canonical_selection,
    ranked.provider_selection,
    ranked.line,
    ranked.decimal_odds,
    ranked.suspended,
    ranked.live,
    ranked.provider_updated_at,
    ranked.captured_at,
    ranked.ingested_at,
    ranked.raw_payload_sha256,
    ranked.source_revision
from (
    select
        o.observation_id,
        o.fixture_id,
        o.provider_fixture_id,
        coalesce(nullif(o.provider_fixture_id, ''),
                 replace(o.fixture_id, 'api_football:', '')) as projection_fixture_id,
        o.competition_id,
        o.provider,
        o.bookmaker_id,
        o.bookmaker_name,
        o.capture_id,
        o.provider_bet_id,
        o.raw_market_label,
        o.canonical_market,
        o.canonical_selection,
        o.provider_selection,
        o.line,
        o.decimal_odds,
        o.suspended,
        o.live,
        o.provider_updated_at,
        o.captured_at,
        o.ingested_at,
        o.raw_payload_sha256,
        o.source_revision,
        row_number() over (
            partition by
                coalesce(nullif(o.provider_fixture_id, ''),
                         replace(o.fixture_id, 'api_football:', '')),
                o.canonical_market,
                o.bookmaker_id,
                o.canonical_selection,
                o.line
            order by o.captured_at desc, o.observation_id asc
        ) as projection_rank
    from matchday_market_observations o
    where not o.suspended and not o.live
) ranked
where ranked.projection_rank = 1
""".strip()

CREATE_PROJECTION_VIEW = (
    f"create view {PROJECTION_VIEW_NAME} as\n{PROJECTION_SELECT}"
)
DROP_PROJECTION_VIEW = f"drop view if exists {PROJECTION_VIEW_NAME}"


# Deliberately not attached to ``Base.metadata``: ``create_all`` must never emit
# ``CREATE TABLE`` for the projection. Selects use this table object; the view
# itself is created by :func:`create_projection_view`.
projection_metadata = sa.MetaData()

current_market_projection = sa.Table(
    PROJECTION_VIEW_NAME,
    projection_metadata,
    sa.Column("observation_id", sa.String(64), primary_key=True),
    sa.Column("fixture_id", sa.String(128), nullable=False),
    sa.Column("provider_fixture_id", sa.String(64), nullable=False),
    sa.Column("projection_fixture_id", sa.String(128), nullable=False),
    sa.Column("competition_id", sa.String(128), nullable=False),
    sa.Column("provider", sa.String(64), nullable=False),
    sa.Column("bookmaker_id", sa.String(64), nullable=False),
    sa.Column("bookmaker_name", sa.String(255), nullable=False),
    sa.Column("capture_id", sa.String(64), nullable=False),
    sa.Column("provider_bet_id", sa.String(64), nullable=False),
    sa.Column("raw_market_label", sa.String(255), nullable=False),
    sa.Column("canonical_market", sa.String(64), nullable=False),
    sa.Column("canonical_selection", sa.String(128), nullable=False),
    sa.Column("provider_selection", sa.String(128), nullable=False),
    sa.Column("line", sa.String(64)),
    sa.Column("decimal_odds", sa.String(32), nullable=False),
    sa.Column("suspended", sa.Boolean, nullable=False),
    sa.Column("live", sa.Boolean, nullable=False),
    sa.Column("provider_updated_at", sa.String(64), nullable=False),
    sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("raw_payload_sha256", sa.String(64), nullable=False),
    sa.Column("source_revision", sa.String(128), nullable=False),
)


def create_projection_view(connection: Connection) -> None:
    connection.execute(sa.text(DROP_PROJECTION_VIEW))
    connection.execute(sa.text(CREATE_PROJECTION_VIEW))


def drop_projection_view(connection: Connection) -> None:
    connection.execute(sa.text(DROP_PROJECTION_VIEW))


@sa.event.listens_for(Base.metadata, "after_create")
def _create_view_after_metadata_create(
    target: sa.MetaData,
    connection: Connection,
    **kwargs: Any,
) -> None:
    if CANONICAL_HISTORY_TABLE not in {table.name for table in kwargs.get("tables", ())}:
        return
    create_projection_view(connection)


@sa.event.listens_for(Base.metadata, "before_drop")
def _drop_view_before_metadata_drop(
    target: sa.MetaData,
    connection: Connection,
    **kwargs: Any,
) -> None:
    if CANONICAL_HISTORY_TABLE not in {table.name for table in kwargs.get("tables", ())}:
        return
    drop_projection_view(connection)
